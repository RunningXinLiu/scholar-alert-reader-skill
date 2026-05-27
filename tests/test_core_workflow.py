from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scholar_alert_reader import __version__
from scholar_alert_reader import core
from scholar_alert_reader.enrich import title_similarity
from scholar_alert_reader.export import export_records
from scholar_alert_reader.weekly import render_weekly_review


def sample_paper() -> dict:
    return {
        "id": "p1",
        "title": "Ambient noise tomography of the Taiwan crust",
        "authors_source": "A Researcher, B Researcher - Journal, 2026",
        "snippet": "We present ambient noise tomography for crustal structure.",
        "url": "https://example.org/p1",
        "scholar_url": "https://scholar.google.com/p1",
        "first_seen": "2026-05-27",
        "last_seen": "2026-05-27",
        "alerts": ["seismic tomography"],
        "occurrences": 1,
        "score": 30,
        "tier": "Must read",
        "matched_terms": ["ambient noise", "tomography", "Taiwan"],
        "tags": ["method", "region"],
        "reasons": ["Synthetic test"],
        "metadata": {
            "openalex": {
                "publication_year": 2026,
                "cited_by_count": 3,
                "source": "Journal",
                "authors": ["A Researcher", "B Researcher"],
            },
            "crossref": {"doi": "10.0000/test"},
        },
        "is_new": True,
    }


class CoreWorkflowTests(unittest.TestCase):
    def test_version_is_set(self) -> None:
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+")

    def test_init_project_creates_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "reader"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "init-project",
                    "--project-dir",
                    str(project),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Project initialized", result.stdout)
            self.assertTrue((project / "profiles" / "research_profile.json").exists())
            self.assertTrue((project / "examples" / "sample_scholar_alerts.mbox").exists())
            self.assertTrue((project / "examples" / "sample_import.bib").exists())
            self.assertTrue((project / "examples" / "sample_import.ris").exists())
            self.assertTrue((project / "demo_reader.sh").exists())
            self.assertTrue((project / "source_check.sh").exists())
            self.assertTrue((project / "run_reader.sh").exists())
            self.assertTrue((project / "bibtex_import.sh").exists())
            self.assertTrue((project / "ris_import.sh").exists())
            self.assertTrue((project / "doctor_reader.sh").exists())
            self.assertTrue((project / "guide_reader.sh").exists())
            self.assertTrue((project / "compare_papers.sh").exists())
            self.assertTrue((project / "obsidian_export.sh").exists())
            self.assertTrue((project / "START_HERE.md").exists())
            self.assertIn("Product Modes", (project / "START_HERE.md").read_text(encoding="utf-8"))
            subprocess.run(
                [str(project / "demo_reader.sh")],
                cwd=project,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertTrue((project / "reader_out" / "demo" / "digest.html").exists())
            self.assertTrue((project / "reader_out" / "demo" / "papers.json").exists())
            source_check = subprocess.run(
                [str(project / "source_check.sh"), "--source", "mbox", "--mbox-path", str(project / "examples" / "sample_scholar_alerts.mbox"), "--live"],
                cwd=project,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("mbox parse", source_check.stdout)

    def test_bibtex_source_runs_full_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile.json"
            profile.write_text((ROOT / "examples" / "research_profile.example.json").read_text(), encoding="utf-8")
            bib = root / "papers.bib"
            bib.write_text(
                """
@article{liu2026ambient,
  title = {Ambient noise tomography of the Taiwan crust},
  author = {Xin Liu and A Researcher},
  journal = {Journal of Geophysics},
  year = {2026},
  doi = {10.0000/taiwan-noise},
  url = {https://example.org/taiwan-noise},
  abstract = {We present ambient noise tomography for Taiwan crustal structure.},
  keywords = {ambient noise; tomography; Taiwan}
}
""".strip(),
                encoding="utf-8",
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "run",
                    "--source-bibtex",
                    str(bib),
                    "--profile",
                    str(profile),
                    "--out-dir",
                    str(root / "out"),
                    "--kb-dir",
                    str(root / "kb"),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            papers = json.loads((root / "out" / "papers.json").read_text(encoding="utf-8"))
            self.assertEqual(len(papers), 1)
            self.assertEqual(papers[0]["title"], "Ambient noise tomography of the Taiwan crust")
            self.assertEqual(papers[0]["metadata"]["bibtex"]["doi"], "10.0000/taiwan-noise")
            self.assertTrue((root / "out" / "digest.html").exists())

    def test_ris_source_runs_full_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile.json"
            profile.write_text((ROOT / "examples" / "research_profile.example.json").read_text(), encoding="utf-8")
            ris = root / "papers.ris"
            ris.write_text(
                """
TY  - JOUR
TI  - Receiver functions across the Tibetan Plateau
AU  - Xin Liu
AU  - B Researcher
JO  - Earth Structure Letters
PY  - 2026
DO  - 10.0000/tibet-rf
UR  - https://example.org/tibet-rf
AB  - We use receiver functions to image crustal structure beneath Tibet.
KW  - receiver function
KW  - Tibet
ER  -
""".strip(),
                encoding="utf-8",
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "run",
                    "--source-ris",
                    str(ris),
                    "--profile",
                    str(profile),
                    "--out-dir",
                    str(root / "out"),
                    "--kb-dir",
                    str(root / "kb"),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            papers = json.loads((root / "out" / "papers.json").read_text(encoding="utf-8"))
            self.assertEqual(len(papers), 1)
            self.assertEqual(papers[0]["title"], "Receiver functions across the Tibetan Plateau")
            self.assertEqual(papers[0]["metadata"]["ris"]["doi"], "10.0000/tibet-rf")
            self.assertTrue((root / "out" / "digest.html").exists())

    def test_feedback_updates_knowledge_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile.json"
            profile.write_text((ROOT / "examples" / "research_profile.example.json").read_text(), encoding="utf-8")
            papers_json = root / "papers.json"
            papers_json.write_text(json.dumps([sample_paper()]), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "feedback",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(root / "kb"),
                    "--papers-json",
                    str(papers_json),
                    "--paper-id",
                    "p1",
                    "--mark",
                    "interested",
                    "--more-like-this",
                    "--no-profile-update",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Feedback updated", result.stdout)
            self.assertTrue((root / "kb" / "library.json").exists())
            self.assertTrue((root / "kb" / "papers" / "p1.md").exists())

    def test_export_and_weekly_renderers(self) -> None:
        records = [sample_paper()]
        bibtex = export_records(records, "bibtex")
        ris = export_records(records, "ris")
        weekly = render_weekly_review(records, {"name": "test profile"}, days=30)
        self.assertIn("@article", bibtex)
        self.assertIn("doi = {10.0000/test}", bibtex)
        self.assertIn("TY  - JOUR", ris)
        self.assertIn("Weekly Literature Review", weekly)

    def test_title_similarity(self) -> None:
        self.assertGreater(
            title_similarity(
                "Ambient noise tomography of the Taiwan crust",
                "Ambient noise tomography in Taiwan crustal structure",
            ),
            0.35,
        )
        self.assertLess(title_similarity("ambient noise tomography", "deep learning for images"), 0.2)

    def test_doctor_command_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile.json"
            profile.write_text((ROOT / "examples" / "research_profile.example.json").read_text(), encoding="utf-8")
            report = root / "doctor.md"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "doctor",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(root / "kb"),
                    "--output",
                    str(report),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Scholar Alert Reader Doctor", report.read_text(encoding="utf-8"))

    def test_guide_command_writes_product_setup_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profiles" / "research_profile.json"
            profile.parent.mkdir(parents=True)
            profile.write_text((ROOT / "examples" / "research_profile.example.json").read_text(), encoding="utf-8")
            guide = root / "START_HERE.md"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "guide",
                    "--project-dir",
                    str(root),
                    "--output",
                    str(guide),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            content = guide.read_text(encoding="utf-8")
            self.assertIn("Product Modes", content)
            self.assertIn("Codex-only", content)
            self.assertIn("Optional Integrations", content)

    def test_copilot_commands_write_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile.json"
            profile.write_text((ROOT / "examples" / "research_profile.example.json").read_text(), encoding="utf-8")
            kb = root / "kb"
            kb.mkdir()
            library = kb / "library.json"
            library.write_text(json.dumps([sample_paper()]), encoding="utf-8")

            deep = root / "deep.md"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "deep-read",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--paper-id",
                    "p1",
                    "--output",
                    str(deep),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Deep Read", deep.read_text(encoding="utf-8"))

            answer = root / "answer.md"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "ask",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--question",
                    "Taiwan ambient noise tomography",
                    "--output",
                    str(answer),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Most Relevant Papers", answer.read_text(encoding="utf-8"))

            advice = root / "advice.md"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "advice",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--output",
                    str(advice),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Research Advice", advice.read_text(encoding="utf-8"))

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "status",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--paper-id",
                    "p1",
                    "--status",
                    "reading",
                    "--label",
                    "must-cite",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("reading", (kb / "reading_status.md").read_text(encoding="utf-8"))

            comparison = root / "compare.md"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "compare",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--paper-id",
                    "p1",
                    "--output",
                    str(comparison),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Paper Comparison", comparison.read_text(encoding="utf-8"))

            research_map = root / "map.md"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "map",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--output",
                    str(research_map),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Research Map", research_map.read_text(encoding="utf-8"))

            zotero_dir = root / "zotero"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "zotero",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--output-dir",
                    str(zotero_dir),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertTrue((zotero_dir / "scholar_alert_reader.bib").exists())
            self.assertTrue((zotero_dir / "scholar_alert_reader.ris").exists())

            obsidian_dir = root / "obsidian"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "obsidian",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--vault-dir",
                    str(obsidian_dir),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertTrue((obsidian_dir / "00_Dashboard" / "Scholar Alert Dashboard.md").exists())
            self.assertTrue((obsidian_dir / "01_Papers").exists())
            self.assertTrue((obsidian_dir / "02_Maps" / "Research Map.md").exists())
            self.assertTrue((obsidian_dir / "03_Reading" / "Reading Status.md").exists())
            self.assertTrue((obsidian_dir / "04_Answers").exists())
            self.assertTrue((obsidian_dir / "05_Comparisons").exists())
            self.assertTrue((obsidian_dir / "06_Deep_Reads").exists())
            paper_note = next((obsidian_dir / "01_Papers").glob("*.md"))
            note = paper_note.read_text(encoding="utf-8")
            self.assertIn("citation_key:", note)
            self.assertIn('doi: "10.0000/test"', note)


if __name__ == "__main__":
    unittest.main()
