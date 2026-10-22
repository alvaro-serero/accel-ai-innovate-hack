"""Postgres access. Owner: Leo.

Usage:
    from backend.app.db import fetch_all, fetch_one, execute
    rows = fetch_all("select * from jobs where is_internship and closed_at is null")
    row = fetch_one("insert into users (name) values (%s) returning id", ("Alvaro",))

Rows come back as dicts. Each call commits on success.
Apply the schema once with:  python -m backend.app.db
"""
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from backend.app.config import settings

_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is not set (see .env.example)")
        _pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row},
            open=True,
        )
    return _pool


def fetch_all(sql: str, params=None) -> list[dict]:
    with pool().connection() as conn:
        return conn.execute(sql, params).fetchall()


def fetch_one(sql: str, params=None) -> dict | None:
    """Also use this for INSERT ... RETURNING."""
    with pool().connection() as conn:
        return conn.execute(sql, params).fetchone()


def execute(sql: str, params=None) -> int:
    """Returns the number of affected rows."""
    with pool().connection() as conn:
        return conn.execute(sql, params).rowcount


def init_schema() -> None:
    sql = (Path(__file__).resolve().parents[2] / "db" / "schema.sql").read_text()
    with pool().connection() as conn:
        conn.execute(sql)
    print("schema applied")


if __name__ == "__main__":
    init_schema()
