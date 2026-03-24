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

_LLM_MODEL_DEFAULT = "claude-haiku-4-5-20251001"
_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_API_VERSION = "2023-06-01"


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


def _is_disambiguation_page(page: dict) -> bool:
    """Return True if the Wikipedia page is a disambiguation page."""
    return "disambiguation" in page.get("pageprops", {})


def _extract_page_metadata(
    page: dict,
    author: str,
    *,
    enrich_bio: bool,
    bio_max_chars: int,
) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    """Extract (image_url, image_source, bio, bio_source, bio_url) from a Wikipedia page dict."""
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

    return image_url, image_source, bio, bio_source, bio_url


def _call_llm_for_disambiguation(
    *,
    author: str,
    extract: str,
    api_key: str,
    model: str,
    timeout_seconds: float,
    retries: int,
    backoff_seconds: float,
) -> str | None:
    """Ask an LLM to identify the correct Wikipedia page title from a disambiguation page.

    Parameters
    ----------
    author : str
        The author name that triggered the disambiguation page.
    extract : str
        The full text of the disambiguation page extract.
    api_key : str
        Anthropic API key.
    model : str
        Anthropic model ID to use.
    timeout_seconds : float
        Request timeout.
    retries : int
        Number of retry attempts on failure.
    backoff_seconds : float
        Base backoff interval between retries.

    Returns
    -------
    str | None
        The Wikipedia page title for the correct author, or None if uncertain or failed.
    """
    prompt = (
        f'The author "{author}" is a poet. '
        f"A Wikipedia search returned a disambiguation page with these options:\n\n"
        f"{extract}\n\n"
        f'Which of the above refers to the poet "{author}"? '
        f'Reply with ONLY the exact Wikipedia page title from the list, or the word "none" '
        f"if you cannot determine it with confidence."
    )

    body = json.dumps({
        "model": model,
        "max_tokens": 64,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    request = urllib.request.Request(
        _ANTHROPIC_API_URL,
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": _ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        },
        method="POST",
    )

    # Retry loop for transient failures
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except Exception:
            if attempt < retries:
                time.sleep(backoff_seconds * (2**attempt))
    else:
        return None

    content = payload.get("content", [])
    if content and isinstance(content[0], dict):
        text = content[0].get("text", "").strip()
        if text and text.lower() != "none":
            return text

    return None


def _fetch_specific_wikipedia_page(
    author: str,
    title: str,
    timeout_seconds: float,
    retries: int,
    backoff_seconds: float,
    *,
    enrich_bio: bool,
    bio_max_chars: int,
) -> AuthorImageRecord:
    """Fetch a specific Wikipedia page by title and return author metadata.

    Does not follow disambiguation pages to prevent infinite loops.

    Parameters
    ----------
    author : str
        The canonical author name (used for the returned record).
    title : str
        The specific Wikipedia page title to fetch.
    timeout_seconds : float
        Request timeout.
    retries : int
        Retry attempts on failure.
    backoff_seconds : float
        Base backoff interval.
    enrich_bio : bool
        Whether to extract bio text.
    bio_max_chars : int
        Max bio length; 0 means unlimited.

    Returns
    -------
    AuthorImageRecord
        Author metadata, with null fields if the page was not found or still a disambiguation.
    """
    encoded = urllib.parse.quote(title, safe="")
    endpoint = (
        "https://en.wikipedia.org/w/api.php"
        "?action=query&prop=pageimages|extracts|pageprops&format=json&redirects=1"
        f"&piprop=thumbnail|original&pithumbsize=600&exintro=1&explaintext=1&titles={encoded}"
    )

    null_record = AuthorImageRecord(name=author, image_url=None, image_source=None)

    try:
        payload = _fetch_with_retry(endpoint, timeout_seconds, retries, backoff_seconds)
    except Exception:
        return null_record

    query = payload.get("query") if isinstance(payload, dict) else None
    pages = query.get("pages") if isinstance(query, dict) else None
    if not isinstance(pages, dict):
        return null_record

    for page in pages.values():
        if not isinstance(page, dict) or _is_disambiguation_page(page):
            continue

        image_url, image_source, bio, bio_source, bio_url = _extract_page_metadata(
            page, author, enrich_bio=enrich_bio, bio_max_chars=bio_max_chars
        )
        if image_url or bio:
            return AuthorImageRecord(
                name=author,
                image_url=image_url,
                image_source=image_source,
                bio=bio,
                bio_source=bio_source,
                bio_url=bio_url,
            )

    return null_record


def resolve_author_image(
    author: str,
    timeout_seconds: float,
    retries: int,
    backoff_seconds: float,
    *,
    enrich_bio: bool = True,
    bio_max_chars: int = 0,
    anthropic_api_key: str | None = None,
    llm_model: str = _LLM_MODEL_DEFAULT,
) -> AuthorImageRecord:
    """Resolve author image and optional bio metadata from Wikipedia.

    Parameters
    ----------
    author : str
        Author name to look up.
    timeout_seconds : float
        Request timeout for Wikipedia and LLM calls.
    retries : int
        Retry attempts on transient failures.
    backoff_seconds : float
        Base backoff interval between retries.
    enrich_bio : bool
        Whether to extract bio text from Wikipedia.
    bio_max_chars : int
        Max bio length; 0 means unlimited.
    anthropic_api_key : str | None
        If set, use Claude to resolve disambiguation pages.
    llm_model : str
        Anthropic model ID for disambiguation resolution.

    Returns
    -------
    AuthorImageRecord
        Author metadata with nullable image and bio fields.
    """
    encoded = urllib.parse.quote(author, safe="")
    endpoint = (
        "https://en.wikipedia.org/w/api.php"
        "?action=query&prop=pageimages|extracts|pageprops&format=json&redirects=1"
        f"&piprop=thumbnail|original&pithumbsize=600&exintro=1&explaintext=1&titles={encoded}"
    )

    null_record = AuthorImageRecord(name=author, image_url=None, image_source=None)

    try:
        payload = _fetch_with_retry(endpoint, timeout_seconds, retries, backoff_seconds)
    except Exception:
        return null_record

    query = payload.get("query") if isinstance(payload, dict) else None
    pages = query.get("pages") if isinstance(query, dict) else None
    if not isinstance(pages, dict):
        return null_record

    for page in pages.values():
        if not isinstance(page, dict):
            continue

        # Resolve disambiguation pages via LLM if available, otherwise skip
        if _is_disambiguation_page(page):
            if anthropic_api_key is None:
                continue
            extract = page.get("extract", "")
            resolved_title = _call_llm_for_disambiguation(
                author=author,
                extract=extract if isinstance(extract, str) else "",
                api_key=anthropic_api_key,
                model=llm_model,
                timeout_seconds=timeout_seconds,
                retries=retries,
                backoff_seconds=backoff_seconds,
            )
            if resolved_title is None:
                continue
            return _fetch_specific_wikipedia_page(
                author,
                resolved_title,
                timeout_seconds,
                retries,
                backoff_seconds,
                enrich_bio=enrich_bio,
                bio_max_chars=bio_max_chars,
            )

        image_url, image_source, bio, bio_source, bio_url = _extract_page_metadata(
            page, author, enrich_bio=enrich_bio, bio_max_chars=bio_max_chars
        )
        if image_url or bio:
            return AuthorImageRecord(
                name=author,
                image_url=image_url,
                image_source=image_source,
                bio=bio,
                bio_source=bio_source,
                bio_url=bio_url,
            )

    return null_record


def enrich_authors(
    authors: list[str],
    timeout_seconds: float,
    retries: int,
    backoff_seconds: float,
    rate_limit_rps: float,
    *,
    enrich_bios: bool = True,
    bio_max_chars: int = 0,
    anthropic_api_key: str | None = None,
    llm_model: str = _LLM_MODEL_DEFAULT,
) -> tuple[list[dict], list[dict]]:
    """Enrich a sorted list of unique authors with nullable metadata.

    Parameters
    ----------
    authors : list[str]
        Sorted list of unique author names.
    timeout_seconds : float
        Request timeout.
    retries : int
        Retry attempts on failure.
    backoff_seconds : float
        Base backoff interval.
    rate_limit_rps : float
        Maximum Wikipedia requests per second.
    enrich_bios : bool
        Whether to fetch bio text.
    bio_max_chars : int
        Max bio length; 0 means unlimited.
    anthropic_api_key : str | None
        If set, use Claude to resolve disambiguation pages.
    llm_model : str
        Anthropic model ID for disambiguation resolution.

    Returns
    -------
    tuple[list[dict], list[dict]]
        Author records and non-fatal errors.
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
                anthropic_api_key=anthropic_api_key,
                llm_model=llm_model,
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
