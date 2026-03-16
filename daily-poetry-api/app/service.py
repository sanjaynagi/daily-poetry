"""Core query logic for Daily Poetry API."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import Select, String, cast, func, select
from sqlalchemy.orm import Session

from app import models


def utc_today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def get_or_create_user_by_token(db: Session, token: str) -> models.User:
    user = db.execute(select(models.User).where(models.User.auth_token == token)).scalar_one_or_none()
    if user is not None:
        return user

    user = models.User(id=str(uuid4()), auth_token=token, created_at=datetime.now(timezone.utc).replace(tzinfo=None))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def issue_anonymous_token(db: Session) -> tuple[models.User, str]:
    token = secrets.token_urlsafe(32)
    user = models.User(id=str(uuid4()), auth_token=token, created_at=datetime.now(timezone.utc).replace(tzinfo=None))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, token


def fetch_daily_payload(db: Session) -> dict:
    today = datetime.now(timezone.utc).date()

    stmt: Select[tuple[models.DailySelection, models.Poem, models.Author]] = (
        select(models.DailySelection, models.Poem, models.Author)
        .join(models.Poem, models.Poem.id == models.DailySelection.poem_id)
        .join(models.Author, models.Author.id == models.Poem.author_id)
        .where(cast(models.DailySelection.date, String) == today.isoformat())
    )

    row = db.execute(stmt).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No daily selection configured for {today.isoformat()}")

    daily, poem, author = row
    return {
        "date": daily.date.isoformat() if hasattr(daily.date, "isoformat") else str(daily.date),
        "poem": {
            "id": poem.id,
            "title": poem.title,
            "text": poem.text,
            "linecount": poem.linecount,
        },
        "author": {
            "id": author.id,
            "name": author.name,
            "bio": author.bio or "",
            "image_url": author.image_url,
        },
    }


def fetch_poem_payload(db: Session, poem_id: str) -> dict:
    latest_featured_date_subquery = (
        select(models.DailySelection.poem_id, func.max(models.DailySelection.date).label("date_featured"))
        .group_by(models.DailySelection.poem_id)
        .subquery()
    )

    row = db.execute(
        select(models.Poem, models.Author, latest_featured_date_subquery.c.date_featured)
        .join(models.Author, models.Author.id == models.Poem.author_id)
        .join(latest_featured_date_subquery, latest_featured_date_subquery.c.poem_id == models.Poem.id, isouter=True)
        .where(models.Poem.id == poem_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Poem not found")

    poem, author, date_featured = row
    return {
        "poem": {
            "id": poem.id,
            "title": poem.title,
            "text": poem.text,
            "linecount": poem.linecount,
        },
        "author": {
            "id": author.id,
            "name": author.name,
            "bio": author.bio or "",
            "image_url": author.image_url,
        },
        "date_featured": (
            date_featured.isoformat()
            if date_featured is not None and hasattr(date_featured, "isoformat")
            else (str(date_featured) if date_featured is not None else None)
        ),
    }


def fetch_poets_payload(db: Session) -> dict:
    rows = db.execute(select(models.Author).order_by(models.Author.name)).scalars().all()
    poets = [
        {
            "id": author.id,
            "name": author.name,
            "bio": author.bio,
            "image_url": author.image_url,
        }
        for author in rows
    ]
    return {"poets": poets}


def fetch_archive_payload(db: Session, *, limit: int = 365) -> dict:
    stmt = (
        select(models.DailySelection, models.Poem, models.Author)
        .join(models.Poem, models.Poem.id == models.DailySelection.poem_id)
        .join(models.Author, models.Author.id == models.Poem.author_id)
        .order_by(models.DailySelection.date.desc())
        .limit(limit)
    )
    rows = db.execute(stmt).all()

    poems: list[dict] = []
    for daily, poem, author in rows:
        poems.append(
            {
                "date_featured": daily.date.isoformat() if hasattr(daily.date, "isoformat") else str(daily.date),
                "poem_id": poem.id,
                "title": poem.title,
                "author": author.name,
            }
        )
    return {"poems": poems}


def fetch_user_favourites(db: Session, user: models.User) -> list[dict]:
    date_subquery = (
        select(models.DailySelection.poem_id, func.max(models.DailySelection.date).label("date_featured"))
        .group_by(models.DailySelection.poem_id)
        .subquery()
    )

    stmt = (
        select(models.Poem, models.Author, date_subquery.c.date_featured)
        .join(models.Favourite, models.Favourite.poem_id == models.Poem.id)
        .join(models.Author, models.Author.id == models.Poem.author_id)
        .join(date_subquery, date_subquery.c.poem_id == models.Poem.id, isouter=True)
        .where(models.Favourite.user_id == user.id)
        .order_by(models.Favourite.created_at.desc())
    )

    rows = db.execute(stmt).all()
    favourites: list[dict] = []
    for poem, author, date_featured in rows:
        favourites.append(
            {
                "poem_id": poem.id,
                "title": poem.title,
                "author": author.name,
                "date_featured": (
                    date_featured.isoformat()
                    if date_featured is not None and hasattr(date_featured, "isoformat")
                    else (str(date_featured) if date_featured is not None else None)
                ),
                "poem_text": poem.text,
            }
        )
    return favourites


def create_favourite(db: Session, user: models.User, poem_id: str) -> None:
    poem = db.execute(select(models.Poem).where(models.Poem.id == poem_id)).scalar_one_or_none()
    if poem is None:
        raise HTTPException(status_code=404, detail="Poem not found")

    existing = db.execute(
        select(models.Favourite).where(models.Favourite.user_id == user.id, models.Favourite.poem_id == poem_id)
    ).scalar_one_or_none()
    if existing is not None:
        return

    favourite = models.Favourite(
        id=str(uuid4()),
        user_id=user.id,
        poem_id=poem_id,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(favourite)
    db.commit()


def delete_favourite(db: Session, user: models.User, poem_id: str) -> None:
    existing = db.execute(
        select(models.Favourite).where(models.Favourite.user_id == user.id, models.Favourite.poem_id == poem_id)
    ).scalar_one_or_none()
    if existing is None:
        return

    db.delete(existing)
    db.commit()


def get_notification_preference(db: Session, user: models.User) -> dict:
    preference = db.execute(
        select(models.NotificationPreference).where(models.NotificationPreference.user_id == user.id)
    ).scalar_one_or_none()
    if preference is None:
        return {"enabled": False, "time_zone": "UTC", "local_hour": 9}

    return {
        "enabled": bool(preference.enabled),
        "time_zone": preference.time_zone,
        "local_hour": preference.local_hour,
    }


def upsert_notification_preference(
    db: Session,
    user: models.User,
    *,
    enabled: bool,
    time_zone: str,
    local_hour: int,
) -> dict:
    try:
        ZoneInfo(time_zone)
    except Exception as exc:  # pragma: no cover - runtime zone DB variations
        raise HTTPException(status_code=400, detail=f"Invalid time zone: {time_zone}") from exc

    preference = db.execute(
        select(models.NotificationPreference).where(models.NotificationPreference.user_id == user.id)
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if preference is None:
        preference = models.NotificationPreference(
            user_id=user.id,
            enabled=enabled,
            time_zone=time_zone,
            local_hour=local_hour,
            updated_at=now,
        )
        db.add(preference)
    else:
        preference.enabled = enabled
        preference.time_zone = time_zone
        preference.local_hour = local_hour
        preference.updated_at = now

    db.commit()
    return {
        "enabled": bool(preference.enabled),
        "time_zone": preference.time_zone,
        "local_hour": preference.local_hour,
    }


def upsert_push_subscription(
    db: Session,
    user: models.User,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
) -> str:
    existing = db.execute(select(models.PushSubscription).where(models.PushSubscription.endpoint == endpoint)).scalar_one_or_none()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    if existing is None:
        created = models.PushSubscription(
            id=str(uuid4()),
            user_id=user.id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(created)
        db.commit()
        return created.id

    existing.user_id = user.id
    existing.p256dh = p256dh
    existing.auth = auth
    existing.active = True
    existing.updated_at = now
    db.commit()
    return existing.id


def delete_push_subscription(db: Session, user: models.User, *, endpoint: str) -> None:
    existing = db.execute(
        select(models.PushSubscription).where(
            models.PushSubscription.user_id == user.id,
            models.PushSubscription.endpoint == endpoint,
        )
    ).scalar_one_or_none()
    if existing is None:
        return

    db.delete(existing)
    db.commit()
