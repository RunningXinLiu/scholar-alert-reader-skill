from __future__ import annotations

import argparse
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
from unittest import mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scholar_alert_reader import __version__
from scholar_alert_reader import core
from scholar_alert_reader.enrich import clean_abstract_text, openalex_abstract_text, title_similarity
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
            "crossref": {"doi": "10.0000/test", "volume": "12", "issue": "3"},
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
            self.assertIn("OPEN_REVIEW_WORKSPACE", (project / "run_reader.sh").read_text(encoding="utf-8"))
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
            serve_script = (project / "serve_reader.sh").read_text(encoding="utf-8")
            self.assertIn("reader_out/foundation/papers.json", serve_script)
            self.assertIn("reader_out/daily/papers.json", serve_script)
            self.assertTrue((project / "obsidian_export.sh").exists())
            self.assertTrue((project / "zotero_sync.sh").exists())
            self.assertTrue((project / "workup_paper.sh").exists())
            self.assertTrue((project / "full_text_paper.sh").exists())
            self.assertTrue((project / "fetch_pdf.sh").exists())
            self.assertTrue((project / "review_paper.sh").exists())
            self.assertTrue((project / "review_workflow.sh").exists())
            self.assertTrue((project / "review_queue.sh").exists())
            self.assertTrue((project / "analysis_index.sh").exists())
            self.assertTrue((project / "evidence_reader.sh").exists())
            self.assertTrue((project / "explain_ranking.sh").exists())
            self.assertTrue((project / "ranking_eval.sh").exists())
            self.assertTrue((project / "embedding_check.sh").exists())
            self.assertTrue((project / "semantic_rerank.sh").exists())
            self.assertTrue((project / "tune_profile.sh").exists())
            self.assertTrue((project / "reading_plan.sh").exists())
            self.assertTrue((project / "START_HERE.md").exists())
            self.assertTrue((project / "START_HERE.html").exists())
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
            self.assertIn("START_HERE.html", (project / ".gitignore").read_text(encoding="utf-8"))
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
            self.assertIn("Source Readiness Gate", schedule_report)
            self.assertIn("Ready for install: `False`", schedule_report)
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
            dry_run_content = dry_run_report.read_text(encoding="utf-8")
            self.assertIn("dry-run install", dry_run_content)
            self.assertIn("Source Readiness Gate", dry_run_content)
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
            self.assertIn("Open First: Review Workspace", dashboard)
            self.assertIn("Latest digest HTML", dashboard)
            self.assertIn("Review Workflow", dashboard)
            self.assertIn("Analysis index HTML", dashboard)
            self.assertIn("Source Readiness", dashboard)
            self.assertIn("Profile Health", dashboard)
            self.assertIn("Privacy check", dashboard)
            self.assertIn("Ranking evaluation", dashboard)
            self.assertIn("Embedding check", dashboard)
            self.assertIn("Semantic rerank report", dashboard)
            self.assertIn("profile_doctor.md", dashboard)
            self.assertTrue((project / "knowledge_base" / "analysis" / "analysis_index.md").exists())
            self.assertTrue((project / "knowledge_base" / "analysis" / "analysis_index.html").exists())
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

    def test_schedule_install_requires_live_source_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "reader"
            project.mkdir()
            run_script = project / "run_reader.sh"
            run_script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            run_script.chmod(0o755)
            plist_path = project / "blocked.plist"
            report_path = project / "SCHEDULE_BLOCKED.md"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "schedule",
                    "--project-dir",
                    str(project),
                    "--action",
                    "install",
                    "--output",
                    str(plist_path),
                    "--report",
                    str(report_path),
                ],
                cwd=project,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Source readiness gate failed", result.stderr)
            self.assertFalse(plist_path.exists())
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("Source Readiness Gate", report)
            self.assertIn("Gate status: `blocked`", report)
            self.assertIn("Ready for install: `False`", report)

    def test_schedule_report_passes_with_live_ok_source_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "reader"
            project.mkdir()
            run_script = project / "run_reader.sh"
            run_script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            run_script.chmod(0o755)
            (project / "SOURCE_CHECK.md").write_text(
                "\n".join(
                    [
                        "# Scholar Alert Reader Source Check",
                        "",
                        "- Requested source: `rss`",
                        "- Effective source: `rss`",
                        "- Platform: `darwin`",
                        "- Live check: `True`",
                        "",
                        "## Checks",
                        "",
                        "- [OK] RSS/Atom live read: 3 papers",
                    ]
                ),
                encoding="utf-8",
            )
            report_path = project / "DRY_RUN_SCHEDULE.md"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "schedule",
                    "--project-dir",
                    str(project),
                    "--action",
                    "install",
                    "--dry-run",
                    "--report",
                    str(report_path),
                ],
                cwd=project,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("dry-run install", result.stdout)
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("Gate status: `pass`", report)
            self.assertIn("Ready for install: `True`", report)

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
            self.assertIn("Quickstart HTML", result.stdout)
            self.assertTrue((project / "QUICKSTART_REPORT.md").exists())
            self.assertTrue((project / "QUICKSTART_REPORT.html").exists())
            self.assertTrue((project / "SOURCE_CHECK.md").exists())
            self.assertTrue((project / "DOCTOR.md").exists())
            self.assertTrue((project / "START_HERE.md").exists())
            self.assertTrue((project / "START_HERE.html").exists())
            self.assertTrue((project / "TROUBLESHOOTING.md").exists())
            report = (project / "QUICKSTART_REPORT.md").read_text(encoding="utf-8")
            self.assertIn("Result: PASS", report)
            self.assertIn("multi-source demo", report)
            self.assertIn("START_HERE.html", report)
            self.assertIn("[Dashboard](DASHBOARD.html)", report)
            self.assertIn("[Browser start guide](START_HERE.html)", report)
            self.assertIn("[Source check](SOURCE_CHECK.md)", report)
            self.assertIn("[mbox demo digest](reader_out/demo_sources/mbox/digest.html)", report)
            self.assertIn("Recommended Next Actions", report)
            self.assertIn("Copy-Paste Commands", report)
            self.assertIn("./source_check.sh --source auto --live", report)
            self.assertIn("./serve_reader.sh", report)
            report_html = (project / "QUICKSTART_REPORT.html").read_text(encoding="utf-8")
            self.assertIn("Copy-Paste Commands", report_html)
            self.assertIn('href="DASHBOARD.html"', report_html)
            self.assertIn('href="START_HERE.html"', report_html)
            self.assertIn('href="SOURCE_CHECK.md"', report_html)
            self.assertIn('href="reader_out/demo_sources/mbox/digest.html"', report_html)
            for source_name in ["mbox", "bibtex", "ris", "web", "rss"]:
                self.assertTrue((project / "reader_out" / "demo_sources" / source_name / "digest.html").exists())

    def test_quickstart_open_writes_and_opens_start_here(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "quickstart-open-reader"
            opened: list[Path] = []
            original_open = core.open_local_path
            try:
                core.open_local_path = lambda path: opened.append(path)
                core.quickstart_command(
                    argparse.Namespace(
                        project_dir=project,
                        profile_template="ai-seismology",
                        force=False,
                        skip_self_test=True,
                        skip_demos=True,
                        strict=True,
                        output=None,
                        html_output=None,
                        no_html=False,
                        open=True,
                    )
                )
            finally:
                core.open_local_path = original_open
            self.assertTrue((project / "QUICKSTART_REPORT.md").exists())
            self.assertTrue((project / "QUICKSTART_REPORT.html").exists())
            self.assertTrue((project / "START_HERE.md").exists())
            self.assertTrue((project / "START_HERE.html").exists())
            self.assertEqual(opened, [(project.resolve(strict=False) / "START_HERE.html")])

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

    def test_paper_evidence_summary_and_digest_badges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kb = root / "knowledge_base"
            kb.mkdir()
            paper_data = sample_paper()
            paper = core.paper_from_dict(paper_data)

            enriched = core.paper_evidence_summary(paper, kb)
            self.assertEqual(enriched["level"], "metadata-enriched")
            self.assertIn("OpenAlex", enriched["badges"])
            self.assertIn("Crossref", enriched["badges"])

            pdf_path = root / "paper.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")
            paper_data["metadata"]["full_text"] = {
                "pdf_url": "https://example.org/paper.pdf",
                "pdf_paths": [str(pdf_path)],
            }
            paper = core.paper_from_dict(paper_data)
            pdf_ready = core.paper_evidence_summary(paper, kb)
            self.assertEqual(pdf_ready["level"], "local-PDF-ready")
            self.assertIn("local PDF present", pdf_ready["badges"])

            (kb / "full_text").mkdir()
            (kb / "full_text" / "p1.txt").write_text("full text cache", encoding="utf-8")
            (kb / "analysis").mkdir()
            (kb / "analysis" / "p1_full_text_brief.md").write_text("# Full-Text Brief", encoding="utf-8")
            full_text_backed = core.paper_evidence_summary(paper, kb)
            self.assertEqual(full_text_backed["level"], "full-text-backed")
            self.assertIn("cached full text", full_text_backed["badges"])
            self.assertIn("full-text brief", full_text_backed["badges"])

            paper.score_components = [
                {
                    "name": "topical_relevance",
                    "value": 9.5,
                    "matched_terms": ["ambient noise", "Taiwan"],
                    "explanation": "Title matched high-priority topic terms.",
                    "evidence_field": "title",
                },
                {
                    "name": "method_relevance",
                    "value": 2.0,
                    "matched_terms": ["tomography"],
                    "explanation": "Method token overlap found.",
                    "evidence_field": "snippet",
                },
            ]

            digest = root / "out" / "digest.md"
            html_digest = root / "out" / "digest.html"
            summary = {"knowledge_base_dir": str(kb), "profile": str(root / "profile.json")}
            core.write_digest(digest, [paper], {"name": "evidence test"}, summary)
            core.write_html_digest(html_digest, [paper], {"name": "evidence test"}, summary)
            self.assertIn("Evidence: full-text-backed", digest.read_text(encoding="utf-8"))
            html_content = html_digest.read_text(encoding="utf-8")
            self.assertIn("evidence full-text-backed", html_content)
            self.assertIn("cached full text", html_content)
            digest_text = digest.read_text(encoding="utf-8")
            self.assertIn("Review Workspace", digest_text)
            self.assertIn("cannot start the local server", digest_text)
            self.assertIn("serve --profile", digest_text)
            self.assertNotIn("Use the `ID` shown under each paper", digest_text)
            self.assertNotIn("--paper-id <ID>", digest_text)
            self.assertIn("Score breakdown:", digest_text)
            self.assertIn("Topic fit", digest_text)
            self.assertIn("Method fit", digest_text)
            self.assertNotIn("topical_relevance", digest_text)
            self.assertNotIn("method_relevance", digest_text)
            self.assertIn("Review Workspace", html_content)
            self.assertIn("Open running workspace", html_content)
            self.assertIn("Step 1: start the workspace server", html_content)
            self.assertIn("cannot start the local server", html_content)
            self.assertNotIn("Use a paper ID from the badges below", html_content)
            self.assertIn("Score breakdown", html_content)

    def test_evidence_command_reports_ladder_and_selected_paper_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ladder_report = root / "evidence_ladder.md"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "evidence",
                    "--output",
                    str(ladder_report),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            ladder_content = ladder_report.read_text(encoding="utf-8")
            self.assertIn("Scholar Alert Reader Evidence Guide", ladder_content)
            self.assertIn("metadata-only", ladder_content)
            self.assertIn("full-text-backed", ladder_content)
            self.assertIn("avoid confusing quick triage", ladder_content)

            kb = root / "knowledge_base"
            (kb / "full_text").mkdir(parents=True)
            (kb / "analysis").mkdir(parents=True)
            (kb / "full_text" / "p1.txt").write_text("cached full text", encoding="utf-8")
            (kb / "analysis" / "p1_full_text_brief.md").write_text("# Full-Text Brief", encoding="utf-8")
            profile = root / "profiles" / "research_profile.json"
            profile.parent.mkdir()
            profile.write_text(json.dumps({"name": "Evidence test"}), encoding="utf-8")
            papers_json = root / "papers.json"
            papers_json.write_text(json.dumps([sample_paper()]), encoding="utf-8")
            paper_report = root / "paper_evidence.md"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "evidence",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(kb),
                    "--papers-json",
                    str(papers_json),
                    "--paper-id",
                    "p1",
                    "--output",
                    str(paper_report),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            paper_content = paper_report.read_text(encoding="utf-8")
            self.assertIn("Paper Evidence Status", paper_content)
            self.assertIn("Current evidence level: `full-text-backed`", paper_content)
            self.assertIn("Full-text cache: <project>/full_text/p1.txt (exists)", paper_content)
            self.assertIn("Review pack: <project>/analysis/p1_review_pack.md (missing)", paper_content)
            self.assertIn("Build an assistant-ready review pack", paper_content)
            self.assertIn("python3 -m scholar_alert_reader review-pack", paper_content)
            self.assertIn("Evidence Ladder", paper_content)

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
                    "matched_terms": [
                        "foundation model",
                        "continuous seismic",
                        "similar:Foundation model for continuous seismic monitoring",
                    ],
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
            feedback["terms"] = [
                {
                    "term": "dissimilar:Old earthquake report",
                    "direction": "positive",
                    "weight": 9,
                    "sources": ["paper"],
                },
                {
                    "term": "similar:Foundation model for continuous seismic monitoring",
                    "direction": "positive",
                    "weight": 9,
                    "sources": ["paper"],
                },
            ]
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
            self.assertNotIn("dissimilar:Old earthquake report", content)
            self.assertNotIn("similar:Foundation model", content)

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
            self.assertFalse(any(str(item["term"]).startswith(("similar:", "dissimilar:")) for item in tuned["focus_terms"]))

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
            paper_record = sample_paper()
            paper_record["score_components"] = [
                {
                    "name": "topical_relevance",
                    "value": 7.0,
                    "matched_terms": ["ambient noise"],
                    "explanation": "title match",
                    "evidence_field": "title",
                },
                {
                    "name": "method_relevance",
                    "value": 4.0,
                    "matched_terms": ["tomography"],
                    "explanation": "method mention",
                    "evidence_field": "snippet",
                },
            ]
            papers.write_text(json.dumps([paper_record]), encoding="utf-8")
            feedback = {
                "version": 1,
                "papers": {
                    "p1": {
                        "status": "interested",
                        "signals": {"more_like_this": True},
                    }
                },
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
            self.assertIn("#### Score Breakdown", content)
            self.assertIn("topical_relevance", content)
            self.assertIn("method_relevance", content)
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
                self.assertIn("PDF / Full-Text Access", workflow_content)
                self.assertIn("PDF/landing URL candidates:", workflow_content)
                self.assertIn(pdf_url, workflow_content)
                self.assertIn("Suggested upgrade:", workflow_content)
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

    def test_enriched_abstract_is_preferred_over_truncated_alert_snippet(self) -> None:
        from scholar_alert_reader.server import abstract_snippet_html

        reconstructed = openalex_abstract_text(
            {
                "This": [0],
                "paper": [1],
                "presents": [2],
                "a": [3],
                "complete": [4],
                "abstract.": [5],
            }
        )
        self.assertEqual(reconstructed, "This paper presents a complete abstract.")
        self.assertEqual(clean_abstract_text("<jats:p>A full abstract &amp; summary.</jats:p>"), "A full abstract & summary.")
        paper = argparse.Namespace(
            snippet="Short Scholar Alert snippet that ends with an ellipsis ...",
            metadata={"openalex": {"abstract": " ".join(["This enriched public abstract is intentionally longer."] * 12)}},
        )
        html_body = abstract_snippet_html(paper)
        self.assertIn("<strong>Abstract</strong>", html_body)
        self.assertIn("enriched public metadata abstract from OpenAlex", html_body)
        self.assertIn("This enriched public abstract", html_body)
        self.assertNotIn("Short Scholar Alert snippet", html_body)

    def test_abstract_renderer_handles_entities_latex_and_escapes_html(self) -> None:
        from scholar_alert_reader.server import abstract_snippet_html

        paper = argparse.Namespace(
            snippet="Short Scholar Alert snippet ...",
            metadata={
                "openalex": {
                    "abstract": (
                        "MIMIR-TGV$^2$ improves $L^2$ smoothing with p&lt;0.0001. "
                        "<script>alert('bad')</script>"
                    )
                }
            },
        )
        html_body = abstract_snippet_html(paper)
        self.assertIn('TGV<span class="math-inline"><sup>2</sup></span>', html_body)
        self.assertIn('<span class="math-inline">L<sup>2</sup></span>', html_body)
        self.assertIn("p&lt;0.0001", html_body)
        self.assertIn("&lt;script&gt;alert", html_body)
        self.assertNotIn("<script>alert", html_body)

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
            self.assertIn("evidence --paper-id", content)
            self.assertIn("analysis-index", content)
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
            resolved_root = root.resolve(strict=False)
            profile = root / "profiles" / "research_profile.json"
            profile.parent.mkdir(parents=True)
            profile.write_text((ROOT / "examples" / "research_profile.example.json").read_text(), encoding="utf-8")
            (root / "import.bib").write_text("@article{demo,title={Demo paper}}\n", encoding="utf-8")
            (root / "feeds.txt").write_text("https://example.org/feed.atom\n", encoding="utf-8")
            (root / "reader.env").write_text(
                "export ARXIV_QUERY='cat:physics.geo-ph'\n"
                "export WEB_SOURCE='https://example.org/article'\n"
                f"export GMAIL_CREDENTIALS='{root / 'missing_credentials.json'}'\n"
                f"export GMAIL_TOKEN='{root / 'missing_token.json'}'\n",
                encoding="utf-8",
            )
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
            self.assertIn("Recommended Next Actions", content)
            self.assertIn("Ready source: BibTeX", content)
            self.assertIn("Ready source: RSS / Atom", content)
            self.assertIn("Ready source: arXiv query", content)
            self.assertIn("Source Setup Matrix", content)
            self.assertIn("Gmail API", content)
            self.assertIn("Apple Mail", content)
            self.assertIn("Exported mbox", content)
            self.assertIn("Structured web metadata", content)
            self.assertIn("RSS / Atom", content)
            self.assertIn("arXiv query", content)
            self.assertIn("Current status", content)
            self.assertIn("Recommended action", content)
            self.assertIn(f"ready file found: `{resolved_root / 'import.bib'}`", content)
            self.assertIn(f"ready file found: `{resolved_root / 'feeds.txt'}`", content)
            self.assertIn("configured URL in `reader.env`: `https://example.org/article`", content)
            self.assertIn("configured in `reader.env`: `cat:physics.geo-ph`", content)
            self.assertIn("./source_check.sh --source gmail --live", content)
            self.assertIn("SOURCE=mbox MODE=foundation ./run_reader.sh", content)
            guide_html = root / "START_HERE.html"
            self.assertTrue(guide_html.exists())
            self.assertIn("<!doctype html>", guide_html.read_text(encoding="utf-8"))
            self.assertIn("Scholar Alert Reader Start Here", guide_html.read_text(encoding="utf-8"))

    def test_guide_recommends_setup_when_no_source_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profiles" / "research_profile.json"
            profile.parent.mkdir(parents=True)
            profile.write_text((ROOT / "examples" / "research_profile.example.json").read_text(), encoding="utf-8")
            (root / "reader.env").write_text(
                f"export GMAIL_CREDENTIALS='{root / 'missing_credentials.json'}'\n"
                f"export GMAIL_TOKEN='{root / 'missing_token.json'}'\n",
                encoding="utf-8",
            )
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
            self.assertIn("No real source looks locally ready yet", content)
            self.assertIn("Try the product with bundled sample data first", content)
            self.assertIn("export Scholar Alert mail to `INBOX.mbox`", content)

    def test_guide_open_writes_default_browser_guide(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profiles" / "research_profile.json"
            profile.parent.mkdir(parents=True)
            profile.write_text((ROOT / "examples" / "research_profile.example.json").read_text(), encoding="utf-8")
            opened: list[Path] = []
            original_open = core.open_local_path
            try:
                core.open_local_path = lambda path: opened.append(path)
                core.guide_command(
                    argparse.Namespace(
                        project_dir=root,
                        profile=None,
                        kb_dir=None,
                        out_dir=None,
                        obsidian_dir=None,
                        zotero_dir=None,
                        output=None,
                        html_output=None,
                        no_html=False,
                        open=True,
                    )
                )
            finally:
                core.open_local_path = original_open
            self.assertTrue((root / "START_HERE.md").exists())
            self.assertTrue((root / "START_HERE.html").exists())
            self.assertEqual(opened, [(root.resolve(strict=False) / "START_HERE.html")])

    def test_deep_read_open_writes_browser_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile.json"
            profile.write_text((ROOT / "examples" / "research_profile.example.json").read_text(), encoding="utf-8")
            kb = root / "kb"
            kb.mkdir()
            (kb / "library.json").write_text(json.dumps([sample_paper()]), encoding="utf-8")
            output = root / "deep.md"
            opened: list[Path] = []
            original_open = core.open_local_path
            try:
                core.open_local_path = lambda path: opened.append(path)
                core.deep_read_command(
                    argparse.Namespace(
                        profile=profile,
                        kb_dir=kb,
                        paper_id="p1",
                        title=None,
                        papers_json=None,
                        feedback_file=None,
                        output=output,
                        limit=12,
                        full_text_path=None,
                        full_text_brief_path=None,
                        max_full_text_brief_chars=7000,
                        html_output=None,
                        no_html=False,
                        open=True,
                    )
                )
            finally:
                core.open_local_path = original_open
            html_output = output.with_suffix(".html")
            self.assertTrue(output.exists())
            self.assertTrue(html_output.exists())
            self.assertIn("Evidence Boundary", html_output.read_text(encoding="utf-8"))
            self.assertEqual(opened, [html_output])

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
            self.assertIn("Evidence Boundary", deep_content)
            self.assertIn("Evidence level: `metadata-enriched`", deep_content)
            self.assertIn("Current evidence level: `metadata-enriched`", deep_content)
            self.assertIn("This report can support triage, profile fit, and discussion questions", deep_content)
            self.assertIn("review-workflow --paper-id p1 --pdf-path /path/to/paper.pdf", deep_content)
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
            (root / "SOURCE_CHECK.md").write_text(
                "\n".join(
                    [
                        "# Scholar Alert Reader Source Check",
                        "",
                        "- Requested source: `mbox`",
                        "- Effective source: `mbox`",
                        "- Platform: `darwin`",
                        "- Live check: `True`",
                        "",
                        "## Checks",
                        "",
                        "- [OK] mbox path: /tmp/reader/INBOX.mbox",
                        "- [OK] mbox parse: 2 papers from 1 Scholar messages",
                        "",
                        "## Setup Guidance",
                        "",
                        "- After a successful live check, run `./run_reader.sh`; open the Review Workspace with `./serve_reader.sh`. Use `reader_out/daily/digest.html` and `knowledge_base/reading_plan.html` as static reference pages.",
                    ]
                ),
                encoding="utf-8",
            )
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
            self.assertIn("Open First: Review Workspace", dashboard_content)
            self.assertIn("Review Workspace source JSON", dashboard_content)
            self.assertIn("Reading plan HTML", dashboard_content)
            self.assertIn("Analysis index HTML", dashboard_content)
            self.assertIn("Source Readiness", dashboard_content)
            self.assertIn("Result: `OK`", dashboard_content)
            self.assertIn("Effective source: `mbox`", dashboard_content)
            self.assertIn("mbox parse: 2 papers from 1 Scholar messages", dashboard_content)
            self.assertIn("Retained library: 1 records", dashboard_content)
            self.assertIn("Profile Health", dashboard_content)
            self.assertIn("Start Here HTML", dashboard_content)
            self.assertIn("Run `./profile_doctor.sh`", dashboard_content)
            self.assertTrue((kb / "analysis" / "analysis_index.md").exists())
            self.assertTrue((kb / "analysis" / "analysis_index.html").exists())
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
            self.assertIn("journal = {Journal}", (zotero_dir / "scholar_alert_reader.bib").read_text(encoding="utf-8"))
            self.assertIn("JO  - Journal", (zotero_dir / "scholar_alert_reader.ris").read_text(encoding="utf-8"))

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
Figure 2. Low velocity zone recovered by ambient noise tomography across the Taiwan crust.
Table 1. Inversion settings and uncertainty ranges for the preferred crustal model.

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
            self.assertTrue(full_text_report.with_suffix(".html").exists())
            self.assertIn("Full-Text Brief", full_text_report.with_suffix(".html").read_text(encoding="utf-8"))
            full_text_content = full_text_report.read_text(encoding="utf-8")
            self.assertIn("Full-Text Brief", full_text_content)
            self.assertIn("Profile Overlap", full_text_content)
            self.assertIn("Section Coverage", full_text_content)
            self.assertIn("Evidence By Section", full_text_content)
            self.assertIn("Methods Excerpt", full_text_content)
            self.assertIn("Data / Study Area Excerpt", full_text_content)
            self.assertIn("Figure And Table Captions", full_text_content)
            self.assertIn("Low velocity zone recovered by ambient noise tomography", full_text_content)
            self.assertIn("Inversion settings and uncertainty ranges", full_text_content)
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
            self.assertTrue(deep_with_full_text.with_suffix(".html").exists())
            self.assertIn("Evidence Boundary", deep_with_full_text.with_suffix(".html").read_text(encoding="utf-8"))
            deep_with_full_text_content = deep_with_full_text.read_text(encoding="utf-8")
            self.assertIn("Evidence level: `full-text-backed`", deep_with_full_text_content)
            self.assertIn("Current evidence level: `full-text-backed`", deep_with_full_text_content)
            self.assertIn("cached local full-text evidence", deep_with_full_text_content)
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
            self.assertTrue(review_pack.with_suffix(".html").exists())
            self.assertIn("Paper Review Context Pack", review_pack.with_suffix(".html").read_text(encoding="utf-8"))
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
            self.assertTrue(workup.with_suffix(".html").exists())
            self.assertIn("Paper Workup", workup.with_suffix(".html").read_text(encoding="utf-8"))
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
            self.assertTrue(workflow.with_suffix(".html").exists())
            self.assertIn("Selected Paper Review Workflow", workflow.with_suffix(".html").read_text(encoding="utf-8"))
            workflow_content = workflow.read_text(encoding="utf-8")
            self.assertIn("Selected Paper Review Workflow", workflow_content)
            self.assertIn("Full-text extraction: extracted with text-file", workflow_content)
            self.assertIn("p1_full_text_brief.html", workflow_content)
            self.assertIn("p1_workup.html", workflow_content)
            self.assertIn("p1_review_pack.html", workflow_content)
            self.assertIn("PDF / Full-Text Access", workflow_content)
            self.assertIn("Text cache: available", workflow_content)
            self.assertIn("Full-text brief: available", workflow_content)
            self.assertIn("Local PDF/text candidates: 2 (1 existing)", workflow_content)
            self.assertIn("Suggested upgrade: `./review_paper.sh --paper-id p1`", workflow_content)
            self.assertTrue((kb / "full_text" / "p1.txt").exists())
            self.assertTrue((kb / "analysis" / "p1_full_text_brief.md").exists())
            self.assertTrue((kb / "analysis" / "p1_full_text_brief.html").exists())
            self.assertTrue((kb / "analysis" / "p1_workup.md").exists())
            self.assertTrue((kb / "analysis" / "p1_workup.html").exists())
            self.assertTrue((kb / "analysis" / "p1_review_pack.md").exists())
            self.assertTrue((kb / "analysis" / "p1_review_pack.html").exists())
            self.assertIn("Local Full Text", (kb / "analysis" / "p1_review_pack.md").read_text(encoding="utf-8"))

            no_html_kb = root / "no_html_kb"
            no_html_kb.mkdir()
            (no_html_kb / "library.json").write_text(json.dumps([sample_paper()]), encoding="utf-8")
            no_html_workflow = root / "no_html_review_workflow.md"
            no_html_workup = root / "no_html_workup.md"
            no_html_pack = root / "no_html_review_pack.md"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "review-workflow",
                    "--profile",
                    str(profile),
                    "--kb-dir",
                    str(no_html_kb),
                    "--paper-id",
                    "p1",
                    "--no-extract",
                    "--no-html",
                    "--output",
                    str(no_html_workflow),
                    "--workup-output",
                    str(no_html_workup),
                    "--review-pack-output",
                    str(no_html_pack),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertTrue(no_html_workflow.exists())
            self.assertTrue(no_html_workup.exists())
            self.assertTrue(no_html_pack.exists())
            self.assertFalse(no_html_workflow.with_suffix(".html").exists())
            self.assertFalse(no_html_workup.with_suffix(".html").exists())
            self.assertFalse(no_html_pack.with_suffix(".html").exists())

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
            self.assertTrue(deep_with_default_full_text.with_suffix(".html").exists())
            deep_with_default_content = deep_with_default_full_text.read_text(encoding="utf-8")
            self.assertIn("Current evidence level: `full-text-backed`", deep_with_default_content)
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
                    "--no-extract",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            analysis_index = root / "analysis_index.md"
            analysis_index_html = root / "analysis_index.html"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "scholar_reader.py"),
                    "analysis-index",
                    "--kb-dir",
                    str(kb),
                    "--output",
                    str(analysis_index),
                    "--html-output",
                    str(analysis_index_html),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            analysis_index_content = analysis_index.read_text(encoding="utf-8")
            self.assertIn("Analysis Report Index", analysis_index_content)
            self.assertIn("Review workflows", analysis_index_content)
            self.assertIn("p1_review_workflow.html", analysis_index_content)
            self.assertIn("Paper workups", analysis_index_content)
            self.assertIn("p1_workup.html", analysis_index_content)
            self.assertIn("Review packs", analysis_index_content)
            self.assertIn("p1_review_pack.html", analysis_index_content)
            self.assertIn("Full-text briefs", analysis_index_content)
            self.assertIn("p1_full_text_brief.html", analysis_index_content)
            self.assertTrue(analysis_index_html.exists())
            self.assertIn("Analysis Report Index", analysis_index_html.read_text(encoding="utf-8"))

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
                    "--obsidian-mode",
                    "full",
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
            (papers_json.parent / "summary.json").write_text(
                json.dumps(
                    {
                        "mode": "daily",
                        "source": "gmail",
                        "source_item_count": 3,
                        "papers_in_digest": 1,
                        "library_papers": 1,
                    }
                ),
                encoding="utf-8",
            )
            (papers_json.parent / "digest.html").write_text("<h1>Daily Digest</h1>", encoding="utf-8")
            (root / "reader_out" / "foundation").mkdir(parents=True)
            (root / "reader_out" / "foundation" / "digest.html").write_text("<h1>Foundation Digest</h1>", encoding="utf-8")
            (kb / "index.html").write_text("<h1>Library Index</h1>", encoding="utf-8")
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
                self.assertIn('name="decision__p1"', initial_body)
                self.assertIn('name="priority__p1"', initial_body)
                self.assertIn('value="must_read"', initial_body)
                self.assertIn('value="background-only"', initial_body)
                self.assertIn('value="not-relevant"', initial_body)
                self.assertIn('id="status"', initial_body)
                self.assertIn('data-status="unread"', initial_body)
                self.assertIn("feedback none", initial_body)
                self.assertIn("Scholar Alert Review Workspace", initial_body)
                self.assertIn('class="title-link"', initial_body)
                self.assertIn('class="source-icon"', initial_body)
                self.assertIn('href="https://example.org/p1"', initial_body)
                self.assertIn('target="_blank"', initial_body)
                self.assertIn("Publication details", initial_body)
                self.assertIn("Journal / venue", initial_body)
                self.assertIn("Year", initial_body)
                self.assertIn("Volume", initial_body)
                self.assertIn("Issue", initial_body)
                self.assertIn(">12<", initial_body)
                self.assertIn(">3<", initial_body)
                self.assertIn("DOI", initial_body)
                self.assertIn("Source domain", initial_body)
                self.assertIn("Scholar source line", initial_body)
                self.assertIn("A Researcher, B Researcher - Journal, 2026", initial_body)
                self.assertIn("Abstract / snippet", initial_body)
                self.assertIn("Showing the full abstract/snippet text available in this source record.", initial_body)
                self.assertIn("We present ambient noise tomography for crustal structure.", initial_body)
                self.assertIn("Daily digest", initial_body)
                self.assertIn("You are reviewing the current run", initial_body)
                self.assertIn("Mode: daily", initial_body)
                self.assertIn("Source: gmail", initial_body)
                self.assertIn("Digest papers: 1", initial_body)
                self.assertIn("Retained library: 1", initial_body)
                self.assertIn('href="#must-read"', initial_body)
                self.assertIn('id="must-read"', initial_body)
                self.assertIn("Load all cards", initial_body)
                self.assertIn("Showing 1 of 1", initial_body)
                self.assertIn("Must read 1", initial_body)
                self.assertIn('/local?name=current_digest', initial_body)
                self.assertIn('/local?name=library_index', initial_body)
                self.assertIn('/local?name=foundation_digest', initial_body)
                self.assertIn("evidence metadata-enriched", initial_body)
                self.assertIn("OpenAlex", initial_body)
                self.assertIn('action="/feedback-batch"', initial_body)
                self.assertIn("Save selected changes", initial_body)
                self.assertIn('name="note__p1"', initial_body)
                self.assertIn('name="note_mode__p1"', initial_body)
                self.assertIn("Replace saved note", initial_body)
                self.assertIn("Clear saved note", initial_body)
                self.assertIn("Learning signal", initial_body)
                self.assertIn("Generate report on save", initial_body)
                self.assertIn("Improve metadata on save", initial_body)
                self.assertIn("Fetch abstract", initial_body)
                self.assertIn('name="metadata_action__p1"', initial_body)
                self.assertIn("combo-warning", initial_body)
                self.assertIn("Interested + Less like this", initial_body)
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
                self.assertIn("/local?name=answers", ask_html)
                answer_files = list((kb / "answers").glob("*.md"))
                self.assertEqual(len(answer_files), 1)
                self.assertTrue((kb / "answers_index.md").exists())
                with urllib.request.urlopen(f"{base_url}/local?name=answers", timeout=5) as response:
                    answer_index_body = response.read().decode("utf-8")
                self.assertIn("Answer Index", answer_index_body)
                self.assertIn("Library-Wide Answers", answer_index_body)
                self.assertIn("Taiwan ambient noise manuscript", answer_index_body)
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
                self.assertIn("Paper answers:", paper_ask_html)
                answer_files = sorted((kb / "answers").glob("*.md"))
                self.assertEqual(len(answer_files), 2)
                selected_answers = [path for path in answer_files if "p1-how-does-this-fit" in path.name]
                self.assertEqual(len(selected_answers), 1)
                self.assertIn(f"/answer?name={urllib.parse.quote(selected_answers[0].name)}", paper_ask_html)
                with urllib.request.urlopen(f"{base_url}/paper?id=p1", timeout=5) as response:
                    updated_workspace = response.read().decode("utf-8")
                self.assertIn("Paper answers:", updated_workspace)
                self.assertIn("How does this fit my foundation", updated_workspace)
                index_content = (kb / "answers_index.md").read_text(encoding="utf-8")
                self.assertIn("Selected-paper answers: 1", index_content)
                self.assertIn("Library-wide answers: 1", index_content)
                self.assertIn("paper `p1`", index_content)
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
                with urllib.request.urlopen(f"{base_url}/local?name=current_digest", timeout=5) as response:
                    current_digest_body = response.read().decode("utf-8")
                self.assertIn("Daily Digest", current_digest_body)
                with urllib.request.urlopen(f"{base_url}/local?name=library_index", timeout=5) as response:
                    library_index_body = response.read().decode("utf-8")
                self.assertIn("Scholar Alert Knowledge Base", library_index_body)
                with urllib.request.urlopen(f"{base_url}/local?name=foundation_digest", timeout=5) as response:
                    foundation_digest_body = response.read().decode("utf-8")
                self.assertIn("Foundation Digest", foundation_digest_body)
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
                self.assertTrue((kb / "analysis" / "p1_workup.html").exists())
                self.assertTrue((kb / "analysis" / "p1_review_pack.html").exists())
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

    def test_review_workspace_defaults_to_active_queue_and_lazy_archive(self) -> None:
        from scholar_alert_reader.server import ServerConfig, make_handler

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "reader"
            profile = root / "profiles" / "research_profile.json"
            profile.parent.mkdir(parents=True)
            profile.write_text((ROOT / "examples" / "research_profile.example.json").read_text(), encoding="utf-8")
            kb = root / "knowledge_base"
            kb.mkdir()
            papers_json = root / "reader_out" / "foundation" / "papers.json"
            papers_json.parent.mkdir(parents=True)
            active = sample_paper()
            archived = sample_paper()
            archived.update(
                {
                    "id": "p2",
                    "title": "Low-priority archive-only paper",
                    "url": "https://example.org/p2",
                    "tier": "Archive",
                    "score": 1,
                }
            )
            papers_json.write_text(json.dumps([active, archived]), encoding="utf-8")
            (papers_json.parent / "summary.json").write_text(
                json.dumps(
                    {
                        "mode": "foundation",
                        "source": "gmail",
                        "source_item_count": 2,
                        "papers_in_digest": 2,
                        "library_papers": 1,
                    }
                ),
                encoding="utf-8",
            )
            config = ServerConfig(profile_path=profile, kb_dir=kb, papers_json=papers_json)
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(config))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base_url = f"http://127.0.0.1:{server.server_port}"
                with urllib.request.urlopen(base_url, timeout=5) as response:
                    body = response.read().decode("utf-8")
                    self.assertEqual(response.headers.get("Connection"), "close")
                self.assertIn("Active review queue", body)
                self.assertIn("Showing: 1 of 2", body)
                self.assertIn("Ambient noise tomography", body)
                self.assertNotIn("Low-priority archive-only paper", body)
                self.assertIn('/?view=archive#archive', body)

                with urllib.request.urlopen(f"{base_url}/feedback-batch", timeout=5) as response:
                    batch_get_body = response.read().decode("utf-8")
                self.assertIn("Scholar Alert Review Workspace", batch_get_body)
                self.assertIn("Ambient noise tomography", batch_get_body)

                with urllib.request.urlopen(f"{base_url}/?view=archive", timeout=5) as response:
                    archive_body = response.read().decode("utf-8")
                self.assertIn("Archive review", archive_body)
                self.assertIn("Showing: 1 of 2", archive_body)
                self.assertIn("Low-priority archive-only paper", archive_body)

                batch_body = urllib.parse.urlencode(
                    {
                        "view": "active",
                        "paper_id": ["p1", "p2"],
                        "decision__p1": "interested",
                        "priority__p1": "must_read",
                        "signal_more__p1": "1",
                        "note__p2": "Keep a note without choosing an action.",
                    },
                    doseq=True,
                ).encode("utf-8")
                batch_request = urllib.request.Request(
                    f"{base_url}/feedback-batch",
                    data=batch_body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                )
                with urllib.request.urlopen(batch_request, timeout=5) as response:
                    batch_response = response.read().decode("utf-8")
                self.assertIn("Saved 2 selected changes", batch_response)
                feedback = json.loads((kb / "feedback.json").read_text(encoding="utf-8"))
                self.assertEqual(feedback["papers"]["p1"]["status"], "interested")
                self.assertEqual(feedback["papers"]["p1"]["priority_override"], "must_read")
                self.assertTrue(feedback["papers"]["p1"]["signals"]["more_like_this"])
                self.assertIn("Keep a note without choosing an action.", feedback["papers"]["p2"]["note"])

                replace_note_body = urllib.parse.urlencode(
                    {
                        "view": "active",
                        "paper_id": ["p2"],
                        "note_mode__p2": "replace",
                        "note__p2": "Replacement note.",
                    },
                    doseq=True,
                ).encode("utf-8")
                replace_note_request = urllib.request.Request(
                    f"{base_url}/feedback-batch",
                    data=replace_note_body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                )
                with urllib.request.urlopen(replace_note_request, timeout=5) as response:
                    replace_note_response = response.read().decode("utf-8")
                self.assertIn("Saved 1 selected change", replace_note_response)
                feedback = json.loads((kb / "feedback.json").read_text(encoding="utf-8"))
                self.assertEqual(feedback["papers"]["p2"]["note"], "Replacement note.")

                clear_note_body = urllib.parse.urlencode(
                    {
                        "view": "active",
                        "paper_id": ["p2"],
                        "note_mode__p2": "clear",
                    },
                    doseq=True,
                ).encode("utf-8")
                clear_note_request = urllib.request.Request(
                    f"{base_url}/feedback-batch",
                    data=clear_note_body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                )
                with urllib.request.urlopen(clear_note_request, timeout=5) as response:
                    clear_note_response = response.read().decode("utf-8")
                self.assertIn("Saved 1 selected change", clear_note_response)
                feedback = json.loads((kb / "feedback.json").read_text(encoding="utf-8"))
                self.assertNotIn("note", feedback["papers"]["p2"])

                warning_body = urllib.parse.urlencode(
                    {
                        "view": "active",
                        "paper_id": ["p1"],
                        "decision__p1": "interested",
                        "signal_less__p1": "1",
                    },
                    doseq=True,
                ).encode("utf-8")
                warning_request = urllib.request.Request(
                    f"{base_url}/feedback-batch",
                    data=warning_body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                )
                with urllib.request.urlopen(warning_request, timeout=5) as response:
                    warning_response = response.read().decode("utf-8")
                self.assertIn("unusual combinations noted: 1", warning_response)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_review_workspace_caps_large_default_batch(self) -> None:
        from scholar_alert_reader.server import DEFAULT_WORKSPACE_CARD_LIMIT, ServerConfig, make_handler

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "reader"
            profile = root / "profiles" / "research_profile.json"
            profile.parent.mkdir(parents=True)
            profile.write_text((ROOT / "examples" / "research_profile.example.json").read_text(), encoding="utf-8")
            kb = root / "knowledge_base"
            kb.mkdir()
            papers_json = root / "reader_out" / "foundation" / "papers.json"
            papers_json.parent.mkdir(parents=True)
            papers = []
            must = sample_paper()
            must.update({"id": "must-1", "title": "Must-read foundation model paper", "tier": "Must read", "score": 30})
            papers.append(must)
            for index in range(DEFAULT_WORKSPACE_CARD_LIMIT + 40):
                paper = sample_paper()
                paper.update(
                    {
                        "id": f"skim-{index}",
                        "title": f"Skim paper {index}",
                        "url": f"https://example.org/skim-{index}",
                        "tier": "Skim",
                        "score": 10,
                    }
                )
                papers.append(paper)
            papers_json.write_text(json.dumps(papers), encoding="utf-8")
            config = ServerConfig(profile_path=profile, kb_dir=kb, papers_json=papers_json)
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(config))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base_url = f"http://127.0.0.1:{server.server_port}"
                with urllib.request.urlopen(base_url, timeout=5) as response:
                    body = response.read().decode("utf-8")
                self.assertIn("Showing a lighter review batch", body)
                self.assertIn(f"Showing: {DEFAULT_WORKSPACE_CARD_LIMIT} of {len(papers)}", body)
                self.assertIn("Must-read foundation model paper", body)
                self.assertIn("Skim paper 0", body)
                self.assertNotIn(f"Skim paper {DEFAULT_WORKSPACE_CARD_LIMIT + 39}", body)

                with urllib.request.urlopen(f"{base_url}/?view=all", timeout=5) as response:
                    full_body = response.read().decode("utf-8")
                self.assertNotIn("Showing a lighter review batch", full_body)
                self.assertIn(f"Skim paper {DEFAULT_WORKSPACE_CARD_LIMIT + 39}", full_body)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_review_workspace_fetch_abstract_metadata_action(self) -> None:
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
            paper = sample_paper()
            paper["snippet"] = "Short Scholar Alert snippet ..."
            paper["metadata"] = {}
            papers_json.write_text(json.dumps([paper]), encoding="utf-8")

            def fake_enrich_record(record, providers, email, user_agent, timeout):
                updated = dict(record)
                metadata = dict(updated.get("metadata") or {})
                metadata["openalex"] = {
                    "source": "Journal of Useful Abstracts",
                    "publication_year": 2026,
                    "abstract": " ".join(["This public abstract is complete enough for review."] * 16),
                }
                updated["metadata"] = metadata
                return updated, {"openalex": 1, "crossref": 0, "errors": 0}

            config = ServerConfig(profile_path=profile, kb_dir=kb, papers_json=papers_json)
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(config))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base_url = f"http://127.0.0.1:{server.server_port}"
                body = urllib.parse.urlencode(
                    {
                        "view": "active",
                        "paper_id": ["p1"],
                        "metadata_action__p1": "abstract",
                    },
                    doseq=True,
                ).encode("utf-8")
                request = urllib.request.Request(
                    f"{base_url}/feedback-batch",
                    data=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                )
                with mock.patch("scholar_alert_reader.enrich.enrich_record", side_effect=fake_enrich_record):
                    with urllib.request.urlopen(request, timeout=5) as response:
                        response_body = response.read().decode("utf-8")
                self.assertIn("Saved metadata request", response_body)
                self.assertIn("public metadata checked: 1, updated: 1, abstracts available: 1", response_body)
                self.assertIn("<strong>Abstract</strong>", response_body)
                self.assertIn("This public abstract is complete enough for review", response_body)
                self.assertIn("enriched public metadata abstract from OpenAlex", response_body)
                stored = json.loads(papers_json.read_text(encoding="utf-8"))
                self.assertIn("abstract", stored[0]["metadata"]["openalex"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
