"""Local diagnostics for Scholar Alert Reader installations."""

from __future__ import annotations

import importlib.util
import json
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def exists_check(name: str, path: Path, required: bool = True) -> Check:
    exists = path.exists()
    ok = exists or not required
    if exists:
        detail = str(path)
    elif required:
        detail = f"missing: {path}"
    else:
        detail = f"optional missing: {path}"
    return Check(name, ok, detail)


def json_count(path: Path) -> tuple[int, str]:
    if not path.exists():
        return 0, "missing"
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return 0, f"invalid JSON: {exc}"
    if isinstance(data, list):
        return len(data), "list"
    if isinstance(data, dict):
        if "seen_ids" in data and isinstance(data["seen_ids"], list):
            return len(data["seen_ids"]), "seen ids"
        if "papers" in data and isinstance(data["papers"], dict):
            return len(data["papers"]), "paper feedback"
        if "terms" in data and isinstance(data["terms"], list):
            return len(data["terms"]), "feedback terms"
        return len(data), "object keys"
    return 0, type(data).__name__


def dependency_check(module_name: str) -> Check:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            found = importlib.util.find_spec(module_name) is not None
        except ModuleNotFoundError:
            found = False
    return Check(f"python module {module_name}", found, "installed" if found else "not installed")


def diagnose(
    profile: Path | None,
    kb_dir: Path | None,
    gmail_credentials: Path,
    gmail_token: Path,
    out_dir: Path | None,
    check_gmail_deps: bool,
    obsidian_dir: Path | None = None,
    zotero_dir: Path | None = None,
) -> tuple[list[Check], list[str]]:
    checks: list[Check] = []
    notes: list[str] = []

    if profile:
        checks.append(exists_check("profile", profile))
    else:
        notes.append("No --profile provided; profile-specific defaults were not checked.")

    if kb_dir:
        checks.append(exists_check("knowledge base directory", kb_dir, required=False))
        for filename in ["library.json", "feedback.json", "weekly_review.md"]:
            path = kb_dir / filename
            checks.append(exists_check(filename, path, required=False))
            if path.suffix == ".json":
                count, kind = json_count(path)
                notes.append(f"{filename}: {count} {kind}")
        for directory in ["papers", "directions"]:
            checks.append(exists_check(directory, kb_dir / directory, required=False))

    if out_dir:
        checks.append(exists_check("output directory", out_dir, required=False))
        for filename in ["digest.md", "digest.html", "papers.json", "summary.json"]:
            checks.append(exists_check(f"output {filename}", out_dir / filename, required=False))

    checks.append(exists_check("gmail credentials", gmail_credentials, required=False))
    checks.append(exists_check("gmail token", gmail_token, required=False))

    if zotero_dir:
        checks.append(exists_check("zotero export directory", zotero_dir, required=False))
        checks.append(exists_check("zotero BibTeX", zotero_dir / "scholar_alert_reader.bib", required=False))
        checks.append(exists_check("zotero RIS", zotero_dir / "scholar_alert_reader.ris", required=False))
    else:
        notes.append("No --zotero-dir provided; Zotero integration is optional.")

    if obsidian_dir:
        checks.append(exists_check("obsidian export directory", obsidian_dir, required=False))
        checks.append(exists_check("obsidian dashboard", obsidian_dir / "00_Dashboard" / "Scholar Alert Dashboard.md", required=False))
        checks.append(exists_check("obsidian paper notes", obsidian_dir / "01_Papers", required=False))
    else:
        notes.append("No --obsidian-dir provided; Obsidian integration is optional.")

    if check_gmail_deps:
        for module_name in [
            "googleapiclient",
            "google.oauth2.credentials",
            "google_auth_oauthlib.flow",
        ]:
            checks.append(dependency_check(module_name))

    return checks, notes


def render_checks(checks: list[Check], notes: list[str]) -> str:
    lines = ["# Scholar Alert Reader Doctor", ""]
    for check in checks:
        marker = "OK" if check.ok else "WARN"
        lines.append(f"- [{marker}] {check.name}: {check.detail}")
    if notes:
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in notes)
    return "\n".join(lines).rstrip() + "\n"
