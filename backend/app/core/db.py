from contextlib import contextmanager
from typing import Iterator

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import POSTGRES_CONNECT_TIMEOUT, POSTGRES_DSN


class PostgreSQLConfigurationError(RuntimeError):
    """Raised when the PostgreSQL connection is not configured."""


def _normalized_dsn() -> str:
    if not POSTGRES_DSN:
        raise PostgreSQLConfigurationError(
            "POSTGRES_DSN is not configured. Example: "
            "postgresql://postgres:<password>@127.0.0.1:5432/postgres"
        )

    return POSTGRES_DSN.replace(
        "postgresql+psycopg://",
        "postgresql://",
        1,
    )


def _configure_connection(connection: psycopg.Connection) -> None:
    connection.row_factory = dict_row
    register_vector(connection)


_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            _normalized_dsn(),
            min_size=1,
            max_size=20,
            timeout=float(POSTGRES_CONNECT_TIMEOUT),
            configure=_configure_connection,
        )
    return _pool


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """获取连接池中的可用连接，离开上下文时自动归还池中。"""
    pool = get_pool()
    with pool.connection() as connection:
        yield connection

