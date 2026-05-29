from __future__ import annotations

import unittest
from pathlib import Path

from scholar_alert_reader import core
from scholar_alert_reader.ingest import web


class IngestWebTests(unittest.TestCase):
    @staticmethod
    def _web_article_path() -> Path:
        return (
            Path(__file__).resolve().parents[1]
            / "scholar_alert_reader"
            / "resources"
            / "examples"
            / "sample_web_article.html"
        )

    def test_parse_web_source_from_saved_html(self) -> None:
        papers, counts = web.parse_web_source(
            self._web_article_path(),
            timeout=20,
            limit=0,
            paper_factory=lambda **kwargs: core.Paper(**kwargs),
        )
        self.assertEqual(counts["web_sources"], 1)
        self.assertEqual(counts["web_unique_papers"], 1)
        self.assertEqual(len(papers), 1)
        paper = papers[0]
        self.assertEqual(
            paper.title,
            "Uncertainty-aware dense array monitoring of induced seismicity",
        )
        self.assertIn("induced seismicity", paper.snippet.lower())


if __name__ == "__main__":
    unittest.main()
