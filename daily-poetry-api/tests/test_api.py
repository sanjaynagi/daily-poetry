from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def _configure_database_path() -> Path:
    db_path = Path(__file__).resolve().parent / "test_api.db"
    if db_path.exists():
        db_path.unlink()
    os.environ["DAILY_POETRY_DATABASE_URL"] = f"sqlite:///{db_path}"
    return db_path


def test_api_endpoints() -> None:
    db_path = _configure_database_path()

    from fastapi.testclient import TestClient

    from app.database import SessionLocal, engine
    from app.main import app
    from app.migrate import run_sql_migrations
    from app.models import Author, DailySelection, Poem

    run_sql_migrations(engine)

    today = datetime.now(timezone.utc).date()

    with SessionLocal() as session:
        session.query(DailySelection).filter(DailySelection.date == today).delete()
        session.commit()

        author_name = f"Percy Bysshe Shelley {uuid4()}"
        author = Author(id=str(uuid4()), name=author_name, bio="Romantic poet", image_url=None)
        poem = Poem(
            id=str(uuid4()),
            title="Ozymandias",
            text="I met a traveller from an antique land",
            linecount=1,
            author_id=author.id,
        )
        daily = DailySelection(date=today, poem_id=poem.id)
        session.add_all([author, poem, daily])
        session.commit()
        poem_id = poem.id

    with TestClient(app) as client:
        auth_response = client.post("/v1/auth/anonymous")
        assert auth_response.status_code == 200
        auth_payload = auth_response.json()
        assert "token" in auth_payload
        token_headers = {"Authorization": f"Bearer {auth_payload['token']}"}

        daily_response = client.get("/v1/daily")
        assert daily_response.status_code == 200
        daily_payload = daily_response.json()
        assert daily_payload["date"] == today.isoformat()
        assert daily_payload["poem"]["id"] == poem_id
        assert daily_payload["author"]["name"] == author_name

        poem_response = client.get(f"/v1/poems/{poem_id}")
        assert poem_response.status_code == 200
        poem_payload = poem_response.json()
        assert poem_payload["poem"]["id"] == poem_id
        assert poem_payload["author"]["name"] == author_name
        assert poem_payload["date_featured"] == today.isoformat()

        archive_response = client.get("/v1/archive")
        assert archive_response.status_code == 200
        archive_payload = archive_response.json()
        assert len(archive_payload["poems"]) >= 1
        assert archive_payload["poems"][0]["poem_id"] == poem_id
        assert archive_payload["poems"][0]["date_featured"] == today.isoformat()

        unauthorized = client.get("/v1/me/favourites")
        assert unauthorized.status_code == 401

        favourites_empty = client.get("/v1/me/favourites", headers=token_headers)
        assert favourites_empty.status_code == 200
        assert favourites_empty.json() == {"favourites": []}

        create_response = client.post("/v1/me/favourites", headers=token_headers, json={"poem_id": poem_id})
        assert create_response.status_code == 201

        favourites_after = client.get("/v1/me/favourites", headers=token_headers)
        assert favourites_after.status_code == 200
        payload = favourites_after.json()
        assert len(payload["favourites"]) == 1
        assert payload["favourites"][0]["poem_id"] == poem_id
        assert payload["favourites"][0]["poem_text"] == "I met a traveller from an antique land"

        delete_response = client.delete(f"/v1/me/favourites/{poem_id}", headers=token_headers)
        assert delete_response.status_code == 204

        favourites_after_delete = client.get("/v1/me/favourites", headers=token_headers)
        assert favourites_after_delete.status_code == 200
        assert favourites_after_delete.json() == {"favourites": []}

        pref_initial = client.get("/v1/me/notifications/preferences", headers=token_headers)
        assert pref_initial.status_code == 200
        assert pref_initial.json() == {"enabled": False, "time_zone": "UTC", "local_hour": 9}

        pref_update = client.put(
            "/v1/me/notifications/preferences",
            headers=token_headers,
            json={"enabled": True, "time_zone": "UTC", "local_hour": 8},
        )
        assert pref_update.status_code == 200
        assert pref_update.json() == {"enabled": True, "time_zone": "UTC", "local_hour": 8}

        sub_create = client.post(
            "/v1/me/notifications/subscriptions",
            headers=token_headers,
            json={
                "endpoint": "https://example.test/sub",
                "keys": {"p256dh": "abc", "auth": "xyz"},
            },
        )
        assert sub_create.status_code == 201
        assert "subscription_id" in sub_create.json()

        sub_delete = client.request(
            "DELETE",
            "/v1/me/notifications/subscriptions",
            headers=token_headers,
            json={"endpoint": "https://example.test/sub"},
        )
        assert sub_delete.status_code == 204

    if db_path.exists():
        db_path.unlink()
