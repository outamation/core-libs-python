"""Unit tests for the COST level, `logger.cost(...)`, and publisher.

These tests do NOT require a running Redis. The publisher's Redis client is
patched via a fake that records pipelined XADD calls in memory.
"""

from __future__ import annotations

import asyncio
import json
import time

import pytest
from loguru import logger

from outamation_pkg_logger import configure_cost_publisher, logger as pkg_logger
from outamation_pkg_logger import cost as cost_module
from outamation_pkg_logger import publisher as publisher_module
from outamation_pkg_logger.publisher import _CostPublisher, _PublisherConfig


# ---------- Fakes ----------


class FakePipeline:
    def __init__(self, client: "FakeRedis"):
        self._client = client
        self._ops: list[tuple] = []

    def xadd(self, stream, fields, maxlen=None, approximate=True):
        self._ops.append((stream, fields, maxlen, approximate))
        return self

    async def execute(self):
        if self._client.fail_next:
            self._client.fail_next = False
            raise ConnectionError("simulated redis failure")
        self._client.published.extend(self._ops)


class FakeRedis:
    def __init__(self):
        self.published: list[tuple] = []
        self.fail_next = False
        self.closed = False

    def pipeline(self, transaction=False):
        return FakePipeline(self)

    async def aclose(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _reset_publisher_singleton(monkeypatch):
    """Force a clean publisher state for each test."""
    # Reset module-level publisher.
    if publisher_module._publisher is not None:
        publisher_module._publisher.stop(timeout=1.0)
        publisher_module._publisher = None
    yield
    if publisher_module._publisher is not None:
        publisher_module._publisher.stop(timeout=1.0)
        publisher_module._publisher = None


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()

    async def _build_client(self):
        return fake

    monkeypatch.setattr(_CostPublisher, "_build_client", _build_client)
    return fake


# ---------- Tests ----------


def test_cost_level_registered():
    level = logger.level("COST")
    assert level.no == 25


def test_cost_method_attached():
    assert hasattr(pkg_logger, "cost")
    assert callable(pkg_logger.cost)


def test_cost_logs_without_publisher_configured():
    """logger.cost(...) emits a log line even when no publisher is set up."""
    with _capture_loguru() as sink:
        pkg_logger.cost(
            event="test_event",
            model="claude-opus-4-7",
            tokens={"input": 10, "output": 5},
            usd=0.01,
            file_id="f-1",
        )
    output = "\n".join(sink)
    assert "test_event" in output
    assert "file_id=f-1" in output


def test_cost_publishes_to_redis(fake_redis):
    configure_cost_publisher(
        redis_url="redis://fake",
        service="test-svc",
        flush_interval=0.1,
    )
    pkg_logger.cost(
        event="extraction_complete",
        model="claude-opus-4-7",
        tokens={"input": 100, "output": 50, "cache_read": 0, "cache_write": 0},
        usd=0.05,
        file_id="abc-123",
    )
    # Wait long enough for one flush tick.
    _wait_until(lambda: len(fake_redis.published) >= 1, timeout=3.0)
    assert len(fake_redis.published) == 1
    stream, fields, maxlen, approximate = fake_redis.published[0]
    assert stream == "outamation:cost-events"
    assert approximate is True
    payload = json.loads(fields["data"])
    assert payload["event_id"]
    assert payload["service"] == "test-svc"
    assert payload["file_id"] == "abc-123"
    assert payload["tokens"]["input"] == 100
    assert payload["metadata"] == {}


def test_buffer_overflow_drops_oldest(fake_redis):
    # Don't start the flusher — build the publisher directly so we can fill
    # the buffer without it being drained mid-test.
    config = _PublisherConfig(
        redis_url="redis://fake",
        service="test",
        buffer_cap=3,
    )
    pub = _CostPublisher(config)
    pub.enqueue({"event_id": "1"})
    pub.enqueue({"event_id": "2"})
    pub.enqueue({"event_id": "3"})
    pub.enqueue({"event_id": "4"})  # forces oldest drop
    items = pub._drain_buffer()
    assert [i["event_id"] for i in items] == ["2", "3", "4"]
    assert pub._dropped_count == 1


def test_redis_failure_requeues_and_backs_off(fake_redis):
    fake_redis.fail_next = True
    configure_cost_publisher(
        redis_url="redis://fake",
        service="test",
        flush_interval=0.1,
    )
    pkg_logger.cost(
        event="ev",
        model="m",
        tokens={"input": 1, "output": 1},
        usd=0.0,
        file_id="f",
    )
    # First publish fails. Eventually the retry should succeed.
    _wait_until(lambda: len(fake_redis.published) >= 1, timeout=10.0)
    assert len(fake_redis.published) >= 1


def test_metadata_over_4kb_warns():
    large = {"k": "x" * 5000}
    with _capture_loguru() as sink:
        pkg_logger.cost(
            event="ev",
            model="m",
            tokens={"input": 0, "output": 0},
            usd=0.0,
            metadata=large,
        )
    output = "\n".join(sink)
    assert "metadata is" in output and "bytes" in output


def test_cost_level_filterable():
    """Sinks can suppress COST lines via a filter."""
    seen: list[str] = []
    sink_id = logger.add(
        lambda msg: seen.append(msg),
        filter=lambda r: r["level"].name != "COST",
        format="{message}",
    )
    try:
        pkg_logger.cost(
            event="ev",
            model="m",
            tokens={"input": 0, "output": 0},
            usd=0.0,
        )
        logger.info("visible")
    finally:
        logger.remove(sink_id)
    assert any("visible" in m for m in seen)
    assert not any("model=m" in m for m in seen)


def test_idempotent_reconfigure(fake_redis):
    configure_cost_publisher(redis_url="redis://fake", service="a")
    first = publisher_module.get_publisher()
    configure_cost_publisher(redis_url="redis://fake", service="b")
    second = publisher_module.get_publisher()
    assert first is not second
    assert second.service == "b"


# ---------- Helpers ----------


from contextlib import contextmanager


@contextmanager
def _capture_loguru():
    """Capture Loguru output to a list (capsys does not work with Loguru)."""
    sink: list[str] = []
    sink_id = logger.add(lambda msg: sink.append(str(msg)), format="{level} | {message}")
    try:
        yield sink
    finally:
        logger.remove(sink_id)


def _wait_until(predicate, timeout: float, interval: float = 0.05) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError("predicate did not become true in time")
