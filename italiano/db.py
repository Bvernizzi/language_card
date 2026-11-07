"""Database connection (credentials from .env) and schema bootstrap."""

import os
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"


def _load_env(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def connect() -> psycopg.Connection:
    _load_env()
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.environ.get("POSTGRES_PORT", "5433")),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        autocommit=True,  # explicit transactions via conn.transaction()
    )


def ensure_schema(conn: psycopg.Connection) -> None:
    """Apply sql/*.sql in order. Tables are IF NOT EXISTS; views are recreated."""
    with conn.transaction():
        for sql_file in sorted(SQL_DIR.glob("*.sql")):
            conn.execute(sql_file.read_text(encoding="utf-8"))
