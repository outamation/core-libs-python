# Outamation PostgreSQL Package

A generic asynchronous PostgreSQL utility package built on [asyncpg](https://github.com/MagicStack/asyncpg). This package provides a high-level, easy-to-use interface for PostgreSQL operations with connection pooling, transaction management, and environment-based configuration.

## Features

- 🚀 **Async/await support** - Built on asyncpg for high performance
- 🏊 **Connection pooling** - Automatic connection pool management
- 🔧 **Environment configuration** - Easy setup via environment variables
- 🔒 **Transaction support** - Built-in transaction context managers
- 📝 **Comprehensive API** - Full CRUD operations with intuitive methods
- 🛡️ **Error handling** - Robust error handling and logging
- 🎯 **Flexible usage** - Works as both singleton and context manager

## Installation

```bash
pip install git+https://github.com/outamation/core-libs-python.git#subdirectory=pkg-postgres
```

## Quick Start

### Environment Variables

Set up your database connection using environment variables:

```bash
export PG_HOST=localhost
export PG_PORT=5432
export PG_USER=postgres
export PG_PASSWORD=your_password
export PG_DATABASE=your_database
```

### Basic Usage

#### As a Context Manager (Recommended for scripts)

```python
import asyncio
from outamation_pkg_postgres import PostgresManager

async def main():
    async with PostgresManager.from_env() as db:
        # Fetch a single value
        count = await db.fetch_val("SELECT COUNT(*) FROM users")
        print(f"Total users: {count}")
        
        # Fetch all rows
        users = await db.fetch_all("SELECT id, name FROM users WHERE active = $1", True)
        for user in users:
            print(f"User: {user['name']}")

asyncio.run(main())
```

#### As a Singleton (Recommended for web applications)

```python
from outamation_pkg_postgres import PostgresManager

# Initialize once (e.g., in your app startup)
db = PostgresManager.from_env()
await db.connect()

# Use throughout your application
async def get_user(user_id: int):
    return await db.fetch_row("SELECT * FROM users WHERE id = $1", user_id)

# Close when shutting down (e.g., in your app shutdown)
await db.close()
```

## API Reference

### Initialization

#### `PostgresManager(host, port, user, password, database, ...)`

Create a new PostgresManager instance with explicit parameters.

**Parameters:**

- `host` (str): Database host (default: "localhost")
- `port` (int): Database port (default: 5432)
- `user` (str): Database user (default: "postgres")
- `password` (str): Database password (default: "")
- `database` (str): Database name (default: "postgres")
- `dsn` (str, optional): Complete DSN string (overrides other params)
- `min_pool_size` (int): Minimum pool size (default: 0)
- `max_pool_size` (int): Maximum pool size (default: 3)
- `init_callback` (callable, optional): Function to run on each new connection

#### `PostgresManager.from_env(**kwargs)`

Create a PostgresManager instance using environment variables.

```python
db = PostgresManager.from_env(
    max_pool_size=10,  # Override environment defaults
    min_pool_size=2
)
```

### Connection Management

#### `await connect()`

Establishes the connection pool.

#### `await close()`

Closes the connection pool.

#### `async with get_connection() as conn:`

Acquires a single connection from the pool for multiple operations.

```python
async with db.get_connection() as conn:
    await conn.execute("SET session_replication_role = replica")
    result = await conn.fetch("SELECT * FROM users")
```

### Data Fetching

#### `await fetch_all(query, *params) -> List[Record]`

Fetch all rows matching the query.

```python
users = await db.fetch_all("SELECT * FROM users WHERE age > $1", 18)
```

#### `await fetch_row(query, *params) -> Optional[Record]`

Fetch the first row matching the query.

```python
user = await db.fetch_row("SELECT * FROM users WHERE id = $1", user_id)
```

#### `await fetch_val(query, *params) -> Any`

Fetch a single value (first column of first row).

```python
count = await db.fetch_val("SELECT COUNT(*) FROM users")
name = await db.fetch_val("SELECT name FROM users WHERE id = $1", user_id)
```

### Data Manipulation

#### `await execute(query, *params) -> str`

Execute a command and return the status string.

```python
status = await db.execute("INSERT INTO users (name, email) VALUES ($1, $2)", 
                         "John Doe", "john@example.com")
print(status)  # "INSERT 0 1"
```

#### `await execute_many(query, args_list)`

Execute a command for multiple argument sets in bulk.

```python
await db.execute_many(
    "INSERT INTO users (name, email) VALUES ($1, $2)",
    [("Alice", "alice@example.com"), ("Bob", "bob@example.com")]
)
```

#### `await execute_and_fetch_row(query, *params) -> Optional[Record]`

Execute a command and return the first row (perfect for `RETURNING` clauses).

```python
new_user = await db.execute_and_fetch_row(
    "INSERT INTO users (name, email) VALUES ($1, $2) RETURNING *",
    "Jane Doe", "jane@example.com"
)
print(f"Created user with ID: {new_user['id']}")
```

### Transaction Management

#### `async with in_transaction() as conn:`

Execute multiple operations within a transaction.

```python
async with db.in_transaction() as conn:
    # All operations here are in the same transaction
    await conn.execute("UPDATE accounts SET balance = balance - $1 WHERE id = $2", 100, 1)
    await conn.execute("UPDATE accounts SET balance = balance + $1 WHERE id = $2", 100, 2)
    # Automatically commits on success, rolls back on exception
```

## Advanced Usage

### Custom Connection Initialization

```python
async def setup_connection(conn):
    """Custom setup for each new connection"""
    await conn.execute("SET timezone = 'UTC'")
    await conn.execute("SET statement_timeout = '30s'")

db = PostgresManager.from_env(init_callback=setup_connection)
```

### Error Handling

```python
async with PostgresManager.from_env() as db:
    try:
        result = await db.fetch_val("SELECT invalid_column FROM users")
    except asyncpg.PostgresError as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
```

### Working with JSON

```python
# Insert JSON data
await db.execute(
    "INSERT INTO settings (user_id, preferences) VALUES ($1, $2)",
    user_id, {"theme": "dark", "notifications": True}
)

# Fetch JSON data
prefs = await db.fetch_val(
    "SELECT preferences FROM settings WHERE user_id = $1", 
    user_id
)
```

## Best Practices

1. **Use environment variables** for configuration in production
2. **Use the context manager** for scripts and short-lived operations
3. **Use the singleton pattern** for web applications and long-running services
4. **Always use parameterized queries** to prevent SQL injection
5. **Use transactions** for operations that must succeed or fail together
6. **Handle exceptions** appropriately for your use case

## Requirements

- Python >= 3.8
- asyncpg

## License

Proprietary

## Contributing

This is a proprietary package developed by Outamation. For issues or feature requests, please contact the development team.
