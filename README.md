# core-libs-python

Monorepo of internal Python packages. Each subdirectory is an independently versioned, independently installed package.

| Package | Purpose |
|---|---|
| [pkg-logger](pkg-logger/README.md) | Pre-configured Loguru logger + custom `COST` level and Redis Streams publisher for cost/token telemetry |
| [pkg-postgres](pkg-postgres/README.md) | Async PostgreSQL helper built on `asyncpg` (pool, transactions, context manager) |
| [pkg-rabbitmq](pkg-rabbitmq/README.md) | Async RabbitMQ client built on `aio-pika` (priority queues, consumer, HTTP management API peek) |
| [pkg-sftp](pkg-sftp/README.md) | SFTP client built on `paramiko` (connection pool, upload/download/remove, HMAC-signed API callbacks) |

## Installation

Each package is installed directly from Git by addressing its subdirectory. Pin to a specific commit SHA for reproducibility:

```bash
pip install "git+https://github.com/outamation/core-libs-python.git@<sha>#subdirectory=pkg-logger"
```

See each package's README for its own Installation + Quick Start + API reference.

## Repo conventions

See [CLAUDE.md](CLAUDE.md) for the full conventions, including package layout, version pinning style, inter-package dependencies, and the cost-event subsystem contract.
