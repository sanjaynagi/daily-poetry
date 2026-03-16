"""Pydantic response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PoemPayload(BaseModel):
    id: str
    title: str
    text: str
    linecount: int


class AuthorPayload(BaseModel):
    id: str
    name: str
    bio: str
    image_url: str | None


class DailyResponse(BaseModel):
    date: str
    poem: PoemPayload
    author: AuthorPayload


class PoemDetailResponse(BaseModel):
    poem: PoemPayload
    author: AuthorPayload
    date_featured: str | None


class ArchiveItemResponse(BaseModel):
    date_featured: str
    poem_id: str
    title: str
    author: str


class ArchiveResponse(BaseModel):
    poems: list[ArchiveItemResponse]


class FavouriteItem(BaseModel):
    poem_id: str
    title: str
    author: str
    date_featured: str | None
    poem_text: str | None


class FavouritesResponse(BaseModel):
    favourites: list[FavouriteItem]


class CreateFavouriteRequest(BaseModel):
    poem_id: str


class AnonymousAuthResponse(BaseModel):
    user_id: str
    token: str


class NotificationPreferencePayload(BaseModel):
    enabled: bool
    time_zone: str
    local_hour: int


class NotificationPreferenceRequest(BaseModel):
    enabled: bool
    time_zone: str
    local_hour: int = Field(ge=0, le=23)


class PushSubscriptionKeysRequest(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionRequest(BaseModel):
    endpoint: str
    keys: PushSubscriptionKeysRequest


class PushSubscriptionDeleteRequest(BaseModel):
    endpoint: str


class NotificationSubscriptionResponse(BaseModel):
    subscription_id: str


class PoetItem(BaseModel):
    id: str
    name: str
    bio: str | None
    image_url: str | None


class PoetsResponse(BaseModel):
    poets: list[PoetItem]
