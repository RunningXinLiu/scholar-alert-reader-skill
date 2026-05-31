"""Local Review Workspace for Scholar Alert Reader."""

from __future__ import annotations

import html
import re
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse


@dataclass
class ServerConfig:
    profile_path: Path
    kb_dir: Path
    papers_json: Path
    host: str = "127.0.0.1"
    port: int = 8765
    open_browser: bool = False


def render_badge(value: str) -> str:
    return f'<span class="badge">{html.escape(value)}</span>'


def paper_feedback_item(feedback: dict[str, Any] | None, paper_id: str) -> dict[str, Any]:
    if not isinstance(feedback, dict):
        return {}
    papers = feedback.get("papers", {})
    if not isinstance(papers, dict):
        return {}
    item = papers.get(paper_id, {})
    return item if isinstance(item, dict) else {}


def paper_reading_status(paper: Any, feedback: dict[str, Any] | None) -> str:
    item = paper_feedback_item(feedback, str(getattr(paper, "id", "")))
    reading_status = str(item.get("reading_status", "") or "")
    if reading_status:
        return reading_status
    status = str(item.get("status", "") or "")
    if status == "archive":
        return "not-relevant"
    return "unread"


def paper_priority_override(paper: Any, feedback: dict[str, Any] | None) -> str:
    item = paper_feedback_item(feedback, str(getattr(paper, "id", "")))
    value = str(item.get("priority_override", "") or "").strip().lower().replace("-", "_")
    if value in {"must_read", "skim", "archive"}:
        return value
    return ""


def feedback_badges(paper: Any, feedback: dict[str, Any] | None) -> str:
    item = paper_feedback_item(feedback, str(getattr(paper, "id", "")))
    if not item:
        return '<div class="badges feedback-badges">' + render_badge("feedback none") + render_badge("reading unread") + "</div>"
    values = [
        f"feedback {item.get('status', 'neutral')}",
        f"reading {paper_reading_status(paper, feedback)}",
    ]
    priority_override = paper_priority_override(paper, feedback)
    if priority_override:
        values.append(f"priority {priority_override.replace('_', ' ')}")
    labels = item.get("labels", [])
    if isinstance(labels, list):
        values.extend(f"label {label}" for label in labels if str(label).strip())
    signals = item.get("signals", {})
    if isinstance(signals, dict):
        if signals.get("more_like_this"):
            values.append("more-like-this")
        if signals.get("less_like_this"):
            values.append("less-like-this")
    return '<div class="badges feedback-badges">' + "".join(render_badge(str(value)) for value in values) + "</div>"


def paper_feedback_note_html(paper: Any, feedback: dict[str, Any] | None) -> str:
    item = paper_feedback_item(feedback, str(getattr(paper, "id", "")))
    note = str(item.get("note", "") or "").strip()
    if not note:
        return ""
    return '<div class="note"><strong>Note</strong><pre>' + html.escape(note) + "</pre></div>"


def append_feedback_note(record: dict[str, Any], note: str | None) -> None:
    clean_note = str(note or "").strip()
    if not clean_note:
        return
    existing = str(record.get("note", "") or "").strip()
    existing_lines = [line for line in existing.splitlines() if line.strip()]
    if clean_note not in existing_lines:
        existing_lines.append(clean_note)
    record["note"] = "\n".join(existing_lines)


def update_feedback_note(record: dict[str, Any], generated_note: str | None, user_note: str | None, note_mode: str = "") -> bool:
    mode = str(note_mode or "").strip().lower().replace("-", "_")
    clean_generated = str(generated_note or "").strip()
    clean_user = str(user_note or "").strip()
    before = str(record.get("note", "") or "").strip()
    if mode == "clear":
        record.pop("note", None)
        return bool(before)
    if mode == "replace":
        lines = []
        for note in [clean_generated, clean_user]:
            if note and note not in lines:
                lines.append(note)
        if lines:
            record["note"] = "\n".join(lines)
        return str(record.get("note", "") or "").strip() != before
    append_feedback_note(record, clean_generated)
    append_feedback_note(record, clean_user)
    return str(record.get("note", "") or "").strip() != before


def select_options(options: list[tuple[str, str]], selected: str = "") -> str:
    parts = []
    for value, label in options:
        selected_attr = ' selected' if value == selected else ""
        parts.append(f'<option value="{html.escape(value, quote=True)}"{selected_attr}>{html.escape(label)}</option>')
    return "".join(parts)


def review_select(name: str, label: str, options: list[tuple[str, str]], help_text: str = "") -> str:
    help_html = f'<span class="control-help">{html.escape(help_text)}</span>' if help_text else ""
    return (
        '<label class="review-field">'
        f"<span>{html.escape(label)}</span>"
        f'<select class="review-select" name="{html.escape(name, quote=True)}">'
        + select_options(options)
        + "</select>"
        + help_html
        + "</label>"
    )


def review_checkbox(name: str, label: str, css_class: str = "") -> str:
    classes = "review-checkbox" + (f" {css_class}" if css_class else "")
    return (
        f'<label class="{classes}">'
        f'<input type="checkbox" name="{html.escape(name, quote=True)}" value="1">'
        f"<span>{html.escape(label)}</span>"
        "</label>"
    )


def feedback_combination_warnings(
    decision: str,
    priority: str,
    reading_status: str,
    signal_more: bool,
    signal_less: bool,
) -> list[str]:
    decision = decision.strip().lower()
    priority = priority.strip().lower().replace("-", "_")
    reading_status = reading_status.strip().lower()
    warnings: list[str] = []
    if decision == "interested" and signal_less:
        warnings.append("Interested + Less like this keeps this paper but downranks similar future papers.")
    if decision == "archive" and signal_more:
        warnings.append("Archive + More like this archives this paper but boosts similar future papers.")
    if priority == "archive" and signal_more:
        warnings.append("Priority Archive + More like this is unusual; archive priority wins for this paper.")
    if priority == "must_read" and signal_less:
        warnings.append("Must read + Less like this is unusual; this paper stays prioritized but similar papers are downranked.")
    if reading_status == "not-relevant" and signal_more:
        warnings.append("Not relevant + More like this is unusual; not-relevant archives this paper.")
    if reading_status == "background-only" and signal_more:
        warnings.append("Background only + More like this is unusual; background-only usually clears ranking signals.")
    if decision == "archive" and priority in {"must_read", "skim"}:
        warnings.append("Archive decision conflicts with a reading priority; Archive wins for ranking.")
    return warnings


def feedback_action_state(action: str) -> dict[str, Any]:
    state: dict[str, Any] = {
        "mark": None,
        "more_like_this": False,
        "less_like_this": False,
        "note": None,
        "reading_status": None,
        "labels": [],
    }
    if action in {"", "save_note"}:
        return state
    if action == "interested_more":
        state.update({"mark": "interested", "more_like_this": True})
    elif action == "archive_less":
        state.update({"mark": "archive", "less_like_this": True, "reading_status": "not-relevant"})
    elif action == "more":
        state["more_like_this"] = True
    elif action == "less":
        state["less_like_this"] = True
    elif action == "deep":
        state.update(
            {
                "mark": "interested",
                "more_like_this": True,
                "reading_status": "reading",
                "note": "Queued for deep reading from Review Workspace.",
            }
        )
    elif action == "workup":
        state.update(
            {
                "mark": "interested",
                "more_like_this": True,
                "reading_status": "reading",
                "note": "Queued for workup from Review Workspace.",
            }
        )
    elif action == "review_pack":
        state.update(
            {
                "mark": "interested",
                "more_like_this": True,
                "reading_status": "reading",
                "note": "Queued for review pack from Review Workspace.",
            }
        )
    elif action == "review_workflow":
        state.update(
            {
                "mark": "interested",
                "more_like_this": True,
                "reading_status": "reading",
                "note": "Queued for full review workflow from Review Workspace.",
            }
        )
    elif action == "status_reading":
        state.update({"mark": "interested", "reading_status": "reading"})
    elif action == "status_read":
        state.update({"mark": "interested", "reading_status": "read"})
    elif action == "status_must_cite":
        state.update({"mark": "interested", "reading_status": "must-cite", "labels": ["must-cite"]})
    elif action == "status_method":
        state.update({"mark": "interested", "reading_status": "method-reference", "labels": ["method-reference"]})
    elif action == "status_background":
        state.update(
            {
                "mark": "neutral",
                "reading_status": "background-only",
                "note": "Marked as background only from Review Workspace.",
            }
        )
    elif action == "status_not_relevant":
        state.update(
            {
                "mark": "archive",
                "less_like_this": True,
                "reading_status": "not-relevant",
                "note": "Marked as not relevant from Review Workspace.",
            }
        )
    return state


def domain_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
    except Exception:
        return ""
    return parsed.netloc.replace("www.", "")


def favicon_url(url: str) -> str:
    domain = domain_from_url(url)
    if not domain:
        return ""
    return f"https://www.google.com/s2/favicons?domain={html.escape(domain, quote=True)}&sz=64"


def source_icon_html(paper: Any) -> str:
    url = str(getattr(paper, "url", "") or "")
    icon = favicon_url(url)
    domain = domain_from_url(url)
    if icon:
        label = f"Source icon: {domain}" if domain else "Source icon"
        return f'<img class="source-icon" alt="{html.escape(label, quote=True)}" title="{html.escape(label, quote=True)}" src="{icon}">'
    tier = str(getattr(paper, "tier", "") or "?").strip()[:1] or "?"
    return f'<div class="source-icon source-icon-placeholder" title="No source icon available">{html.escape(tier)}</div>'


def _clean_metadata_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        values = [_clean_metadata_value(item) for item in value]
        return ", ".join(item for item in values if item)
    if isinstance(value, dict):
        if "date-parts" in value:
            return _clean_metadata_value(value.get("date-parts"))
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.startswith("https://doi.org/"):
        text = text.removeprefix("https://doi.org/")
    return re.sub(r"\s+", " ", text)


def _nested_metadata(metadata: dict[str, Any], key: str) -> dict[str, Any]:
    item = metadata.get(key)
    return item if isinstance(item, dict) else {}


def _first_metadata_value(*values: Any) -> str:
    for value in values:
        cleaned = _clean_metadata_value(value)
        if cleaned:
            return cleaned
    return ""


def parse_authors_source(authors_source: str) -> dict[str, str]:
    cleaned = re.sub(r"\s+[-–—]\s+", " - ", authors_source or "").strip()
    parts = [part.strip() for part in cleaned.split(" - ", 1)]
    authors = parts[0] if parts else ""
    source_line = parts[1] if len(parts) > 1 else ""
    year_match = re.search(r"\b(?:19|20)\d{2}\b", source_line or cleaned)
    year = year_match.group(0) if year_match else ""
    venue = source_line
    if year:
        venue = re.sub(r",?\s*\b(?:19|20)\d{2}\b\s*$", "", venue).strip(" ,;")
    return {"authors": authors, "venue": venue, "year": year}


def publication_metadata_values(paper: Any) -> dict[str, str]:
    metadata = getattr(paper, "metadata", {}) or {}
    if not isinstance(metadata, dict):
        metadata = {}
    openalex = _nested_metadata(metadata, "openalex")
    crossref = _nested_metadata(metadata, "crossref")
    bibtex = _nested_metadata(metadata, "bibtex")
    ris = _nested_metadata(metadata, "ris")
    web = _nested_metadata(metadata, "web")
    feed = _nested_metadata(metadata, "feed")
    parsed = parse_authors_source(str(getattr(paper, "authors_source", "") or ""))

    venue = _first_metadata_value(
        openalex.get("source"),
        openalex.get("host_venue"),
        crossref.get("container_title"),
        crossref.get("short-container-title"),
        bibtex.get("journal"),
        bibtex.get("booktitle"),
        ris.get("journal"),
        ris.get("source"),
        web.get("journal"),
        web.get("citation_journal_title"),
        feed.get("source"),
        parsed.get("venue"),
    )
    year = _first_metadata_value(
        openalex.get("publication_year"),
        crossref.get("year"),
        crossref.get("published-print"),
        crossref.get("published-online"),
        crossref.get("issued"),
        bibtex.get("year"),
        ris.get("year"),
        web.get("year"),
        web.get("citation_publication_date"),
        feed.get("year"),
        parsed.get("year"),
    )
    year_match = re.search(r"\b(?:19|20)\d{2}\b", year)
    if year_match:
        year = year_match.group(0)
    volume = _first_metadata_value(crossref.get("volume"), bibtex.get("volume"), ris.get("volume"), web.get("volume"), web.get("citation_volume"))
    issue = _first_metadata_value(crossref.get("issue"), bibtex.get("number"), bibtex.get("issue"), ris.get("issue"), web.get("issue"), web.get("citation_issue"))
    pages = _first_metadata_value(crossref.get("page"), bibtex.get("pages"), ris.get("pages"), web.get("pages"), web.get("citation_firstpage"))
    doi = _first_metadata_value(crossref.get("doi"), openalex.get("doi"), bibtex.get("doi"), ris.get("doi"), web.get("doi"), web.get("citation_doi"))
    domain = domain_from_url(str(getattr(paper, "url", "") or ""))
    return {
        "venue": venue,
        "year": year,
        "volume": volume,
        "issue": issue,
        "pages": pages,
        "doi": doi,
        "domain": domain,
    }


def publication_metadata(paper: Any) -> list[tuple[str, str]]:
    values = publication_metadata_values(paper)
    fields = [
        ("Journal / venue", values["venue"]),
        ("Year", values["year"]),
        ("Volume", values["volume"]),
        ("Issue", values["issue"]),
        ("Pages", values["pages"]),
        ("DOI", values["doi"]),
        ("Source domain", values["domain"]),
    ]
    return [(label, value) for label, value in fields if value]


def publication_metadata_html(paper: Any) -> str:
    values = publication_metadata_values(paper)
    core_fields = [
        ("Journal / venue", values["venue"] or "Unavailable from current alert/metadata"),
        ("Year", values["year"] or "Unavailable from current alert/metadata"),
        ("Volume", values["volume"] or "Unavailable from current alert/metadata"),
        ("Issue", values["issue"] or "Unavailable from current alert/metadata"),
    ]
    optional_fields = [
        ("Pages", values["pages"]),
        ("DOI", values["doi"]),
        ("Source domain", values["domain"]),
    ]
    fields = core_fields + [(label, value) for label, value in optional_fields if value]
    items = "".join(
        f'<div class="pub-field"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>'
        for label, value in fields
    )
    return f'<div class="publication-meta"><strong>Publication details</strong><div class="pub-grid">{items}</div></div>'


def scholar_source_line_html(paper: Any) -> str:
    source_line = str(getattr(paper, "authors_source", "") or "").strip()
    if not source_line:
        return ""
    return (
        '<p class="source-line"><strong>Scholar source line</strong>'
        f"<span>{html.escape(source_line)}</span></p>"
    )


def abstract_snippet_html(paper: Any) -> str:
    snippet = str(getattr(paper, "snippet", "") or "").strip()
    if not snippet:
        return '<div class="snippet-block missing"><strong>Abstract / snippet</strong><p>No abstract or alert snippet is available.</p></div>'
    label = "Abstract / snippet"
    source_truncated = snippet.endswith("…") or snippet.endswith("...")
    hint = (
        '<div class="snippet-hint">The source record already ends with an ellipsis; the UI is showing all text available from the alert/source item.</div>'
        if source_truncated
        else '<div class="snippet-hint">Showing the full abstract/snippet text available in this source record.</div>'
    )
    return f'<div class="snippet-block"><strong>{html.escape(label)}</strong><p>{html.escape(snippet)}</p>{hint}</div>'


def paper_metadata_summary(paper: Any) -> str:
    metadata = getattr(paper, "metadata", {}) or {}
    openalex = metadata.get("openalex") if isinstance(metadata, dict) else None
    crossref = metadata.get("crossref") if isinstance(metadata, dict) else None
    items: list[str] = []
    if isinstance(openalex, dict):
        if openalex.get("publication_year"):
            items.append(f"year {openalex.get('publication_year')}")
        if openalex.get("cited_by_count") is not None:
            items.append(f"cited by {openalex.get('cited_by_count')}")
        if openalex.get("source"):
            items.append(str(openalex.get("source")))
    if isinstance(crossref, dict) and crossref.get("doi"):
        items.append(f"DOI {crossref.get('doi')}")
    return " · ".join(items)


def paper_title_html(paper: Any) -> str:
    title = html.escape(str(getattr(paper, "title", "")))
    url = str(getattr(paper, "url", "") or "").strip()
    icon = source_icon_html(paper)
    if not url:
        return f'<div class="paper-heading">{icon}<h2>{title}</h2></div>'
    return (
        f'<div class="paper-heading">{icon}<h2><a class="title-link" '
        f'href="{html.escape(url, quote=True)}" target="_blank" rel="noreferrer">{title}</a></h2></div>'
    )


def paper_evidence_html(paper: Any, config: ServerConfig) -> str:
    from . import core

    summary = core.paper_evidence_summary(paper, config.kb_dir)
    badges = [f"evidence {summary['level']}"]
    badges.extend(str(item) for item in summary["badges"][1:8])
    return (
        '<div class="badges evidence-badges">'
        + "".join(render_badge(value) for value in badges)
        + "</div>"
        + f'<p class="evidence-note">{html.escape(str(summary["description"]))}</p>'
    )


def report_links(paper_id: str, config: ServerConfig) -> str:
    analysis_dir = config.kb_dir / "analysis"
    reports = [
        ("Deep read", f"{paper_id}_deep_read.md"),
        ("Review workflow", f"{paper_id}_review_workflow.md"),
        ("Workup", f"{paper_id}_workup.md"),
        ("Full-text brief", f"{paper_id}_full_text_brief.md"),
        ("Review pack", f"{paper_id}_review_pack.md"),
    ]
    links = []
    for label, filename in reports:
        path = analysis_dir / filename
        if path.exists():
            links.append(f'<a href="/report?name={quote(filename, safe="")}">{html.escape(label)}</a>')
    if not links:
        return ""
    return '<p class="reports">Reports: ' + " · ".join(links) + "</p>"


def markdown_title_fallback(path: Path, content: str) -> str:
    for line in content.splitlines():
        cleaned = line.strip()
        if cleaned.startswith("# "):
            title = cleaned[2:].strip()
            title = title.removeprefix("Selected Paper Answer:").strip()
            if len(title) > 90:
                return title[:87].rstrip() + "..."
            return title or path.stem
    return path.stem


def selected_answer_links(paper_id: str, config: ServerConfig, limit: int = 5) -> str:
    answers_dir = config.kb_dir / "answers"
    if not answers_dir.exists():
        return ""
    marker = f"Target paper: `{paper_id}`"
    links: list[str] = []
    for path in sorted(answers_dir.glob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if marker not in content:
            continue
        label = markdown_title_fallback(path, content)
        links.append(f'<a href="/answer?name={quote(path.name, safe="")}">{html.escape(label)}</a>')
        if len(links) >= limit:
            break
    if not links:
        return ""
    return '<p class="reports">Paper answers: ' + " · ".join(links) + "</p>"


def safe_report_path(config: ServerConfig, name: str) -> Path | None:
    if not name or "/" in name or "\\" in name or not name.endswith(".md"):
        return None
    analysis_dir = (config.kb_dir / "analysis").resolve()
    report_path = (analysis_dir / name).resolve()
    try:
        report_path.relative_to(analysis_dir)
    except ValueError:
        return None
    return report_path


def safe_answer_path(config: ServerConfig, name: str) -> Path | None:
    if not name or "/" in name or "\\" in name or not name.endswith(".md"):
        return None
    answers_dir = (config.kb_dir / "answers").resolve()
    answer_path = (answers_dir / name).resolve()
    try:
        answer_path.relative_to(answers_dir)
    except ValueError:
        return None
    return answer_path


def local_file_targets(config: ServerConfig) -> list[tuple[str, str, Path]]:
    from . import core

    project_dir = core.infer_project_dir(config.profile_path, config.kb_dir, config.papers_json)
    out_dir = config.papers_json.parent
    candidates: list[tuple[str, str, Path | None]] = [
        ("current_digest", "Current digest", out_dir / "digest.html"),
        ("library_index", "Library index", config.kb_dir / "index.html"),
        ("reading_plan", "Reading plan", config.kb_dir / "reading_plan.html"),
        ("foundation", "Foundation", config.kb_dir / "foundation.md"),
        ("interested", "Interested", config.kb_dir / "interested.md"),
        ("reading_status", "Reading status", config.kb_dir / "reading_status.md"),
        ("weekly_review", "Weekly review", config.kb_dir / "weekly_review.md"),
        ("answers", "Answers", config.kb_dir / "answers_index.md"),
    ]
    if project_dir:
        candidates.insert(0, ("dashboard", "Dashboard", project_dir / "DASHBOARD.html"))
        candidates.extend(
            [
                ("daily_digest", "Daily digest", project_dir / "reader_out" / "daily" / "digest.html"),
                ("foundation_digest", "Foundation digest", project_dir / "reader_out" / "foundation" / "digest.html"),
            ]
        )
    seen: set[str] = set()
    targets: list[tuple[str, str, Path]] = []
    for key, label, path in candidates:
        if path is None or not path.exists() or key in seen:
            continue
        seen.add(key)
        targets.append((key, label, path))
    return targets


def local_nav_links(config: ServerConfig) -> str:
    links = [
        f'<a href="/local?name={quote(key, safe="")}">{html.escape(label)}</a>'
        for key, label, _ in local_file_targets(config)
    ]
    if not links:
        return ""
    return '<nav class="quick-links">' + "".join(links) + "</nav>"


def safe_local_file_path(config: ServerConfig, name: str) -> Path | None:
    if not name or "/" in name or "\\" in name:
        return None
    for key, _, path in local_file_targets(config):
        if key == name:
            return path.resolve()
    return None


def workspace_run_label(config: ServerConfig) -> str:
    parts = [part.lower() for part in config.papers_json.parts]
    if "foundation" in parts:
        return "Foundation review"
    if "daily" in parts:
        return "Daily digest"
    if "recent" in parts:
        return "Recent review"
    if "demo" in parts:
        return "Demo review"
    return config.papers_json.parent.name or "Current run"


def load_workspace_context(config: ServerConfig) -> dict[str, Any]:
    from . import core

    summary_path = config.papers_json.parent / "summary.json"
    summary: dict[str, Any] = {}
    if summary_path.exists():
        try:
            loaded_summary = core.load_json(summary_path)
            if isinstance(loaded_summary, dict):
                summary = loaded_summary
        except Exception:
            summary = {}
    profile: dict[str, Any] = {}
    if config.profile_path.exists():
        try:
            loaded_profile = core.load_profile(config.profile_path)
            if isinstance(loaded_profile, dict):
                profile = loaded_profile
        except Exception:
            profile = {}
    return {"summary": summary, "profile": profile, "run_label": workspace_run_label(config)}


def _summary_count(summary: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = summary.get(key)
        if isinstance(value, (int, float)):
            return str(int(value))
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "0"


def _summary_text(summary: dict[str, Any], key: str) -> str:
    value = summary.get(key)
    if isinstance(value, (str, int, float)):
        return str(value)
    return ""


def profile_questions(profile: dict[str, Any], limit: int = 3) -> list[str]:
    raw_questions = profile.get("current_questions") or profile.get("questions") or profile.get("research_questions") or []
    if not isinstance(raw_questions, list):
        return []
    questions: list[str] = []
    for item in raw_questions:
        text = str(item).strip()
        if text:
            questions.append(text)
        if len(questions) >= limit:
            break
    return questions


def render_workspace_overview(
    papers: list[Any],
    config: ServerConfig,
    context: dict[str, Any],
    tier_counts: dict[str, int],
    status_counts: dict[str, int],
    view: str = "active",
    visible_count: int | None = None,
) -> str:
    summary = context.get("summary") if isinstance(context.get("summary"), dict) else {}
    profile = context.get("profile") if isinstance(context.get("profile"), dict) else {}
    run_label = str(context.get("run_label") or workspace_run_label(config))
    questions = profile_questions(profile)
    source = _summary_text(summary, "source") or "local papers.json"
    mode = _summary_text(summary, "mode") or run_label
    retained = _summary_count(
        summary,
        "library_papers",
        "library_total",
        "retained_library_papers",
        "cumulative_retained_papers",
    )
    source_items = _summary_count(summary, "source_item_count", "source_items", "gmail_message_count")
    papers_in_digest = _summary_count(summary, "papers_in_digest", "papers")
    if "Foundation" in run_label:
        note = "You are reviewing the foundation library. Feedback here updates interested/foundation outputs and tunes future daily ranking."
    elif len(papers) == 0:
        note = "This run has no reviewable papers. Open Foundation review from the top links, or run ./serve_reader.sh without PAPERS_JSON to fall back automatically."
    else:
        note = "You are reviewing the current run. Paper actions here refresh Foundation, Interested, Reading Plan, and future ranking signals."
    question_html = (
        '<div class="question-strip">'
        + "".join(f'<div class="question-pill">{html.escape(question)}</div>' for question in questions)
        + "</div>"
        if questions
        else ""
    )
    view_labels = {
        "active": "Active review queue",
        "must-read": "Must read only",
        "skim": "Skim only",
        "archive": "Archive review",
        "all": "Full review set",
    }
    visible = len(papers) if visible_count is None else visible_count
    return "\n".join(
        [
            '<section class="workspace-overview" id="overview">',
            '<div class="overview-copy">',
            f"<h2>{html.escape(run_label)}</h2>",
            f'<p class="meta">{html.escape(note)}</p>',
            "</div>",
            '<div class="digest-panels">',
            f'<a class="digest-panel" href="#must-read"><strong>{tier_counts.get("Must read", 0)}</strong><span>Must read</span></a>',
            f'<a class="digest-panel" href="#skim"><strong>{tier_counts.get("Skim", 0)}</strong><span>Skim</span></a>',
            f'<a class="digest-panel" href="#archive"><strong>{tier_counts.get("Archive", 0)}</strong><span>Archive</span></a>',
            f'<div class="digest-panel"><strong>{status_counts.get("unread", 0)}</strong><span>Unread</span></div>',
            "</div>",
            '<div class="run-details">',
            f"<span>View: {html.escape(view_labels.get(view, view))}</span>",
            f"<span>Showing: {visible} of {len(papers)}</span>",
            f"<span>Mode: {html.escape(mode)}</span>",
            f"<span>Source: {html.escape(source)}</span>",
            f"<span>Source items: {html.escape(source_items)}</span>",
            f"<span>Digest papers: {html.escape(papers_in_digest or str(len(papers)))}</span>",
            f"<span>Retained library: {html.escape(retained)}</span>",
            "</div>",
            question_html,
            '<nav class="workspace-tabs">',
            '<a href="/?view=active#overview">Active queue</a>',
            '<a href="/?view=must-read#must-read">Must read</a>',
            '<a href="/?view=skim#skim">Skim</a>',
            '<a href="/?view=archive#archive">Archive</a>',
            '<a href="/?view=all#all-papers">Load all cards</a>',
            "</nav>",
            "</section>",
        ]
    )


def tier_anchor(tier: str) -> str:
    return {"Must read": "must-read", "Skim": "skim", "Archive": "archive"}.get(tier, "other")


def workspace_view_from_query(query: dict[str, list[str]]) -> str:
    view = (query.get("view") or ["active"])[0].strip().lower()
    aliases = {
        "": "active",
        "review": "active",
        "queue": "active",
        "must": "must-read",
        "must_read": "must-read",
        "must read": "must-read",
        "skim": "skim",
        "archive": "archive",
        "archived": "archive",
        "all": "all",
        "full": "all",
    }
    return aliases.get(view, "active")


def filter_papers_for_view(papers: list[Any], view: str, feedback: dict[str, Any] | None = None) -> list[Any]:
    if view == "all":
        return papers
    if view == "must-read":
        return [paper for paper in papers if str(getattr(paper, "tier", "")) == "Must read"]
    if view == "skim":
        return [paper for paper in papers if str(getattr(paper, "tier", "")) == "Skim"]
    if view == "archive":
        return [
            paper
            for paper in papers
            if str(getattr(paper, "tier", "")) == "Archive"
            or paper_feedback_item(feedback, str(getattr(paper, "id", ""))).get("status") == "archive"
            or paper_priority_override(paper, feedback) == "archive"
        ]
    return [
        paper
        for paper in papers
        if str(getattr(paper, "tier", "")) != "Archive"
        and paper_feedback_item(feedback, str(getattr(paper, "id", ""))).get("status") != "archive"
        and paper_priority_override(paper, feedback) != "archive"
    ]


def render_grouped_cards(card_rows: list[tuple[str, str]], tier_counts: dict[str, int]) -> str:
    if not card_rows:
        return (
            '<section class="empty-panel">'
            "<h2>No papers in this run</h2>"
            '<p class="empty">This papers.json is empty. Use the navigation above to open Foundation, Interested, or a previous digest, or run the workspace against foundation papers.</p>'
            "</section>"
        )
    grouped: dict[str, list[str]] = {}
    for tier, card in card_rows:
        grouped.setdefault(tier, []).append(card)
    sections = ['<div id="all-papers"></div>']
    for tier in ["Must read", "Skim", "Archive"]:
        cards = grouped.pop(tier, [])
        if not cards:
            continue
        sections.append(
            "\n".join(
                [
                    f'<section class="tier-section" id="{tier_anchor(tier)}">',
                    f'<h2 class="section-heading">{html.escape(tier)} <span>{tier_counts.get(tier, len(cards))}</span></h2>',
                    *cards,
                    "</section>",
                ]
            )
        )
    for tier, cards in grouped.items():
        sections.append(
            "\n".join(
                [
                    f'<section class="tier-section" id="{html.escape(tier_anchor(tier), quote=True)}">',
                    f'<h2 class="section-heading">{html.escape(tier)} <span>{len(cards)}</span></h2>',
                    *cards,
                    "</section>",
                ]
            )
        )
    return "\n".join(sections)


def batch_save_bar(position: str = "top") -> str:
    label = "Save selected changes"
    return "\n".join(
        [
            f'<div class="batch-save-bar batch-save-bar-{html.escape(position, quote=True)}">',
            '<div><strong>Batch review</strong><span class="pending-count">No pending changes</span></div>',
            f'<button class="primary-save" type="submit">{label}</button>',
            "</div>",
        ]
    )


def render_page(
    papers: list[Any],
    config: ServerConfig,
    message: str = "",
    feedback: dict[str, Any] | None = None,
    message_html: str = "",
    focused_paper: Any | None = None,
    all_papers: list[Any] | None = None,
    view: str = "active",
) -> str:
    all_papers = all_papers or papers
    card_rows: list[tuple[str, str]] = []
    tier_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    visible_tier_counts: dict[str, int] = {}
    for paper in all_papers:
        tier = str(getattr(paper, "tier", "") or "Unknown")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        status = paper_reading_status(paper, feedback)
        status_counts[status] = status_counts.get(status, 0) + 1
    for paper in papers:
        tier = str(getattr(paper, "tier", "") or "Unknown")
        visible_tier_counts[tier] = visible_tier_counts.get(tier, 0) + 1
    for paper in papers:
        reasons = "".join(f"<li>{html.escape(reason)}</li>" for reason in paper.reasons[:3])
        reading_status = paper_reading_status(paper, feedback)
        searchable = " ".join(
            [
                paper.title,
                paper.authors_source,
                paper.snippet,
                " ".join(paper.matched_terms),
                " ".join(paper.alerts),
            ]
        ).lower()
        metadata_summary = paper_metadata_summary(paper)
        card_rows.append(
            (
                str(paper.tier),
                "\n".join(
                    [
                        f'<article class="paper" data-tier="{html.escape(str(paper.tier), quote=True)}" data-status="{html.escape(reading_status, quote=True)}" data-search="{html.escape(searchable, quote=True)}">',
                        paper_title_html(paper),
                        '<div class="badges">'
                        + render_badge(f"id {paper.id}")
                        + render_badge(str(paper.tier))
                        + render_badge(f"score {paper.score}")
                        + "</div>",
                        paper_evidence_html(paper, config),
                        feedback_badges(paper, feedback),
                        paper_feedback_note_html(paper, feedback),
                        scholar_source_line_html(paper),
                        f'<p class="meta enrichment-line"><strong>Metadata enrichment</strong><span>{html.escape(metadata_summary)}</span></p>'
                        if metadata_summary
                        else "",
                        publication_metadata_html(paper),
                        abstract_snippet_html(paper),
                        '<p class="paper-links">'
                        + (
                            f'<a href="/paper?id={quote(paper.id, safe="")}">Open workspace</a>'
                            if focused_paper is None
                            else '<a href="/">Back to review workspace</a>'
                        )
                        + (f' · <a href="{html.escape(paper.url, quote=True)}">Open paper</a>' if paper.url else "")
                        + "</p>",
                        report_links(paper.id, config),
                        selected_answer_links(paper.id, config),
                        f"<ul>{reasons}</ul>" if reasons else "",
                        '<div class="review-controls">',
                        f'<input type="hidden" name="paper_id" value="{html.escape(paper.id, quote=True)}">',
                        f'<input type="hidden" class="report-action" name="report_action__{html.escape(paper.id, quote=True)}" value="">',
                        '<div class="review-grid">',
                        review_select(
                            f"decision__{paper.id}",
                            "Decision",
                            [
                                ("", "No change"),
                                ("interested", "Interested"),
                                ("neutral", "Neutral"),
                                ("archive", "Archive"),
                            ],
                            "Keep/archive decision.",
                        ),
                        review_select(
                            f"priority__{paper.id}",
                            "Priority",
                            [
                                ("", "No change"),
                                ("auto", "Auto"),
                                ("must_read", "Must read"),
                                ("skim", "Skim"),
                                ("archive", "Archive"),
                            ],
                            "Manual tier override.",
                        ),
                        review_select(
                            f"reading__{paper.id}",
                            "Reading status",
                            [
                                ("", "No change"),
                                ("unread", "Unread"),
                                ("reading", "Reading"),
                                ("read", "Read"),
                                ("must-cite", "Must cite"),
                                ("method-reference", "Method ref"),
                                ("background-only", "Background only"),
                                ("not-relevant", "Not relevant"),
                            ],
                            "Reading progress or use.",
                        ),
                        "</div>",
                        '<div class="review-field learning-field"><span>Learning signal</span><div class="checkbox-row">',
                        review_checkbox(f"signal_more__{paper.id}", "More like this", "signal-more"),
                        review_checkbox(f"signal_less__{paper.id}", "Less like this", "signal-less"),
                        review_checkbox(f"signal_clear__{paper.id}", "Clear signal", "signal-clear"),
                        "</div><span class=\"control-help\">Optional ranking feedback for future runs.</span></div>",
                        '<div class="combo-warning" hidden></div>',
                        '<div class="review-field report-field"><span>Generate report on save</span>',
                        '<div class="action-row">',
                        '<button type="button" class="action-chip" data-set-report="deep" value="deep">Deep read</button>',
                        '<button type="button" class="action-chip" data-set-report="review_workflow" value="review_workflow">Full review</button>',
                        '<button type="button" class="action-chip" data-set-report="workup" value="workup">Workup</button>',
                        '<button type="button" class="action-chip" data-set-report="review_pack" value="review_pack">Review pack</button>',
                        '<button type="button" class="action-chip clear-action" data-set-report="" value="">Clear report</button>',
                        "</div></div>",
                        '<label class="note-input"><span>Personal note</span>'
                        + '<div class="note-tools">'
                        + f'<select class="review-select note-mode" name="note_mode__{html.escape(paper.id, quote=True)}">'
                        + select_options(
                            [
                                ("", "Append typed note"),
                                ("replace", "Replace saved note"),
                                ("clear", "Clear saved note"),
                            ]
                        )
                        + "</select>"
                        + '<span class="control-help">Blank text with the default mode leaves existing notes unchanged.</span>'
                        + "</div>"
                        + f'<textarea class="paper-note" name="note__{html.escape(paper.id, quote=True)}" rows="2" placeholder="Optional note; choose Replace to overwrite, or Clear saved note to remove the current note."></textarea></label>',
                        "</div>",
                        "</article>",
                    ]
                ),
            )
        )
    content = render_grouped_cards(card_rows, visible_tier_counts)
    context = load_workspace_context(config)
    overview = "" if focused_paper is not None else render_workspace_overview(all_papers, config, context, tier_counts, status_counts, view=view, visible_count=len(papers))
    stat_items = [
        f"Showing {len(papers)} of {len(all_papers)}",
        f"Must read {tier_counts.get('Must read', 0)}",
        f"Skim {tier_counts.get('Skim', 0)}",
        f"Archive {tier_counts.get('Archive', 0)}",
        f"Unread {status_counts.get('unread', 0)}",
        f"Reading {status_counts.get('reading', 0)}",
        f"Read {status_counts.get('read', 0)}",
    ]
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>Scholar Alert Review Workspace</title>",
            "<style>",
            """
            :root {
              color-scheme: light;
              --ink: #1f2933;
              --muted: #64748b;
              --line: #d9e2ec;
              --bg: #f7f9fb;
              --panel: #ffffff;
              --accent: #0f766e;
            }
            * { box-sizing: border-box; }
            body {
              margin: 0;
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
              background: var(--bg);
              color: var(--ink);
              line-height: 1.5;
            }
            header {
              background: var(--panel);
              border-bottom: 1px solid var(--line);
              padding: 24px;
            }
            main { max-width: 980px; margin: 0 auto; padding: 20px; }
            h1 { margin: 0 0 8px; font-size: 26px; letter-spacing: 0; }
            h2 { margin: 0 0 8px; font-size: 18px; letter-spacing: 0; }
            .meta, .empty { color: var(--muted); }
            .toolbar {
              display: grid;
              grid-template-columns: minmax(220px, 1fr) 180px 180px;
              gap: 10px;
              margin-top: 16px;
              max-width: 960px;
            }
            .ask-form {
              display: grid;
              grid-template-columns: minmax(240px, 1fr) auto;
              gap: 8px;
              max-width: 960px;
              margin: 12px 0 0;
            }
            input, select, textarea {
              border: 1px solid var(--line);
              border-radius: 8px;
              padding: 9px 10px;
              font: inherit;
              background: #fff;
              color: var(--ink);
              min-width: 0;
            }
            .message {
              margin-top: 12px;
              padding: 10px 12px;
              border-radius: 8px;
              background: #d9f4ef;
              color: #0f5f59;
            }
            .quick-links {
              display: flex;
              flex-wrap: wrap;
              gap: 8px;
              margin: 14px 0 2px;
            }
            .quick-links a {
              border: 1px solid var(--line);
              border-radius: 8px;
              background: #fff;
              color: var(--ink);
              padding: 7px 10px;
              font-size: 14px;
            }
            .quick-links a:hover { border-color: var(--accent); color: var(--accent); text-decoration: none; }
            .workspace-overview {
              max-width: 980px;
              margin: 18px auto 0;
              padding: 18px;
              border: 1px solid var(--line);
              border-radius: 8px;
              background: #fbfdff;
            }
            .overview-copy h2 {
              font-size: 21px;
              margin: 0 0 4px;
            }
            .digest-panels {
              display: grid;
              grid-template-columns: repeat(4, minmax(0, 1fr));
              gap: 10px;
              margin: 14px 0;
            }
            .digest-panel {
              border: 1px solid var(--line);
              border-radius: 8px;
              background: #fff;
              padding: 10px;
              color: var(--ink);
              min-width: 0;
            }
            .digest-panel:hover { border-color: var(--accent); text-decoration: none; }
            .digest-panel strong {
              display: block;
              font-size: 24px;
              line-height: 1.1;
            }
            .digest-panel span {
              color: var(--muted);
              font-size: 13px;
            }
            .run-details {
              display: flex;
              flex-wrap: wrap;
              gap: 8px;
              color: var(--muted);
              font-size: 13px;
            }
            .run-details span {
              border: 1px solid var(--line);
              border-radius: 999px;
              background: #fff;
              padding: 4px 8px;
            }
            .question-strip {
              display: grid;
              grid-template-columns: repeat(3, minmax(0, 1fr));
              gap: 10px;
              margin-top: 14px;
            }
            .question-pill {
              border-left: 4px solid var(--accent);
              border-radius: 8px;
              background: #d9f4ef;
              color: #40546b;
              padding: 10px;
              font-weight: 600;
            }
            .workspace-tabs {
              display: flex;
              flex-wrap: wrap;
              gap: 8px;
              margin-top: 14px;
            }
            .workspace-tabs a {
              border: 1px solid var(--line);
              border-radius: 8px;
              background: #fff;
              color: var(--ink);
              padding: 7px 10px;
              font-size: 14px;
            }
            .workspace-tabs a:hover { border-color: var(--accent); color: var(--accent); text-decoration: none; }
            .run-stats {
              display: flex;
              flex-wrap: wrap;
              gap: 8px;
              margin: 14px 0 0;
            }
            .run-stat {
              border: 1px solid var(--line);
              border-radius: 8px;
              background: #fbfdff;
              color: var(--muted);
              padding: 6px 9px;
              font-size: 13px;
            }
            .empty-panel {
              background: var(--panel);
              border: 1px solid var(--line);
              border-radius: 8px;
              padding: 18px;
            }
            .reports {
              color: var(--muted);
              font-size: 14px;
            }
            .reports a { margin-right: 8px; }
            .paper-links {
              display: flex;
              flex-wrap: wrap;
              gap: 8px;
              color: var(--muted);
              font-size: 14px;
            }
            .note {
              margin: 10px 0;
              border-left: 3px solid var(--accent);
              padding: 8px 10px;
              background: #f0fdfa;
            }
            .note strong { display: block; margin-bottom: 4px; }
            .note pre {
              margin: 0;
              white-space: pre-wrap;
              font: inherit;
              color: var(--ink);
            }
            .paper {
              background: var(--panel);
              border: 1px solid var(--line);
              border-radius: 8px;
              padding: 16px;
              margin-bottom: 12px;
            }
            .paper.pending-change {
              border-color: var(--accent);
              box-shadow: 0 0 0 2px rgba(15, 118, 110, 0.08);
            }
            .paper.has-combo-warning {
              border-color: #f59e0b;
              box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.12);
            }
            .batch-feedback-form {
              display: block;
              margin: 0;
            }
            .batch-save-bar {
              position: sticky;
              top: 0;
              z-index: 5;
              display: flex;
              align-items: center;
              justify-content: space-between;
              gap: 12px;
              background: rgba(247, 249, 251, 0.96);
              border: 1px solid var(--line);
              border-radius: 8px;
              padding: 10px 12px;
              margin: 0 0 14px;
              backdrop-filter: blur(8px);
            }
            .batch-save-bar-bottom {
              position: static;
              margin: 16px 0 0;
            }
            .batch-save-bar strong {
              display: block;
              font-size: 14px;
            }
            .batch-save-bar span {
              color: var(--muted);
              font-size: 13px;
            }
            .primary-save {
              background: var(--accent);
              color: #fff;
              border-color: var(--accent);
              font-weight: 700;
            }
            .primary-save:hover {
              background: #0b5f59;
              color: #fff;
            }
            .title-link {
              color: #0b5cad;
            }
            .title-link:hover {
              color: var(--accent);
            }
            .paper-heading {
              display: grid;
              grid-template-columns: 46px 1fr;
              gap: 12px;
              align-items: start;
            }
            .paper-heading h2 {
              margin-top: 0;
            }
            .source-icon {
              width: 46px;
              height: 46px;
              border-radius: 8px;
              border: 1px solid var(--line);
              background: #fff;
              object-fit: contain;
              padding: 5px;
            }
            .source-icon-placeholder {
              display: grid;
              place-items: center;
              color: var(--muted);
              font-weight: 800;
            }
            .tier-section {
              scroll-margin-top: 16px;
              margin-bottom: 18px;
            }
            .section-heading {
              display: flex;
              align-items: baseline;
              gap: 8px;
              margin: 22px 0 12px;
              font-size: 22px;
            }
            .section-heading span {
              color: var(--muted);
              font-size: 14px;
              font-weight: 500;
            }
            .badges { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
            .feedback-badges { margin-top: -2px; }
            .publication-meta,
            .snippet-block {
              border: 1px solid var(--line);
              border-radius: 8px;
              background: #fbfdff;
              padding: 10px;
              margin: 10px 0;
            }
            .source-line,
            .enrichment-line {
              display: grid;
              gap: 3px;
              margin: 8px 0;
              color: var(--muted);
            }
            .source-line strong,
            .enrichment-line strong {
              color: var(--ink);
              font-size: 13px;
            }
            .source-line span,
            .enrichment-line span {
              overflow-wrap: anywhere;
            }
            .publication-meta > strong,
            .snippet-block > strong {
              display: block;
              margin-bottom: 6px;
            }
            .publication-meta.missing,
            .snippet-block.missing {
              color: var(--muted);
            }
            .pub-grid {
              display: grid;
              grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
              gap: 8px;
            }
            .pub-field {
              display: grid;
              gap: 2px;
            }
            .pub-field span {
              color: var(--muted);
              font-size: 12px;
            }
            .pub-field strong {
              font-size: 14px;
              font-weight: 650;
            }
            .snippet-block p {
              margin: 0;
              white-space: pre-wrap;
              overflow-wrap: anywhere;
            }
            .snippet-hint {
              margin-top: 6px;
              color: var(--muted);
              font-size: 12px;
            }
            .evidence-badges .badge {
              background: #e0f2fe;
              color: #075985;
            }
            .evidence-note {
              margin: -2px 0 8px;
              color: var(--muted);
              font-size: 13px;
            }
            .badge {
              border-radius: 999px;
              background: #eef2f7;
              color: #334e68;
              padding: 3px 8px;
              font-size: 12px;
            }
            form { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
            .ask-form { display: grid; }
            .review-controls {
              display: grid;
              gap: 10px;
              margin-top: 12px;
            }
            .review-grid {
              display: grid;
              grid-template-columns: repeat(3, minmax(180px, 1fr));
              gap: 10px;
            }
            .review-field {
              display: grid;
              gap: 4px;
              color: var(--muted);
              font-size: 13px;
            }
            .review-field > span:first-child,
            .note-input > span:first-child {
              color: var(--ink);
              font-weight: 650;
            }
            .review-select {
              width: 100%;
              border: 1px solid var(--line);
              border-radius: 8px;
              background: #fff;
              color: var(--ink);
              padding: 8px 10px;
              font: inherit;
            }
            .review-select:focus,
            .note-input textarea:focus {
              outline: 2px solid rgba(15, 118, 110, 0.18);
              border-color: var(--accent);
            }
            .control-help {
              color: var(--muted);
              font-size: 12px;
            }
            .learning-field,
            .report-field {
              border: 1px solid var(--line);
              border-radius: 8px;
              padding: 10px;
              background: #fbfdff;
            }
            .combo-warning {
              border: 1px solid #fbbf24;
              border-radius: 8px;
              background: #fffbeb;
              color: #92400e;
              padding: 8px 10px;
              font-size: 13px;
            }
            .combo-warning[hidden] {
              display: none;
            }
            .checkbox-row {
              display: flex;
              flex-wrap: wrap;
              gap: 8px;
            }
            .review-checkbox {
              display: inline-flex;
              align-items: center;
              gap: 6px;
              border: 1px solid var(--line);
              border-radius: 8px;
              background: #fff;
              padding: 7px 10px;
              color: var(--ink);
              cursor: pointer;
            }
            .review-checkbox input {
              margin: 0;
            }
            .review-checkbox:has(input:checked) {
              border-color: var(--accent);
              background: #d9f4ef;
              color: #0f5f59;
              font-weight: 650;
            }
            .action-row {
              display: flex;
              flex-wrap: wrap;
              gap: 8px;
            }
            .note-input {
              flex: 1 0 100%;
              display: grid;
              gap: 4px;
              color: var(--muted);
              font-size: 13px;
            }
            .note-tools {
              display: flex;
              align-items: center;
              flex-wrap: wrap;
              gap: 8px;
            }
            .note-mode {
              width: min(220px, 100%);
            }
            .note-input textarea {
              resize: vertical;
              min-height: 48px;
              color: var(--ink);
            }
            button {
              border: 1px solid var(--line);
              border-radius: 8px;
              background: #fff;
              color: var(--ink);
              padding: 8px 10px;
              cursor: pointer;
              font: inherit;
            }
            button:hover { border-color: var(--accent); color: var(--accent); }
            .action-chip.selected-report {
              border-color: var(--accent);
              background: #d9f4ef;
              color: #0f5f59;
              font-weight: 650;
            }
            .clear-action {
              color: var(--muted);
            }
            a { color: #0b5cad; text-decoration: none; }
            a:hover { text-decoration: underline; }
            @media (max-width: 640px) {
              .toolbar { grid-template-columns: 1fr; }
              .review-grid { grid-template-columns: 1fr; }
              .ask-form { grid-template-columns: 1fr; }
              .digest-panels, .question-strip { grid-template-columns: 1fr; }
            }
            """,
            "</style>",
            "</head>",
            "<body>",
            "<header>",
            "<h1>Scholar Alert Paper Workspace</h1>" if focused_paper is not None else "<h1>Scholar Alert Review Workspace</h1>",
            f'<div class="meta">Profile: {html.escape(str(config.profile_path))}</div>',
            f'<div class="meta">Papers: {html.escape(str(config.papers_json))}</div>',
            f'<div class="meta">Knowledge base: {html.escape(str(config.kb_dir))}</div>',
            local_nav_links(config),
            '<div class="run-stats">' + "".join(f'<span class="run-stat">{html.escape(item)}</span>' for item in stat_items) + "</div>",
            '<div class="toolbar">',
            '<input id="search" type="search" placeholder="Search title, alert, term, source">',
            '<select id="tier"><option value="">All tiers</option><option>Must read</option><option>Skim</option><option>Archive</option></select>',
            '<select id="status"><option value="">All statuses</option><option>unread</option><option>reading</option><option>read</option><option>must-cite</option><option>method-reference</option><option>background-only</option><option>not-relevant</option></select>',
            "</div>",
            '<form class="ask-form" method="post" action="/ask">',
            f'<input type="hidden" name="view" value="{html.escape(view, quote=True)}">',
            f'<input type="hidden" name="paper_id" value="{html.escape(str(getattr(focused_paper, "id", "")), quote=True)}">'
            if focused_paper is not None
            else "",
            '<input name="question" type="search" placeholder="Ask about this paper against your foundation/interested library">'
            if focused_paper is not None
            else '<input name="question" type="search" placeholder="Ask your library, e.g. which papers are closest to my current project?">',
            "<button>Ask about this paper</button>" if focused_paper is not None else "<button>Ask library</button>",
            "</form>",
            f'<div class="message">{message_html}</div>'
            if message_html
            else f'<div class="message">{html.escape(message)}</div>' if message else "",
            overview,
            "</header>",
            "<main>",
            f'<form class="batch-feedback-form" method="post" action="/feedback-batch">',
            f'<input type="hidden" name="view" value="{html.escape(view, quote=True)}">',
            batch_save_bar("top"),
            content,
            batch_save_bar("bottom"),
            "</form>",
            "</main>",
            "<script>",
            """
            const search = document.getElementById('search');
            const tier = document.getElementById('tier');
            const status = document.getElementById('status');
            const cards = Array.from(document.querySelectorAll('.paper'));
            function applyFilters() {
              const q = search.value.trim().toLowerCase();
              const wantedTier = tier.value;
              const wantedStatus = status.value;
              for (const card of cards) {
                const matchesText = !q || card.dataset.search.includes(q);
                const matchesTier = !wantedTier || card.dataset.tier === wantedTier;
                const matchesStatus = !wantedStatus || card.dataset.status === wantedStatus;
                card.style.display = matchesText && matchesTier && matchesStatus ? '' : 'none';
              }
            }
            search.addEventListener('input', applyFilters);
            tier.addEventListener('change', applyFilters);
            status.addEventListener('change', applyFilters);

            const batchForm = document.querySelector('.batch-feedback-form');
            function markCardDirty(card) {
              if (card) card.classList.add('pending-change');
            }
            function reviewValue(card, prefix) {
              return (card.querySelector(`[name^="${prefix}__"]`)?.value || '').trim();
            }
            function reviewChecked(card, prefix) {
              return Boolean(card.querySelector(`[name^="${prefix}__"]`)?.checked);
            }
            function combinationWarnings(card) {
              const decision = reviewValue(card, 'decision');
              const priority = reviewValue(card, 'priority').replace('-', '_');
              const reading = reviewValue(card, 'reading');
              const more = reviewChecked(card, 'signal_more');
              const less = reviewChecked(card, 'signal_less');
              const warnings = [];
              if (decision === 'interested' && less) {
                warnings.push('Interested + Less like this keeps this paper but downranks similar future papers.');
              }
              if (decision === 'archive' && more) {
                warnings.push('Archive + More like this archives this paper but boosts similar future papers.');
              }
              if (priority === 'archive' && more) {
                warnings.push('Priority Archive + More like this is unusual; archive priority wins for this paper.');
              }
              if (priority === 'must_read' && less) {
                warnings.push('Must read + Less like this is unusual; this paper stays prioritized but similar papers are downranked.');
              }
              if (reading === 'not-relevant' && more) {
                warnings.push('Not relevant + More like this is unusual; not-relevant archives this paper.');
              }
              if (reading === 'background-only' && more) {
                warnings.push('Background only + More like this is unusual; background-only usually clears ranking signals.');
              }
              if (decision === 'archive' && (priority === 'must_read' || priority === 'skim')) {
                warnings.push('Archive decision conflicts with a reading priority; Archive wins for ranking.');
              }
              return warnings;
            }
            function refreshCombinationWarning(card) {
              const warningBox = card.querySelector('.combo-warning');
              if (!warningBox) return [];
              const warnings = combinationWarnings(card);
              if (warnings.length) {
                warningBox.hidden = false;
                warningBox.textContent = warnings.join(' ');
                card.classList.add('has-combo-warning');
              } else {
                warningBox.hidden = true;
                warningBox.textContent = '';
                card.classList.remove('has-combo-warning');
              }
              return warnings;
            }
            function refreshAllCombinationWarnings() {
              const warnings = [];
              for (const card of cards) {
                for (const warning of refreshCombinationWarning(card)) {
                  warnings.push(warning);
                }
              }
              return warnings;
            }
            function cardHasChanges(card) {
              if (!card) return false;
              const note = card.querySelector('.paper-note');
              const noteMode = card.querySelector('.note-mode');
              const report = card.querySelector('.report-action');
              const selects = card.querySelectorAll('.review-select');
              const checks = card.querySelectorAll('.review-checkbox input');
              if (report && report.value) return true;
              if (note && note.value.trim()) return true;
              if (noteMode && noteMode.value === 'clear') return true;
              for (const item of selects) {
                if (item.classList.contains('note-mode')) {
                  if (item.value === 'clear') return true;
                } else if (item.value) {
                  return true;
                }
              }
              for (const item of checks) {
                if (item.checked) return true;
              }
              return false;
            }
            function updatePendingCount() {
              const changed = new Set();
              for (const card of cards) {
                if (cardHasChanges(card)) changed.add(card);
              }
              refreshAllCombinationWarnings();
              const text = changed.size === 0 ? 'No pending changes' : `${changed.size} pending change${changed.size === 1 ? '' : 's'}`;
              document.querySelectorAll('.pending-count').forEach(el => { el.textContent = text; });
            }
            document.querySelectorAll('.action-chip[data-set-report]').forEach(button => {
              button.addEventListener('click', () => {
                const card = button.closest('.paper');
                const actionInput = card.querySelector('.report-action');
                actionInput.value = button.dataset.setReport || '';
                card.querySelectorAll('.action-chip[data-set-report]').forEach(item => item.classList.remove('selected-report'));
                if (actionInput.value) button.classList.add('selected-report');
                markCardDirty(card);
                updatePendingCount();
              });
            });
            document.querySelectorAll('.review-select').forEach(input => {
              input.addEventListener('change', () => {
                markCardDirty(input.closest('.paper'));
                updatePendingCount();
              });
            });
            document.querySelectorAll('.review-checkbox input').forEach(input => {
              input.addEventListener('change', () => {
                const card = input.closest('.paper');
                if (input.checked && input.closest('.signal-more')) {
                  card.querySelectorAll('.signal-less input, .signal-clear input').forEach(item => { item.checked = false; });
                } else if (input.checked && input.closest('.signal-less')) {
                  card.querySelectorAll('.signal-more input, .signal-clear input').forEach(item => { item.checked = false; });
                } else if (input.checked && input.closest('.signal-clear')) {
                  card.querySelectorAll('.signal-more input, .signal-less input').forEach(item => { item.checked = false; });
                }
                markCardDirty(card);
                updatePendingCount();
              });
            });
            document.querySelectorAll('.paper-note').forEach(note => {
              note.addEventListener('input', () => {
                markCardDirty(note.closest('.paper'));
                updatePendingCount();
              });
            });
            document.querySelectorAll('.note-mode').forEach(mode => {
              mode.addEventListener('change', () => {
                markCardDirty(mode.closest('.paper'));
                updatePendingCount();
              });
            });
            if (batchForm) {
              batchForm.addEventListener('submit', event => {
                let changed = false;
                for (const card of cards) {
                  if (cardHasChanges(card)) {
                    changed = true;
                    break;
                  }
                }
                if (!changed) {
                  event.preventDefault();
                  alert('No selected actions or notes to save.');
                  return;
                }
                const warnings = refreshAllCombinationWarnings();
                if (warnings.length) {
                  const uniqueWarnings = [...new Set(warnings)].slice(0, 5).join('\n');
                  if (!confirm(`Some feedback combinations are unusual:\n\n${uniqueWarnings}\n\nSave anyway?`)) {
                    event.preventDefault();
                  }
                }
              });
            }
            """,
            "</script>",
            "</body>",
            "</html>",
        ]
    )


def make_handler(config: ServerConfig):
    from . import core

    class FeedbackHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def send_html(self, body: bytes) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def run_review_artifact(self, action: str, paper_id: str, feedback_file: Path) -> list[tuple[str, Path]]:
            if action == "deep":
                return [
                    (
                        "deep-read report",
                        core.write_deep_read_report(
                            profile_path=config.profile_path,
                            kb_dir=config.kb_dir,
                            paper_id=paper_id,
                            papers_json=config.papers_json,
                            feedback_file=feedback_file,
                        ),
                    )
                ]
            if action == "review_workflow":
                workflow_report, _, workup_report, review_pack_report = core.write_review_workflow_report(
                    profile_path=config.profile_path,
                    kb_dir=config.kb_dir,
                    paper_id=paper_id,
                    papers_json=config.papers_json,
                    feedback_file=feedback_file,
                )
                return [
                    ("review workflow", workflow_report),
                    ("workup report", workup_report),
                    ("review pack", review_pack_report),
                ]
            if action == "workup":
                workup_report, _, _ = core.write_paper_workup_report(
                    profile_path=config.profile_path,
                    kb_dir=config.kb_dir,
                    paper_id=paper_id,
                    papers_json=config.papers_json,
                    feedback_file=feedback_file,
                )
                return [("workup report", workup_report)]
            if action == "review_pack":
                review_pack_report, _, _ = core.write_review_context_pack_report(
                    profile_path=config.profile_path,
                    kb_dir=config.kb_dir,
                    paper_id=paper_id,
                    papers_json=config.papers_json,
                    feedback_file=feedback_file,
                )
                return [("review pack", review_pack_report)]
            return []

        def apply_feedback_choice(self, feedback: dict[str, Any], paper: Any, action: str, user_note: str, note_mode: str = "") -> bool:
            if not action and not user_note.strip() and note_mode != "clear":
                return False
            state = feedback_action_state(action)
            core.update_paper_feedback(
                feedback,
                paper,
                state["mark"],
                bool(state["more_like_this"]),
                bool(state["less_like_this"]),
                None,
            )
            record = feedback.setdefault("papers", {}).setdefault(paper.id, {})
            reading_status = state.get("reading_status")
            if reading_status:
                record["reading_status"] = reading_status
            if action == "status_background":
                signals = record.setdefault("signals", {})
                signals["more_like_this"] = False
                signals["less_like_this"] = False
            labels = [str(label) for label in state.get("labels", []) if str(label).strip()]
            if labels:
                current = [str(label) for label in record.get("labels", []) if str(label).strip()]
                for label in labels:
                    if label not in current:
                        current.append(label)
                record["labels"] = current
            if action == "status_background":
                core.remove_feedback_terms_for_paper(feedback, paper.id)
            elif state["more_like_this"]:
                core.remove_feedback_terms_for_paper(feedback, paper.id, "negative")
            elif state["less_like_this"]:
                core.remove_feedback_terms_for_paper(feedback, paper.id, "positive")
            if state["more_like_this"]:
                for term, weight in core.feedback_terms_from_paper(paper):
                    core.add_feedback_term(feedback, term, "positive", weight, "paper", paper.id)
            if state["less_like_this"]:
                for term, weight in core.feedback_terms_from_paper(paper):
                    core.add_feedback_term(feedback, term, "negative", weight, "paper", paper.id)
            update_feedback_note(record, state.get("note"), user_note, note_mode)
            return True

        def apply_feedback_fields(
            self,
            feedback: dict[str, Any],
            paper: Any,
            decision: str,
            priority: str,
            reading_status: str,
            signal_more: bool,
            signal_less: bool,
            signal_clear: bool,
            report_action: str,
            user_note: str,
            note_mode: str = "",
        ) -> bool:
            note_mode = note_mode.strip().lower().replace("-", "_")
            if not any(
                [
                    decision,
                    priority,
                    reading_status,
                    signal_more,
                    signal_less,
                    signal_clear,
                    report_action,
                    user_note.strip(),
                    note_mode == "clear",
                ]
            ):
                return False

            mark = decision if decision in {"interested", "archive", "neutral"} else None
            more_like_this = bool(signal_more)
            less_like_this = bool(signal_less)
            labels: list[str] = []
            generated_note = None

            report_state = feedback_action_state(report_action)
            if report_action:
                mark = mark or report_state.get("mark")
                more_like_this = more_like_this or bool(report_state.get("more_like_this"))
                less_like_this = less_like_this or bool(report_state.get("less_like_this"))
                if not reading_status:
                    reading_status = str(report_state.get("reading_status") or "")
                labels.extend(str(label) for label in report_state.get("labels", []) if str(label).strip())
                generated_note = str(report_state.get("note") or "").strip() or None

            priority = priority.strip().lower().replace("-", "_")
            if priority in {"must_read", "skim"} and not mark:
                mark = "interested"
            elif priority == "archive":
                mark = "archive"
                less_like_this = True

            reading_status = reading_status.strip().lower()
            if reading_status in {"reading", "read", "must-cite", "method-reference"} and not mark:
                mark = "interested"
            if reading_status == "must-cite":
                labels.append("must-cite")
            elif reading_status == "method-reference":
                labels.append("method-reference")
            elif reading_status == "background-only":
                mark = mark or "neutral"
                signal_clear = True
                generated_note = generated_note or "Marked as background only from Review Workspace."
            elif reading_status == "not-relevant":
                mark = "archive"
                less_like_this = True
                generated_note = generated_note or "Marked as not relevant from Review Workspace."

            if mark == "archive":
                less_like_this = True
                more_like_this = False
            elif more_like_this:
                less_like_this = False
            elif less_like_this:
                more_like_this = False

            core.update_paper_feedback(feedback, paper, mark, more_like_this, less_like_this, None)
            record = feedback.setdefault("papers", {}).setdefault(paper.id, {})
            if priority == "auto":
                record.pop("priority_override", None)
            elif priority in {"must_read", "skim", "archive"}:
                record["priority_override"] = priority
            if reading_status == "unread":
                record.pop("reading_status", None)
            elif reading_status:
                record["reading_status"] = reading_status
            if labels:
                current = [str(label) for label in record.get("labels", []) if str(label).strip()]
                for label in labels:
                    if label not in current:
                        current.append(label)
                record["labels"] = current

            if signal_clear:
                signals = record.setdefault("signals", {})
                signals["more_like_this"] = False
                signals["less_like_this"] = False
                core.remove_feedback_terms_for_paper(feedback, paper.id)
            elif more_like_this:
                core.remove_feedback_terms_for_paper(feedback, paper.id, "negative")
                for term, weight in core.feedback_terms_from_paper(paper):
                    core.add_feedback_term(feedback, term, "positive", weight, "paper", paper.id)
            elif less_like_this:
                core.remove_feedback_terms_for_paper(feedback, paper.id, "positive")
                for term, weight in core.feedback_terms_from_paper(paper):
                    core.add_feedback_term(feedback, term, "negative", weight, "paper", paper.id)

            update_feedback_note(record, generated_note, user_note, note_mode)
            return True

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/report":
                query = parse_qs(parsed.query)
                name = (query.get("name") or [""])[0]
                report_path = safe_report_path(config, name)
                if report_path is None:
                    self.send_error(400, "Invalid report name")
                    return
                if not report_path.exists():
                    self.send_error(404, "Report not found")
                    return
                content = report_path.read_text(encoding="utf-8", errors="replace")
                body = core.markdown_to_basic_html(content, f"Scholar Alert Report: {report_path.stem}").encode("utf-8")
                self.send_html(body)
                return
            if parsed.path == "/answer":
                query = parse_qs(parsed.query)
                name = (query.get("name") or [""])[0]
                answer_path = safe_answer_path(config, name)
                if answer_path is None:
                    self.send_error(400, "Invalid answer name")
                    return
                if not answer_path.exists():
                    self.send_error(404, "Answer not found")
                    return
                content = answer_path.read_text(encoding="utf-8", errors="replace")
                body = core.markdown_to_basic_html(content, f"Scholar Alert Answer: {answer_path.stem}").encode("utf-8")
                self.send_html(body)
                return
            if parsed.path == "/local":
                query = parse_qs(parsed.query)
                name = (query.get("name") or [""])[0]
                local_path = safe_local_file_path(config, name)
                if local_path is None:
                    self.send_error(400, "Invalid local file name")
                    return
                if not local_path.exists():
                    self.send_error(404, "Local file not found")
                    return
                content = local_path.read_text(encoding="utf-8", errors="replace")
                if local_path.suffix.lower() in {".html", ".htm"}:
                    body = content.encode("utf-8")
                else:
                    body = core.markdown_to_basic_html(content, f"Scholar Alert: {local_path.stem}").encode("utf-8")
                self.send_html(body)
                return
            if parsed.path != "/":
                if parsed.path == "/paper":
                    query = parse_qs(parsed.query)
                    paper_id = (query.get("id") or [""])[0]
                    papers = core.load_papers_json(config.papers_json)
                    selected = [paper for paper in papers if paper.id == paper_id]
                    if not selected:
                        self.send_error(404, "Paper ID not found")
                        return
                    feedback = core.load_feedback(core.default_feedback_file(config.kb_dir))
                    body = render_page(
                        selected,
                        config,
                        message=f"Focused workspace for {paper_id}",
                        feedback=feedback,
                        focused_paper=selected[0],
                        all_papers=selected,
                        view="focused",
                    ).encode("utf-8")
                    self.send_html(body)
                    return
                self.send_error(404)
                return
            query = parse_qs(parsed.query)
            view = workspace_view_from_query(query)
            all_papers = core.load_papers_json(config.papers_json)
            feedback = core.load_feedback(core.default_feedback_file(config.kb_dir))
            papers = filter_papers_for_view(all_papers, view, feedback)
            body = render_page(papers, config, feedback=feedback, all_papers=all_papers, view=view).encode("utf-8")
            self.send_html(body)

        def do_POST(self) -> None:
            if self.path == "/ask":
                length = int(self.headers.get("Content-Length", "0") or "0")
                form = parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"))
                question = (form.get("question") or [""])[0].strip()
                paper_id = (form.get("paper_id") or [""])[0].strip()
                view = workspace_view_from_query(form)
                if not question:
                    self.send_error(400, "Question is required")
                    return
                if paper_id:
                    try:
                        output = core.write_selected_paper_answer_report(
                            profile_path=config.profile_path,
                            kb_dir=config.kb_dir,
                            question=question,
                            paper_id=paper_id,
                            papers_json=config.papers_json,
                            feedback_file=core.default_feedback_file(config.kb_dir),
                        )
                    except SystemExit:
                        self.send_error(404, "Paper ID not found")
                        return
                else:
                    output = core.write_literature_answer_report(
                        profile_path=config.profile_path,
                        kb_dir=config.kb_dir,
                        question=question,
                        papers_json=config.papers_json,
                        feedback_file=core.default_feedback_file(config.kb_dir),
                    )
                all_papers = core.load_papers_json(config.papers_json)
                feedback = core.load_feedback(core.default_feedback_file(config.kb_dir))
                selected = [paper for paper in all_papers if paper.id == paper_id] if paper_id else []
                papers = selected or filter_papers_for_view(all_papers, view, feedback)
                answer_link = f'<a href="/answer?name={quote(output.name, safe="")}">{html.escape(output.name)}</a>'
                body = render_page(
                    papers,
                    config,
                    feedback=feedback,
                    message_html=(
                        f"Answered paper question for {html.escape(paper_id)}: {html.escape(question)}; answer: {answer_link}"
                        if paper_id
                        else f"Answered library question: {html.escape(question)}; answer: {answer_link}"
                    ),
                    focused_paper=selected[0] if selected else None,
                    all_papers=selected or all_papers,
                    view="focused" if selected else view,
                ).encode("utf-8")
                self.send_html(body)
                return
            if self.path == "/feedback-batch":
                length = int(self.headers.get("Content-Length", "0") or "0")
                form = parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"))
                view = workspace_view_from_query(form)
                all_papers = core.load_papers_json(config.papers_json)
                paper_map = {paper.id: paper for paper in all_papers}
                profile = core.load_profile(config.profile_path)
                feedback_file = core.default_feedback_file(config.kb_dir)
                feedback = core.load_feedback(feedback_file)
                changed: list[Any] = []
                review_actions: list[tuple[str, str]] = []
                combination_warnings: list[str] = []
                seen_ids: set[str] = set()
                for paper_id in form.get("paper_id", []):
                    if paper_id in seen_ids:
                        continue
                    seen_ids.add(paper_id)
                    paper = paper_map.get(paper_id)
                    if paper is None:
                        continue
                    decision = (form.get(f"decision__{paper_id}") or [""])[0].strip()
                    priority = (form.get(f"priority__{paper_id}") or [""])[0].strip()
                    reading_status = (form.get(f"reading__{paper_id}") or [""])[0].strip()
                    signal_more = bool(form.get(f"signal_more__{paper_id}"))
                    signal_less = bool(form.get(f"signal_less__{paper_id}"))
                    signal_clear = bool(form.get(f"signal_clear__{paper_id}"))
                    report_action = (form.get(f"report_action__{paper_id}") or [""])[0].strip()
                    note_mode = (form.get(f"note_mode__{paper_id}") or [""])[0].strip()
                    user_note = (form.get(f"note__{paper_id}") or [""])[0].strip()
                    combination_warnings.extend(
                        feedback_combination_warnings(
                            decision,
                            priority,
                            reading_status,
                            signal_more,
                            signal_less,
                        )
                    )
                    if self.apply_feedback_fields(
                        feedback,
                        paper,
                        decision,
                        priority,
                        reading_status,
                        signal_more,
                        signal_less,
                        signal_clear,
                        report_action,
                        user_note,
                        note_mode,
                    ):
                        changed.append(paper)
                        if report_action in {"deep", "review_workflow", "workup", "review_pack"}:
                            review_actions.append((paper.id, report_action))
                if changed:
                    core.save_feedback(feedback_file, feedback)
                    core.apply_feedback_to_knowledge_base(
                        config.kb_dir,
                        changed,
                        profile,
                        feedback,
                        feedback_file,
                        config.profile_path,
                    )
                    core.write_reading_status_report(
                        config.kb_dir,
                        [core.asdict(paper) for paper in core.load_paper_library(config.kb_dir)],
                        feedback,
                    )
                    refreshed = core.refresh_feedback_dependent_outputs(config.kb_dir, config.profile_path, profile, config.papers_json)
                    review_artifacts: list[tuple[str, str, Path]] = []
                    for paper_id, action in review_actions:
                        for label, artifact in self.run_review_artifact(action, paper_id, feedback_file):
                            review_artifacts.append((paper_id, label, artifact))
                    message = f"Saved {len(changed)} selected change{'s' if len(changed) != 1 else ''}."
                    if refreshed.get("reading_plan_html"):
                        message += f"; reading plan: {refreshed['reading_plan_html']}"
                    if refreshed.get("dashboard_html"):
                        message += f"; dashboard: {refreshed['dashboard_html']}"
                    if combination_warnings:
                        message += f"; unusual combinations noted: {len(combination_warnings)}"
                    for paper_id, label, artifact in review_artifacts:
                        message += f"; {paper_id} {label}: {artifact}"
                else:
                    message = "No selected actions or notes to save."
                all_papers = core.load_papers_json(config.papers_json)
                papers = filter_papers_for_view(all_papers, view, feedback)
                for paper in changed:
                    if not any(getattr(item, "id", "") == getattr(paper, "id", "") for item in papers):
                        papers = [paper] + papers
                body = render_page(papers, config, message, feedback=feedback, all_papers=all_papers, view=view).encode("utf-8")
                self.send_html(body)
                return
            if self.path != "/feedback":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            form = parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"))
            paper_id = (form.get("paper_id") or [""])[0]
            action = (form.get("action") or [""])[0]
            note_mode = (form.get("note_mode") or [""])[0].strip()
            user_note = (form.get("note") or [""])[0].strip()
            view = workspace_view_from_query(form)
            papers = core.load_papers_json(config.papers_json)
            selected = [paper for paper in papers if paper.id == paper_id]
            if not selected:
                self.send_error(404, "Paper ID not found")
                return

            mark = None
            more_like_this = False
            less_like_this = False
            note = None
            reading_status = None
            labels: list[str] = []
            if action == "save_note":
                note = None
            elif action == "interested_more":
                mark = "interested"
                more_like_this = True
            elif action == "archive_less":
                mark = "archive"
                less_like_this = True
                reading_status = "not-relevant"
            elif action == "more":
                more_like_this = True
            elif action == "less":
                less_like_this = True
            elif action == "deep":
                mark = "interested"
                more_like_this = True
                reading_status = "reading"
                note = "Queued for deep reading from Review Workspace."
            elif action == "workup":
                mark = "interested"
                more_like_this = True
                reading_status = "reading"
                note = "Queued for workup from Review Workspace."
            elif action == "review_pack":
                mark = "interested"
                more_like_this = True
                reading_status = "reading"
                note = "Queued for review pack from Review Workspace."
            elif action == "review_workflow":
                mark = "interested"
                more_like_this = True
                reading_status = "reading"
                note = "Queued for full review workflow from Review Workspace."
            elif action == "status_reading":
                mark = "interested"
                reading_status = "reading"
            elif action == "status_read":
                mark = "interested"
                reading_status = "read"
            elif action == "status_must_cite":
                mark = "interested"
                reading_status = "must-cite"
                labels = ["must-cite"]
            elif action == "status_method":
                mark = "interested"
                reading_status = "method-reference"
                labels = ["method-reference"]
            elif action == "status_background":
                mark = "neutral"
                reading_status = "background-only"
                note = "Marked as background only from Review Workspace."
            elif action == "status_not_relevant":
                mark = "archive"
                less_like_this = True
                reading_status = "not-relevant"
                note = "Marked as not relevant from Review Workspace."

            profile = core.load_profile(config.profile_path)
            feedback_file = core.default_feedback_file(config.kb_dir)
            feedback = core.load_feedback(feedback_file)
            for paper in selected:
                core.update_paper_feedback(feedback, paper, mark, more_like_this, less_like_this, None)
                record = feedback.setdefault("papers", {}).setdefault(paper.id, {})
                if reading_status:
                    record["reading_status"] = reading_status
                if action == "status_background":
                    signals = record.setdefault("signals", {})
                    signals["more_like_this"] = False
                    signals["less_like_this"] = False
                if labels:
                    current = [str(label) for label in record.get("labels", []) if str(label).strip()]
                    for label in labels:
                        if label not in current:
                            current.append(label)
                    record["labels"] = current
                if action == "status_background":
                    core.remove_feedback_terms_for_paper(feedback, paper.id)
                elif more_like_this:
                    core.remove_feedback_terms_for_paper(feedback, paper.id, "negative")
                elif less_like_this:
                    core.remove_feedback_terms_for_paper(feedback, paper.id, "positive")
                if more_like_this:
                    for term, weight in core.feedback_terms_from_paper(paper):
                        core.add_feedback_term(feedback, term, "positive", weight, "paper", paper.id)
                if less_like_this:
                    for term, weight in core.feedback_terms_from_paper(paper):
                        core.add_feedback_term(feedback, term, "negative", weight, "paper", paper.id)
                update_feedback_note(record, note, user_note, note_mode)
            core.save_feedback(feedback_file, feedback)
            core.apply_feedback_to_knowledge_base(
                config.kb_dir,
                selected,
                profile,
                feedback,
                feedback_file,
                config.profile_path,
            )
            core.write_reading_status_report(config.kb_dir, [core.asdict(paper) for paper in core.load_paper_library(config.kb_dir)], feedback)
            refreshed = core.refresh_feedback_dependent_outputs(config.kb_dir, config.profile_path, profile, config.papers_json)
            deep_report = None
            workflow_report = None
            workup_report = None
            review_pack_report = None
            if action == "deep":
                deep_report = core.write_deep_read_report(
                    profile_path=config.profile_path,
                    kb_dir=config.kb_dir,
                    paper_id=paper_id,
                    papers_json=config.papers_json,
                    feedback_file=feedback_file,
                )
            elif action == "review_workflow":
                workflow_report, _, workup_report, review_pack_report = core.write_review_workflow_report(
                    profile_path=config.profile_path,
                    kb_dir=config.kb_dir,
                    paper_id=paper_id,
                    papers_json=config.papers_json,
                    feedback_file=feedback_file,
                )
            elif action == "workup":
                workup_report, _, _ = core.write_paper_workup_report(
                    profile_path=config.profile_path,
                    kb_dir=config.kb_dir,
                    paper_id=paper_id,
                    papers_json=config.papers_json,
                    feedback_file=feedback_file,
                )
            elif action == "review_pack":
                review_pack_report, _, _ = core.write_review_context_pack_report(
                    profile_path=config.profile_path,
                    kb_dir=config.kb_dir,
                    paper_id=paper_id,
                    papers_json=config.papers_json,
                    feedback_file=feedback_file,
                )

            all_papers = core.load_papers_json(config.papers_json)
            papers = filter_papers_for_view(all_papers, view, feedback)
            if selected and not any(getattr(paper, "id", "") == paper_id for paper in papers):
                papers = selected + papers
            message = f"Saved feedback for {paper_id}: {action}"
            if refreshed.get("reading_plan_html"):
                message += f"; reading plan: {refreshed['reading_plan_html']}"
            if refreshed.get("dashboard_html"):
                message += f"; dashboard: {refreshed['dashboard_html']}"
            if deep_report:
                message += f"; deep-read report: {deep_report}"
            if workflow_report:
                message += f"; review workflow: {workflow_report}"
            if workup_report:
                message += f"; workup report: {workup_report}"
            if review_pack_report:
                message += f"; review pack: {review_pack_report}"
            body = render_page(papers, config, message, feedback=feedback, all_papers=all_papers, view=view).encode("utf-8")
            self.send_html(body)

    return FeedbackHandler


def serve(config: ServerConfig) -> None:
    server = ThreadingHTTPServer((config.host, config.port), make_handler(config))
    url = f"http://{config.host}:{config.port}/"
    print(f"Scholar Alert Review Workspace: {url}")
    print("Press Ctrl-C to stop.")
    if config.open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped Review Workspace.")
    finally:
        server.server_close()
