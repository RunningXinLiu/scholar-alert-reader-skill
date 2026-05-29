from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from scholar_alert_reader import core
from scholar_alert_reader.ingest import arxiv
from scholar_alert_reader.ingest import rss


class IngestArxivTests(unittest.TestCase):
    @staticmethod
    def _arxiv_feed_path() -> Path:
        return (
            Path(__file__).resolve().parents[1]
            / "scholar_alert_reader"
            / "resources"
            / "examples"
            / "sample_arxiv.atom"
        )

    def test_arxiv_api_url(self) -> None:
        url = arxiv.arxiv_api_url("all:seismic tomography", 12)
        parsed = urlparse(url)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "export.arxiv.org")
        self.assertEqual(parsed.path, "/api/query")
        params = parse_qs(parsed.query)
        self.assertEqual(params.get("search_query"), ["all:seismic tomography"])
        self.assertEqual(params.get("max_results"), ["12"])
        self.assertEqual(params.get("sortBy"), ["submittedDate"])
        self.assertEqual(params.get("sortOrder"), ["descending"])

    def test_parse_arxiv_source_uses_rss_parser(self) -> None:
        captured: dict[str, str] = {}
        original_parse_rss_source = rss.parse_rss_source

        def fake_parse_rss_source(
            source: str,
            timeout: int = 20,
            limit: int = 0,
            paper_factory=None,
        ):
            captured["source"] = source
            return original_parse_rss_source(
                self._arxiv_feed_path(),
                timeout=timeout,
                limit=limit,
                paper_factory=paper_factory,
            )

        with patch.object(arxiv.rss, "parse_rss_source", side_effect=fake_parse_rss_source):
            papers, counts = arxiv.parse_arxiv_source(
                "all:foundation model seismology",
                limit=5,
                timeout=20,
                paper_factory=lambda **kwargs: core.Paper(**kwargs),
            )

        self.assertEqual(len(papers), 1)
        self.assertEqual(counts["feed_entries"], 1)
        self.assertEqual(counts["arxiv_query"], "all:foundation model seismology")
        self.assertTrue(counts["arxiv_api_url"].startswith("https://export.arxiv.org/api/query?"))
        self.assertIn("search_query=all%3Afoundation+model+seismology", captured["source"])


if __name__ == "__main__":
    unittest.main()
