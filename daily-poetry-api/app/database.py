"""Database engine and session management."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import get_database_url

DATABASE_URL = get_database_url()

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    engine = create_engine(DATABASE_URL, future=True, connect_args=connect_args)
elif DATABASE_URL.startswith("postgresql+psycopg"):
    # Supabase transaction poolers can fail with server-side prepared statements.
    # NullPool avoids holding open connections between serverless invocations.
    connect_args = {"prepare_threshold": None}
    engine = create_engine(DATABASE_URL, future=True, connect_args=connect_args, poolclass=NullPool)
else:
    connect_args = {}
    engine = create_engine(DATABASE_URL, future=True, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
