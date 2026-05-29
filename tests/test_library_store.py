from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from scholar_alert_reader import core
from scholar_alert_reader.library import store


def _save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _paper(**overrides) -> core.Paper:
    base = {
        "id": "paper-1",
        "title": "Demo Paper",
        "authors_source": "A. Author - Demo Source - 2026",
        "snippet": "Demo snippet",
        "url": "https://example.org/demo",
        "scholar_url": "",
        "first_seen": "2026-05-29",
        "last_seen": "2026-05-29",
        "alerts": ["Scholar alert"],
        "occurrences": 1,
        "score": 10,
        "tier": "Skim",
        "matched_terms": ["ambient noise"],
        "tags": ["ambient-noise", "adaptive"],
        "reasons": ["Matched focus term ambient noise"],
        "metadata": {},
        "is_new": True,
    }
    base.update(overrides)
    return core.Paper(**base)


class LibraryStoreTests(unittest.TestCase):
    def test_kb_settings_defaults(self) -> None:
        settings = store.kb_settings({})
        self.assertEqual(settings["foundation_tiers"], ["Must read", "Skim"])
        self.assertEqual(settings["interested_tiers"], ["Must read"])
        self.assertEqual(settings["interested_limit"], 50)
        self.assertEqual(settings["foundation_limit_per_direction"], 40)
        self.assertFalse(settings["write_archive_index"])

    def test_paper_directions_filters_internal_tags(self) -> None:
        paper = _paper(tags=["adaptive", "boost", "ambient-noise", "tomography"])
        self.assertEqual(store.paper_directions(paper), ["ambient-noise", "tomography"])
        self.assertEqual(store.paper_directions(_paper(tags=["adaptive"])), ["uncategorized"])

    def test_merge_papers_updates_higher_score_and_unions_lists(self) -> None:
        existing = _paper(
            id="same-id",
            score=9,
            tier="Skim",
            alerts=["alert-a"],
            matched_terms=["term-a"],
            tags=["tag-a"],
            reasons=["reason-a"],
            last_seen="2026-05-20",
            first_seen="2026-05-20",
        )
        incoming = _paper(
            id="same-id",
            title="Updated Title",
            score=20,
            tier="Must read",
            alerts=["alert-b"],
            matched_terms=["term-b"],
            tags=["tag-b"],
            reasons=["reason-b"],
            last_seen="2026-05-29",
            first_seen="2026-05-21",
            snippet="Updated snippet",
        )

        merged = store.merge_papers([existing], [incoming])
        self.assertEqual(len(merged), 1)
        paper = merged[0]
        self.assertEqual(paper.title, "Updated Title")
        self.assertEqual(paper.score, 20)
        self.assertEqual(paper.tier, "Must read")
        self.assertEqual(paper.first_seen, "2026-05-20")
        self.assertEqual(paper.last_seen, "2026-05-29")
        self.assertIn("alert-a", paper.alerts)
        self.assertIn("alert-b", paper.alerts)
        self.assertIn("term-a", paper.matched_terms)
        self.assertIn("term-b", paper.matched_terms)
        self.assertIn("tag-a", paper.tags)
        self.assertIn("tag-b", paper.tags)
        self.assertIn("reason-a", paper.reasons)
        self.assertIn("reason-b", paper.reasons)

    def test_save_and_load_paper_library_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kb_dir = Path(tmp)
            papers = [_paper(id="a"), _paper(id="b", title="Second")]
            store.save_paper_library(kb_dir, papers, _save_json, asdict_fn=asdict)
            loaded = store.load_paper_library(
                kb_dir,
                paper_factory=lambda **kwargs: core.Paper(**kwargs),
                load_json=_load_json,
            )
            self.assertEqual([paper.id for paper in loaded], ["a", "b"])
            self.assertEqual(loaded[1].title, "Second")


if __name__ == "__main__":
    unittest.main()

