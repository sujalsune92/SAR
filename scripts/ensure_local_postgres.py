from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import psycopg2
from dotenv import load_dotenv
from psycopg2 import OperationalError
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/sar_audit"
ROOT_DIR = Path(__file__).resolve().parents[1]


def parse_database_url(database_url: str) -> dict[str, str | int | None]:
    parsed = urlparse(database_url)
    database_name = parsed.path.lstrip("/")
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "database": database_name or "sar_audit",
    }


def database_exists(admin_connection, database_name: str) -> bool:
    with admin_connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database_name,))
        return cursor.fetchone() is not None


def main() -> None:
    load_dotenv(ROOT_DIR / ".env")

    database_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    settings = parse_database_url(database_url)

    admin_db = os.getenv("POSTGRES_ADMIN_DB", "postgres")
    try:
        admin_connection = psycopg2.connect(
            host=settings["host"],
            port=settings["port"],
            user=settings["user"],
            password=settings["password"],
            dbname=admin_db,
        )
    except OperationalError as exc:
        print("Failed to connect to PostgreSQL.")
        print(
            "Connection details: "
            f"host={settings['host']} port={settings['port']} user={settings['user']} db={admin_db}"
        )
        print("Tip: verify DATABASE_URL and POSTGRES_ADMIN_DB in .env, and confirm PostgreSQL is running.")
        raise SystemExit(1) from exc

    admin_connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

    try:
        if database_exists(admin_connection, str(settings["database"])):
            print(f"Database '{settings['database']}' already exists.")
        else:
            with admin_connection.cursor() as cursor:
                cursor.execute(f'CREATE DATABASE "{settings["database"]}"')
            print(f"Database '{settings['database']}' created successfully.")
    finally:
        admin_connection.close()


if __name__ == "__main__":
    main()