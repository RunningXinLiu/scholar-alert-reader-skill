from __future__ import annotations

import unittest
from pathlib import Path

from scholar_alert_reader import core
from scholar_alert_reader.ingest import ris


class IngestRisTests(unittest.TestCase):
    @staticmethod
    def _ris_path() -> Path:
        return (
            Path(__file__).resolve().parents[1]
            / "scholar_alert_reader"
            / "resources"
            / "examples"
            / "sample_import.ris"
        )

    def test_parse_ris_entries(self) -> None:
        text = self._ris_path().read_text(encoding="utf-8")
        entries = ris.parse_ris_entries(text)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["TY"], "JOUR")
        self.assertEqual(entries[1]["TY"], "JOUR")

    def test_parse_ris_source(self) -> None:
        papers, counts = ris.parse_ris_source(
            self._ris_path(),
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

    def test_paper_from_ris_entry(self) -> None:
        text = self._ris_path().read_text(encoding="utf-8")
        entry = ris.parse_ris_entries(text)[1]
        paper = ris.paper_from_ris_entry(
            entry,
            self._ris_path(),
            paper_factory=lambda **kwargs: core.Paper(**kwargs),
        )
        self.assertIsNotNone(paper)
        assert paper is not None
        self.assertEqual(paper.title, "Receiver functions across the Tibetan Plateau")
        self.assertIn("RIS import", paper.alerts)


if __name__ == "__main__":
    unittest.main()
