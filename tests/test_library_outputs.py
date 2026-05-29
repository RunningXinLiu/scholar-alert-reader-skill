from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scholar_alert_reader import core


def _paper(**overrides) -> core.Paper:
    base = {
        "id": "paper-output-1",
        "title": "Output Test Paper",
        "authors_source": "Demo Author - Demo Venue - 2026",
        "snippet": "A paper used to validate standalone library outputs.",
        "url": "https://example.org/output-test-paper",
        "scholar_url": "",
        "first_seen": "2026-05-29",
        "last_seen": "2026-05-29",
        "alerts": ["Scholar alert"],
        "occurrences": 1,
        "score": 19,
        "tier": "Must read",
        "matched_terms": ["induced seismicity", "dense array"],
        "tags": ["induced-seismicity", "dense-array"],
        "reasons": ["Matched high-priority focus terms."],
        "metadata": {},
        "score_components": [
            {
                "name": "topical_relevance",
                "value": 5.0,
                "matched_terms": ["ambient noise"],
                "explanation": "Title and snippet matched topical keyword.",
                "evidence_field": "title",
            },
            {
                "name": "method_relevance",
                "value": 3.0,
                "matched_terms": ["tomography"],
                "explanation": "Method signal matched.",
                "evidence_field": "title",
            },
        ],
        "is_new": True,
    }
    base.update(overrides)
    return core.Paper(**base)


class LibraryOutputTests(unittest.TestCase):
    def test_library_outputs_include_index_html_paper_note_and_search_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kb_dir = Path(tmp) / "knowledge_base"
            kb_dir.mkdir(parents=True, exist_ok=True)

            profile = {"name": "test-profile", "knowledge_base": {}}
            paper = _paper()
            feedback = core.empty_feedback()
            feedback["papers"] = {
                paper.id: {
                    "id": paper.id,
                    "title": paper.title,
                    "url": paper.url,
                    "status": "interested",
                    "reading_status": "reading",
                    "labels": ["must-cite"],
                    "signals": {"more_like_this": True},
                    "note": "Core method for our current project.",
                    "created_at": "2026-05-29T09:00:00",
                    "updated_at": "2026-05-29T09:30:00",
                }
            }

            core.write_kb_index(
                kb_dir,
                [paper],
                profile,
                {
                    "mode": "daily",
                    "state_file": "seen_papers.json",
                    "feedback_file": "feedback.json",
                    "library_papers": 1,
                },
            )
            core.write_kb_paper_pages(kb_dir, [paper], feedback)
            core.write_kb_search_index(kb_dir, [paper], feedback)

            self.assertTrue((kb_dir / "index.md").exists())
            self.assertTrue((kb_dir / "index.html").exists())
            self.assertTrue((kb_dir / "papers" / f"{paper.id}.md").exists())
            self.assertTrue((kb_dir / "search_index.json").exists())

            note_text = (kb_dir / "papers" / f"{paper.id}.md").read_text(encoding="utf-8")
            self.assertTrue(note_text.startswith("---\n"))
            self.assertIn("paper_id:", note_text)
            self.assertIn("score_components:", note_text)
            self.assertIn("topical_relevance", note_text)
            self.assertIn("- Reading status: reading", note_text)
            self.assertIn("- Labels: must-cite", note_text)
            self.assertIn("## Source history", note_text)
            self.assertIn("## Why selected", note_text)

            search_records = json.loads((kb_dir / "search_index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(search_records), 1)
            self.assertEqual(search_records[0]["id"], paper.id)
            self.assertEqual(search_records[0]["feedback_status"], "interested")
            self.assertEqual(search_records[0]["reading_status"], "reading")
            self.assertIn("score_breakdown", search_records[0])
            self.assertIn("topical_relevance", search_records[0]["score_breakdown"])
            self.assertEqual(search_records[0]["score_breakdown"]["topical_relevance"], 5.0)


if __name__ == "__main__":
    unittest.main()
