"""FastAPI app for Daily Poetry backend MVP."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.auth import require_bearer_token
from app.config import get_cors_origins
from app.database import engine, get_db
from app.migrate import run_sql_migrations
from app.schemas import (
    ArchiveResponse,
    AnonymousAuthResponse,
    CreateFavouriteRequest,
    DailyResponse,
    FavouritesResponse,
    NotificationPreferencePayload,
    NotificationPreferenceRequest,
    PoemDetailResponse,
    NotificationSubscriptionResponse,
    PoetsResponse,
    PushSubscriptionDeleteRequest,
    PushSubscriptionRequest,
)
from app.service import (
    create_favourite,
    delete_push_subscription,
    delete_favourite,
    fetch_archive_payload,
    fetch_daily_payload,
    fetch_poem_payload,
    fetch_poets_payload,
    fetch_user_favourites,
    get_or_create_user_by_token,
    get_notification_preference,
    issue_anonymous_token,
    upsert_notification_preference,
    upsert_push_subscription,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    run_sql_migrations(engine)
    yield


app = FastAPI(title="Daily Poetry API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/auth/anonymous", response_model=AnonymousAuthResponse)
def post_anonymous_auth(db: Session = Depends(get_db)) -> dict:
    user, token = issue_anonymous_token(db)
    return {"user_id": user.id, "token": token}


@app.get("/v1/daily", response_model=DailyResponse)
def get_daily(db: Session = Depends(get_db)) -> dict:
    return fetch_daily_payload(db)


@app.get("/v1/poems/{poem_id}", response_model=PoemDetailResponse)
def get_poem(poem_id: str, db: Session = Depends(get_db)) -> dict:
    return fetch_poem_payload(db, poem_id)


@app.get("/v1/poets", response_model=PoetsResponse)
def get_poets(db: Session = Depends(get_db)) -> dict:
    return fetch_poets_payload(db)


@app.get("/v1/archive", response_model=ArchiveResponse)
def get_archive(limit: int = 365, db: Session = Depends(get_db)) -> dict:
    safe_limit = max(1, min(limit, 2000))
    return fetch_archive_payload(db, limit=safe_limit)


@app.get("/v1/me/favourites", response_model=FavouritesResponse)
def get_my_favourites(
    token: str = Depends(require_bearer_token),
    db: Session = Depends(get_db),
) -> dict:
    user = get_or_create_user_by_token(db, token)
    favourites = fetch_user_favourites(db, user)
    return {"favourites": favourites}


@app.post("/v1/me/favourites", status_code=201)
def post_my_favourite(
    payload: CreateFavouriteRequest,
    token: str = Depends(require_bearer_token),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    user = get_or_create_user_by_token(db, token)
    create_favourite(db, user, payload.poem_id)
    return {"status": "ok"}


@app.delete("/v1/me/favourites/{poem_id}", status_code=204)
def delete_my_favourite(
    poem_id: str,
    token: str = Depends(require_bearer_token),
    db: Session = Depends(get_db),
) -> None:
    user = get_or_create_user_by_token(db, token)
    delete_favourite(db, user, poem_id)


@app.get("/v1/me/notifications/preferences", response_model=NotificationPreferencePayload)
def get_my_notification_preferences(
    token: str = Depends(require_bearer_token),
    db: Session = Depends(get_db),
) -> dict:
    user = get_or_create_user_by_token(db, token)
    return get_notification_preference(db, user)


@app.put("/v1/me/notifications/preferences", response_model=NotificationPreferencePayload)
def put_my_notification_preferences(
    payload: NotificationPreferenceRequest,
    token: str = Depends(require_bearer_token),
    db: Session = Depends(get_db),
) -> dict:
    user = get_or_create_user_by_token(db, token)
    return upsert_notification_preference(
        db,
        user,
        enabled=payload.enabled,
        time_zone=payload.time_zone,
        local_hour=payload.local_hour,
    )


@app.post("/v1/me/notifications/subscriptions", response_model=NotificationSubscriptionResponse, status_code=201)
def post_my_notification_subscription(
    payload: PushSubscriptionRequest,
    token: str = Depends(require_bearer_token),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    user = get_or_create_user_by_token(db, token)
    subscription_id = upsert_push_subscription(
        db,
        user,
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
    )
    return {"subscription_id": subscription_id}


@app.delete("/v1/me/notifications/subscriptions", status_code=204)
def delete_my_notification_subscription(
    payload: PushSubscriptionDeleteRequest,
    token: str = Depends(require_bearer_token),
    db: Session = Depends(get_db),
) -> None:
    user = get_or_create_user_by_token(db, token)
    delete_push_subscription(db, user, endpoint=payload.endpoint)
