from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scholar_alert_reader import __version__
from scholar_alert_reader import core
from scholar_alert_reader.enrich import title_similarity
from scholar_alert_reader.export import export_records
from scholar_alert_reader.semantic import semantic_rerank_records
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

    def test_module_entrypoint_reports_version(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scholar_alert_reader",
                "--version",
            ],
            text=True,
            capture_output=True,
            check=True,
            cwd=ROOT,
        )
        self.assertIn(__version__, result.stdout)

    def test_skill_cli_command_falls_back_to_module_without_source_script(self) -> None:
        original = core.skill_wrapper_path
        try:
            setattr(core, "skill_wrapper_path", lambda: ROOT / "missing" / "scripts" / "scholar_reader.py")
            self.assertEqual(core.skill_cli_command(), [sys.executable, "-m", "scholar_alert_reader"])
        finally:
            setattr(core, "skill_wrapper_path", original)

    def test_profile_template_commands(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "scholar_reader.py"),
                "list-profile-templates",
            ],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("ai-seismology", result.stdout)
        self.assertIn("general-geophysics", result.stdout)
        self.assertIn("Starter source:", result.stdout)
        catalog_json = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "scholar_reader.py"),
                "list-profile-templates",
                "--format",
                "json",
            ],
            text=True,
            capture_output=True,
            check=True,
        )
        catalog = json.loads(catalog_json.stdout)
        by_slug = {item["slug"]: item for item in catalog}
        self.assertIn("starter_sources", by_slug["ai-seismology"])
        self.assertIn("recommended_first_edits", by_slug["seismic-imaging"])

        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "profile.json"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "init-profile",
                    "--profile",
                    str(profile),
                    "--template",
                    "ai-seismology",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            data = json.loads(profile.read_text(encoding="utf-8"))
            self.assertIn("AI seismology", data["name"])
            self.assertEqual(data["profile_meta"]["slug"], "ai-seismology")
            self.assertTrue(any(item["term"] == "seismic foundation model" for item in data["focus_terms"]))

            report = Path(tmp) / "profile_onboarding.md"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "profile-wizard",
                    "--project-dir",
                    str(Path(tmp)),
                    "--profile",
                    str(profile),
                    "--name",
                    "Personal seismic monitoring triage",
                    "--question",
                    "Which dense-array monitoring papers are worth reading?",
                    "--focus",
                    "dense seismic array, continuous waveform",
                    "--method",
                    "phase picking",
                    "--region",
                    "Sichuan Basin",
                    "--semantic-query",
                    "machine learning for dense array earthquake monitoring",
                    "--must-read-limit",
                    "7",
                    "--report",
                    str(report),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            data = json.loads(profile.read_text(encoding="utf-8"))
            self.assertEqual(data["name"], "Personal seismic monitoring triage")
            self.assertEqual(data["limits"]["must_read"], 7)
            self.assertIn("Which dense-array monitoring papers are worth reading?", data["research_questions"])
            self.assertTrue(any(item["term"] == "dense seismic array" and item["weight"] == 7 for item in data["focus_terms"]))
            self.assertTrue(any(item["term"] == "phase picking" for item in data["methods"]))
            self.assertTrue(any(item["term"] == "Sichuan Basin" for item in data["regions"]))
            self.assertTrue(any(item["term"] == "machine learning for dense array earthquake monitoring" for item in data["semantic_queries"]))
            self.assertIn("Research Profile Onboarding", report.read_text(encoding="utf-8"))

            doctor = Path(tmp) / "profile_doctor.md"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "profile-doctor",
                    "--project-dir",
                    str(Path(tmp)),
                    "--profile",
                    str(profile),
                    "--output",
                    str(doctor),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            doctor_content = doctor.read_text(encoding="utf-8")
            self.assertIn("Research Profile Doctor", doctor_content)
            self.assertIn("Recommended Actions", doctor_content)
            self.assertIn("Focus term", doctor_content)

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
            self.assertTrue((project / "profiles" / "templates" / "ai-seismology.json").exists())
            self.assertTrue((project / "profiles" / "templates" / "induced-seismicity.json").exists())
            self.assertTrue((project / "examples" / "sample_scholar_alerts.mbox").exists())
            self.assertTrue((project / "examples" / "sample_import.bib").exists())
            self.assertTrue((project / "examples" / "sample_import.ris").exists())
            self.assertTrue((project / "examples" / "sample_web_article.html").exists())
            self.assertTrue((project / "examples" / "web_sources.example.txt").exists())
            self.assertTrue((project / "examples" / "sample_feed.atom").exists())
            self.assertTrue((project / "examples" / "feeds.example.txt").exists())
            self.assertTrue((project / "demo_reader.sh").exists())
            self.assertTrue((project / "demo_sources.sh").exists())
            self.assertTrue((project / "copy_profile_template.sh").exists())
            self.assertTrue((project / "setup_reader.sh").exists())
            self.assertTrue((project / "setup_wizard.sh").exists())
            self.assertTrue((project / "schedule_reader.sh").exists())
            self.assertTrue((project / "source_check.sh").exists())
            self.assertTrue((project / "self_test.sh").exists())
            self.assertTrue((project / "profile_wizard.sh").exists())
            self.assertTrue((project / "profile_doctor.sh").exists())
            self.assertTrue((project / "run_reader.sh").exists())
            self.assertTrue((project / "bibtex_import.sh").exists())
            self.assertTrue((project / "ris_import.sh").exists())
            self.assertTrue((project / "web_import.sh").exists())
            self.assertTrue((project / "rss_import.sh").exists())
            self.assertTrue((project / "arxiv_search.sh").exists())
            self.assertTrue((project / "doctor_reader.sh").exists())
            self.assertTrue((project / "support_bundle.sh").exists())
            self.assertTrue((project / "privacy_check.sh").exists())
            self.assertTrue((project / "capabilities.sh").exists())
            self.assertTrue((project / "dashboard_reader.sh").exists())
            self.assertTrue((project / "guide_reader.sh").exists())
            self.assertTrue((project / "compare_papers.sh").exists())
            self.assertTrue((project / "obsidian_export.sh").exists())
            self.assertTrue((project / "zotero_sync.sh").exists())
            self.assertTrue((project / "workup_paper.sh").exists())
            self.assertTrue((project / "full_text_paper.sh").exists())
            self.assertTrue((project / "fetch_pdf.sh").exists())
            self.assertTrue((project / "review_paper.sh").exists())
            self.assertTrue((project / "review_workflow.sh").exists())
            self.assertTrue((project / "review_queue.sh").exists())
            self.assertTrue((project / "explain_ranking.sh").exists())
            self.assertTrue((project / "ranking_eval.sh").exists())
            self.assertTrue((project / "embedding_check.sh").exists())
            self.assertTrue((project / "semantic_rerank.sh").exists())
            self.assertTrue((project / "tune_profile.sh").exists())
            self.assertTrue((project / "reading_plan.sh").exists())
            self.assertTrue((project / "START_HERE.md").exists())
            self.assertTrue((project / "TROUBLESHOOTING.md").exists())
            self.assertIn("reader.env", (project / ".gitignore").read_text(encoding="utf-8"))
            self.assertIn("zotero.bib", (project / ".gitignore").read_text(encoding="utf-8"))
            self.assertIn("zotero.ris", (project / ".gitignore").read_text(encoding="utf-8"))
            self.assertIn("*.mbox.partial", (project / ".gitignore").read_text(encoding="utf-8"))
            self.assertIn("*.pdf", (project / ".gitignore").read_text(encoding="utf-8"))
            self.assertIn("web_sources.txt", (project / ".gitignore").read_text(encoding="utf-8"))
            self.assertIn(".self_test/", (project / ".gitignore").read_text(encoding="utf-8"))
            self.assertIn("PRIVACY_CHECK.md", (project / ".gitignore").read_text(encoding="utf-8"))
            self.assertIn("EMBEDDING_CHECK.md", (project / ".gitignore").read_text(encoding="utf-8"))
            self.assertIn("profiles/profile_onboarding.md", (project / ".gitignore").read_text(encoding="utf-8"))
            self.assertIn("profiles/profile_doctor.md", (project / ".gitignore").read_text(encoding="utf-8"))
            start_here = (project / "START_HERE.md").read_text(encoding="utf-8")
            self.assertIn("Product Modes", start_here)
            self.assertIn("Capability boundary", start_here)
            self.assertIn("./capabilities.sh", start_here)
            self.assertIn("./privacy_check.sh", start_here)
            self.assertIn("DASHBOARD.html", start_here)
            self.assertIn("Bundled templates", start_here)
            self.assertIn("./profile_wizard.sh", start_here)
            self.assertIn("./profile_doctor.sh", start_here)
            self.assertIn("./ranking_eval.sh", start_here)
            self.assertIn("./embedding_check.sh", start_here)
            self.assertIn("./semantic_rerank.sh", start_here)
            self.assertIn("./fetch_pdf.sh", start_here)
            subprocess.run(
                [
                    str(project / "setup_reader.sh"),
                    "--source",
                    "rss",
                    "--rss-source",
                    str(project / "examples" / "sample_feed.atom"),
                    "--profile-template",
                    "ai-seismology",
                    "--schedule-time",
                    "10:30",
                    "--schedule-days",
                    "weekdays",
                    "--obsidian-dir",
                    str(project / "obsidian_export"),
                    "--zotero-dir",
                    str(project / "zotero_export"),
                ],
                cwd=project,
                text=True,
                capture_output=True,
                check=True,
            )
            env_content = (project / "reader.env").read_text(encoding="utf-8")
            self.assertIn("export SOURCE=rss", env_content)
            self.assertIn("export SCHEDULE_TIME=10:30", env_content)
            self.assertIn("OBSIDIAN_EXPORT_DIR", env_content)
            schedule_plist = project / "test_schedule.plist"
            subprocess.run(
                [
                    str(project / "schedule_reader.sh"),
                    "--action",
                    "write",
                    "--output",
                    str(schedule_plist),
                ],
                cwd=project,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertTrue(schedule_plist.exists())
            schedule_data = plistlib.loads(schedule_plist.read_bytes())
            resolved_project = project.resolve()
            self.assertEqual(schedule_data["ProgramArguments"], [str(resolved_project / "run_reader.sh")])
            self.assertEqual(schedule_data["WorkingDirectory"], str(resolved_project))
            self.assertEqual(schedule_data["StartCalendarInterval"][0]["Hour"], 10)
            self.assertEqual(schedule_data["StartCalendarInterval"][0]["Minute"], 30)
            self.assertTrue((project / "SCHEDULE.md").exists())
            schedule_report = (project / "SCHEDULE.md").read_text(encoding="utf-8")
            self.assertIn("Scholar Alert Reader Schedule", schedule_report)
            self.assertIn("weekdays", schedule_report)
            dry_run_plist = project / "dry_run_schedule.plist"
            dry_run_report = project / "DRY_RUN_SCHEDULE.md"
            subprocess.run(
                [
                    str(project / "schedule_reader.sh"),
                    "--action",
                    "install",
                    "--dry-run",
                    "--output",
                    str(dry_run_plist),
                    "--report",
                    str(dry_run_report),
                ],
                cwd=project,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertFalse(dry_run_plist.exists())
            self.assertIn("dry-run install", dry_run_report.read_text(encoding="utf-8"))
            start_here = (project / "START_HERE.md").read_text(encoding="utf-8")
            self.assertIn("Persistent Configuration", start_here)
            self.assertIn("SOURCE: `rss`", start_here)
            subprocess.run(
                [str(project / "demo_reader.sh")],
                cwd=project,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertTrue((project / "reader_out" / "demo" / "digest.html").exists())
            self.assertTrue((project / "reader_out" / "demo" / "papers.json").exists())
            demo_summary = json.loads((project / "reader_out" / "demo" / "summary.json").read_text(encoding="utf-8"))
            self.assertIn("sample_scholar_alerts.mbox", demo_summary["source"])
            subprocess.run(
                [str(project / "demo_sources.sh")],
                cwd=project,
                text=True,
                capture_output=True,
                check=True,
            )
            for source_name in ["mbox", "bibtex", "ris", "web", "rss"]:
                self.assertTrue((project / "reader_out" / "demo_sources" / source_name / "digest.html").exists())
                source_summary = json.loads(
                    (project / "reader_out" / "demo_sources" / source_name / "summary.json").read_text(encoding="utf-8")
                )
                self.assertFalse(source_summary["knowledge_base_updated"])
            web_run = subprocess.run(
                [
                    str(project / "web_import.sh"),
                ],
                cwd=project,
                text=True,
                capture_output=True,
                check=True,
                env={**os.environ, "WEB_SOURCE": str(project / "examples" / "sample_web_article.html")},
            )
            self.assertTrue((project / "reader_out" / "web" / "digest.html").exists())
            self.assertIn("Reading plan:", web_run.stdout)
            self.assertIn("Reading plan HTML:", web_run.stdout)
            self.assertTrue((project / "knowledge_base" / "reading_plan.md").exists())
            self.assertTrue((project / "knowledge_base" / "reading_plan.html").exists())
            web_summary = json.loads((project / "reader_out" / "web" / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(Path(web_summary["reading_plan"]).resolve(), (project / "knowledge_base" / "reading_plan.md").resolve())
            self.assertEqual(Path(web_summary["reading_plan_html"]).resolve(), (project / "knowledge_base" / "reading_plan.html").resolve())
            self.assertIn("Reading Plan", (project / "knowledge_base" / "reading_plan.html").read_text(encoding="utf-8"))
            self.assertIn("reading_plan.md", (project / "knowledge_base" / "index.md").read_text(encoding="utf-8"))
            self.assertIn("reading_plan.html", (project / "knowledge_base" / "index.md").read_text(encoding="utf-8"))
            self.assertTrue((project / "DASHBOARD.md").exists())
            self.assertTrue((project / "DASHBOARD.html").exists())
            dashboard = (project / "DASHBOARD.md").read_text(encoding="utf-8")
            self.assertIn("Scholar Alert Reader Dashboard", dashboard)
            self.assertIn("Latest digest HTML", dashboard)
            self.assertIn("Review Workflow", dashboard)
            self.assertIn("Profile Health", dashboard)
            self.assertIn("Privacy check", dashboard)
            self.assertIn("Ranking evaluation", dashboard)
            self.assertIn("Embedding check", dashboard)
            self.assertIn("Semantic rerank report", dashboard)
            self.assertIn("profile_doctor.md", dashboard)
            self.assertIn("sample_web_article.html", dashboard)
            self.assertTrue((project / "profiles" / "profile_doctor.md").exists())
            source_check = subprocess.run(
                [str(project / "source_check.sh"), "--source", "mbox", "--mbox-path", str(project / "examples" / "sample_scholar_alerts.mbox"), "--live"],
                cwd=project,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("mbox parse", source_check.stdout)

            rss_check = subprocess.run(
                [str(project / "source_check.sh"), "--source", "rss", "--rss-source", str(project / "examples" / "sample_feed.atom"), "--live"],
                cwd=project,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("RSS/Atom live read", rss_check.stdout)

            module_fallback = subprocess.run(
                [str(project / "source_check.sh"), "--source", "mbox", "--mbox-path", str(project / "examples" / "sample_scholar_alerts.mbox"), "--live"],
                cwd=project,
                text=True,
                capture_output=True,
                check=True,
                env={**os.environ, "PYTHONPATH": str(ROOT), "SKILL_SCRIPT": str(project / "missing_scholar_reader.py")},
            )
            self.assertIn("mbox parse", module_fallback.stdout)

    def test_privacy_check_flags_private_project_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "reader"
            subprocess.run(
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
            (project / "client_secret_test.json").write_text("{}", encoding="utf-8")
            (project / "INBOX.mbox.partial").write_text("From private@example.org\n", encoding="utf-8")
            (project / "reader.env").write_text("export GMAIL_TOKEN=/tmp/token.json\n", encoding="utf-8")
            (project / "import.bib").write_text("@article{private,title={Private Paper}}\n", encoding="utf-8")
            (project / "paper.pdf").write_bytes(b"%PDF-1.4\n")
            analysis_dir = project / "knowledge_base" / "analysis"
            analysis_dir.mkdir(parents=True, exist_ok=True)
            (project / "knowledge_base" / "feedback.json").write_text('{"papers": {"p1": {}}}', encoding="utf-8")
            (analysis_dir / "p1_review_pack.md").write_text("private review context", encoding="utf-8")

            report = project / "PRIVACY_CHECK.md"
            result = subprocess.run(
                [
                    str(project / "privacy_check.sh"),
                    "--output",
                    str(report),
                ],
                cwd=project,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Result: FAIL", result.stdout)
            content = report.read_text(encoding="utf-8")
            self.assertIn("Privacy Check", content)
            self.assertIn("High Risk: Do Not Publish", content)
            self.assertIn("client_secret_test.json", content)
            self.assertIn("INBOX.mbox.partial", content)
            self.assertIn("reader.env", content)
            self.assertIn("knowledge_base/feedback.json", content)
            self.assertIn("knowledge_base/analysis/p1_review_pack.md", content)
            self.assertIn("Do not publish", content)
            self.assertIn("Git Ignore Coverage", content)
            self.assertNotIn("sample_scholar_alerts.mbox - Raw mailbox export", content)

            strict = subprocess.run(
                [
                    str(project / "privacy_check.sh"),
                    "--strict",
                    "--output",
                    str(report),
                ],
                cwd=project,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(strict.returncode, 0)

    def test_setup_wizard_initializes_project_with_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "wizard-reader"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "setup-wizard",
                    "--project-dir",
                    str(project),
                    "--defaults",
                    "--source",
                    "rss",
                    "--rss-source",
                    str(project / "examples" / "sample_feed.atom"),
                    "--profile-template",
                    "ai-seismology",
                    "--schedule-time",
                    "11:15",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Wizard complete", result.stdout)
            self.assertIn("Source note:", result.stdout)
            self.assertIn("Source check report", result.stdout)
            self.assertTrue((project / "run_reader.sh").exists())
            self.assertTrue((project / "setup_wizard.sh").exists())
            self.assertTrue((project / "SOURCE_CHECK.md").exists())
            env_content = (project / "reader.env").read_text(encoding="utf-8")
            self.assertIn("export SOURCE=rss", env_content)
            self.assertIn("export SCHEDULE_TIME=11:15", env_content)
            self.assertIn("sample_feed.atom", env_content)
            source_check = (project / "SOURCE_CHECK.md").read_text(encoding="utf-8")
            self.assertIn("RSS/Atom source", source_check)
            self.assertIn("## Setup Guidance", source_check)
            self.assertIn("RSS/Atom is usually the most stable non-email source", source_check)
            self.assertIn("knowledge_base/reading_plan.html", source_check)
            check = subprocess.run(
                [str(project / "source_check.sh"), "--source", "rss", "--rss-source", str(project / "examples" / "sample_feed.atom"), "--live"],
                cwd=project,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("RSS/Atom live read", check.stdout)

    def test_daily_zero_run_explains_all_seen_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "reader"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "init-project",
                    "--project-dir",
                    str(project),
                    "--profile-template",
                    "ai-seismology",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            env = {
                **os.environ,
                "SOURCE": "mbox",
                "MBOX_PATH": str(project / "examples" / "sample_scholar_alerts.mbox"),
                "MODE": "foundation",
            }
            subprocess.run([str(project / "run_reader.sh")], cwd=project, env=env, text=True, capture_output=True, check=True)
            env["MODE"] = "daily"
            result = subprocess.run(
                [str(project / "run_reader.sh")],
                cwd=project,
                env=env,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("No-paper diagnosis:", result.stdout)
            summary = json.loads((project / "reader_out" / "daily" / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["papers_in_digest"], 0)
            self.assertGreater(summary["unique_papers_before_state_filter"], 0)
            self.assertEqual(summary["empty_run_diagnosis"]["reason"], "all_seen")
            digest = (project / "reader_out" / "daily" / "digest.md").read_text(encoding="utf-8")
            self.assertIn("No-paper diagnosis", digest)
            self.assertIn("No new papers after the seen-state filter", digest)
            dashboard = (project / "DASHBOARD.md").read_text(encoding="utf-8")
            self.assertIn("No-Paper Diagnosis", dashboard)
            self.assertIn("all_seen", dashboard)

    def test_zero_web_run_explains_parser_empty_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile.json"
            profile.write_text((ROOT / "examples" / "research_profile.example.json").read_text(), encoding="utf-8")
            no_metadata = root / "no_metadata.html"
            no_metadata.write_text("<html><body>No citation metadata here.</body></html>", encoding="utf-8")
            out_dir = root / "out"
            kb_dir = root / "kb"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "run",
                    "--source-web",
                    str(no_metadata),
                    "--profile",
                    str(profile),
                    "--out-dir",
                    str(out_dir),
                    "--kb-dir",
                    str(kb_dir),
                    "--no-kb-update",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["source_items"], 1)
            self.assertEqual(summary["unique_papers_before_state_filter"], 0)
            self.assertEqual(summary["empty_run_diagnosis"]["reason"], "parsed_no_papers")
            self.assertIn("webpage source was read", "\n".join(summary["empty_run_diagnosis"]["next_steps"]))
            self.assertIn("Source was readable", (out_dir / "digest.md").read_text(encoding="utf-8"))
            self.assertIn("Source was readable", (out_dir / "digest.html").read_text(encoding="utf-8"))

    def test_quickstart_command_creates_project_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "quickstart-reader"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "quickstart",
                    "--project-dir",
                    str(project),
                    "--profile-template",
                    "ai-seismology",
                    "--skip-self-test",
                    "--strict",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Quickstart report", result.stdout)
            self.assertTrue((project / "QUICKSTART_REPORT.md").exists())
            self.assertTrue((project / "SOURCE_CHECK.md").exists())
            self.assertTrue((project / "DOCTOR.md").exists())
            self.assertTrue((project / "START_HERE.md").exists())
            self.assertTrue((project / "TROUBLESHOOTING.md").exists())
            report = (project / "QUICKSTART_REPORT.md").read_text(encoding="utf-8")
            self.assertIn("Result: PASS", report)
            self.assertIn("multi-source demo", report)
            for source_name in ["mbox", "bibtex", "ris", "web", "rss"]:
                self.assertTrue((project / "reader_out" / "demo_sources" / source_name / "digest.html").exists())

    def test_init_project_accepts_profile_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "reader"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "init-project",
                    "--project-dir",
                    str(project),
                    "--profile-template",
                    "induced-seismicity",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            data = json.loads((project / "profiles" / "research_profile.json").read_text(encoding="utf-8"))
            self.assertIn("Induced seismicity", data["name"])
            self.assertTrue(any(item["term"] == "induced seismicity" for item in data["focus_terms"]))

    def test_semantic_queries_rescue_non_exact_matches(self) -> None:
        paper = core.Paper(
            id="semantic1",
            title="A scalable uncertainty-aware framework for earthquake monitoring",
            authors_source="Journal, 2026",
            snippet="Probabilistic seismic event detection for dense regional networks.",
            url="https://example.org/semantic1",
            scholar_url="",
            first_seen="2026-05-27",
            last_seen="2026-05-27",
            alerts=["AI seismology"],
            occurrences=1,
        )
        profile = {
            "semantic_queries": [
                {
                    "term": "uncertainty quantification for seismic monitoring",
                    "weight": 6,
                    "tags": ["uncertainty", "monitoring"],
                }
            ],
            "tier_thresholds": {"must_read": 8, "skim": 3},
        }
        core.score_paper(paper, profile, None)
        self.assertGreaterEqual(paper.score, 3)
        self.assertEqual(paper.tier, "Skim")
        self.assertIn("uncertainty quantification for seismic monitoring", paper.matched_terms)
        self.assertIn("semantic", paper.tags)
        self.assertTrue(any("语义匹配" in reason for reason in paper.reasons))

    def test_adaptive_ranking_uses_interested_library_seed(self) -> None:
        seed = core.Paper(
            id="seed1",
            title="Foundation model for continuous seismic monitoring",
            authors_source="Journal, 2026",
            snippet="Self-supervised waveform representation learning for seismic monitoring.",
            url="https://example.org/seed1",
            scholar_url="",
            first_seen="2026-05-27",
            last_seen="2026-05-27",
            alerts=["AI seismology"],
            occurrences=1,
            score=20,
            tier="Must read",
            matched_terms=["foundation model", "continuous seismic"],
            tags=["ai", "foundation-model"],
        )
        paper = core.Paper(
            id="candidate1",
            title="Continuous waveform representations for seismic monitoring",
            authors_source="Journal, 2026",
            snippet="A scalable approach for earthquake waveform monitoring.",
            url="https://example.org/candidate1",
            scholar_url="",
            first_seen="2026-05-27",
            last_seen="2026-05-27",
            alerts=["new methods"],
            occurrences=1,
        )
        profile = {
            "adaptive_ranking": {"enabled": True, "min_overlap": 2, "positive_weight": 4},
            "tier_thresholds": {"must_read": 8, "skim": 3},
        }
        feedback = {
            "papers": {
                "seed1": {
                    "status": "interested",
                    "signals": {"more_like_this": True},
                }
            }
        }
        core.score_paper(paper, profile, None, feedback, [seed])
        self.assertGreaterEqual(paper.score, 3)
        self.assertEqual(paper.tier, "Skim")
        self.assertIn("adaptive", paper.tags)
        self.assertTrue(any(term.startswith("similar:") for term in paper.matched_terms))
        self.assertTrue(any("反馈相似度加权" in reason for reason in paper.reasons))

    def test_adaptive_ranking_penalizes_archive_like_papers(self) -> None:
        paper = core.Paper(
            id="candidate2",
            title="Medical imaging education benchmark for seismic data",
            authors_source="Journal, 2026",
            snippet="A course-style benchmark for medical imaging education.",
            url="https://example.org/candidate2",
            scholar_url="",
            first_seen="2026-05-27",
            last_seen="2026-05-27",
            alerts=["new methods"],
            occurrences=1,
        )
        profile = {
            "adaptive_ranking": {"enabled": True, "min_overlap": 2, "negative_weight": 5},
            "tier_thresholds": {"must_read": 8, "skim": 3},
        }
        feedback = {
            "papers": {
                "bad1": {
                    "title": "Medical imaging education course announcement",
                    "status": "archive",
                    "signals": {"less_like_this": True},
                }
            }
        }
        core.score_paper(paper, profile, None, feedback, [])
        self.assertLess(paper.score, 0)
        self.assertEqual(paper.tier, "Archive")
        self.assertIn("adaptive", paper.tags)
        self.assertTrue(any(term.startswith("dissimilar:") for term in paper.matched_terms))
        self.assertTrue(any("反馈相似度降权" in reason for reason in paper.reasons))

    def test_profile_tune_reports_and_applies_feedback_suggestions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile.json"
            profile.write_text(
                json.dumps(
                    {
                        "name": "Tuning test",
                        "focus_terms": [],
                        "regions": [],
                        "methods": [],
                        "semantic_queries": [],
                        "exclude_terms": [],
                    }
                ),
                encoding="utf-8",
            )
            kb = root / "kb"
            kb.mkdir()
            library = [
                {
                    **sample_paper(),
                    "id": "positive",
                    "title": "Foundation model for continuous seismic monitoring",
                    "matched_terms": ["foundation model", "continuous seismic"],
                    "tags": ["ai", "monitoring"],
                },
                {
                    **sample_paper(),
                    "id": "negative",
                    "title": "Medical imaging education course announcement",
                    "matched_terms": ["medical imaging"],
                    "tags": ["education"],
                },
            ]
            (kb / "library.json").write_text(json.dumps(library), encoding="utf-8")
            feedback = {
                "version": 1,
                "papers": {
                    "positive": {"status": "interested", "signals": {"more_like_this": True}},
                    "negative": {"status": "archive", "signals": {"less_like_this": True}},
                },
                "terms": [],
            }
            (kb / "feedback.json").write_text(json.dumps(feedback), encoding="utf-8")
            report = root / "profile_tuning.md"

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "profile-tune",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--output",
                    str(report),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            content = report.read_text(encoding="utf-8")
            self.assertIn("Profile Tuning Suggestions", content)
            self.assertIn("foundation model", content)
            self.assertIn("medical imaging", content)

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "profile-tune",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--apply",
                    "--output",
                    str(report),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            tuned = json.loads(profile.read_text(encoding="utf-8"))
            self.assertTrue(any(item["term"] == "foundation model" for item in tuned["focus_terms"]))
            self.assertTrue(any(item["term"] == "medical imaging" for item in tuned["exclude_terms"]))

    def test_explain_ranking_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile.json"
            profile.write_text(
                json.dumps(
                    {
                        "name": "Explain ranking test",
                        "focus_terms": [{"term": "ambient noise", "weight": 7}],
                        "regions": [{"term": "Taiwan", "weight": 5}],
                        "methods": [{"term": "tomography", "weight": 5}],
                        "semantic_queries": [],
                        "exclude_terms": [],
                        "tier_thresholds": {"must_read": 20, "skim": 5},
                    }
                ),
                encoding="utf-8",
            )
            kb = root / "kb"
            kb.mkdir()
            papers = root / "papers.json"
            papers.write_text(json.dumps([sample_paper()]), encoding="utf-8")
            feedback = {
                "version": 1,
                "papers": {"p1": {"status": "interested", "signals": {"more_like_this": True}}},
                "terms": [],
            }
            (kb / "feedback.json").write_text(json.dumps(feedback), encoding="utf-8")
            report = root / "ranking_explanation.md"

            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "explain-ranking",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--papers-json",
                    str(papers),
                    "--paper-id",
                    "p1",
                    "--output",
                    str(report),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            content = report.read_text(encoding="utf-8")
            self.assertIn("Ranking Explanation", content)
            self.assertIn("Thresholds: Must read >= 20; Skim >= 5", content)
            self.assertIn("Ambient noise tomography of the Taiwan crust", content)
            self.assertIn("Matched terms: ambient noise, tomography, Taiwan", content)
            self.assertIn("Feedback status: status=interested", content)
            self.assertIn("Why It Ranked This Way", content)
            self.assertIn("Next Tuning Moves", content)

    def test_ranking_evaluation_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile.json"
            profile.write_text(
                json.dumps(
                    {
                        "name": "Ranking eval test",
                        "focus_terms": [{"term": "ambient noise", "weight": 7}],
                        "regions": [{"term": "Taiwan", "weight": 5}],
                        "methods": [{"term": "tomography", "weight": 5}],
                        "semantic_queries": [],
                        "exclude_terms": [],
                        "tier_thresholds": {"must_read": 20, "skim": 5},
                    }
                ),
                encoding="utf-8",
            )
            kb = root / "kb"
            kb.mkdir()
            papers = root / "papers.json"
            positive_high = sample_paper()
            negative_high = {
                **sample_paper(),
                "id": "p2",
                "title": "Generic medical imaging tomography benchmark",
                "score": 28,
                "tier": "Must read",
                "matched_terms": ["tomography"],
            }
            positive_low = {
                **sample_paper(),
                "id": "p3",
                "title": "A useful low-scored dense array catalog",
                "score": 2,
                "tier": "Archive",
                "matched_terms": [],
            }
            negative_low = {
                **sample_paper(),
                "id": "p4",
                "title": "Workshop announcement outside the research scope",
                "score": 1,
                "tier": "Archive",
                "matched_terms": [],
            }
            papers.write_text(json.dumps([positive_high, negative_high, positive_low, negative_low]), encoding="utf-8")
            feedback = {
                "version": 1,
                "papers": {
                    "p1": {"status": "interested", "signals": {"more_like_this": True}},
                    "p2": {"status": "archive", "signals": {"less_like_this": True}},
                    "p3": {"status": "interested"},
                    "p4": {"status": "archive"},
                },
                "terms": [],
            }
            (kb / "feedback.json").write_text(json.dumps(feedback), encoding="utf-8")
            report = root / "ranking_evaluation.md"

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "ranking-eval",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--papers-json",
                    str(papers),
                    "--top-k",
                    "1,3",
                    "--output",
                    str(report),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Result: WARN", result.stdout)
            content = report.read_text(encoding="utf-8")
            self.assertIn("Ranking Evaluation", content)
            self.assertIn("Average precision", content)
            self.assertIn("## Precision@K", content)
            self.assertIn("Potential False Positives", content)
            self.assertIn("Generic medical imaging tomography benchmark", content)
            self.assertIn("Potential Missed Positives", content)
            self.assertIn("A useful low-scored dense array catalog", content)
            self.assertIn("Tier Calibration", content)

            strict = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "ranking-eval",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--papers-json",
                    str(papers),
                    "--strict",
                    "--output",
                    str(report),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(strict.returncode, 0)

    def test_semantic_rerank_report_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile.json"
            profile.write_text(
                json.dumps(
                    {
                        "name": "Semantic rerank test",
                        "research_questions": ["Which waveform representation learning papers matter for earthquake monitoring?"],
                        "focus_terms": [{"term": "seismic foundation model", "weight": 8}],
                        "methods": [{"term": "representation learning", "weight": 6}],
                        "semantic_queries": [
                            {"term": "self-supervised waveform representation learning for earthquake monitoring", "weight": 7}
                        ],
                        "exclude_terms": [],
                        "tier_thresholds": {"must_read": 20, "skim": 5},
                    }
                ),
                encoding="utf-8",
            )
            kb = root / "kb"
            kb.mkdir()
            papers = root / "papers.json"
            seed = {
                **sample_paper(),
                "id": "seed",
                "title": "Self-supervised seismic waveform representation learning",
                "snippet": "A foundation model for continuous earthquake monitoring with waveform embeddings.",
                "score": 25,
                "tier": "Must read",
                "matched_terms": ["seismic foundation model"],
                "tags": ["ai", "waveform"],
            }
            rescue = {
                **sample_paper(),
                "id": "rescue",
                "title": "Contrastive waveform representations for event monitoring",
                "snippet": "Learns reusable earthquake signal representations from continuous seismic waveforms.",
                "score": 1,
                "tier": "Archive",
                "matched_terms": [],
                "tags": [],
            }
            noise = {
                **sample_paper(),
                "id": "noise",
                "title": "Medical ultrasound image segmentation benchmark",
                "snippet": "A clinical imaging dataset unrelated to earthquake monitoring.",
                "score": 8,
                "tier": "Skim",
                "matched_terms": ["benchmark"],
                "tags": [],
            }
            papers.write_text(json.dumps([noise, rescue, seed]), encoding="utf-8")
            feedback = {
                "version": 1,
                "papers": {
                    "seed": {"status": "interested", "signals": {"more_like_this": True}},
                    "noise": {"status": "archive", "signals": {"less_like_this": True}},
                },
                "terms": [],
            }
            (kb / "feedback.json").write_text(json.dumps(feedback), encoding="utf-8")
            report = root / "semantic_rerank.md"
            reranked_json = root / "semantic_reranked.json"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "semantic-rerank",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--papers-json",
                    str(papers),
                    "--output",
                    str(report),
                    "--json-output",
                    str(reranked_json),
                    "--min-delta",
                    "1",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            content = report.read_text(encoding="utf-8")
            self.assertIn("Semantic Rerank", content)
            self.assertIn("local sparse TF-IDF", content)
            self.assertIn("Potential Semantic Rescues", content)
            self.assertIn("Contrastive waveform representations", content)
            reranked = json.loads(reranked_json.read_text(encoding="utf-8"))
            by_id = {item["id"]: item for item in reranked}
            self.assertIn("semantic_rerank", by_id["rescue"])
            self.assertGreater(by_id["rescue"]["semantic_delta"], 0)
            self.assertLess(by_id["rescue"]["semantic_rerank"]["rank"], by_id["rescue"]["semantic_rerank"]["base_rank"])

    def test_semantic_rerank_embedding_backend_with_injected_encoder(self) -> None:
        seed = {
            **sample_paper(),
            "id": "seed",
            "title": "Self-supervised seismic waveform representation learning",
            "snippet": "A foundation model for continuous earthquake monitoring with waveform embeddings.",
            "score": 25,
            "tier": "Must read",
        }
        rescue = {
            **sample_paper(),
            "id": "rescue",
            "title": "Contrastive waveform representations for event monitoring",
            "snippet": "Learns reusable earthquake signal representations from continuous seismic waveforms.",
            "score": 1,
            "tier": "Archive",
        }
        noise = {
            **sample_paper(),
            "id": "noise",
            "title": "Medical ultrasound image segmentation benchmark",
            "snippet": "A clinical imaging dataset unrelated to earthquake monitoring.",
            "score": 8,
            "tier": "Skim",
        }

        def fake_encoder(texts: list[str], model_name: str, batch_size: int) -> list[list[float]]:
            self.assertEqual(model_name, "fake-model")
            self.assertEqual(batch_size, 4)
            vectors: list[list[float]] = []
            for value in texts:
                lowered = value.lower()
                if "medical" in lowered or "clinical" in lowered:
                    vectors.append([0.0, 1.0])
                elif "waveform" in lowered or "earthquake" in lowered or "seismic" in lowered:
                    vectors.append([1.0, 0.0])
                else:
                    vectors.append([0.5, 0.5])
            return vectors

        rows = semantic_rerank_records(
            [noise, seed, rescue],
            ["waveform representation learning for earthquake monitoring"],
            ["self-supervised seismic waveform foundation model"],
            ["medical clinical imaging benchmark"],
            backend="sentence-transformers",
            embedding_model="fake-model",
            embedding_batch_size=4,
            embedding_encoder=fake_encoder,
        )
        by_id = {row.record["id"]: row for row in rows}
        self.assertEqual(by_id["rescue"].backend, "sentence-transformers:fake-model")
        self.assertGreater(by_id["rescue"].delta, 0)
        self.assertLess(by_id["rescue"].rank, by_id["rescue"].base_rank)
        self.assertLess(by_id["noise"].delta, 0)

    def test_embedding_check_sparse_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "embedding.md"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "embedding-check",
                    "--project-dir",
                    str(root),
                    "--backend",
                    "sparse",
                    "--strict",
                    "--output",
                    str(report),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Result: PASS", result.stdout)
            content = report.read_text(encoding="utf-8")
            self.assertIn("Embedding Backend Check", content)
            self.assertIn("Sparse TF-IDF backend", content)
            self.assertIn("sentence-transformers dependency", content)
            self.assertIn("Model load", content)

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

    def test_rss_source_runs_full_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile.json"
            profile.write_text((ROOT / "examples" / "research_profile.example.json").read_text(), encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "run",
                    "--source-rss",
                    str(ROOT / "examples" / "feeds.example.txt"),
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
            self.assertEqual(len(papers), 2)
            self.assertEqual(papers[0]["metadata"]["feed"]["source"], "Demo Geophysics Feed")
            self.assertTrue((root / "out" / "digest.html").exists())

    def test_web_source_runs_full_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile.json"
            profile.write_text((ROOT / "examples" / "research_profile.example.json").read_text(), encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "run",
                    "--source-web",
                    str(ROOT / "examples" / "web_sources.example.txt"),
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
            self.assertEqual(papers[0]["title"], "Uncertainty-aware dense array monitoring of induced seismicity")
            self.assertEqual(papers[0]["metadata"]["web"]["doi"], "10.0000/web-demo")
            self.assertEqual(papers[0]["metadata"]["web"]["pdf_url"], "https://example.org/web-demo.pdf")
            self.assertTrue((root / "out" / "digest.html").exists())

    def test_fetch_pdf_from_open_metadata_updates_library(self) -> None:
        class PdfHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path != "/paper.pdf":
                    self.send_response(404)
                    self.end_headers()
                    return
                content = b"%PDF-1.4\n% sanitized test pdf\n"
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            def log_message(self, format: str, *args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), PdfHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                profile = root / "profile.json"
                profile.write_text((ROOT / "examples" / "research_profile.example.json").read_text(), encoding="utf-8")
                kb = root / "kb"
                kb.mkdir()
                record = sample_paper()
                pdf_url = f"http://127.0.0.1:{server.server_port}/paper.pdf"
                record["metadata"]["openalex"]["pdf_url"] = pdf_url
                (kb / "library.json").write_text(json.dumps([record]), encoding="utf-8")
                output_pdf = root / "downloaded.pdf"
                result = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "scholar_reader.py"),
                        "fetch-pdf",
                        "--profile",
                        str(profile),
                        "--kb-dir",
                        str(kb),
                        "--paper-id",
                        "p1",
                        "--output",
                        str(output_pdf),
                        "--update-library",
                    ],
                    text=True,
                    capture_output=True,
                    check=True,
                )
                self.assertIn("PDF saved:", result.stdout)
                self.assertIn("Library metadata updated: True", result.stdout)
                self.assertTrue(output_pdf.read_bytes().startswith(b"%PDF"))
                library = json.loads((kb / "library.json").read_text(encoding="utf-8"))
                full_text = library[0]["metadata"]["full_text"]
                self.assertEqual(full_text["pdf_url"], pdf_url)
                self.assertIn(str(output_pdf), full_text["pdf_paths"])
                note = (kb / "papers" / "p1.md").read_text(encoding="utf-8")
                self.assertIn("## Full Text", note)
                self.assertIn(str(output_pdf), note)
                workflow = root / "workflow.md"
                subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "scholar_reader.py"),
                        "review-workflow",
                        "--profile",
                        str(profile),
                        "--kb-dir",
                        str(kb),
                        "--paper-id",
                        "p1",
                        "--fetch-pdf",
                        "--pdf-url",
                        pdf_url,
                        "--output",
                        str(workflow),
                    ],
                    text=True,
                    capture_output=True,
                    check=True,
                )
                workflow_content = workflow.read_text(encoding="utf-8")
                self.assertIn("Selected Paper Review Workflow", workflow_content)
                self.assertIn("fetched from", workflow_content)
                self.assertIn("Full-text extraction: unavailable", workflow_content)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_arxiv_url_builder(self) -> None:
        url = core.arxiv_api_url('cat:physics.geo-ph AND all:"receiver function"', 25)
        self.assertIn("https://export.arxiv.org/api/query?", url)
        self.assertIn("max_results=25", url)
        self.assertIn("cat%3Aphysics.geo-ph", url)

    def test_feedback_updates_knowledge_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "reader"
            profile = root / "profiles" / "research_profile.json"
            profile.parent.mkdir(parents=True)
            profile.write_text((ROOT / "examples" / "research_profile.example.json").read_text(), encoding="utf-8")
            papers_json = root / "reader_out" / "daily" / "papers.json"
            papers_json.parent.mkdir(parents=True)
            papers_json.write_text(json.dumps([sample_paper()]), encoding="utf-8")
            kb = root / "knowledge_base"

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "feedback",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--papers-json",
                    str(papers_json),
                    "--paper-id",
                    "p1",
                    "--mark",
                    "interested",
                    "--more-like-this",
                    "--note",
                    "Strong candidate for the Taiwan manuscript.",
                    "--no-profile-update",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Feedback updated", result.stdout)
            self.assertIn("Reading plan refreshed", result.stdout)
            self.assertIn("Dashboard refreshed", result.stdout)
            self.assertTrue((kb / "library.json").exists())
            self.assertTrue((kb / "papers" / "p1.md").exists())
            self.assertTrue((kb / "reading_plan.html").exists())
            self.assertTrue((root / "DASHBOARD.html").exists())
            reading_plan = (kb / "reading_plan.md").read_text(encoding="utf-8")
            self.assertIn("Reading Plan", reading_plan)
            dashboard = (root / "DASHBOARD.md").read_text(encoding="utf-8")
            self.assertIn("Reading plan HTML", dashboard)
            self.assertIn("Feedback records: 1 paper feedback records", dashboard)
            foundation = (kb / "foundation.md").read_text(encoding="utf-8")
            self.assertIn("Feedback: interested; signals: more-like-this", foundation)
            self.assertIn("Strong candidate for the Taiwan manuscript.", foundation)
            interested = (kb / "interested.md").read_text(encoding="utf-8")
            self.assertIn("Feedback: interested; signals: more-like-this", interested)
            self.assertIn("Strong candidate for the Taiwan manuscript.", interested)
            direction_path = next(path for path in (kb / "directions").glob("*.md") if path.name != "index.md")
            direction = direction_path.read_text(encoding="utf-8")
            self.assertIn("Strong candidate for the Taiwan manuscript.", direction)

    def test_export_and_weekly_renderers(self) -> None:
        records = [sample_paper()]
        bibtex = export_records(records, "bibtex")
        ris = export_records(records, "ris")
        feedback = {
            "papers": {
                "p1": {
                    "status": "interested",
                    "reading_status": "reading",
                    "labels": ["must-cite"],
                    "note": "Useful comparison for the Taiwan manuscript.",
                }
            }
        }
        weekly = render_weekly_review(records, {"name": "test profile"}, feedback=feedback, days=30)
        self.assertIn("@article", bibtex)
        self.assertIn("doi = {10.0000/test}", bibtex)
        self.assertIn("TY  - JOUR", ris)
        self.assertIn("Weekly Literature Review", weekly)
        self.assertIn("Personal Notes Review", weekly)
        self.assertIn("Useful comparison for the Taiwan manuscript.", weekly)

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

    def test_support_bundle_sanitizes_private_paths_and_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "reader"
            project.mkdir()
            profile_dir = project / "profiles"
            profile_dir.mkdir()
            profile = profile_dir / "research_profile.json"
            profile.write_text((ROOT / "examples" / "research_profile.example.json").read_text(), encoding="utf-8")
            kb = project / "knowledge_base"
            kb.mkdir()
            (kb / "library.json").write_text(json.dumps([sample_paper()]), encoding="utf-8")
            private_token = root / "private" / "gmail_token.json"
            private_token.parent.mkdir()
            private_token.write_text('{"token":"secret-token-value"}', encoding="utf-8")
            private_feed = root / "private" / "feeds.txt"
            private_feed.write_text("https://private.example.invalid/feed?token=secret", encoding="utf-8")
            env_file = project / "reader.env"
            env_file.write_text(
                f"""
SOURCE=rss
RSS_SOURCE={private_feed}
GMAIL_TOKEN={private_token}
SCHEDULE_TIME=09:00
""".strip()
                + "\n",
                encoding="utf-8",
            )
            (project / "SOURCE_CHECK.md").write_text(
                f"- [WARN] RSS/Atom source: {private_feed}\n- URL: https://private.example.invalid/feed?token=secret\n",
                encoding="utf-8",
            )
            bundle = project / "SUPPORT_BUNDLE.md"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "support-bundle",
                    "--project-dir",
                    str(project),
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--env-file",
                    str(env_file),
                    "--output",
                    str(bundle),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            content = bundle.read_text(encoding="utf-8")
            self.assertIn("Scholar Alert Reader Support Bundle", content)
            self.assertIn("RSS_SOURCE", content)
            self.assertIn("GMAIL_TOKEN", content)
            self.assertIn("<external>/feeds.txt", content)
            self.assertIn("<external>/gmail_token.json", content)
            self.assertNotIn(str(root), content)
            self.assertNotIn("secret-token-value", content)
            self.assertNotIn("private.example.invalid", content)

    def test_capabilities_command_describes_product_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "reader"
            subprocess.run(
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
            report = project / "CAPABILITIES.md"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "capabilities",
                    "--project-dir",
                    str(project),
                    "--output",
                    str(report),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            content = report.read_text(encoding="utf-8")
            self.assertIn("Scholar Alert Reader Capabilities", content)
            self.assertIn("Capability Boundary", content)
            self.assertIn("Not Promised", content)
            self.assertIn("publisher access", content)
            self.assertIn("review-pack", content)
            self.assertIn("embedding-check", content)
            self.assertIn("<project>", content)
            self.assertNotIn(str(root), content)

    def test_self_test_command_runs_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "self-test-project"
            report = root / "self-test.md"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "self-test",
                    "--project-dir",
                    str(project),
                    "--output",
                    str(report),
                    "--strict",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            content = report.read_text(encoding="utf-8")
            self.assertIn("Scholar Alert Reader Self-Test", content)
            self.assertIn("Result: PASS", content)
            self.assertTrue((project / "reader_out" / "self_test_demo" / "digest.html").exists())
            self.assertTrue((project / "reader_out" / "self_test_demo" / "papers.json").exists())

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
            self.assertIn("Capability boundary", content)
            self.assertIn("ai-seismology", content)

    def test_copilot_commands_write_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile.json"
            profile.write_text((ROOT / "examples" / "research_profile.example.json").read_text(), encoding="utf-8")
            kb = root / "kb"
            kb.mkdir()
            library = kb / "library.json"
            library.write_text(json.dumps([sample_paper()]), encoding="utf-8")
            core.save_feedback(
                core.default_feedback_file(kb),
                {
                    "papers": {
                        "p1": {
                            "id": "p1",
                            "title": sample_paper()["title"],
                            "url": sample_paper()["url"],
                            "status": "interested",
                            "reading_status": "reading",
                            "labels": ["must-cite"],
                            "note": "Useful comparison for the Taiwan manuscript.",
                        }
                    },
                    "terms": [],
                },
            )

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
            deep_content = deep.read_text(encoding="utf-8")
            self.assertIn("Deep Read", deep_content)
            self.assertIn("Your Feedback", deep_content)
            self.assertIn("Useful comparison for the Taiwan manuscript.", deep_content)

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
            answer_content = answer.read_text(encoding="utf-8")
            self.assertIn("Most Relevant Papers", answer_content)
            self.assertIn("Retrieved papers with personal notes: 1", answer_content)
            self.assertIn("Useful comparison for the Taiwan manuscript.", answer_content)

            note_answer = root / "note_answer.md"
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
                    "manuscript comparison",
                    "--output",
                    str(note_answer),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            note_answer_content = note_answer.read_text(encoding="utf-8")
            self.assertIn("Most Relevant Papers", note_answer_content)
            self.assertIn("Useful comparison for the Taiwan manuscript.", note_answer_content)

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
            advice_content = advice.read_text(encoding="utf-8")
            self.assertIn("Research Advice", advice_content)
            self.assertIn("Personal Notes To Revisit", advice_content)
            self.assertIn("Useful comparison for the Taiwan manuscript.", advice_content)

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
            reading_status_content = (kb / "reading_status.md").read_text(encoding="utf-8")
            self.assertIn("reading", reading_status_content)
            self.assertIn("Useful comparison for the Taiwan manuscript.", reading_status_content)
            paper_page_content = (kb / "papers" / "p1.md").read_text(encoding="utf-8")
            self.assertIn("## Saved Feedback", paper_page_content)
            self.assertIn("Useful comparison for the Taiwan manuscript.", paper_page_content)
            foundation_content = (kb / "foundation.md").read_text(encoding="utf-8")
            self.assertIn("Reading status: reading", foundation_content)
            self.assertIn("Labels: must-cite", foundation_content)
            self.assertIn("Useful comparison for the Taiwan manuscript.", foundation_content)
            interested_content = (kb / "interested.md").read_text(encoding="utf-8")
            self.assertIn("Reading status: reading", interested_content)
            self.assertIn("Useful comparison for the Taiwan manuscript.", interested_content)
            weekly_content = (kb / "weekly_review.md").read_text(encoding="utf-8")
            self.assertIn("Personal Notes Review", weekly_content)
            self.assertIn("Useful comparison for the Taiwan manuscript.", weekly_content)
            auto_plan_content = (kb / "reading_plan.md").read_text(encoding="utf-8")
            self.assertIn("Reading Plan", auto_plan_content)
            self.assertIn("reading: 1", auto_plan_content)

            reading_plan = root / "reading_plan.md"
            reading_plan_html = root / "reading_plan.html"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "reading-plan",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--output",
                    str(reading_plan),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            reading_plan_content = reading_plan.read_text(encoding="utf-8")
            self.assertIn("Reading Plan", reading_plan_content)
            self.assertIn("Read First", reading_plan_content)
            self.assertIn("already in reading", reading_plan_content)
            self.assertTrue(reading_plan_html.exists())
            self.assertIn("<!doctype html>", reading_plan_html.read_text(encoding="utf-8"))

            dashboard = root / "DASHBOARD.md"
            dashboard_html = root / "DASHBOARD.html"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "dashboard",
                    "--project-dir",
                    str(root),
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--out-dir",
                    str(root),
                    "--output",
                    str(dashboard),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            dashboard_content = dashboard.read_text(encoding="utf-8")
            self.assertIn("Scholar Alert Reader Dashboard", dashboard_content)
            self.assertIn("Reading plan HTML", dashboard_content)
            self.assertIn("Retained library: 1 records", dashboard_content)
            self.assertIn("Profile Health", dashboard_content)
            self.assertIn("Run `./profile_doctor.sh`", dashboard_content)
            self.assertTrue(dashboard_html.exists())
            self.assertIn("<!doctype html>", dashboard_html.read_text(encoding="utf-8"))

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
            comparison_content = comparison.read_text(encoding="utf-8")
            self.assertIn("Paper Comparison", comparison_content)
            self.assertIn("Saved Personal Note", comparison_content)
            self.assertIn("Useful comparison for the Taiwan manuscript.", comparison_content)

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
            research_map_content = research_map.read_text(encoding="utf-8")
            self.assertIn("Research Map", research_map_content)
            self.assertIn("Personal notes: 1", research_map_content)
            self.assertIn("Useful comparison for the Taiwan manuscript.", research_map_content)

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

            zotero_bib = root / "zotero.bib"
            pdf_path = root / "Ambient Noise.pdf"
            zotero_bib.write_text(
                f"""
@article{{zoteroAmbient2026,
  title = {{Ambient noise tomography of the Taiwan crust}},
  author = {{A Researcher and B Researcher}},
  journal = {{Journal}},
  year = {{2026}},
  doi = {{10.0000/test}},
  file = {{Full Text PDF:{pdf_path}:application/pdf}},
  uri = {{http://zotero.org/users/1/items/ABCD1234}},
  zotero-key = {{ABCD1234}}
}}
""".strip(),
                encoding="utf-8",
            )
            sync_report = root / "zotero_sync.md"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "zotero-sync",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--bibtex",
                    str(zotero_bib),
                    "--report",
                    str(sync_report),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            synced_library = json.loads(library.read_text(encoding="utf-8"))
            zotero_meta = synced_library[0]["metadata"]["zotero"]
            self.assertEqual(zotero_meta["citation_key"], "zoteroAmbient2026")
            self.assertEqual(zotero_meta["item_key"], "ABCD1234")
            self.assertIn(str(pdf_path), zotero_meta["pdf_paths"])
            self.assertIn("Matched papers: 1", sync_report.read_text(encoding="utf-8"))
            self.assertIn("Citation key: zoteroAmbient2026", (kb / "papers" / "p1.md").read_text(encoding="utf-8"))

            full_text_source = root / "ambient_full_text.txt"
            full_text_source.write_text(
                """
Abstract
This study uses ambient noise tomography and uncertainty quantification to image the Taiwan crust.

1 Introduction
Ambient noise tomography is increasingly used to connect crustal structure with tectonic interpretation.

2 Data
We use continuous waveform data from a dense seismic array in Taiwan between 2020 and 2025.

3 Methods
We measure seismic surface wave dispersion from continuous waveform data and invert for crustal structure.

4 Results
The resulting velocity model resolves a robust low velocity zone beneath the target region, as shown in Figure 2 and Table 1.

5 Limitations
The analysis does not resolve short-period scattering or all uncertainty sources in the inversion.

Data Availability
The waveform dataset is available from the IRIS repository, and processing scripts are available on GitHub.

6 Conclusions
The results show a robust low velocity zone and demonstrate how ambient noise tomography can constrain tectonic interpretation.
""".strip(),
                encoding="utf-8",
            )
            full_text_report = root / "full_text.md"
            full_text_cache = root / "full_text.txt"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "full-text",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--paper-id",
                    "p1",
                    "--pdf-path",
                    str(full_text_source),
                    "--text-output",
                    str(full_text_cache),
                    "--output",
                    str(full_text_report),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("ambient noise tomography", full_text_cache.read_text(encoding="utf-8"))
            full_text_content = full_text_report.read_text(encoding="utf-8")
            self.assertIn("Full-Text Brief", full_text_content)
            self.assertIn("Profile Overlap", full_text_content)
            self.assertIn("Section Coverage", full_text_content)
            self.assertIn("Evidence By Section", full_text_content)
            self.assertIn("Methods Excerpt", full_text_content)
            self.assertIn("Data / Study Area Excerpt", full_text_content)
            self.assertIn("Visual, Table, Data, And Code Signals", full_text_content)
            self.assertIn("Figure 2", full_text_content)
            self.assertIn("Table 1", full_text_content)
            self.assertIn("GitHub", full_text_content)
            self.assertIn("Citation Readiness Checklist", full_text_content)
            self.assertIn("Missing Or Weak Sections", full_text_content)

            deep_with_full_text = root / "deep_with_full_text.md"
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
                    "--full-text-path",
                    str(full_text_cache),
                    "--full-text-brief-path",
                    str(full_text_report),
                    "--output",
                    str(deep_with_full_text),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            deep_with_full_text_content = deep_with_full_text.read_text(encoding="utf-8")
            self.assertIn("Local Full-Text Evidence Snapshot", deep_with_full_text_content)
            self.assertIn("Section coverage:", deep_with_full_text_content)
            self.assertIn("Visual/data/code signals: Figures, Tables, Data Availability, Code / Software", deep_with_full_text_content)
            self.assertIn("Profile Overlap From Full Text", deep_with_full_text_content)
            self.assertIn("Full-Text Brief Excerpt", deep_with_full_text_content)

            review_pack = root / "review_pack.md"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "review-pack",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--paper-id",
                    "p1",
                    "--full-text-path",
                    str(full_text_cache),
                    "--full-text-brief-path",
                    str(full_text_report),
                    "--output",
                    str(review_pack),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            review_pack_content = review_pack.read_text(encoding="utf-8")
            self.assertIn("Paper Review Context Pack", review_pack_content)
            self.assertIn("Review Task For The Assistant", review_pack_content)
            self.assertIn("Local Full-Text Brief", review_pack_content)
            self.assertIn("Visual, Table, Data, And Code Signals", review_pack_content)
            self.assertIn("Local Full Text", review_pack_content)
            self.assertIn("ambient noise tomography", review_pack_content)

            workup = root / "workup.md"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "workup",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--paper-id",
                    "p1",
                    "--full-text-path",
                    str(full_text_cache),
                    "--full-text-brief-path",
                    str(full_text_report),
                    "--output",
                    str(workup),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            workup_content = workup.read_text(encoding="utf-8")
            self.assertIn("Paper Workup", workup_content)
            self.assertIn("Decision Snapshot", workup_content)
            self.assertIn("Personal Note", workup_content)
            self.assertIn("Useful comparison for the Taiwan manuscript.", workup_content)
            self.assertIn("Possible Manuscript Role", workup_content)
            self.assertIn("What To Check Before Citing", workup_content)
            self.assertIn("Visual/data/code signals: Figures, Tables, Data Availability, Code / Software", workup_content)
            self.assertIn("review-pack", workup_content)

            workflow = root / "review_workflow.md"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "review-workflow",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--paper-id",
                    "p1",
                    "--pdf-path",
                    str(full_text_source),
                    "--force-extract",
                    "--output",
                    str(workflow),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            workflow_content = workflow.read_text(encoding="utf-8")
            self.assertIn("Selected Paper Review Workflow", workflow_content)
            self.assertIn("Full-text extraction: extracted with text-file", workflow_content)
            self.assertIn("paper workup", workflow_content)
            self.assertIn("review pack", workflow_content)
            self.assertTrue((kb / "full_text" / "p1.txt").exists())
            self.assertTrue((kb / "analysis" / "p1_full_text_brief.md").exists())
            self.assertTrue((kb / "analysis" / "p1_workup.md").exists())
            self.assertTrue((kb / "analysis" / "p1_review_pack.md").exists())
            self.assertIn("Local Full Text", (kb / "analysis" / "p1_review_pack.md").read_text(encoding="utf-8"))

            deep_with_default_full_text = root / "deep_with_default_full_text.md"
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
                    str(deep_with_default_full_text),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            deep_with_default_content = deep_with_default_full_text.read_text(encoding="utf-8")
            self.assertIn("Local Full-Text Evidence Snapshot", deep_with_default_content)
            self.assertIn("Visual/data/code signals: Figures, Tables, Data Availability, Code / Software", deep_with_default_content)

            default_full_text_dir = kb / "full_text"
            default_full_text_dir.mkdir(parents=True, exist_ok=True)
            (default_full_text_dir / "p1.txt").write_text(full_text_cache.read_text(encoding="utf-8"), encoding="utf-8")
            default_analysis_dir = kb / "analysis"
            default_analysis_dir.mkdir(parents=True, exist_ok=True)
            (default_analysis_dir / "p1_full_text_brief.md").write_text(full_text_content, encoding="utf-8")
            review_queue = root / "review_queue.md"
            review_queue_html = root / "review_queue.html"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "review-queue",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--paper-id",
                    "p1",
                    "--no-extract",
                    "--output",
                    str(review_queue),
                    "--html-output",
                    str(review_queue_html),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            review_queue_content = review_queue.read_text(encoding="utf-8")
            self.assertIn("Review Queue", review_queue_content)
            self.assertIn("Queue Summary", review_queue_content)
            self.assertIn("Review packs written: 1", review_queue_content)
            self.assertIn("Full-text briefs available: 1", review_queue_content)
            self.assertIn("Papers with visual/data/code signals: 1", review_queue_content)
            self.assertIn("Signals: Figures, Tables, Data Availability, Code / Software", review_queue_content)
            self.assertIn("Next action: Open the review pack", review_queue_content)
            self.assertIn("p1_review_pack.md", review_queue_content)
            self.assertTrue(review_queue_html.exists())
            self.assertIn("<!doctype html>", review_queue_html.read_text(encoding="utf-8"))
            self.assertIn("Scholar Alert Review Queue", review_queue_html.read_text(encoding="utf-8"))
            queued_pack = (kb / "analysis" / "p1_review_pack.md").read_text(encoding="utf-8")
            self.assertIn("ambient noise tomography", queued_pack)
            self.assertIn("Local Full-Text Brief", queued_pack)
            self.assertIn("Visual, Table, Data, And Code Signals", queued_pack)
            answers_dir = kb / "answers"
            answers_dir.mkdir(parents=True, exist_ok=True)
            (answers_dir / "2026-05-28_p1_selected_answer.md").write_text(
                "# Selected Paper Answer\n\nUseful selected-paper answer.",
                encoding="utf-8",
            )
            comparisons_dir = kb / "comparisons"
            comparisons_dir.mkdir(parents=True, exist_ok=True)
            (comparisons_dir / "2026-05-28_p1_vs_p2.md").write_text(
                "# Paper Comparison\n\nUseful comparison.",
                encoding="utf-8",
            )

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
            self.assertTrue((obsidian_dir / "04_Answers" / "Answer Index.md").exists())
            self.assertTrue((obsidian_dir / "05_Comparisons" / "Comparison Index.md").exists())
            self.assertTrue((obsidian_dir / "06_Deep_Reads" / "Analysis Index.md").exists())
            dashboard_note = (obsidian_dir / "00_Dashboard" / "Scholar Alert Dashboard.md").read_text(encoding="utf-8")
            self.assertIn("Personal notes: 1", dashboard_note)
            self.assertIn("[[04_Answers/Answer Index|Library And Paper Answers]]", dashboard_note)
            answer_index = (obsidian_dir / "04_Answers" / "Answer Index.md").read_text(encoding="utf-8")
            self.assertIn("[[2026-05-28_p1_selected_answer]]", answer_index)
            comparison_index = (obsidian_dir / "05_Comparisons" / "Comparison Index.md").read_text(encoding="utf-8")
            self.assertIn("[[2026-05-28_p1_vs_p2]]", comparison_index)
            analysis_index = (obsidian_dir / "06_Deep_Reads" / "Analysis Index.md").read_text(encoding="utf-8")
            self.assertIn("[[p1_review_pack]]", analysis_index)
            paper_note = next((obsidian_dir / "01_Papers").glob("*.md"))
            note = paper_note.read_text(encoding="utf-8")
            self.assertIn('citation_key: "zoteroAmbient2026"', note)
            self.assertIn('doi: "10.0000/test"', note)
            self.assertIn(str(pdf_path), note)
            self.assertIn("## Saved Feedback", note)
            self.assertIn("Useful comparison for the Taiwan manuscript.", note)

    def test_workup_accepts_loose_library_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile.json"
            profile.write_text((ROOT / "examples" / "research_profile.example.json").read_text(), encoding="utf-8")
            kb = root / "kb"
            kb.mkdir()
            (kb / "library.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "loose1",
                            "title": "Ambient noise tomography of the Taiwan crust",
                            "snippet": "A loose imported record with enough metadata for a workup.",
                            "score": 18,
                            "tier": "Skim",
                            "matched_terms": ["ambient noise", "tomography"],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            output = root / "loose_workup.md"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "workup",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--paper-id",
                    "loose1",
                    "--output",
                    str(output),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            content = output.read_text(encoding="utf-8")
            self.assertIn("Paper Workup", content)
            self.assertIn("Decision Snapshot", content)

    def test_feedback_ui_report_actions_write_and_serve_reports(self) -> None:
        from scholar_alert_reader.server import ServerConfig, make_handler

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "reader"
            profile = root / "profiles" / "research_profile.json"
            profile.parent.mkdir(parents=True)
            profile.write_text((ROOT / "examples" / "research_profile.example.json").read_text(), encoding="utf-8")
            kb = root / "knowledge_base"
            kb.mkdir()
            papers_json = root / "reader_out" / "daily" / "papers.json"
            papers_json.parent.mkdir(parents=True)
            papers_json.write_text(json.dumps([sample_paper()]), encoding="utf-8")
            config = ServerConfig(profile_path=profile, kb_dir=kb, papers_json=papers_json)
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(config))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base_url = f"http://127.0.0.1:{server.server_port}"
                with urllib.request.urlopen(base_url, timeout=5) as response:
                    initial_body = response.read().decode("utf-8")
                self.assertIn('value="review_workflow"', initial_body)
                self.assertIn("Full review", initial_body)
                self.assertIn('value="status_background"', initial_body)
                self.assertIn('value="status_not_relevant"', initial_body)
                self.assertIn('id="status"', initial_body)
                self.assertIn('data-status="unread"', initial_body)
                self.assertIn("feedback none", initial_body)
                self.assertIn('name="note"', initial_body)
                self.assertIn("Save note", initial_body)
                self.assertIn('action="/ask"', initial_body)
                self.assertIn("Ask library", initial_body)
                self.assertIn("/paper?id=p1", initial_body)
                self.assertIn("Open workspace", initial_body)

                ask_body = urllib.parse.urlencode({"question": "Taiwan ambient noise manuscript"}).encode("utf-8")
                ask_request = urllib.request.Request(
                    f"{base_url}/ask",
                    data=ask_body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                )
                with urllib.request.urlopen(ask_request, timeout=5) as response:
                    ask_html = response.read().decode("utf-8")
                self.assertIn("Answered library question", ask_html)
                self.assertIn("/answer?name=", ask_html)
                answer_files = list((kb / "answers").glob("*.md"))
                self.assertEqual(len(answer_files), 1)
                with urllib.request.urlopen(f"{base_url}/answer?name={urllib.parse.quote(answer_files[0].name)}", timeout=5) as response:
                    answer_body = response.read().decode("utf-8")
                self.assertIn("Literature Answer", answer_body)
                self.assertIn("Taiwan ambient noise manuscript", answer_body)
                with self.assertRaises(urllib.error.HTTPError) as raised_answer:
                    urllib.request.urlopen(f"{base_url}/answer?name=../feedback.json", timeout=5)
                raised_answer.exception.close()

                with urllib.request.urlopen(f"{base_url}/paper?id=p1", timeout=5) as response:
                    paper_workspace = response.read().decode("utf-8")
                self.assertIn("Scholar Alert Paper Workspace", paper_workspace)
                self.assertIn("Ask about this paper", paper_workspace)
                self.assertIn('name="paper_id" value="p1"', paper_workspace)
                self.assertIn("Ambient noise tomography of the Taiwan crust", paper_workspace)
                paper_ask_body = urllib.parse.urlencode(
                    {
                        "paper_id": "p1",
                        "question": "How does this fit my foundation and citation plan?",
                    }
                ).encode("utf-8")
                paper_ask_request = urllib.request.Request(
                    f"{base_url}/ask",
                    data=paper_ask_body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                )
                with urllib.request.urlopen(paper_ask_request, timeout=5) as response:
                    paper_ask_html = response.read().decode("utf-8")
                self.assertIn("Answered paper question for p1", paper_ask_html)
                self.assertIn("Scholar Alert Paper Workspace", paper_ask_html)
                answer_files = sorted((kb / "answers").glob("*.md"))
                self.assertEqual(len(answer_files), 2)
                selected_answers = [path for path in answer_files if "p1-how-does-this-fit" in path.name]
                self.assertEqual(len(selected_answers), 1)
                with urllib.request.urlopen(
                    f"{base_url}/answer?name={urllib.parse.quote(selected_answers[0].name)}",
                    timeout=5,
                ) as response:
                    selected_answer_body = response.read().decode("utf-8")
                self.assertIn("Selected Paper Answer", selected_answer_body)
                self.assertIn("How does this fit my foundation", selected_answer_body)
                self.assertIn("Ambient noise tomography of the Taiwan crust", selected_answer_body)
                with self.assertRaises(urllib.error.HTTPError) as raised_paper:
                    urllib.request.urlopen(f"{base_url}/paper?id=missing", timeout=5)
                raised_paper.exception.close()

                body = urllib.parse.urlencode(
                    {
                        "paper_id": "p1",
                        "action": "save_note",
                        "note": "Useful comparison for the Taiwan manuscript.",
                    }
                ).encode("utf-8")
                request = urllib.request.Request(
                    f"{base_url}/feedback",
                    data=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    html_body = response.read().decode("utf-8")
                self.assertIn("Saved feedback for p1: save_note", html_body)
                self.assertIn("reading plan:", html_body)
                self.assertTrue((kb / "reading_plan.html").exists())
                self.assertTrue((root / "DASHBOARD.html").exists())
                self.assertIn('/local?name=reading_plan', html_body)
                self.assertIn('/local?name=dashboard', html_body)
                self.assertIn('/local?name=foundation', html_body)
                self.assertIn("Useful comparison for the Taiwan manuscript.", html_body)
                with urllib.request.urlopen(f"{base_url}/local?name=reading_plan", timeout=5) as response:
                    plan_body = response.read().decode("utf-8")
                self.assertIn("Reading Plan", plan_body)
                with urllib.request.urlopen(f"{base_url}/local?name=dashboard", timeout=5) as response:
                    dashboard_body = response.read().decode("utf-8")
                self.assertIn("Scholar Alert Reader Dashboard", dashboard_body)
                with urllib.request.urlopen(f"{base_url}/local?name=foundation", timeout=5) as response:
                    foundation_body = response.read().decode("utf-8")
                self.assertIn("Foundation Library", foundation_body)
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(f"{base_url}/local?name=../VERSION", timeout=5)
                raised.exception.close()
                feedback = json.loads((kb / "feedback.json").read_text(encoding="utf-8"))
                self.assertIn("Useful comparison for the Taiwan manuscript.", feedback["papers"]["p1"]["note"])

                body = urllib.parse.urlencode({"paper_id": "p1", "action": "deep"}).encode("utf-8")
                request = urllib.request.Request(
                    f"{base_url}/feedback",
                    data=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    html_body = response.read().decode("utf-8")
                deep = kb / "analysis" / "p1_deep_read.md"
                self.assertTrue(deep.exists())
                self.assertIn("Saved feedback for p1: deep", html_body)
                self.assertIn("/report?name=p1_deep_read.md", html_body)
                with urllib.request.urlopen(f"{base_url}/report?name=p1_deep_read.md", timeout=5) as response:
                    report_body = response.read().decode("utf-8")
                self.assertIn("Your Feedback", report_body)
                self.assertIn("Useful comparison for the Taiwan manuscript.", report_body)

                body = urllib.parse.urlencode({"paper_id": "p1", "action": "workup"}).encode("utf-8")
                request = urllib.request.Request(
                    f"{base_url}/feedback",
                    data=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    html_body = response.read().decode("utf-8")
                workup = kb / "analysis" / "p1_workup.md"
                self.assertTrue(workup.exists())
                self.assertIn("Saved feedback for p1: workup", html_body)
                self.assertIn("/report?name=p1_workup.md", html_body)
                with urllib.request.urlopen(f"{base_url}/report?name=p1_workup.md", timeout=5) as response:
                    report_body = response.read().decode("utf-8")
                self.assertIn("Paper Workup", report_body)
                self.assertIn("Decision Snapshot", report_body)
                self.assertIn("Personal Note", report_body)
                self.assertIn("Useful comparison for the Taiwan manuscript.", report_body)

                body = urllib.parse.urlencode({"paper_id": "p1", "action": "review_pack"}).encode("utf-8")
                request = urllib.request.Request(
                    f"{base_url}/feedback",
                    data=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    html_body = response.read().decode("utf-8")
                review_pack = kb / "analysis" / "p1_review_pack.md"
                self.assertTrue(review_pack.exists())
                self.assertIn("Saved feedback for p1: review_pack", html_body)
                self.assertIn("/report?name=p1_review_pack.md", html_body)
                with urllib.request.urlopen(f"{base_url}/report?name=p1_review_pack.md", timeout=5) as response:
                    report_body = response.read().decode("utf-8")
                self.assertIn("Paper Review Context Pack", report_body)
                self.assertIn("Review Task For The Assistant", report_body)

                body = urllib.parse.urlencode({"paper_id": "p1", "action": "review_workflow"}).encode("utf-8")
                request = urllib.request.Request(
                    f"{base_url}/feedback",
                    data=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    html_body = response.read().decode("utf-8")
                workflow = kb / "analysis" / "p1_review_workflow.md"
                self.assertTrue(workflow.exists())
                self.assertIn("Saved feedback for p1: review_workflow", html_body)
                self.assertIn("/report?name=p1_review_workflow.md", html_body)
                self.assertIn("/report?name=p1_workup.md", html_body)
                self.assertIn("/report?name=p1_review_pack.md", html_body)
                with urllib.request.urlopen(f"{base_url}/report?name=p1_review_workflow.md", timeout=5) as response:
                    report_body = response.read().decode("utf-8")
                self.assertIn("Selected Paper Review Workflow", report_body)
                self.assertIn("Review pack", report_body)

                body = urllib.parse.urlencode({"paper_id": "p1", "action": "status_background"}).encode("utf-8")
                request = urllib.request.Request(
                    f"{base_url}/feedback",
                    data=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    html_body = response.read().decode("utf-8")
                self.assertIn("Saved feedback for p1: status_background", html_body)
                self.assertIn('data-status="background-only"', html_body)
                self.assertIn("feedback neutral", html_body)
                self.assertIn("reading background-only", html_body)
                feedback = json.loads((kb / "feedback.json").read_text(encoding="utf-8"))
                self.assertEqual(feedback["papers"]["p1"]["reading_status"], "background-only")
                self.assertEqual(feedback["papers"]["p1"]["status"], "neutral")
                self.assertFalse(feedback["papers"]["p1"]["signals"]["more_like_this"])
                self.assertFalse(feedback["papers"]["p1"]["signals"]["less_like_this"])
                self.assertFalse(
                    any("p1" in item.get("source_paper_ids", []) for item in feedback.get("terms", []))
                )
                self.assertIn("background-only", (kb / "reading_status.md").read_text(encoding="utf-8"))

                body = urllib.parse.urlencode({"paper_id": "p1", "action": "status_not_relevant"}).encode("utf-8")
                request = urllib.request.Request(
                    f"{base_url}/feedback",
                    data=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    html_body = response.read().decode("utf-8")
                self.assertIn("Saved feedback for p1: status_not_relevant", html_body)
                self.assertIn('data-status="not-relevant"', html_body)
                self.assertIn("feedback archive", html_body)
                self.assertIn("reading not-relevant", html_body)
                self.assertIn("less-like-this", html_body)
                feedback = json.loads((kb / "feedback.json").read_text(encoding="utf-8"))
                self.assertEqual(feedback["papers"]["p1"]["reading_status"], "not-relevant")
                self.assertEqual(feedback["papers"]["p1"]["status"], "archive")
                self.assertTrue(feedback["papers"]["p1"]["signals"]["less_like_this"])
                self.assertFalse(
                    any(
                        item.get("direction") == "positive" and "p1" in item.get("source_paper_ids", [])
                        for item in feedback.get("terms", [])
                    )
                )
                self.assertTrue(
                    any(
                        item.get("direction") == "negative" and "p1" in item.get("source_paper_ids", [])
                        for item in feedback.get("terms", [])
                    )
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
