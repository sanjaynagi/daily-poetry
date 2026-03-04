"""Multiprocess PoetryDB ingestion pipeline."""

from __future__ import annotations

import json
import multiprocessing as mp
import queue
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any

from daily_poetry_ingest.author_images import enrich_authors
from daily_poetry_ingest.dedupe import dedupe_poems
from daily_poetry_ingest.gutenberg import ingest_gutenberg_candidates, load_catalog_candidates
from daily_poetry_ingest.normalize import NormalizationError, NormalizedPoem, normalize_record


class _ProgressRenderer:
    """Render lightweight progress bars to stderr."""

    def __init__(self) -> None:
        self._is_tty = sys.stderr.isatty()
        self._last_emit = 0.0

    @staticmethod
    def _build_bar(current: int, total: int, width: int = 28) -> str:
        if total <= 0:
            return "[" + ("." * width) + "]"
        ratio = max(0.0, min(1.0, current / total))
        filled = int(round(ratio * width))
        return "[" + ("#" * filled) + ("." * (width - filled)) + "]"

    def render_gutenberg(self, *, processed: int, total: int, force: bool = False) -> None:
        self._render_line(
            message=f"gutenberg extract {self._build_bar(processed, total)} {processed}/{total}",
            force=force,
        )

    def render_poetrydb(
        self,
        *,
        fetch_done: int,
        fetch_total: int,
        normalized_done: int,
        force: bool = False,
    ) -> None:
        fetch_bar = self._build_bar(fetch_done, fetch_total)
        self._render_line(
            message=(
                f"poetrydb fetch {fetch_bar} {fetch_done}/{fetch_total} "
                f"| normalized={normalized_done}"
            ),
            force=force,
        )

    def _render_line(self, *, message: str, force: bool) -> None:
        now = time.monotonic()
        if not force and (now - self._last_emit) < 0.15:
            return
        self._last_emit = now
        if self._is_tty:
            sys.stderr.write("\r" + message)
        else:
            sys.stderr.write(message + "\n")
        sys.stderr.flush()
        if force and self._is_tty:
            sys.stderr.write("\n")
            sys.stderr.flush()


def _fetch_json(url: str, timeout_seconds: float) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "daily-poetry-ingest/0.1"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        data = response.read().decode("utf-8")
        return json.loads(data)


def _fetch_with_retry(url: str, timeout_seconds: float, retries: int, backoff_seconds: float) -> Any:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return _fetch_json(url, timeout_seconds)
        except Exception as exc:  # pragma: no cover - network behavior varies
            last_error = exc
            if attempt < retries:
                time.sleep(backoff_seconds * (2**attempt))
    assert last_error is not None
    raise last_error


def fetch_authors(base_url: str, timeout_seconds: float, retries: int, backoff_seconds: float) -> list[str]:
    payload = _fetch_with_retry(
        f"{base_url}/author", timeout_seconds=timeout_seconds, retries=retries, backoff_seconds=backoff_seconds
    )
    authors = payload.get("authors", []) if isinstance(payload, dict) else []
    return [author for author in authors if isinstance(author, str) and author.strip()]


def _fetch_worker(
    base_url: str,
    author_queue: mp.Queue,
    raw_queue: mp.Queue,
    error_queue: mp.Queue,
    fetch_progress_queue: mp.Queue,
    timeout_seconds: float,
    retries: int,
    backoff_seconds: float,
    rate_limit_rps: float,
) -> None:
    delay = 1.0 / rate_limit_rps if rate_limit_rps > 0 else 0.0
    while True:
        author = author_queue.get()
        if author is None:
            return

        url_author = urllib.parse.quote(author, safe="")
        endpoint = f"{base_url}/author/{url_author}"
        try:
            payload = _fetch_with_retry(endpoint, timeout_seconds, retries, backoff_seconds)
            if isinstance(payload, list):
                for record in payload:
                    if isinstance(record, dict):
                        raw_queue.put(record)
            else:
                error_queue.put({"kind": "fetch_error", "author": author, "reason": "unexpected_payload"})
        except Exception as exc:  # pragma: no cover - network behavior varies
            error_queue.put({"kind": "fetch_error", "author": author, "reason": str(exc)})
        finally:
            fetch_progress_queue.put({"kind": "fetch_done"})

        if delay > 0:
            time.sleep(delay)


def _normalize_worker(raw_queue: mp.Queue, normalized_queue: mp.Queue, error_queue: mp.Queue) -> None:
    while True:
        record = raw_queue.get()
        if record is None:
            normalized_queue.put({"kind": "normalize_worker_done"})
            return

        result = normalize_record(record)
        if isinstance(result, NormalizationError):
            error_queue.put(
                {
                    "kind": "normalize_error",
                    "reason": result.reason,
                    "title": record.get("title"),
                    "author": record.get("author"),
                }
            )
        else:
            normalized_queue.put({"kind": "normalized", "payload": asdict(result)})


def _drain_queue(message_queue: mp.Queue) -> list[dict]:
    items: list[dict] = []
    while True:
        try:
            items.append(message_queue.get_nowait())
        except queue.Empty:
            break
    return items


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _build_report(
    *,
    source: str,
    output_dir: Path,
    canonical: list[dict],
    duplicates: list[dict],
    author_records: list[dict],
    errors: list[dict],
    extra_metrics: dict | None = None,
) -> dict:
    poems_path = output_dir / "poems.jsonl"
    duplicates_path = output_dir / "duplicates.jsonl"
    authors_path = output_dir / "authors.jsonl"
    report_path = output_dir / "report.json"

    _write_jsonl(poems_path, canonical)
    _write_jsonl(duplicates_path, duplicates)
    _write_jsonl(authors_path, author_records)

    report = {
        "source": source,
        "authors_enriched": len(author_records),
        "authors_without_images": sum(1 for record in author_records if record["image_url"] is None),
        "authors_with_bios": sum(
            1 for record in author_records if isinstance(record.get("bio"), str) and record["bio"].strip()
        ),
        "authors_without_bios": sum(
            1
            for record in author_records
            if not (isinstance(record.get("bio"), str) and record["bio"].strip())
        ),
        "canonical_poems": len(canonical),
        "duplicates": len(duplicates),
        "errors": errors,
        "artifacts": {
            "poems": str(poems_path),
            "duplicates": str(duplicates_path),
            "authors": str(authors_path),
            "report": str(report_path),
        },
    }
    if extra_metrics:
        report.update(extra_metrics)

    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")

    return report


def run_poetrydb_ingestion(
    output_dir: Path,
    base_url: str = "https://poetrydb.org",
    fetch_workers: int = 4,
    normalize_workers: int = 4,
    timeout_seconds: float = 20.0,
    retries: int = 3,
    backoff_seconds: float = 0.5,
    rate_limit_rps: float = 2.0,
    enrich_author_bios: bool = True,
    author_bio_max_chars: int = 280,
) -> dict:
    """Run ingestion end-to-end and write artifacts into output_dir."""

    output_dir.mkdir(parents=True, exist_ok=True)

    authors = fetch_authors(base_url, timeout_seconds, retries, backoff_seconds)

    author_queue: mp.Queue = mp.Queue()
    raw_queue: mp.Queue = mp.Queue()
    normalized_queue: mp.Queue = mp.Queue()
    error_queue: mp.Queue = mp.Queue()
    fetch_progress_queue: mp.Queue = mp.Queue()

    for author in authors:
        author_queue.put(author)
    for _ in range(fetch_workers):
        author_queue.put(None)

    fetch_processes = [
        mp.Process(
            target=_fetch_worker,
            args=(
                base_url,
                author_queue,
                raw_queue,
                error_queue,
                fetch_progress_queue,
                timeout_seconds,
                retries,
                backoff_seconds,
                rate_limit_rps,
            ),
        )
        for _ in range(fetch_workers)
    ]
    normalize_processes = [
        mp.Process(target=_normalize_worker, args=(raw_queue, normalized_queue, error_queue))
        for _ in range(normalize_workers)
    ]

    for process in fetch_processes + normalize_processes:
        process.start()

    progress = _ProgressRenderer()
    fetch_done = 0
    normalized_done = 0
    total_authors = len(authors)
    errors: list[dict] = []

    while fetch_done < total_authors:
        for message in _drain_queue(fetch_progress_queue):
            if message.get("kind") == "fetch_done":
                fetch_done += 1
        for error in _drain_queue(error_queue):
            errors.append(error)
        progress.render_poetrydb(fetch_done=fetch_done, fetch_total=total_authors, normalized_done=normalized_done)
        time.sleep(0.02)

    for process in fetch_processes:
        process.join()

    progress.render_poetrydb(fetch_done=fetch_done, fetch_total=total_authors, normalized_done=normalized_done)

    for _ in range(normalize_workers):
        raw_queue.put(None)

    normalized_payloads: list[NormalizedPoem] = []
    done_count = 0
    while done_count < normalize_workers:
        message = normalized_queue.get()
        if message.get("kind") == "normalize_worker_done":
            done_count += 1
        elif message.get("kind") == "normalized":
            payload = message["payload"]
            normalized_payloads.append(NormalizedPoem(**payload))
            normalized_done += 1

        for error in _drain_queue(error_queue):
            errors.append(error)
            if error.get("kind") == "normalize_error":
                normalized_done += 1
        progress.render_poetrydb(fetch_done=fetch_done, fetch_total=total_authors, normalized_done=normalized_done)

    for process in normalize_processes:
        process.join()
    errors.extend(_drain_queue(error_queue))
    progress.render_poetrydb(fetch_done=fetch_done, fetch_total=total_authors, normalized_done=normalized_done, force=True)

    canonical, duplicates = dedupe_poems(normalized_payloads)
    unique_authors = sorted({record["author"] for record in canonical if isinstance(record.get("author"), str)})
    author_records, author_errors = enrich_authors(
        unique_authors,
        timeout_seconds=timeout_seconds,
        retries=retries,
        backoff_seconds=backoff_seconds,
        rate_limit_rps=rate_limit_rps,
        enrich_bios=enrich_author_bios,
        bio_max_chars=author_bio_max_chars,
    )
    errors.extend(author_errors)

    return _build_report(
        source="poetrydb",
        output_dir=output_dir,
        canonical=canonical,
        duplicates=duplicates,
        author_records=author_records,
        errors=errors,
        extra_metrics={
            "base_url": base_url,
            "authors_requested": len(authors),
            "normalized_poems": len(normalized_payloads),
        },
    )


def run_gutenberg_ingestion(
    output_dir: Path,
    *,
    catalog_csv: Path,
    texts_dir: Path,
    language: str = "en",
    max_non_empty_lines: int = 120,
    timeout_seconds: float = 20.0,
    retries: int = 3,
    backoff_seconds: float = 0.5,
    rate_limit_rps: float = 2.0,
    enrich_author_bios: bool = True,
    author_bio_max_chars: int = 280,
) -> dict:
    """Run strict Project Gutenberg ingestion and write standard artifacts."""

    output_dir.mkdir(parents=True, exist_ok=True)

    candidates, metadata_errors = load_catalog_candidates(catalog_csv, language=language)
    progress = _ProgressRenderer()
    total_candidates = len(candidates)

    if total_candidates == 0:
        progress.render_gutenberg(processed=0, total=0, force=True)
        normalized_payloads = []
        extract_errors = []
    else:
        # Run per-candidate to provide progress without introducing third-party deps.
        normalized_payloads = []
        extract_errors = []
        for index, candidate in enumerate(candidates, start=1):
            poems, errors = ingest_gutenberg_candidates(
                [candidate],
                texts_dir=texts_dir,
                max_non_empty_lines=max_non_empty_lines,
            )
            normalized_payloads.extend(poems)
            extract_errors.extend(errors)
            if index < total_candidates:
                progress.render_gutenberg(processed=index, total=total_candidates)
        progress.render_gutenberg(processed=total_candidates, total=total_candidates, force=True)
    canonical, duplicates = dedupe_poems(normalized_payloads)
    unique_authors = sorted({record["author"] for record in canonical if isinstance(record.get("author"), str)})
    author_records, author_errors = enrich_authors(
        unique_authors,
        timeout_seconds=timeout_seconds,
        retries=retries,
        backoff_seconds=backoff_seconds,
        rate_limit_rps=rate_limit_rps,
        enrich_bios=enrich_author_bios,
        bio_max_chars=author_bio_max_chars,
    )
    errors = metadata_errors + extract_errors + author_errors

    return _build_report(
        source="gutenberg",
        output_dir=output_dir,
        canonical=canonical,
        duplicates=duplicates,
        author_records=author_records,
        errors=errors,
        extra_metrics={
            "catalog_csv": str(catalog_csv),
            "texts_dir": str(texts_dir),
            "language": language,
            "max_non_empty_lines": max_non_empty_lines,
            "catalog_candidates": len(candidates),
            "normalized_poems": len(normalized_payloads),
        },
    )


def run_ingestion(
    output_dir: Path,
    base_url: str = "https://poetrydb.org",
    fetch_workers: int = 4,
    normalize_workers: int = 4,
    timeout_seconds: float = 20.0,
    retries: int = 3,
    backoff_seconds: float = 0.5,
    rate_limit_rps: float = 2.0,
    enrich_author_bios: bool = True,
    author_bio_max_chars: int = 280,
) -> dict:
    """Backward-compatible alias for PoetryDB ingestion."""

    return run_poetrydb_ingestion(
        output_dir=output_dir,
        base_url=base_url,
        fetch_workers=fetch_workers,
        normalize_workers=normalize_workers,
        timeout_seconds=timeout_seconds,
        retries=retries,
        backoff_seconds=backoff_seconds,
        rate_limit_rps=rate_limit_rps,
        enrich_author_bios=enrich_author_bios,
        author_bio_max_chars=author_bio_max_chars,
    )


def auto_worker_split(cpu_count: int | None = None) -> tuple[int, int]:
    """Choose fetch/normalize worker counts while using available cores."""

    total = cpu_count or (mp.cpu_count() or 2)
    if total <= 2:
        return 1, 1
    fetch = max(1, total // 2)
    normalize = max(1, total - fetch)
    return fetch, normalize


def print_report(report: dict) -> None:
    """Human-readable summary for CLI usage."""

    lines = ["Ingestion complete", f"source: {report['source']}"]
    for key in (
        "authors_requested",
        "catalog_candidates",
        "authors_enriched",
        "authors_without_images",
        "authors_with_bios",
        "authors_without_bios",
        "normalized_poems",
        "canonical_poems",
        "duplicates",
    ):
        if key in report:
            lines.append(f"{key}: {report[key]}")
    lines.append(f"errors: {len(report['errors'])}")
    sys.stdout.write("\n".join(lines) + "\n")
