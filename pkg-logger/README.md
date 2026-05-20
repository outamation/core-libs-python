# Outamation Logger Package

A lightweight organizational logging utility built on [Loguru](https://github.com/Delgan/loguru). It provides:

## Features

- 🔌 **Zero-config default**: Import and log immediately with sensible console formatting.
- 🧩 **Single shared logger**: Unified logging across all internal services/packages.
- 🗂️ **Optional file logging**: Easily add rotating & retained compressed log files.
- � **Rotation & retention**: Configure size/time based rotation and automatic cleanup.
- 🧵 **Async-safe**: `enqueue=True` used for file sinks (safe for multi-process logging).
- 🎨 **Readable format**: Timestamp, level, source (module:function:line), message.
- 🌱 **Environment override**: Set `LOG_LEVEL` to change default console verbosity.

## Installation

```bash
pip install git+https://github.com/outamation/core-libs-python.git#subdirectory=pkg-logger
```

> If using from a monorepo checkout, you can install editable:
>
> ```bash
> pip install -e pkg-logger/src/outamation_pkg_logger
> ```

## Quick Start

```python
from outamation_pkg_logger import logger

logger.info("Service starting...")
logger.warning("Cache miss for key={}", "user:42")
logger.error("Something went wrong")
```

## Enabling File Logging

```python
from outamation_pkg_logger import logger, setup_logging

setup_logging(
    console_level="INFO",          # Console threshold
    file_level="DEBUG",            # File threshold
    log_file_path="logs/app.log",  # Enable file logging
    rotation="10 MB",              # Rotate when file reaches 10 MB
    retention="10 days"            # Purge logs older than 10 days
)

logger.debug("Detailed diagnostics saved to file.")
```

### Environment Variable Control

Set `LOG_LEVEL` before import to influence the initial console handler added by the package:

```bash
export LOG_LEVEL=DEBUG
```

Then in Python:

```python
from outamation_pkg_logger import logger
logger.debug("Now visible because LOG_LEVEL=DEBUG")
```

## API

### `logger`

The shared Loguru `logger` instance. Use it directly for application logging.

### `setup_logging(console_level="INFO", file_level="DEBUG", log_file_path=None, rotation="10 MB", retention="10 days")`

Reconfigures all handlers. Removes the default sink and applies new console sink, plus optional file sink.

| Parameter        | Type     | Description |
|------------------|----------|-------------|
| `console_level`  | `str`    | Minimum level for console output. |
| `file_level`     | `str`    | Minimum level for file output. |
| `log_file_path`  | `str` / `None` | Path to log file; if `None` no file sink added. |
| `rotation`       | `str`    | Rotation policy (size/time, e.g. `"10 MB"`, `"1 day"`, `"00:00"`). |
| `retention`      | `str`    | How long to keep old rotated logs (e.g. `"10 days"`). |

File sink also uses:

- `compression="zip"` — compresses rotated archives.
- `enqueue=True` — async queue for thread/process safety.

## Structured / Contextual Logging

Use Loguru's `bind` for contextual enrichment:

```python
req_logger = logger.bind(request_id="abc123", user_id=42)
req_logger.info("Started handling request")
req_logger.success("Completed")
```

## Cost Event Logging

The package provides a custom `COST` log level (numeric `25`, between `INFO` and `WARNING`) and a `logger.cost(...)` method for emitting structured cost/token events. When a publisher is configured, events are batched and published to Redis Streams for downstream consumption (e.g. by the cost notification service).

```python
from outamation_pkg_logger import logger, configure_cost_publisher

# Enable the publisher at application startup. Safe to skip if you only want
# the log line — logger.cost() then becomes a log-only no-op on the wire.
configure_cost_publisher(
    redis_url="redis://localhost:6379/0",
    service="doc-ai-app",
)

logger.cost(
    event="extraction_complete",
    model="claude-opus-4-7",
    tokens={"input": 1234, "output": 567, "cache_read": 0, "cache_write": 0},
    usd=0.1234,
    file_id="abc-123",
    tenant_id="acme-corp",
    request_id="req-xyz",
    tags={"team": "doc-ai", "stage": "extraction"},
    metadata={},  # reserved for future fields, NOT used by routing
)
```

### Filtering COST out of a sink

```python
logger.add(sys.stderr, filter=lambda r: r["level"].name != "COST")
```

### `configure_cost_publisher(...)` parameters

| Parameter | Default | Description |
|---|---|---|
| `redis_url` | required | e.g. `"redis://localhost:6379/0"` |
| `stream` | `"outamation:cost-events"` | Redis Streams key |
| `flush_interval` | `5.0` | Seconds between flush ticks |
| `service` | `""` | Producer service name (stamped on every event) |
| `buffer_cap` | `10_000` | Max in-memory events; oldest dropped on overflow |
| `stream_maxlen` | `250_000` | Approximate trim cap for the Redis stream |
| `enabled` | `True` | When `False`, the call is a no-op |

### Behavior notes

- Failures to publish are caught and retried with exponential backoff (5s → 10s → 30s → 60s, capped). The calling app never blocks and never sees an exception.
- Buffer overflow drops the **oldest** events with a rate-limited WARN log.
- `metadata` larger than 4 KB triggers a WARN but is still published.
- An `atexit` handler does a final sync flush with a 2-second timeout on process exit. Hard kills (`os._exit`, `kill -9`) skip this.

## Exception Logging

```python
try:
    risky_operation()
except Exception:
    logger.exception("Unexpected failure during risky_operation")
```

## Best Practices

1. Use `LOG_LEVEL` in container/orchestrator configs for dynamic verbosity.
2. Call `setup_logging()` once at application bootstrap; avoid repeated reconfiguration.
3. Use contextual logging (`bind`) for traceability in distributed systems.
4. Prefer structured messages instead of concatenated strings: `logger.info("User {} logged in", user_id)`.
5. Keep rotation size/time conservative to ease log shipping.

## FAQ

**Q: Why remove existing handlers first?**  
To guarantee consistent configuration and avoid duplicate sinks when reinitializing.

**Q: Can I add custom sinks?**  
Yes. After `setup_logging()` call `logger.add(…)` with additional destinations (e.g., syslog, JSON file).

**Q: Does this interfere with other packages using Loguru?**  
All code using `from loguru import logger` shares the same global instance. Configure once at startup.

## Requirements

- Python >= 3.8
- loguru >= 0.7.0

## License

Proprietary

## Contributing

Internal Outamation package. Open issues or feature requests in the monorepo; include example use cases.

## Minimal Smoke Test

```python
from outamation_pkg_logger import logger, setup_logging
setup_logging(log_file_path="logs/test.log", console_level="DEBUG")
logger.debug("debug visible")
logger.info("info visible")
logger.warning("warning")
logger.error("error")
logger.critical("critical")
```

Check `logs/test.log` for persisted entries.
