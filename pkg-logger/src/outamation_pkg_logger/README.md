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
pip install outamation_pkg_logger
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
