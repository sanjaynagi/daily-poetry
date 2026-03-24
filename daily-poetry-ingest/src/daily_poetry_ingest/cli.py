"""CLI entrypoint for PoetryDB ingestion."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from daily_poetry_ingest.pipeline import (
    auto_worker_split,
    print_report,
    run_gutenberg_ingestion,
    run_poetrydb_ingestion,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest poems into Daily Poetry JSONL artifacts")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/ingestion"))
    parser.add_argument("--source", choices=["poetrydb", "gutenberg"], default="poetrydb")
    parser.add_argument("--base-url", default="https://poetrydb.org")
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--backoff-seconds", type=float, default=0.5)
    parser.add_argument("--rate-limit-rps", type=float, default=2.0)
    parser.add_argument(
        "--enrich-author-bios",
        dest="enrich_author_bios",
        action="store_true",
        default=True,
        help="Enable author bio enrichment from upstream metadata.",
    )
    parser.add_argument(
        "--no-enrich-author-bios",
        dest="enrich_author_bios",
        action="store_false",
        help="Disable author bio enrichment and emit null bio fields.",
    )
    parser.add_argument(
        "--author-bio-max-chars",
        type=int,
        default=0,
        help="Maximum length for enriched author bios. <=0 keeps full text.",
    )
    parser.add_argument(
        "--llm-disambiguate",
        action="store_true",
        default=False,
        help=(
            "Use an LLM to resolve Wikipedia disambiguation pages. "
            "Requires ANTHROPIC_API_KEY to be set in the environment."
        ),
    )
    parser.add_argument("--fetch-workers", type=int, default=None)
    parser.add_argument("--normalize-workers", type=int, default=None)
    parser.add_argument("--gutenberg-catalog-csv", type=Path, default=None)
    parser.add_argument("--gutenberg-texts-dir", type=Path, default=None)
    parser.add_argument("--gutenberg-language", type=str, default="en")
    parser.add_argument(
        "--gutenberg-max-non-empty-lines",
        type=int,
        default=40,
        help="Maximum non-empty poem lines allowed for strict Gutenberg extraction.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    fetch_workers = args.fetch_workers
    normalize_workers = args.normalize_workers
    if fetch_workers is None or normalize_workers is None:
        auto_fetch, auto_normalize = auto_worker_split()
        fetch_workers = fetch_workers or auto_fetch
        normalize_workers = normalize_workers or auto_normalize

    # Resolve Anthropic API key if LLM disambiguation is requested
    anthropic_api_key: str | None = None
    if args.llm_disambiguate:
        anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip() or None
        if anthropic_api_key is None:
            parser.error("--llm-disambiguate requires ANTHROPIC_API_KEY to be set in the environment")

    if args.source == "poetrydb":
        report = run_poetrydb_ingestion(
            output_dir=args.output_dir,
            base_url=args.base_url,
            fetch_workers=fetch_workers,
            normalize_workers=normalize_workers,
            timeout_seconds=args.timeout_seconds,
            retries=args.retries,
            backoff_seconds=args.backoff_seconds,
            rate_limit_rps=args.rate_limit_rps,
            enrich_author_bios=args.enrich_author_bios,
            author_bio_max_chars=args.author_bio_max_chars,
            anthropic_api_key=anthropic_api_key,
        )
    else:
        if args.gutenberg_catalog_csv is None:
            parser.error("--gutenberg-catalog-csv is required when --source gutenberg")
        if args.gutenberg_texts_dir is None:
            parser.error("--gutenberg-texts-dir is required when --source gutenberg")
        report = run_gutenberg_ingestion(
            output_dir=args.output_dir,
            catalog_csv=args.gutenberg_catalog_csv,
            texts_dir=args.gutenberg_texts_dir,
            language=args.gutenberg_language,
            max_non_empty_lines=args.gutenberg_max_non_empty_lines,
            timeout_seconds=args.timeout_seconds,
            retries=args.retries,
            backoff_seconds=args.backoff_seconds,
            rate_limit_rps=args.rate_limit_rps,
            enrich_author_bios=args.enrich_author_bios,
            author_bio_max_chars=args.author_bio_max_chars,
            anthropic_api_key=anthropic_api_key,
        )
    print_report(report)


if __name__ == "__main__":
    main()
