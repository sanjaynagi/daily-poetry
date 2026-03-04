"""Simple SQL migration runner for backend MVP."""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError


def _coerce_postgres_notification_flag_columns_to_boolean(connection) -> None:
    # Older production databases may have INTEGER flag columns from early SQLite-first DDL.
    # Coerce these to BOOLEAN so SQLAlchemy bool writes do not fail on Postgres.
    columns = [
        ("push_subscriptions", "active"),
        ("notification_preferences", "enabled"),
    ]

    for table_name, column_name in columns:
        type_row = connection.execute(
            text(
                """
                SELECT data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :table_name
                  AND column_name = :column_name
                """
            ),
            {"table_name": table_name, "column_name": column_name},
        ).fetchone()

        if type_row is None:
            continue

        data_type = str(type_row[0]).lower()
        if data_type == "boolean":
            continue

        if data_type not in {"smallint", "integer", "bigint"}:
            continue

        # Legacy integer defaults (0/1) must be removed before Postgres can alter type.
        connection.execute(text(f"ALTER TABLE {table_name} ALTER COLUMN {column_name} DROP DEFAULT"))
        connection.execute(
            text(
                f"""
                ALTER TABLE {table_name}
                ALTER COLUMN {column_name} TYPE boolean
                USING CASE WHEN {column_name} = 0 THEN FALSE ELSE TRUE END
                """
            )
        )
        # Restore semantic defaults for new rows.
        default_literal = "TRUE" if (table_name, column_name) == ("push_subscriptions", "active") else "FALSE"
        connection.execute(text(f"ALTER TABLE {table_name} ALTER COLUMN {column_name} SET DEFAULT {default_literal}"))


def run_sql_migrations(engine: Engine) -> None:
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))

    with engine.begin() as connection:
        dialect_name = connection.dialect.name
        for migration_file in migration_files:
            sql_text = migration_file.read_text(encoding="utf-8")
            for statement in [chunk.strip() for chunk in sql_text.split(";")]:
                if statement:
                    sql_statement = statement
                    if dialect_name == "sqlite":
                        sql_statement = re.sub(
                            r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS",
                            "ADD COLUMN",
                            sql_statement,
                            flags=re.IGNORECASE,
                        )

                    try:
                        connection.execute(text(sql_statement))
                    except OperationalError as exc:
                        message = str(exc).lower()
                        if (
                            dialect_name == "sqlite"
                            and "idx_poems_editorial_status" in sql_statement
                            and "no such column: editorial_status" in message
                        ):
                            connection.execute(
                                text("ALTER TABLE poems ADD COLUMN editorial_status TEXT NOT NULL DEFAULT 'pending'")
                            )
                            connection.execute(text(sql_statement))
                            continue
                        if "duplicate column name" in message or "already exists" in message:
                            continue
                        # RENAME COLUMN on a column that no longer exists means it was
                        # already renamed in a previous run or by the ORM schema.
                        if "rename" in sql_statement.lower() and "no such column" in message:
                            continue
                        raise

        if dialect_name == "postgresql":
            _coerce_postgres_notification_flag_columns_to_boolean(connection)
