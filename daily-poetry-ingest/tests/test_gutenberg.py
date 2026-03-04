import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from daily_poetry_ingest.gutenberg import (
    _has_prose_boilerplate,
    _parse_marc_author,
    extract_strict_poem_lines,
    ingest_gutenberg_candidates,
    load_catalog_candidates,
)


_VALID_POEM_TEXT = """*** START OF THE PROJECT GUTENBERG EBOOK 9999 ***
O Captain! My Captain!
by Walt Whitman

O Captain! my Captain! our fearful trip is done,
The ship has weather'd every rack, the prize we sought is won,
The port is near, the bells I hear, the people all exulting,
While follow eyes the steady keel, the vessel grim and daring;

But O heart! heart! heart!
O the bleeding drops of red,
Where on the deck my Captain lies,
Fallen cold and dead.
*** END OF THE PROJECT GUTENBERG EBOOK 9999 ***"""


class GutenbergTests(unittest.TestCase):
    def test_load_catalog_candidates_filters_strictly(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "pg_catalog.csv"
            csv_path.write_text(
                "Text#,Type,Title,Language,Authors,Subjects,Bookshelves,LoCC\n"
                "10,Text,O Captain! My Captain!,en,Walt Whitman,Poetry,Poetry,PS\n"
                "11,Text,Collected Poems,en,Walt Whitman,Poetry,Poetry,PS\n"
                "12,Text,Novel,en,Jane Doe,Fiction,Fiction,PR\n"
                "13,Text,No Author,en,,Poetry,Poetry,PS\n",
                encoding="utf-8",
            )

            candidates, errors = load_catalog_candidates(csv_path, language="en")

        self.assertEqual([candidate.ebook_id for candidate in candidates], [10])
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["kind"], "metadata_error")

    def test_extract_strict_poem_lines_rejects_prose(self) -> None:
        prose = """*** START OF THE PROJECT GUTENBERG EBOOK 1 ***
Chapter 1
This is a very long prose paragraph that keeps going on and on with sentence structure
that is not shaped like poetry and should therefore fail strict extraction checks.

Another very long paragraph continues the prose shape.
*** END OF THE PROJECT GUTENBERG EBOOK 1 ***"""
        self.assertIsNone(extract_strict_poem_lines(prose, "Chapter 1", "Prose Author"))

    def test_ingest_gutenberg_candidates_normalizes_strict_poems(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            texts_dir = Path(tmp_dir) / "texts"
            texts_dir.mkdir(parents=True)
            (texts_dir / "10.txt").write_text(_VALID_POEM_TEXT, encoding="utf-8")

            candidates, _ = load_catalog_candidates(
                _write_catalog(
                    Path(tmp_dir) / "catalog.csv",
                    rows=[
                        "10,Text,O Captain! My Captain!,en,Walt Whitman,Poetry,Poetry,PS",
                    ],
                ),
                language="en",
            )
            poems, errors = ingest_gutenberg_candidates(candidates, texts_dir=texts_dir)

        self.assertEqual(errors, [])
        self.assertEqual(len(poems), 1)
        self.assertEqual(poems[0].title, "O Captain! My Captain!")
        self.assertEqual(poems[0].author, "Walt Whitman")
        self.assertTrue(poems[0].source.startswith("gutenberg:"))

    def test_ingest_gutenberg_candidates_supports_nested_epub_cache_layout(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            cache_root = Path(tmp_dir) / "cache" / "epub" / "10"
            cache_root.mkdir(parents=True)
            (cache_root / "pg10.txt").write_text(_VALID_POEM_TEXT, encoding="utf-8")

            candidates, _ = load_catalog_candidates(
                _write_catalog(
                    Path(tmp_dir) / "catalog.csv",
                    rows=[
                        "10,Text,O Captain! My Captain!,en,Walt Whitman,Poetry,Poetry,PS",
                    ],
                ),
                language="en",
            )
            poems, errors = ingest_gutenberg_candidates(candidates, texts_dir=Path(tmp_dir) / "cache")

        self.assertEqual(errors, [])
        self.assertEqual(len(poems), 1)
        self.assertEqual(poems[0].linecount, 9)

    def test_ingest_gutenberg_candidates_applies_max_non_empty_line_filter(self) -> None:
        body_lines = [f"Soft winds carry bright dawn over quiet fields tonight {idx}." for idx in range(1, 22)]
        body_lines.append("")
        body_lines.extend(f"Soft winds carry bright dawn over quiet fields tonight {idx}." for idx in range(22, 42))
        long_poem = """*** START OF THE PROJECT GUTENBERG EBOOK 10 ***
O Captain! My Captain!
by Walt Whitman

{body}
*** END OF THE PROJECT GUTENBERG EBOOK 10 ***"""
        long_poem = long_poem.format(body="\n".join(body_lines))

        with TemporaryDirectory() as tmp_dir:
            texts_dir = Path(tmp_dir) / "texts"
            texts_dir.mkdir(parents=True)
            (texts_dir / "10.txt").write_text(long_poem, encoding="utf-8")

            candidates, _ = load_catalog_candidates(
                _write_catalog(
                    Path(tmp_dir) / "catalog.csv",
                    rows=[
                        "10,Text,O Captain! My Captain!,en,Walt Whitman,Poetry,Poetry,PS",
                    ],
                ),
                language="en",
            )
            poems_relaxed, errors_relaxed = ingest_gutenberg_candidates(
                candidates,
                texts_dir=texts_dir,
                max_non_empty_lines=120,
            )
            poems_strict, errors_strict = ingest_gutenberg_candidates(
                candidates,
                texts_dir=texts_dir,
                max_non_empty_lines=40,
            )

        self.assertEqual(len(poems_relaxed), 1)
        self.assertEqual(errors_relaxed, [])
        self.assertEqual(poems_strict, [])
        self.assertEqual(len(errors_strict), 1)
        self.assertEqual(errors_strict[0]["kind"], "extract_error")


class MarcAuthorParserTests(unittest.TestCase):
    def test_simple_surname_forename(self) -> None:
        self.assertEqual(_parse_marc_author("Whitman, Walt"), "Walt Whitman")

    def test_strips_dates(self) -> None:
        self.assertEqual(_parse_marc_author("Blake, William, 1757-1827"), "William Blake")

    def test_strips_parens_and_dates(self) -> None:
        self.assertEqual(
            _parse_marc_author("Adams, Franklin P. (Franklin Pierce), 1881-1960"),
            "Franklin P. Adams",
        )

    def test_multi_part_forename(self) -> None:
        self.assertEqual(
            _parse_marc_author("Browning, Elizabeth Barrett, 1806-1861"),
            "Elizabeth Barrett Browning",
        )

    def test_non_marc_name_returned_as_is(self) -> None:
        self.assertEqual(_parse_marc_author("Walt Whitman"), "Walt Whitman")
        self.assertEqual(_parse_marc_author("Anonymous"), "Anonymous")

    def test_editor_role_returns_none(self) -> None:
        self.assertIsNone(_parse_marc_author("Abbot, Anne W. (Anne Wales), 1808-1908 [Editor]"))

    def test_translator_role_returns_none(self) -> None:
        self.assertIsNone(_parse_marc_author("Smith, John, 1800-1860 [Translator]"))

    def test_multi_author_uses_first(self) -> None:
        self.assertEqual(
            _parse_marc_author("Adams, John G. (John Greenleaf), 1810-1887; Chapin, E. H. (Edwin Hubbell), 1814-1880"),
            "John G. Adams",
        )

    def test_name_without_dates(self) -> None:
        self.assertEqual(_parse_marc_author("Carroll, Lewis"), "Lewis Carroll")

    def test_empty_string_returns_none(self) -> None:
        self.assertIsNone(_parse_marc_author(""))


class ProseBoilerplateTests(unittest.TestCase):
    def _lines(self, text: str) -> list[str]:
        return text.splitlines()

    def test_produced_by_marker_detected(self) -> None:
        lines = self._lines(
            "Produced by Mark Meiss from page images\n"
            "and the Online Distributed Proofreading Team.\n"
            "\n"
            "Some poem line here\n"
        )
        self.assertTrue(_has_prose_boilerplate(lines))

    def test_url_marker_detected(self) -> None:
        lines = self._lines("https://www.gutenberg.org/cache/epub/1234/\nSome content\n")
        self.assertTrue(_has_prose_boilerplate(lines))

    def test_prose_paragraph_detected(self) -> None:
        # Five or more consecutive lines averaging well over 9 words (editorial note style)
        lines = self._lines(
            "The pieces gathered into this volume were, with two exceptions, written for the entertainment.\n"
            "The editor would express her thanks to the writers who at her solicitation allowed them.\n"
            "They are published with the hope of aiding a work of charity for poor people here.\n"
            "Permission was graciously extended by the authors for publication in this charitable volume now.\n"
            "All proceeds from the sale of this volume will be devoted to charitable purposes only.\n"
        )
        self.assertTrue(_has_prose_boilerplate(lines))

    def test_clean_poem_not_detected(self) -> None:
        lines = self._lines(
            "O Captain! my Captain! our fearful trip is done,\n"
            "The ship has weather'd every rack, the prize we sought is won,\n"
            "\n"
            "But O heart! heart! heart!\n"
            "O the bleeding drops of red,\n"
        )
        self.assertFalse(_has_prose_boilerplate(lines))


class ProseBoilerplateExtractionTests(unittest.TestCase):
    def test_extract_rejects_front_matter_boilerplate(self) -> None:
        text = (
            "*** START OF THE PROJECT GUTENBERG EBOOK 1 ***\n"
            "My Poem\n"
            "by Some Author\n"
            "\n"
            "Produced by Mark Meiss from page images and corrected digital text\n"
            "generously provided by the Wright American Fiction Project of the Library\n"
            "Electronic Text Service of Indiana University.\n"
            "\n"
            "Note: Images of the original pages are available through this project.\n"
            "\n"
            "AUTUMN LEAVES.\n"
            "Original Pieces in Prose and Verse.\n"
            "Cambridge: John Bartlett. 1853.\n"
            "*** END OF THE PROJECT GUTENBERG EBOOK 1 ***\n"
        )
        self.assertIsNone(extract_strict_poem_lines(text, "My Poem", "Some Author"))


class MarcNameCatalogIntegrationTests(unittest.TestCase):
    def test_marc_names_normalised_in_candidates(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "catalog.csv"
            csv_path.write_text(
                "Text#,Type,Title,Language,Authors,Subjects,Bookshelves,LoCC\n"
                "10,Text,O Captain!,en,\"Whitman, Walt, 1819-1892\",Poetry,Poetry,PS\n"
                "11,Text,The Raven,en,\"Poe, Edgar Allan, 1809-1849\",Poetry,Poetry,PS\n"
                "12,Text,Anthology,en,\"Smith, Jane, 1800-1850 [Editor]\",Poetry,Poetry,PS\n",
                encoding="utf-8",
            )
            candidates, _ = load_catalog_candidates(csv_path, language="en")

        # Editor entry skipped; both poets have natural-order names
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].author, "Walt Whitman")
        self.assertEqual(candidates[1].author, "Edgar Allan Poe")


def _write_catalog(path: Path, *, rows: list[str]) -> Path:
    path.write_text(
        "Text#,Type,Title,Language,Authors,Subjects,Bookshelves,LoCC\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    return path


if __name__ == "__main__":
    unittest.main()
