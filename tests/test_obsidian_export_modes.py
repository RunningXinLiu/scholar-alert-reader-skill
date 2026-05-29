from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path

from scholar_alert_reader import core


ROOT = Path(__file__).resolve().parents[1]


def _record(paper_id: str, title: str, tier: str, score: int) -> dict:
    return {
        "id": paper_id,
        "title": title,
        "authors_source": "A Researcher, B Researcher - Journal, 2026",
        "snippet": "Test record for Obsidian export mode coverage.",
        "url": f"https://example.org/{paper_id}",
        "scholar_url": f"https://scholar.google.com/{paper_id}",
        "first_seen": "2026-05-29",
        "last_seen": "2026-05-29",
        "alerts": ["scholar-alert", "rss"],
        "occurrences": 1,
        "score": score,
        "tier": tier,
        "matched_terms": ["ambient noise", "tomography"],
        "tags": ["obsidian", "triage"],
        "reasons": ["Matched high-priority profile terms."],
        "metadata": {},
        "is_new": True,
    }


class ObsidianExportModeTests(unittest.TestCase):
    def test_clean_mode_exports_selected_notes_only_without_wikilinks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kb_dir = root / "knowledge_base"
            kb_dir.mkdir(parents=True, exist_ok=True)
            profile_path = root / "profile.json"
            profile_path.write_text(
                (ROOT / "examples" / "research_profile.example.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            records = [
                _record("p-must", "Must read tomography paper", "Must read", 26),
                _record("p-skim", "Skim-only baseline paper", "Skim", 14),
                _record("p-interest", "Archive-tier but interested paper", "Archive", 3),
            ]
            (kb_dir / "library.json").write_text(json.dumps(records), encoding="utf-8")

            feedback = core.empty_feedback()
            feedback["papers"] = {
                "p-interest": {
                    "id": "p-interest",
                    "title": "Archive-tier but interested paper",
                    "url": "https://example.org/p-interest",
                    "status": "interested",
                    "reading_status": "reading",
                    "labels": ["must-cite"],
                    "note": "Keep this despite low base score.",
                }
            }
            core.save_feedback(core.default_feedback_file(kb_dir), feedback)

            vault_dir = root / "obsidian"
            legacy_dashboard = vault_dir / "00_Dashboard" / "Scholar Alert Dashboard.md"
            legacy_dashboard.parent.mkdir(parents=True, exist_ok=True)
            legacy_dashboard.write_text("# Old generated dashboard", encoding="utf-8")
            legacy_search = vault_dir / "search_index.json"
            legacy_search.write_text("{}", encoding="utf-8")
            manifest_path = vault_dir / core.OBSIDIAN_FULL_EXPORT_MANIFEST
            manifest_path.write_text(
                json.dumps(
                    {
                        "marker": core.OBSIDIAN_FULL_EXPORT_MARKER,
                        "managed_paths": ["00_Dashboard", "search_index.json"],
                    }
                ),
                encoding="utf-8",
            )

            args = argparse.Namespace(
                profile=profile_path,
                kb_dir=kb_dir,
                feedback_file=None,
                tiers="Must read,Skim",
                limit=0,
                vault_dir=vault_dir,
                obsidian_mode="clean",
                no_prune=False,
            )
            core.obsidian_export_command(args)

            papers_dir = vault_dir / "01_Papers"
            self.assertTrue(papers_dir.exists())
            notes = sorted(papers_dir.glob("*.md"))
            self.assertEqual(len(notes), 2)

            note_texts = [path.read_text(encoding="utf-8") for path in notes]
            combined = "\n\n".join(note_texts)
            self.assertIn('paper_id: "p-must"', combined)
            self.assertIn('paper_id: "p-interest"', combined)
            self.assertNotIn('paper_id: "p-skim"', combined)

            for note_text in note_texts:
                self.assertTrue(note_text.startswith("---\n"))
                self.assertIn("type: paper", note_text)
                self.assertIn("generated: true", note_text)
                self.assertIn("source_tool: scholar-alert-reader", note_text)
                self.assertIn('obsidian_import: "clean"', note_text)
                self.assertIn("tier:", note_text)
                self.assertIn("score:", note_text)
                self.assertIn("reading_status:", note_text)
                self.assertIn("tags:", note_text)
                self.assertIn("source_types:", note_text)
                self.assertNotIn("[[", note_text)

            forbidden = [
                vault_dir / "00_Dashboard" / "Scholar Alert Dashboard.md",
                vault_dir / "02_Maps" / "Research Map.md",
                vault_dir / "03_Reading" / "Reading Status.md",
                vault_dir / "04_Answers" / "Answer Index.md",
                vault_dir / "05_Comparisons" / "Comparison Index.md",
                vault_dir / "06_Deep_Reads" / "Analysis Index.md",
                vault_dir / "DASHBOARD.md",
                vault_dir / "DASHBOARD.html",
                vault_dir / "index.md",
                vault_dir / "index.html",
                vault_dir / "search_index.json",
                vault_dir / "daily_additions.md",
                vault_dir / "weekly_review.md",
                vault_dir / "review_queue.md",
                vault_dir / "reading_plan.md",
            ]
            for path in forbidden:
                self.assertFalse(path.exists(), f"unexpected path in clean export: {path}")

            self.assertFalse((vault_dir / "directions").exists())
            self.assertFalse((vault_dir / "runs").exists())
            self.assertFalse((vault_dir / "answers").exists())
            self.assertFalse((vault_dir / "analysis").exists())
            self.assertFalse((vault_dir / core.OBSIDIAN_FULL_EXPORT_MANIFEST).exists())

            extra_markdown = [
                path for path in vault_dir.rglob("*.md") if papers_dir not in path.parents
            ]
            self.assertEqual(extra_markdown, [])

    def test_clean_mode_no_prune_keeps_existing_full_export_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kb_dir = root / "knowledge_base"
            kb_dir.mkdir(parents=True, exist_ok=True)
            profile_path = root / "profile.json"
            profile_path.write_text(
                (ROOT / "examples" / "research_profile.example.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            records = [
                _record("p-must", "Must read tomography paper", "Must read", 26),
                _record("p-interest", "Interested archival paper", "Archive", 3),
            ]
            (kb_dir / "library.json").write_text(json.dumps(records), encoding="utf-8")
            feedback = core.empty_feedback()
            feedback["papers"] = {
                "p-interest": {
                    "id": "p-interest",
                    "title": "Interested archival paper",
                    "url": "https://example.org/p-interest",
                    "status": "interested",
                }
            }
            core.save_feedback(core.default_feedback_file(kb_dir), feedback)

            vault_dir = root / "obsidian"
            legacy_dashboard = vault_dir / "00_Dashboard" / "Scholar Alert Dashboard.md"
            legacy_dashboard.parent.mkdir(parents=True, exist_ok=True)
            legacy_dashboard.write_text("# Existing generated dashboard", encoding="utf-8")
            manifest_path = vault_dir / core.OBSIDIAN_FULL_EXPORT_MANIFEST
            manifest_path.write_text(
                json.dumps(
                    {
                        "marker": core.OBSIDIAN_FULL_EXPORT_MARKER,
                        "managed_paths": ["00_Dashboard"],
                    }
                ),
                encoding="utf-8",
            )

            args = argparse.Namespace(
                profile=profile_path,
                kb_dir=kb_dir,
                feedback_file=None,
                tiers="Must read,Skim",
                limit=0,
                vault_dir=vault_dir,
                obsidian_mode="clean",
                no_prune=True,
            )
            core.obsidian_export_command(args)

            self.assertTrue(legacy_dashboard.exists())
            self.assertTrue(manifest_path.exists())
            papers_dir = vault_dir / "01_Papers"
            self.assertTrue(papers_dir.exists())
            notes = sorted(papers_dir.glob("*.md"))
            self.assertEqual(len(notes), 2)


if __name__ == "__main__":
    unittest.main()
