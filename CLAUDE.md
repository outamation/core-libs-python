# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

This is a **monorepo of independent internal Python packages**, one per top-level subdirectory. There is intentionally **no root `pyproject.toml`** and no monorepo build orchestration — each package is built, versioned, and installed independently.

Current packages:

| Subdirectory | Distribution name | Purpose |
|---|---|---|
| `pkg-logger/` | `outamation_pkg_logger` | Pre-configured Loguru logger; custom `COST` level + Redis Streams publisher for cost/token telemetry |
| `pkg-postgres/` | `outamation_pkg_postgres` | Async PostgreSQL helper built on `asyncpg` (pool, transactions, context manager) |
| `pkg-rabbitmq/` | `outamation_pkg_rabbitmq` | Async RabbitMQ client built on `aio-pika` (robust connection, priority queues, consumer, HTTP management API peek) |
| `pkg-sftp/` | `outamation_pkg_sftp` | SFTP client built on `paramiko` (connection pool per `project_id`, upload/download/remove, HMAC-signed API callbacks, polling-based batch processing) |

When adding a new package, follow the established conventions:
- `<pkg>/pyproject.toml` (setuptools, `src/` layout)
- `<pkg>/src/<distribution_name>/` for code
- `<pkg>/README.md` with Installation + Quick Start + API reference
- Python `>=3.8`, license `"Proprietary"`

## Installation (downstream apps)

There is no private PyPI — every internal package is installed directly from Git, addressing the relevant subdirectory. Downstream apps (e.g. `doc-ai-app`, `doc-ai-extraction-consumer`) pin to a **specific commit SHA** for reproducibility, not to `main`:

```
outamation_pkg_logger @ git+https://github.com/outamation/core-libs-python.git@<sha>#subdirectory=pkg-logger
```

When making changes that downstream apps depend on, increment the package version in `<pkg>/pyproject.toml` and note the new commit SHA in the PR description so consumers can bump their pin.

## Development

### Editable install (single package)

```bash
pip install -e pkg-logger
# or
pip install -e pkg-postgres
```

### Tests

`pkg-logger` has a pytest suite under `pkg-logger/tests/`:

```bash
pytest pkg-logger/tests -v
```

`pkg-postgres` has no test suite yet.

### Linting

The repo uses `ruff` (a `.ruff_cache/` is present at the root). No explicit `ruff.toml` is checked in, so defaults apply.

```bash
ruff check .
```

### Notes on the checked-in `venv/`

A `venv/` exists at the repo root but is pinned to a Python interpreter path that may not exist on every developer's machine. Treat it as disposable — create your own venv if needed, or use the editable install pattern above against your project's venv.

## Architectural points worth knowing

### Inter-package dependencies on `pkg-logger`

Three of the four packages import `outamation_pkg_logger` at module-level, but only one declares the dependency:

| Package | Imports `outamation_pkg_logger` | Declares it in `pyproject.toml` |
|---|---|---|
| `pkg-postgres` | yes | **no** ❌ |
| `pkg-rabbitmq` | yes | **no** ❌ |
| `pkg-sftp` | yes | yes ✅ |

Installing `pkg-postgres` or `pkg-rabbitmq` *alone* (without pulling `pkg-logger` separately) fails at import time. Downstream apps work today because they install `pkg-logger` themselves. If you touch any of these packages' metadata, consider formalizing the missing declarations.

### Version-pinning style varies per package

Pinning is inconsistent across packages and worth matching whichever one you're editing:

| Package | Style |
|---|---|
| `pkg-logger` | `loguru==0.7.3`, `redis>=4.2.0` (mixed: exact + floor) |
| `pkg-postgres` | `asyncpg` (no pin) |
| `pkg-rabbitmq` | `aio-pika==9.5.7`, `python-dotenv==1.1.1`, `aiohttp==3.12.15` (all exact) |
| `pkg-sftp` | `paramiko==3.0.0`, `python-dotenv==1.0.0`, `requests==2.31.0`, `outamation_pkg_logger` (all exact except the internal dep) |

Note that `pkg-sftp` and `pkg-rabbitmq` both pin `python-dotenv` but to **different exact versions** (1.0.0 vs 1.1.1). This is a latent conflict for any app that installs both.

### `pkg-logger` cost-event subsystem

`outamation_pkg_logger` ships a custom `COST` log level (numeric 25) and a `logger.cost(...)` method for emitting structured cost/token events. The publisher side is **opt-in**:

- Without `configure_cost_publisher(...)`, `logger.cost(...)` only emits a log line — no Redis dependency at runtime.
- With `configure_cost_publisher(redis_url=..., service=...)`, structured events are batched on a daemon thread and written to Redis Streams (`outamation:cost-events`) via `XADD ... MAXLEN ~ 250000`.
- The producer side is non-blocking and never raises into callers, even when Redis is unreachable (failures retry with exponential backoff; buffer drops oldest on overflow).
- Downstream of this stream sits a separate notification service (in a different repo) that consumes events for trend analysis and alerting.

When changing anything in `pkg-logger/src/outamation_pkg_logger/cost.py` or `publisher.py`, be aware that the event schema is a **stable contract** consumed by external services — the keys `event_id`, `timestamp`, `service`, `tenant_id`, `request_id`, `file_id`, `model`, `tokens`, `usd`, `tags`, `metadata` are all relied on. `tags` drives downstream routing; `metadata` is intentionally ignored by routing and reserved as a forward-compat slot.

### Each package owns its own dependencies

Dependencies are declared per-package in each `pyproject.toml`. A change in `pkg-logger`'s deps does **not** propagate to `pkg-postgres` consumers and vice versa. Avoid implicit cross-package coupling unless you also declare it.

## When making changes

- Bump the version in the affected package's `pyproject.toml` if downstream apps will need to repin (any user-facing change qualifies).
- Update the package's `README.md` for new public API or behavior.
- Tests live alongside their package (e.g. `pkg-logger/tests/`), not at the repo root.
- The package `__init__.py` mutates the shared Loguru `logger` (custom levels, handlers, attached methods). Be deliberate about side-effect imports — re-importing should not re-attach methods or re-register levels.
