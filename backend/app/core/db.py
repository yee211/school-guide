"""PostgreSQL 连接封装（基础设施，供 rag / structured 复用）。"""
from __future__ import annotations

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

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


def connect() -> psycopg.Connection:
    connection = psycopg.connect(
        _normalized_dsn(),
        connect_timeout=POSTGRES_CONNECT_TIMEOUT,
        row_factory=dict_row,
    )

    try:
        register_vector(connection)
    except Exception:
        connection.close()
        raise

    return connection
