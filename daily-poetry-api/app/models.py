"""SQLAlchemy models for Daily Poetry backend MVP."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Author(Base):
    __tablename__ = "authors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)


class Poem(Base):
    __tablename__ = "poems"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    linecount: Mapped[int] = mapped_column(Integer, nullable=False)
    editorial_status: Mapped[Literal["pending", "approved", "rejected"]] = mapped_column(
        Text, nullable=False, default="pending"
    )
    author_id: Mapped[str] = mapped_column(String(36), ForeignKey("authors.id"), nullable=False)


class DailySelection(Base):
    __tablename__ = "daily_selection"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    poem_id: Mapped[str] = mapped_column(String(36), ForeignKey("poems.id"), nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    auth_token: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Favourite(Base):
    __tablename__ = "favourites"
    __table_args__ = (UniqueConstraint("user_id", "poem_id", name="uq_favourites_user_poem"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    poem_id: Mapped[str] = mapped_column(String(36), ForeignKey("poems.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    time_zone: Mapped[str] = mapped_column(Text, nullable=False, default="UTC")
    local_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=9)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(Text, nullable=False)
    auth: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_notified_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
