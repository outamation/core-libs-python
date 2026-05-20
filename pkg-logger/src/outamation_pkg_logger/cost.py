"""COST log level + `logger.cost(...)` structured event API.

Attaches `cost` to the shared Loguru `logger` instance and registers the COST
custom level (numeric 25, between INFO and WARNING). The method emits a
normal Loguru log line and, when a publisher is configured, hands the
structured payload off to the background Redis Streams publisher.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from .publisher import get_publisher

COST_LEVEL_NAME = "COST"
COST_LEVEL_NO = 25
METADATA_MAX_BYTES = 4096


def _register_level() -> None:
    try:
        logger.level(COST_LEVEL_NAME, no=COST_LEVEL_NO, color="<cyan>", icon="$")
    except ValueError:
        # Already registered (e.g. module re-import in tests).
        pass


def _build_event(
    event: str,
    *,
    model: str,
    tokens: dict,
    usd: float,
    file_id: Optional[str],
    tenant_id: Optional[str],
    request_id: Optional[str],
    tags: Optional[dict],
    metadata: Optional[dict],
    service: str,
) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": service,
        "tenant_id": tenant_id,
        "request_id": request_id,
        "file_id": file_id,
        "model": model,
        "tokens": {
            "input": int(tokens.get("input", 0)),
            "output": int(tokens.get("output", 0)),
            "cache_read": int(tokens.get("cache_read", 0)),
            "cache_write": int(tokens.get("cache_write", 0)),
        },
        "usd": float(usd),
        "tags": tags or {},
        "metadata": metadata or {},
    }


def _format_log_line(payload: dict, event: str) -> str:
    t = payload["tokens"]
    return (
        f"file_id={payload['file_id']} | {event} | model={payload['model']} | "
        f"usd={payload['usd']:.4f} | "
        f"tokens=in:{t['input']},out:{t['output']},"
        f"cache_r:{t['cache_read']},cache_w:{t['cache_write']}"
    )


def _check_metadata_size(metadata: Optional[dict]) -> None:
    if not metadata:
        return
    try:
        size = len(json.dumps(metadata, default=str).encode("utf-8"))
    except (TypeError, ValueError):
        logger.warning("Cost event metadata is not JSON-serializable; sending as-is")
        return
    if size > METADATA_MAX_BYTES:
        logger.warning(
            f"Cost event metadata is {size} bytes "
            f"(cap={METADATA_MAX_BYTES}); event will still be published"
        )


def cost(
    event: str,
    *,
    model: str,
    tokens: dict,
    usd: float,
    file_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    request_id: Optional[str] = None,
    tags: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Emit a structured cost event.

    Always logs a single line at COST level. When a publisher has been
    configured via `configure_cost_publisher(...)`, the structured payload
    is also enqueued for publication to Redis Streams.

    Args:
        event: short event name, e.g. "extraction_complete"
        model: model identifier, e.g. "claude-opus-4-7"
        tokens: dict with input/output/cache_read/cache_write counts (missing
            keys default to 0)
        usd: cost in USD
        file_id: source file the cost is attributed to (when applicable)
        tenant_id: tenant / customer
        request_id: correlation id from the surrounding request
        tags: free-form routing inputs (read by the notification service)
        metadata: free-form passenger data (NOT used by routing; warns above
            4KB but is still published)
    """
    _check_metadata_size(metadata)

    publisher = get_publisher()
    service = publisher.service if publisher is not None else ""
    payload = _build_event(
        event,
        model=model,
        tokens=tokens,
        usd=usd,
        file_id=file_id,
        tenant_id=tenant_id,
        request_id=request_id,
        tags=tags,
        metadata=metadata,
        service=service,
    )

    logger.log(COST_LEVEL_NAME, _format_log_line(payload, event))

    if publisher is not None:
        publisher.enqueue(payload)


def _attach_to_logger() -> None:
    # Guard against re-attachment on re-import (e.g. test reloads).
    if getattr(logger, "_outamation_cost_attached", False):
        return
    logger.cost = cost  # type: ignore[attr-defined]
    logger._outamation_cost_attached = True  # type: ignore[attr-defined]


_register_level()
_attach_to_logger()
