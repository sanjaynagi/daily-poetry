from __future__ import annotations

from datetime import date
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_editorial_list_and_status_update(tmp_path) -> None:
    from app.editorial_cli import auto_reject_long_poems, fetch_random_poem, list_poems, set_editorial_status
    from app.migrate import run_sql_migrations
    from app.models import Author, DailySelection, Favourite, Poem, User

    db_path = tmp_path / "editorial.db"
    test_engine = create_engine(f"sqlite:///{db_path}", future=True, connect_args={"check_same_thread": False})
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine, future=True)
    run_sql_migrations(test_engine)

    author_id = str(uuid4())
    poem_id = str(uuid4())

    with TestSession() as session:
        session.query(Favourite).delete()
        session.query(DailySelection).delete()
        session.query(Poem).delete()
        session.query(Author).delete()
        session.query(User).delete()
        session.add(Author(id=author_id, name="Percy Bysshe Shelley", bio="", image_url=None))
        session.add(
            Poem(
                id=poem_id,
                title="Ozymandias",
                text="I met a traveller from an antique land",
                linecount=1,
                editorial_status="pending",
                author_id=author_id,
            )
        )
        session.add(DailySelection(date=date(2026, 2, 20), poem_id=poem_id))
        session.commit()

    with TestSession() as session:
        pending_rows, pending_total = list_poems(session, status="pending", limit=20, offset=0)
        assert pending_total == 1
        assert pending_rows[0].poem_id == poem_id
        random_pending = fetch_random_poem(session, status="pending")
        assert random_pending is not None
        assert random_pending.poem_id == poem_id

        updated = set_editorial_status(session, poem_id, "approved")
        assert updated is True

        approved_rows, approved_total = list_poems(session, status="approved", limit=20, offset=0)
        assert approved_total == 1
        assert approved_rows[0].poem_id == poem_id
        random_pending_after = fetch_random_poem(session, status="pending")
        assert random_pending_after is None

        long_poem_id = str(uuid4())
        session.add(
            Poem(
                id=long_poem_id,
                title="Long Poem",
                text="x",
                linecount=51,
                editorial_status="pending",
                author_id=author_id,
            )
        )
        session.commit()

        rejected_count = auto_reject_long_poems(session, max_lines=50, status="pending")
        assert rejected_count == 1

        rejected_rows, rejected_total = list_poems(session, status="rejected", limit=50, offset=0)
        assert rejected_total == 1
        assert rejected_rows[0].poem_id == long_poem_id
