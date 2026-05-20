"""Redis Streams publisher for cost events.

Internal module. Public surface is `configure_cost_publisher` (also re-exported
from the package root) plus `get_publisher` for use by `cost.py`.

Design notes:
- Buffer: collections.deque(maxlen=N) under a threading.Lock — auto-drops oldest.
- Flusher: daemon thread running a private asyncio loop with redis.asyncio.
- Caller side (logger.cost): only touches the deque; never blocks, never awaits.
- Failures: retry with exponential backoff, never raised into the caller.
- Process exit: atexit handler signals shutdown and waits up to 2s for drain.
"""

from __future__ import annotations

import asyncio
import atexit
import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

from loguru import logger

DEFAULT_STREAM = "outamation:cost-events"
DEFAULT_FLUSH_INTERVAL = 5.0
DEFAULT_BUFFER_CAP = 10_000
DEFAULT_STREAM_MAXLEN = 250_000
BACKOFF_SCHEDULE = (5.0, 10.0, 30.0, 60.0)
ATEXIT_FLUSH_TIMEOUT = 2.0
SOCKET_TIMEOUT = 5.0
OVERFLOW_WARN_INTERVAL = 60.0


@dataclass
class _PublisherConfig:
    redis_url: str
    stream: str = DEFAULT_STREAM
    flush_interval: float = DEFAULT_FLUSH_INTERVAL
    service: str = ""
    buffer_cap: int = DEFAULT_BUFFER_CAP
    stream_maxlen: int = DEFAULT_STREAM_MAXLEN


class _CostPublisher:
    def __init__(self, config: _PublisherConfig):
        self._config = config
        self._buffer: deque = deque(maxlen=config.buffer_cap)
        self._lock = threading.Lock()
        self._shutdown = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._dropped_count = 0
        self._last_overflow_warn = 0.0
        self._atexit_registered = False

    @property
    def service(self) -> str:
        return self._config.service

    def enqueue(self, event: dict) -> None:
        with self._lock:
            was_full = len(self._buffer) >= (self._buffer.maxlen or 0)
            self._buffer.append(event)
            if was_full:
                self._dropped_count += 1
                self._maybe_warn_overflow_locked()

    def _maybe_warn_overflow_locked(self) -> None:
        now = time.time()
        if now - self._last_overflow_warn >= OVERFLOW_WARN_INTERVAL:
            dropped = self._dropped_count
            self._last_overflow_warn = now
            logger.warning(
                f"Cost publisher buffer overflow: {dropped} event(s) dropped "
                f"since last warning (cap={self._config.buffer_cap})"
            )

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._shutdown.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="cost-publisher"
        )
        self._thread.start()
        if not self._atexit_registered:
            atexit.register(self._final_flush)
            self._atexit_registered = True

    def stop(self, timeout: float = ATEXIT_FLUSH_TIMEOUT) -> None:
        self._shutdown.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._flusher_loop())
        except Exception as exc:
            logger.warning(f"Cost publisher flusher thread crashed: {exc}")
        finally:
            try:
                loop.close()
            except Exception:
                pass

    async def _flusher_loop(self) -> None:
        client = None
        backoff_idx = -1
        try:
            client = await self._build_client()
            while not self._shutdown.is_set():
                sleep_time = (
                    self._config.flush_interval
                    if backoff_idx < 0
                    else BACKOFF_SCHEDULE[
                        min(backoff_idx, len(BACKOFF_SCHEDULE) - 1)
                    ]
                )
                if self._wait_or_shutdown(sleep_time):
                    break
                batch = self._drain_buffer()
                if not batch:
                    continue
                try:
                    await self._publish_batch(client, batch)
                    backoff_idx = -1
                except Exception as exc:
                    logger.warning(
                        f"Cost publish failed ({type(exc).__name__}: {exc}); "
                        f"requeuing {len(batch)} event(s) with backoff"
                    )
                    self._requeue_front(batch)
                    backoff_idx = min(backoff_idx + 1, len(BACKOFF_SCHEDULE) - 1)

            # Shutdown drain — try one last publish without further retry.
            final_batch = self._drain_buffer()
            if final_batch and client is not None:
                try:
                    await self._publish_batch(client, final_batch)
                except Exception as exc:
                    logger.warning(
                        f"Cost publisher final flush failed: {exc}; "
                        f"{len(final_batch)} event(s) lost"
                    )
        finally:
            if client is not None:
                try:
                    await client.aclose()
                except Exception:
                    pass

    def _wait_or_shutdown(self, seconds: float) -> bool:
        """Sleep up to `seconds`. Returns True if shutdown was signalled."""
        # threading.Event.wait is safe to call from any thread; we use it
        # here instead of asyncio.sleep so shutdown wakes the loop promptly.
        return self._shutdown.wait(timeout=seconds)

    def _drain_buffer(self) -> list[dict]:
        with self._lock:
            items = list(self._buffer)
            self._buffer.clear()
        return items

    def _requeue_front(self, items: list[dict]) -> None:
        with self._lock:
            for item in reversed(items):
                self._buffer.appendleft(item)

    async def _build_client(self):
        from redis.asyncio import Redis

        return Redis.from_url(
            self._config.redis_url,
            socket_timeout=SOCKET_TIMEOUT,
            socket_keepalive=True,
            decode_responses=False,
        )

    async def _publish_batch(self, client, batch: list[dict]) -> None:
        pipe = client.pipeline(transaction=False)
        for event in batch:
            pipe.xadd(
                self._config.stream,
                {"data": json.dumps(event, default=str)},
                maxlen=self._config.stream_maxlen,
                approximate=True,
            )
        await pipe.execute()

    def _final_flush(self) -> None:
        # Runs on the main thread at interpreter shutdown. Signal the flusher
        # to drain once and exit; wait briefly so we don't block forever.
        self.stop(timeout=ATEXIT_FLUSH_TIMEOUT)


_publisher: Optional[_CostPublisher] = None
_publisher_lock = threading.Lock()


def configure_cost_publisher(
    redis_url: str,
    *,
    stream: str = DEFAULT_STREAM,
    flush_interval: float = DEFAULT_FLUSH_INTERVAL,
    service: str = "",
    buffer_cap: int = DEFAULT_BUFFER_CAP,
    stream_maxlen: int = DEFAULT_STREAM_MAXLEN,
    enabled: bool = True,
) -> None:
    """Initialize the cost-event publisher.

    Idempotent: calling again replaces the existing publisher (the old
    daemon thread is signalled to drain + exit). When `enabled=False`,
    the call is a no-op and `logger.cost(...)` will only emit log lines.

    Args:
        redis_url: e.g. "redis://localhost:6379/0"
        stream: Redis Streams key to publish to
        flush_interval: seconds between flush ticks
        service: producer service name (stamped on every event)
        buffer_cap: max in-memory events before oldest are dropped
        stream_maxlen: approximate trim cap for the Redis stream
        enabled: when False, do nothing
    """
    global _publisher
    if not enabled:
        return

    config = _PublisherConfig(
        redis_url=redis_url,
        stream=stream,
        flush_interval=flush_interval,
        service=service,
        buffer_cap=buffer_cap,
        stream_maxlen=stream_maxlen,
    )

    with _publisher_lock:
        old = _publisher
        new = _CostPublisher(config)
        _publisher = new
        new.start()

    if old is not None:
        # Drain the old publisher off the lock to avoid stalling new calls.
        try:
            old.stop(timeout=ATEXIT_FLUSH_TIMEOUT)
        except Exception:
            pass


def get_publisher() -> Optional[_CostPublisher]:
    """Internal accessor used by cost.py."""
    return _publisher
