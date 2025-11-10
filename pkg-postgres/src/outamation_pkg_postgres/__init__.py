import loguru
import asyncpg
import contextlib
import os
from typing import Optional, Any, List, Tuple, AsyncGenerator, Callable, Awaitable

# Get a logger. The consuming app is responsible for configuring it.
log = loguru.logger


class PostgresManager:
    """
    An async context manager for handling an asyncpg connection pool.

    Provides two main ways to use it:

    1. As a web-app singleton:
       db = PostgresManager.from_env()
       await db.connect()  # On app startup
       ...
       await db.close()    # On app shutdown

    2. As a script context manager:
       async with PostgresManager.from_env() as db:
           await db.fetch_val("SELECT 1")
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        user: str = "postgres",
        password: str = "",
        database: str = "postgres",
        dsn: Optional[str] = None,
        min_pool_size: int = 0,
        max_pool_size: int = 3,
        init_callback: Optional[Callable[[asyncpg.Connection], Awaitable[None]]] = None,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.dsn = dsn
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self.pool: Optional[asyncpg.Pool] = None
        self.init_callback = init_callback  # NEW: Hook for app-specific setup

    @classmethod
    def from_env(cls, **kwargs):
        """
        NEW: Create an instance using environment variables.
        This mirrors the pattern from your db_utils.py.
        """
        return cls(
            host=os.getenv("PG_HOST", "localhost"),
            port=int(os.getenv("PG_PORT", 5432)),
            user=os.getenv("PG_USER", "postgres"),
            password=os.getenv("PG_PASSWORD", ""),
            database=os.getenv("PG_DATABASE", "postgres"),
            **kwargs,  # Allow overriding env vars
        )

    async def connect(self):
        """Creates the connection pool."""
        if self.pool:
            return

        try:
            self.pool = await asyncpg.create_pool(
                dsn=self.dsn,
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                min_size=self.min_pool_size,
                max_size=self.max_pool_size,
                init=self.init_callback,  # NEW: Use the setup callback
            )
            log.info(
                f"Postgres pool created for {self.user}@{self.host}:{self.port}/{self.database}"
            )
        except Exception as e:
            log.exception(f"Failed to create Postgres pool: {e}")
            raise

    async def close(self):
        """Closes the connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            log.info("Postgres connection pool closed.")

    async def __aenter__(self) -> "PostgresManager":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """Async context manager exit."""
        await self.close()

    def _get_pool(self) -> asyncpg.Pool:
        """Internal helper to ensure pool exists."""
        if not self.pool:
            raise RuntimeError(
                "Connection pool is not initialized. "
                "Did you forget to call 'await db.connect()' or use 'async with'?"
            )
        return self.pool

    # --- NEW: Connection Context Manager ---

    @contextlib.asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """
        NEW: Acquires a single connection from the pool.

        This is the perfect replacement for your 'run_with_conn' pattern,
        especially when you need to run multiple commands on one connection
        (like setting audit info before a query).
        """
        pool = self._get_pool()
        async with pool.acquire() as conn:
            yield conn

    # --- Data Fetching Methods ---

    async def fetch_all(self, query: str, *params) -> List[asyncpg.Record]:
        """Fetches all rows for a query."""
        pool = self._get_pool()  # FIX: Was 'self_get_pool'
        async with pool.acquire() as conn:
            return await conn.fetch(query, *params)

    async def fetch_row(self, query: str, *params) -> Optional[asyncpg.Record]:
        """Fetches the first row for a query."""
        pool = self._get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(query, *params)

    async def fetch_val(self, query: str, *params) -> Any:
        """Fetches a single value (the first column of the first row)."""
        pool = self._get_pool()
        async with pool.acquire() as conn:
            value = await conn.fetchval(query, *params)
            return value

    # --- Data Manipulation Methods ---

    async def execute(self, query: str, *params) -> str:
        """
        Executes a command (INSERT, UPDATE, DELETE) and returns the status.
        e.g., "INSERT 1"
        """
        pool = self._get_pool()
        async with pool.acquire() as conn:
            return await conn.execute(query, *params)

    async def execute_many(self, query: str, args_list: List[Tuple]):
        """Executes a command for a list of arguments in bulk."""
        pool = self._get_pool()
        async with pool.acquire() as conn:
            await conn.executemany(query, args_list)

    async def execute_and_fetch_row(
        self, query: str, *params
    ) -> Optional[asyncpg.Record]:
        """
        Executes a command and returns the first row,
        perfect for 'INSERT ... RETURNING *'.
        """
        pool = self._get_pool()
        # This must be done in a transaction to guarantee
        # we get the right row back.
        async with pool.acquire() as conn:
            async with conn.transaction():
                return await conn.fetchrow(query, *params)

    # --- Transaction Helper ---

    @contextlib.asynccontextmanager
    async def in_transaction(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """
        Provides a dedicated connection inside a transaction.
        Commits on success, rolls back on error.

        Usage:
            async with db.in_transaction() as conn:
                await conn.execute(...)
                await conn.execute(...)
        """
        pool = self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                try:
                    yield conn
                except Exception:
                    log.error("Transaction failed, rolling back.", exc_info=True)
                    # The transaction context manager handles the rollback.
                    raise
