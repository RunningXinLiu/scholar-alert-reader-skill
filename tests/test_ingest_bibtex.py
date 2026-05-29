from __future__ import annotations

import unittest
from pathlib import Path

from scholar_alert_reader import core
from scholar_alert_reader.ingest import bibtex


class IngestBibtexTests(unittest.TestCase):
    @staticmethod
    def _bibtex_path() -> Path:
        return (
            Path(__file__).resolve().parents[1]
            / "scholar_alert_reader"
            / "resources"
            / "examples"
            / "sample_import.bib"
        )

    def test_parse_bibtex_entries(self) -> None:
        text = self._bibtex_path().read_text(encoding="utf-8")
        entries = bibtex.parse_bibtex_entries(text)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["_type"], "article")
        self.assertEqual(entries[1]["_key"], "demo2025receiver")

    def test_parse_bibtex_source(self) -> None:
        papers, counts = bibtex.parse_bibtex_source(
            self._bibtex_path(),
            paper_factory=lambda **kwargs: core.Paper(**kwargs),
        )
        self.assertEqual(counts["bibliography_files"], 1)
        self.assertEqual(counts["bibliography_entries"], 2)
        self.assertEqual(counts["bibliography_unique_papers"], 2)
        self.assertEqual(len(papers), 2)
        titles = sorted(paper.title for paper in papers)
        self.assertEqual(
            titles,
            [
                "Ambient noise tomography of the Taiwan crust",
                "Receiver functions across the Tibetan Plateau",
            ],
        )

    def test_paper_from_bibtex_entry(self) -> None:
        text = self._bibtex_path().read_text(encoding="utf-8")
        entry = bibtex.parse_bibtex_entries(text)[1]
        paper = bibtex.paper_from_bibtex_entry(
            entry,
            self._bibtex_path(),
            paper_factory=lambda **kwargs: core.Paper(**kwargs),
        )
        self.assertIsNotNone(paper)
        assert paper is not None
        self.assertEqual(paper.title, "Receiver functions across the Tibetan Plateau")
        self.assertIn("BibTeX import", paper.alerts)


if __name__ == "__main__":
    unittest.main()
