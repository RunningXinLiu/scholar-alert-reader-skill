from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scholar_alert_reader.duplicates import find_duplicate_candidates, render_duplicate_report


class DuplicateReportTests(unittest.TestCase):
    def test_candidates_use_fuzzy_title_year_and_first_author_evidence(self) -> None:
        records = [
            {
                "paper_id": "scholar-1",
                "title": "Ambient Noise Tomography of the Taiwan Crust",
                "year": 2024,
                "authors": ["Jane Doe", "A. Researcher"],
                "source_types": ["scholar_alert"],
            },
            {
                "paper_id": "zotero-1",
                "title": "Imaging Taiwan crustal structure with ambient-noise tomography",
                "year": "2025",
                "metadata": {"zotero": {"authors": ["Doe, Jane", "Researcher, A."]}},
                "source_types": ["zotero"],
            },
            {
                "paper_id": "zotero-old",
                "title": "Ambient noise tomography of the Taiwan crust",
                "year": 2017,
                "authors": ["Jane Doe"],
                "source_types": ["zotero"],
            },
            {
                "paper_id": "already-unified",
                "title": "Ambient noise tomography of the Taiwan crust",
                "year": 2024,
                "authors": ["Jane Doe"],
                "source_types": ["scholar_alert", "zotero"],
            },
        ]

        candidates = find_duplicate_candidates(records, title_threshold=0.70, year_tolerance=2)

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate["left"]["id"], "scholar-1")
        self.assertEqual(candidate["right"]["id"], "zotero-1")
        self.assertTrue(candidate["evidence"]["first_author_match"])
        self.assertEqual(candidate["evidence"]["year_difference"], 1)
        self.assertIn(candidate["confidence"], {"high", "medium"})
        self.assertEqual(candidate["review_status"], "unreviewed")
        self.assertIsNone(candidate["review_decision"])

    def test_exact_doi_is_strong_evidence_but_never_an_auto_merge(self) -> None:
        records = [
            {
                "paper_id": "s1",
                "title": "Crustal imaging using dense arrays",
                "year": 2023,
                "authors_source": "Li Wang, A Researcher - Journal, 2023",
                "doi": "https://doi.org/10.1234/EXAMPLE",
                "source_types": ["scholar_alert"],
            },
            {
                "paper_id": "z1",
                "title": "Crustal imaging with a dense array",
                "year": 2023,
                "authors": ["Wang, Li"],
                "metadata": {"zotero": {"doi": "10.1234/example"}},
                "source_types": ["zotero"],
            },
        ]

        candidates = find_duplicate_candidates(records, title_threshold=0.60)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["confidence"], "high")
        self.assertTrue(candidates[0]["evidence"]["doi_match"])
        self.assertEqual(candidates[0]["suggested_action"], "manual_review")
        report = render_duplicate_report(candidates, universe_path=Path("paper_universe.jsonl"), total_records=2)
        self.assertIn("does not merge or modify", report)
        self.assertIn("same-work", report)
        self.assertIn("10.1234/example", report)

    def test_cli_writes_review_artifacts_without_modifying_universe(self) -> None:
        records = [
            {
                "paper_id": "s1",
                "title": "Distributed acoustic sensing for earthquake monitoring",
                "year": 2025,
                "authors": ["A. Smith"],
                "source_types": ["scholar_alert"],
            },
            {
                "paper_id": "z1",
                "title": "Distributed acoustic sensing in earthquake monitoring",
                "year": 2025,
                "authors": ["Smith, A."],
                "source_types": ["zotero"],
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kb_dir = root / "knowledge_base"
            kb_dir.mkdir()
            universe = kb_dir / "paper_universe.jsonl"
            original = "".join(json.dumps(record, sort_keys=True) + "\n" for record in records)
            universe.write_text(original, encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "duplicate-report",
                    "--kb-dir",
                    str(kb_dir),
                    "--title-threshold",
                    "0.65",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            self.assertIn("Duplicate candidates: 1", result.stdout)
            self.assertEqual(universe.read_text(encoding="utf-8"), original)
            report = kb_dir / "graph" / "fuzzy_duplicate_report.md"
            worksheet = kb_dir / "graph" / "fuzzy_duplicate_candidates.jsonl"
            self.assertTrue(report.exists())
            self.assertTrue(worksheet.exists())
            candidate = json.loads(worksheet.read_text(encoding="utf-8").strip())
            self.assertEqual(candidate["review_status"], "unreviewed")
            self.assertEqual(candidate["suggested_action"], "manual_review")

            candidate["review_status"] = "reviewed"
            candidate["review_decision"] = "same-work"
            candidate["review_notes"] = "Verified against the DOI landing page."
            worksheet.write_text(json.dumps(candidate, sort_keys=True) + "\n", encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "duplicate-report",
                    "--kb-dir",
                    str(kb_dir),
                    "--title-threshold",
                    "0.65",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            refreshed = json.loads(worksheet.read_text(encoding="utf-8").strip())
            self.assertEqual(refreshed["review_status"], "reviewed")
            self.assertEqual(refreshed["review_decision"], "same-work")
            self.assertEqual(refreshed["review_notes"], "Verified against the DOI landing page.")
            self.assertIn("same-work", report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
