from __future__ import annotations

import unittest

from scholar_alert_reader import core
from scholar_alert_reader.ranking import format as ranking_format
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

    def test_focus_terms_map_to_topical_relevance(self) -> None:
        paper = mk_paper(id="f1", title="Surface-wave anisotropy in brittle crust", snippet="")
        profile = {"focus_terms": [{"term": "anisotropy", "weight": 4}], "tier_thresholds": {"must_read": 8, "skim": 3}}
        result = scorer.score_paper(paper, profile, None, None, [])
        self.assertIn("topical_relevance", [c.name for c in result.components])
        self.assertTrue(any(c.name == "topical_relevance" and c.value > 0 for c in result.components))

    def test_scoring_reasons_follow_profile_language(self) -> None:
        english_paper = mk_paper(id="lang-en", title="Ambient noise tomography", snippet="")
        english = {"language": "en", "focus_terms": [{"term": "ambient noise", "weight": 4}], "tier_thresholds": {"must_read": 8, "skim": 3}}
        scorer.score_paper(english_paper, english, None, None, [])
        self.assertTrue(any("Title matched" in reason for reason in english_paper.reasons))
        self.assertFalse(any("标题命中" in reason for reason in english_paper.reasons))

        chinese_paper = mk_paper(id="lang-zh", title="Ambient noise tomography", snippet="")
        chinese = {"language": "zh-CN", "focus_terms": [{"term": "ambient noise", "weight": 4}], "tier_thresholds": {"must_read": 8, "skim": 3}}
        scorer.score_paper(chinese_paper, chinese, None, None, [])
        self.assertTrue(any("标题命中" in reason for reason in chinese_paper.reasons))

    def test_methods_map_to_method_relevance(self) -> None:
        paper = mk_paper(id="m1", title="An AI phase picking model for earthquakes", snippet="")
        profile = {"methods": [{"term": "phase picking", "weight": 3}], "tier_thresholds": {"must_read": 8, "skim": 3}}
        result = scorer.score_paper(paper, profile, None, None, [])
        self.assertIn("method_relevance", [c.name for c in result.components])
        self.assertTrue(any(c.name == "method_relevance" and c.value > 0 for c in result.components))

    def test_regions_map_to_domain_relevance(self) -> None:
        paper = mk_paper(id="r1", title="Microseismic survey in Taiwan", snippet="")
        profile = {"regions": [{"term": "Taiwan", "weight": 2}], "tier_thresholds": {"must_read": 8, "skim": 3}}
        result = scorer.score_paper(paper, profile, None, None, [])
        self.assertIn("domain_relevance", [c.name for c in result.components])
        self.assertTrue(any(c.name == "domain_relevance" and c.value > 0 for c in result.components))

    def test_semantic_queries_map_to_semantic_similarity(self) -> None:
        paper = mk_paper(id="s1", title="Neural operator for earthquake source inversion", snippet="new framework for crustal imaging")
        profile = {
            "semantic_queries": [{"term": "seismic source inversion", "weight": 5}],
            "tier_thresholds": {"must_read": 8, "skim": 3},
        }
        result = scorer.score_paper(paper, profile, None, None, [])
        self.assertIn("semantic_similarity", [c.name for c in result.components])
        self.assertTrue(any(c.name == "semantic_similarity" and c.value > 0 for c in result.components))

    def test_watch_authors_map_to_authority_signal(self) -> None:
        paper = mk_paper(id="a1", title="General geophysical method", authors_source="Famous Author - Journal - 2026")
        profile = {
            "watch_authors": [{"term": "famous author", "weight": 4}],
            "tier_thresholds": {"must_read": 8, "skim": 3},
        }
        result = scorer.score_paper(paper, profile, None, None, [])
        self.assertIn("authority_signal", [c.name for c in result.components])

    def test_exclude_terms_apply_penalty_component(self) -> None:
        paper = mk_paper(id="x1", title="A benchmark paper on reservoir data", snippet="")
        profile = {
            "focus_terms": [{"term": "reservoir", "weight": 5}],
            "exclude_terms": [{"term": "benchmark", "weight": 2}],
            "tier_thresholds": {"must_read": 8, "skim": 3},
        }
        result = scorer.score_paper(paper, profile, None, None, [])
        self.assertIn("exclusion_penalty", [c.name for c in result.components])
        self.assertLess(sum(c.value for c in result.components if c.name == "exclusion_penalty"), 0)

    def test_feedback_interested_retains_as_skim_without_priority_override(self) -> None:
        paper = mk_paper(id="f2", title="Sparse monitoring of crust", snippet="")
        feedback = {"papers": {"f2": {"status": "interested"}}, "terms": [], "version": 1}
        result = scorer.score_paper(paper, {}, None, feedback, [])
        self.assertEqual(paper.tier, "Skim")
        self.assertIn("feedback_similarity", [c.name for c in result.components])

    def test_priority_override_forces_must_read(self) -> None:
        paper = mk_paper(id="f2b", title="Sparse monitoring of crust", snippet="")
        feedback = {"papers": {"f2b": {"status": "interested", "priority_override": "must_read"}}, "terms": [], "version": 1}
        result = scorer.score_paper(paper, {}, None, feedback, [])
        self.assertEqual(paper.tier, "Must read")
        self.assertIn("feedback_similarity", [c.name for c in result.components])

    def test_feedback_archive_forces_archive(self) -> None:
        paper = mk_paper(id="f3", title="Interesting paper", snippet="")
        feedback = {"papers": {"f3": {"status": "archive"}}, "terms": [], "version": 1}
        result = scorer.score_paper(paper, {"focus_terms": [{"term": "paper", "weight": 99}], "tier_thresholds": {"must_read": 8, "skim": 3}}, None, feedback, [])
        self.assertEqual(paper.tier, "Archive")
        self.assertIn("feedback_similarity", [c.name for c in result.components])

    def test_more_like_this_and_less_like_this_feedback_signals(self) -> None:
        paper = mk_paper(id="f4", title="Robust ambient noise workflow", snippet="")
        feedback = {
            "papers": {
                "f4": {
                    "status": "interested",
                    "signals": {"more_like_this": True, "less_like_this": False},
                }
            },
            "terms": [],
            "version": 1,
        }
        result = scorer.score_paper(paper, {}, None, feedback, [])
        self.assertEqual(paper.tier, "Skim")
        component_names = {c.name for c in result.components}
        self.assertIn("feedback_similarity", component_names)
        self.assertTrue(
            any(c.name == "feedback_similarity" and c.value > 0 for c in result.components),
            "positive feedback signal should be reflected in feedback_similarity",
        )

    def test_adaptive_positive_and_negative_seed_scores_affect_feedback_similarity(self) -> None:
        profile = {"adaptive_ranking": {"enabled": True, "positive_weight": 5, "negative_weight": 5, "min_overlap": 2, "max_seed_papers": 5}}
        seed_positive = mk_paper(
            id="seed-p",
            title="Sparse ambient noise tomography",
            snippet="surface-wave tomography ambient noise",
            authors_source="Expert A",
        )
        seed_negative = mk_paper(
            id="seed-n",
            title="Synthetic benchmark dataset",
            snippet="machine learning benchmark",
            authors_source="Expert B",
        )
        target = mk_paper(id="target", title="Ambient noise tomography of crustal structure", snippet="surface wave inversion")
        feedback = {
            "papers": {
                "seed-p": {"status": "interested"},
                "seed-n": {"status": "archive", "signals": {"less_like_this": True}},
            },
            "version": 1,
            "terms": [],
        }

        result = scorer.score_paper(target, profile, None, feedback, [seed_positive, seed_negative])
        self.assertIn("feedback_similarity", [c.name for c in result.components])
        self.assertAlmostEqual(
            result.total,
            sum(c.value for c in result.components),
            places=6,
        )

        feedback_delta = sum(c.value for c in result.components if c.name == "feedback_similarity")
        self.assertNotEqual(feedback_delta, 0.0)

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
        profile = {"language": "zh-CN", "adaptive_ranking": {"enabled": True, "min_overlap": 2, "positive_weight": 4, "negative_weight": 5}}
        feedback = {
            "version": 1,
            "updated_at": "2026-01-01T00:00:00",
            "papers": {
                "p4": {"status": "interested", "priority_override": "must_read"},
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

    def test_human_score_component_lines_are_readable_and_show_penalties(self) -> None:
        paper = mk_paper(id="hr1", title="Readable score output")
        paper.score_components = [
            {
                "name": "topical_relevance",
                "value": 5.0,
                "matched_terms": ["ambient noise"],
                "explanation": "Title matched topical query.",
                "evidence_field": "title",
            },
            {
                "name": "exclusion_penalty",
                "value": -2.0,
                "matched_terms": ["benchmark"],
                "explanation": "Excluded benchmark-like wording.",
                "evidence_field": "snippet",
            },
        ]

        lines = ranking_format.human_score_component_lines(paper, include_zero=True)

        topic_line = next((line for line in lines if "Topic fit" in line), "")
        penalty_line = next((line for line in lines if "Exclusion penalty" in line), "")
        self.assertTrue(topic_line, "Expected topical component line in readable output.")
        self.assertTrue(penalty_line, "Expected exclusion component line in readable output.")
        self.assertIn("Topic fit", topic_line)
        self.assertNotIn("topical_relevance", topic_line)
        self.assertIn("ambient noise", topic_line)
        self.assertRegex(topic_line, r"\+\d")
        self.assertIn("Exclusion penalty", penalty_line)
        self.assertNotIn("exclusion_penalty", penalty_line)
        self.assertIn("penalty", penalty_line.lower())
        self.assertIn("benchmark", penalty_line)
        self.assertRegex(penalty_line, r"-\d")


if __name__ == "__main__":
    unittest.main()
