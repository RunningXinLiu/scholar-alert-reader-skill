from __future__ import annotations

import unittest

from scholar_alert_reader.copilot import render_obsidian_paper
from scholar_alert_reader.export import render_bibtex, render_markdown, render_ris
from scholar_alert_reader.export_filters import public_export_keywords, public_export_tags, public_export_terms


def record() -> dict:
    return {
        "id": "p1",
        "title": "Seismic foundation model paper",
        "authors_source": "A Researcher - Journal, 2026",
        "snippet": "A useful paper.",
        "url": "https://example.org/p1",
        "score": 30,
        "tier": "Must read",
        "matched_terms": [
            "seismic foundation model",
            "similar:Old positive seed",
            "dissimilar:Old negative seed",
            "user:seismic",
            "user:-noise",
        ],
        "tags": ["foundation-model", "feedback", "semantic", "watchlist"],
        "metadata": {},
    }


class UserFacingExportTests(unittest.TestCase):
    def test_public_export_terms_hide_internal_feedback_signals(self) -> None:
        self.assertEqual(
            public_export_terms(record()["matched_terms"] + record()["tags"]),
            ["seismic foundation model", "foundation-model", "feedback", "semantic", "watchlist"],
        )
        self.assertEqual(public_export_tags(record()["tags"]), ["foundation-model"])
        self.assertEqual(
            public_export_keywords(record()["matched_terms"], record()["tags"]),
            ["seismic foundation model", "foundation-model"],
        )

    def test_zotero_exports_do_not_emit_internal_feedback_keywords(self) -> None:
        bib = render_bibtex([record()])
        ris = render_ris([record()])
        for content in [bib, ris]:
            self.assertIn("seismic foundation model", content)
            self.assertIn("foundation-model", content)
            self.assertNotIn("feedback", content)
            self.assertNotIn("semantic", content)
            self.assertNotIn("watchlist", content)
            self.assertNotIn("similar:", content)
            self.assertNotIn("dissimilar:", content)
            self.assertNotIn("user:", content)
            self.assertNotIn("user:-", content)

    def test_markdown_export_hides_internal_feedback_terms(self) -> None:
        markdown = render_markdown([record()])
        self.assertIn("Matched: seismic foundation model", markdown)
        self.assertNotIn("similar:", markdown)
        self.assertNotIn("dissimilar:", markdown)
        self.assertNotIn("user:", markdown)

    def test_obsidian_paper_frontmatter_hides_internal_matched_terms(self) -> None:
        note = render_obsidian_paper(record(), feedback=None, citation_key="paper2026", obsidian_import="clean")
        self.assertIn('matched_terms: ["seismic foundation model"]', note)
        self.assertIn('tags: ["foundation-model"]', note)
        self.assertNotIn('"feedback"', note)
        self.assertNotIn('"semantic"', note)
        self.assertNotIn('"watchlist"', note)
        self.assertNotIn("similar:", note)
        self.assertNotIn("dissimilar:", note)
        self.assertNotIn("user:", note)
        self.assertNotIn("[[", note)


if __name__ == "__main__":
    unittest.main()
