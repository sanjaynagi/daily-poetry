"""Author image enrichment utilities.

This module resolves image and bio metadata for authors via Wikipedia APIs and
produces nullable author metadata records for ingestion artifacts.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AuthorImageRecord:
    """Represents author metadata for a single author."""

    name: str
    image_url: str | None
    image_source: str | None
    bio: str | None = None
    bio_source: str | None = None
    bio_url: str | None = None


def _fetch_json(url: str, timeout_seconds: float) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "daily-poetry-ingest/0.1"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_with_retry(url: str, timeout_seconds: float, retries: int, backoff_seconds: float) -> Any:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return _fetch_json(url, timeout_seconds)
        except Exception as exc:  # pragma: no cover - network variability
            last_error = exc
            if attempt < retries:
                time.sleep(backoff_seconds * (2**attempt))
    assert last_error is not None
    raise last_error


def _extract_thumbnail(page: dict) -> str | None:
    thumbnail = page.get("thumbnail")
    if isinstance(thumbnail, dict):
        source = thumbnail.get("source")
        if isinstance(source, str) and source.strip():
            return source.strip()

    original = page.get("original")
    if isinstance(original, dict):
        source = original.get("source")
        if isinstance(source, str) and source.strip():
            return source.strip()

    return None


def _normalize_bio_text(raw_text: str, max_chars: int) -> str | None:
    cleaned = " ".join(raw_text.split())
    if not cleaned:
        return None
    if max_chars <= 0 or len(cleaned) <= max_chars:
        return cleaned
    truncated = cleaned[:max_chars].rstrip()
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    return truncated.rstrip(" ,;:.") + "..."


def _build_wikipedia_page_url(title: str) -> str:
    normalized = title.strip().replace(" ", "_")
    return "https://en.wikipedia.org/wiki/" + urllib.parse.quote(normalized, safe="()'/_-")


def resolve_author_image(
    author: str,
    timeout_seconds: float,
    retries: int,
    backoff_seconds: float,
    *,
    enrich_bio: bool = True,
    bio_max_chars: int = 0,
) -> AuthorImageRecord:
    """Resolve author image and optional bio metadata from Wikipedia."""

    encoded = urllib.parse.quote(author, safe="")
    endpoint = (
        "https://en.wikipedia.org/w/api.php"
        "?action=query&prop=pageimages|extracts&format=json&redirects=1"
        f"&piprop=thumbnail|original&pithumbsize=600&exintro=1&explaintext=1&titles={encoded}"
    )

    try:
        payload = _fetch_with_retry(endpoint, timeout_seconds, retries, backoff_seconds)
    except Exception:
        return AuthorImageRecord(name=author, image_url=None, image_source=None)

    query = payload.get("query") if isinstance(payload, dict) else None
    pages = query.get("pages") if isinstance(query, dict) else None
    if not isinstance(pages, dict):
        return AuthorImageRecord(name=author, image_url=None, image_source=None)

    for page in pages.values():
        if not isinstance(page, dict):
            continue
        image_url = _extract_thumbnail(page)
        image_source = "wikipedia" if image_url else None

        bio: str | None = None
        bio_source: str | None = None
        bio_url: str | None = None
        if enrich_bio:
            extract = page.get("extract")
            if isinstance(extract, str):
                bio = _normalize_bio_text(extract, bio_max_chars)
                if bio:
                    bio_source = "wikipedia"
                    title = page.get("title")
                    if isinstance(title, str) and title.strip():
                        bio_url = _build_wikipedia_page_url(title)
                    else:
                        bio_url = _build_wikipedia_page_url(author)

        if image_url or bio:
            return AuthorImageRecord(
                name=author,
                image_url=image_url,
                image_source=image_source,
                bio=bio,
                bio_source=bio_source,
                bio_url=bio_url,
            )

    return AuthorImageRecord(
        name=author,
        image_url=None,
        image_source=None,
        bio=None,
        bio_source=None,
        bio_url=None,
    )


def enrich_authors(
    authors: list[str],
    timeout_seconds: float,
    retries: int,
    backoff_seconds: float,
    rate_limit_rps: float,
    *,
    enrich_bios: bool = True,
    bio_max_chars: int = 0,
) -> tuple[list[dict], list[dict]]:
    """Enrich a sorted list of unique authors with nullable metadata.

    Returns records and non-fatal errors.
    """

    records: list[dict] = []
    errors: list[dict] = []
    delay = 1.0 / rate_limit_rps if rate_limit_rps > 0 else 0.0

    for author in authors:
        try:
            record = resolve_author_image(
                author,
                timeout_seconds,
                retries,
                backoff_seconds,
                enrich_bio=enrich_bios,
                bio_max_chars=bio_max_chars,
            )
            records.append(
                {
                    "name": record.name,
                    "image_url": record.image_url,
                    "image_source": record.image_source,
                    "bio": record.bio,
                    "bio_source": record.bio_source,
                    "bio_url": record.bio_url,
                }
            )
        except Exception as exc:  # pragma: no cover - defensive catch
            records.append(
                {
                    "name": author,
                    "image_url": None,
                    "image_source": None,
                    "bio": None,
                    "bio_source": None,
                    "bio_url": None,
                }
            )
            errors.append({"kind": "author_image_error", "author": author, "reason": str(exc)})

        if delay > 0:
            time.sleep(delay)

    records.sort(key=lambda item: item["name"])
    return records, errors
