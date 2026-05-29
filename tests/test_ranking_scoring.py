from __future__ import annotations

import unittest

from scholar_alert_reader import core
from scholar_alert_reader.ranking import scorer


def mk_paper(**kwargs: object) -> core.Paper:
    defaults = {
        "id": "paper-1",
        "title": "",
        "authors_source": "",
        "snippet": "",
        "url": "https://example.org/paper",
        "scholar_url": "https://scholar.google.com/paper",
        "first_seen": "2026-01-01",
        "last_seen": "2026-01-01",
        "alerts": ["demo"],
        "occurrences": 1,
    }
    defaults.update(kwargs)
    return core.Paper(**defaults)  # type: ignore[arg-type]


class RankingScoringTests(unittest.TestCase):
    def test_score_breakdown_matches_legacy_score(self) -> None:
        paper = mk_paper(
            id="p1",
            title="Ambient noise tomography for Taiwan crust",
            authors_source="A Researcher",
            snippet="We test ambient noise and surface-wave tomography.",
            occurrences=2,
        )
        profile = {
            "focus_terms": [{"term": "ambient noise", "weight": 4}],
            "methods": [{"term": "tomography", "weight": 3}],
            "regions": [{"term": "Taiwan", "weight": 2}],
            "watch_authors": [{"term": "A Researcher", "weight": 5}],
            "tier_thresholds": {"must_read": 8, "skim": 3},
        }

        result = scorer.score_paper(paper, profile, None, None, [])

        self.assertEqual(result.total, paper.score)
        self.assertEqual(result.total, paper.score)
        self.assertIn("topical_relevance", {c.name for c in result.components})
        self.assertIn("method_relevance", {c.name for c in result.components})
        self.assertIn("authority_signal", {c.name for c in result.components})
        self.assertIn("novelty_signal", {c.name for c in result.components})
        self.assertAlmostEqual(result.total, sum(c.value for c in result.components), places=6)

    def test_exclude_term_creates_penalty(self) -> None:
        paper = mk_paper(
            id="p2",
            title="A dataset paper on microseism",
            snippet="This dataset includes many test cases.",
            occurrences=1,
            authors_source="",
        )
        profile = {
            "focus_terms": [{"term": "fault", "weight": 2}],
            "exclude_terms": [{"term": "dataset", "weight": 3}],
            "tier_thresholds": {"must_read": 8, "skim": 3},
        }

        result = scorer.score_paper(paper, profile, None, None, [])

        self.assertLess(sum(c.value for c in result.components if c.name == "exclusion_penalty"), 0)
        self.assertLessEqual(paper.score, 0)
        self.assertEqual(paper.tier, "Archive")

    def test_runtime_boost_is_applied_as_topical_relevance(self) -> None:
        paper = mk_paper(id="p3", title="Phase picking for induced seismicity")
        result = scorer.score_paper(paper, {}, "phase picking", None, [])

        self.assertEqual(result.total, paper.score)
        self.assertIn("topical_relevance", {c.name for c in result.components})
        self.assertGreater(paper.score, 0)
        self.assertEqual(paper.tier, "Must read")

    def test_feedback_and_adaptive_signals_are_reflected_in_score(self) -> None:
        paper = mk_paper(id="p4", title="Ambient noise for crustal model")
        profile = {"adaptive_ranking": {"enabled": True, "min_overlap": 2, "positive_weight": 4, "negative_weight": 5}}
        feedback = {
            "version": 1,
            "updated_at": "2026-01-01T00:00:00",
            "papers": {
                "p4": {"status": "interested"},
                "seed": {
                    "status": "interested",
                    "title": "Ambient noise deep array",
                    "note": "good signal example",
                },
            },
            "terms": [],
        }
        seed = mk_paper(
            id="seed",
            title="Ambient noise deep array",
            snippet="dense array",
            authors_source="B Researcher",
            alerts=["seed"],
            tier="Must read",
        )

        result = scorer.score_paper(paper, profile, None, feedback, [seed])

        self.assertEqual(result.total, paper.score)
        self.assertEqual(paper.tier, "Must read")
        self.assertIn("feedback_similarity", {c.name for c in result.components})
        self.assertTrue(any("反馈相似度加权" in reason for reason in result.reasons))


if __name__ == "__main__":
    unittest.main()
