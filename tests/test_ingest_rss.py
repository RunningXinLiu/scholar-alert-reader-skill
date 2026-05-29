from __future__ import annotations

import unittest
from pathlib import Path

from scholar_alert_reader import core
from scholar_alert_reader.ingest import rss


class IngestRssTests(unittest.TestCase):
    @staticmethod
    def _feed_path() -> Path:
        return (
            Path(__file__).resolve().parents[1]
            / "scholar_alert_reader"
            / "resources"
            / "examples"
            / "sample_feed.atom"
        )

    @staticmethod
    def _arxiv_feed_path() -> Path:
        return (
            Path(__file__).resolve().parents[1]
            / "scholar_alert_reader"
            / "resources"
            / "examples"
            / "sample_arxiv.atom"
        )

    def test_parse_feed_xml_from_atom_file(self) -> None:
        papers, counts = rss.parse_rss_source(
            self._feed_path(),
            timeout=20,
            limit=0,
            paper_factory=lambda **kwargs: core.Paper(**kwargs),
        )
        self.assertEqual(counts["feed_sources"], 1)
        self.assertEqual(counts["feed_entries"], 2)
        self.assertEqual(counts["feed_unique_papers"], 2)
        self.assertEqual(len(papers), 2)
        titles = sorted(paper.title for paper in papers)
        self.assertEqual(
            titles,
            [
                "Ambient noise tomography of the Taiwan crust",
                "Receiver functions across the Tibetan Plateau",
            ],
        )

    def test_parse_feed_xml_arxiv_metadata(self) -> None:
        papers, counts = rss.parse_rss_source(
            self._arxiv_feed_path(),
            timeout=20,
            limit=0,
            paper_factory=lambda **kwargs: core.Paper(**kwargs),
        )
        self.assertEqual(counts["feed_sources"], 1)
        self.assertEqual(counts["feed_entries"], 1)
        self.assertEqual(counts["feed_unique_papers"], 1)
        self.assertEqual(len(papers), 1)
        paper = papers[0]
        self.assertIn("arxiv", paper.metadata)
        self.assertEqual(
            paper.metadata["arxiv"].get("id"),
            "2605.00001",
        )


if __name__ == "__main__":
    unittest.main()
