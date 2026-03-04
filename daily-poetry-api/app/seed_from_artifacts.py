"""Seed Daily Poetry API DB from ingestion artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import NAMESPACE_DNS, uuid5

from sqlalchemy import String, cast, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.migrate import run_sql_migrations
from app.models import Author, DailySelection, Poem

EDITORIAL_STATUSES = {"pending", "approved", "rejected"}


def author_id_from_name(name: str) -> str:
    return str(uuid5(NAMESPACE_DNS, f"author:{name.strip().lower()}"))


def poem_id_from_hash(content_hash: str) -> str:
    return str(uuid5(NAMESPACE_DNS, f"poem:{content_hash.strip().lower()}"))


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _upsert_authors(db: Session, author_rows: list[dict], poem_rows: list[dict]) -> dict[str, str]:
    by_name: dict[str, dict] = {}

    for row in poem_rows:
        name = row.get("author")
        if isinstance(name, str) and name.strip():
            by_name.setdefault(
                name.strip(),
                {
                    "name": name.strip(),
                    "image_url": None,
                    "image_source": None,
                    "bio": None,
                    "bio_source": None,
                    "bio_url": None,
                },
            )

    for row in author_rows:
        name = row.get("name")
        if isinstance(name, str) and name.strip():
            by_name[name.strip()] = {
                "name": name.strip(),
                "image_url": row.get("image_url") if isinstance(row.get("image_url"), str) else None,
                "image_source": row.get("image_source") if isinstance(row.get("image_source"), str) else None,
                "bio": row.get("bio") if isinstance(row.get("bio"), str) else None,
                "bio_source": row.get("bio_source") if isinstance(row.get("bio_source"), str) else None,
                "bio_url": row.get("bio_url") if isinstance(row.get("bio_url"), str) else None,
            }

    id_map: dict[str, str] = {}
    for payload in by_name.values():
        name = payload["name"]
        author_id = author_id_from_name(name)
        model = db.execute(select(Author).where(Author.name == name)).scalar_one_or_none()
        if model is None:
            model = db.execute(select(Author).where(Author.id == author_id)).scalar_one_or_none()

        if model is None:
            db.add(
                Author(
                    id=author_id,
                    name=name,
                    bio=payload["bio"],
                    image_url=payload["image_url"],
                )
            )
            id_map[name] = author_id
        else:
            model.name = name
            model.bio = payload["bio"]
            model.image_url = payload["image_url"]
            id_map[name] = model.id

    db.commit()
    return id_map


def _upsert_poems(
    db: Session, poem_rows: list[dict], author_ids: dict[str, str], *, new_poem_status: str = "pending"
) -> list[str]:
    if new_poem_status not in EDITORIAL_STATUSES:
        raise ValueError(f"Unsupported editorial status: {new_poem_status}")

    poem_ids: list[str] = []
    for row in poem_rows:
        title = row.get("title")
        author = row.get("author")
        text = row.get("text")
        linecount = row.get("linecount")
        content_hash = row.get("content_hash")

        if not all(isinstance(v, str) and v.strip() for v in [title, author, text, content_hash]):
            continue
        if not isinstance(linecount, int):
            continue

        author_id = author_ids.get(author.strip())
        if author_id is None:
            continue

        poem_id = poem_id_from_hash(content_hash)
        poem_ids.append(poem_id)

        model = db.execute(select(Poem).where(Poem.id == poem_id)).scalar_one_or_none()
        if model is None:
            db.add(
                Poem(
                    id=poem_id,
                    title=title.strip(),
                    text=text,
                    linecount=linecount,
                    editorial_status=new_poem_status,
                    author_id=author_id,
                )
            )
        else:
            model.title = title.strip()
            model.text = text
            model.linecount = linecount
            model.author_id = author_id

    db.commit()
    return sorted(set(poem_ids))


def _seed_daily_selection(db: Session, poem_ids: list[str], start_date: date, days: int) -> int:
    if not poem_ids or days <= 0:
        return 0

    created = 0
    offset = start_date.toordinal()
    for i in range(days):
        current_date = start_date.fromordinal(offset + i)
        poem_id = poem_ids[(offset + i) % len(poem_ids)]

        model = db.execute(
            select(DailySelection).where(cast(DailySelection.date, String) == current_date.isoformat())
        ).scalar_one_or_none()
        if model is None:
            db.add(DailySelection(date=current_date, poem_id=poem_id))
            created += 1
        else:
            model.poem_id = poem_id

    db.commit()
    return created


def _fetch_approved_poem_ids(db: Session) -> list[str]:
    rows = db.execute(select(Poem.id).where(Poem.editorial_status == "approved").order_by(Poem.id.asc())).all()
    return [row[0] for row in rows]


def seed_from_artifacts(
    artifacts_dir: Path,
    schedule_days: int,
    schedule_start: date | None = None,
    *,
    new_poem_status: str = "pending",
    require_approved_for_schedule: bool = True,
    db_engine: Engine = engine,
    session_factory: Callable[[], Session] = SessionLocal,
) -> dict:
    run_sql_migrations(db_engine)

    authors_path = artifacts_dir / "authors.jsonl"
    poems_path = artifacts_dir / "poems.jsonl"

    author_rows = _read_jsonl(authors_path)
    poem_rows = _read_jsonl(poems_path)

    with session_factory() as db:
        author_ids = _upsert_authors(db, author_rows, poem_rows)
        poem_ids = _upsert_poems(db, poem_rows, author_ids, new_poem_status=new_poem_status)
        start = schedule_start or datetime.now(timezone.utc).date()
        approved_poem_ids = _fetch_approved_poem_ids(db)
        if schedule_days > 0 and require_approved_for_schedule and not approved_poem_ids:
            raise ValueError("No approved poems available for scheduling. Approve poems before creating schedule.")
        scheduled = _seed_daily_selection(db, approved_poem_ids, start, schedule_days)

    return {
        "authors": len(author_ids),
        "poems": len(poem_ids),
        "approved_poems": len(approved_poem_ids),
        "scheduled_days": scheduled,
        "start_date": (schedule_start or datetime.now(timezone.utc).date()).isoformat(),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed Daily Poetry API from ingestion artifacts")
    parser.add_argument("--artifacts-dir", type=Path, default=Path("../artifacts/ingestion"))
    parser.add_argument("--schedule-days", type=int, default=365)
    parser.add_argument("--schedule-start", type=str, default=None, help="YYYY-MM-DD (UTC)")
    parser.add_argument(
        "--new-poem-status",
        type=str,
        choices=sorted(EDITORIAL_STATUSES),
        default="pending",
        help="Editorial status to assign when inserting new poems.",
    )
    parser.add_argument(
        "--allow-empty-approved-schedule",
        action="store_true",
        help="Do not fail when there are no approved poems for scheduling.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    schedule_start = date.fromisoformat(args.schedule_start) if args.schedule_start else None
    summary = seed_from_artifacts(
        args.artifacts_dir,
        args.schedule_days,
        schedule_start,
        new_poem_status=args.new_poem_status,
        require_approved_for_schedule=not args.allow_empty_approved_schedule,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
