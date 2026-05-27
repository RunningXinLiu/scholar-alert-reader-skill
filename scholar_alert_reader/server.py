"""Local feedback UI for Scholar Alert Reader."""

from __future__ import annotations

import html
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


def feedback_badges(paper: Any, feedback: dict[str, Any] | None) -> str:
    item = paper_feedback_item(feedback, str(getattr(paper, "id", "")))
    if not item:
        return '<div class="badges feedback-badges">' + render_badge("feedback none") + render_badge("reading unread") + "</div>"
    values = [
        f"feedback {item.get('status', 'neutral')}",
        f"reading {paper_reading_status(paper, feedback)}",
    ]
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


def render_page(papers: list[Any], config: ServerConfig, message: str = "", feedback: dict[str, Any] | None = None) -> str:
    cards = []
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
        cards.append(
            "\n".join(
                [
                    f'<article class="paper" data-tier="{html.escape(str(paper.tier), quote=True)}" data-status="{html.escape(reading_status, quote=True)}" data-search="{html.escape(searchable, quote=True)}">',
                    f"<h2>{html.escape(paper.title)}</h2>",
                    '<div class="badges">'
                    + render_badge(f"id {paper.id}")
                    + render_badge(str(paper.tier))
                    + render_badge(f"score {paper.score}")
                    + "</div>",
                    feedback_badges(paper, feedback),
                    paper_feedback_note_html(paper, feedback),
                    f'<p class="meta">{html.escape(paper.authors_source)}</p>',
                    f'<p class="meta">{html.escape(metadata_summary)}</p>' if metadata_summary else "",
                    f'<p>{html.escape(paper.snippet)}</p>',
                    f'<p><a href="{html.escape(paper.url, quote=True)}">Open paper</a></p>' if paper.url else "",
                    report_links(paper.id, config),
                    f"<ul>{reasons}</ul>" if reasons else "",
                    f'<form method="post" action="/feedback">',
                    f'<input type="hidden" name="paper_id" value="{html.escape(paper.id, quote=True)}">',
                    '<label class="note-input"><span>Personal note</span><textarea name="note" rows="2" placeholder="Why keep, cite, skim, or reject this paper?"></textarea></label>',
                    '<button name="action" value="save_note">Save note</button>',
                    '<button name="action" value="interested_more">Interested + more like this</button>',
                    '<button name="action" value="archive_less">Archive + less like this</button>',
                    '<button name="action" value="more">More like this</button>',
                    '<button name="action" value="less">Less like this</button>',
                    '<button name="action" value="deep">Deep read</button>',
                    '<button name="action" value="review_workflow">Full review</button>',
                    '<button name="action" value="workup">Workup</button>',
                    '<button name="action" value="review_pack">Review pack</button>',
                    '<button name="action" value="status_reading">Reading</button>',
                    '<button name="action" value="status_read">Read</button>',
                    '<button name="action" value="status_must_cite">Must cite</button>',
                    '<button name="action" value="status_method">Method ref</button>',
                    '<button name="action" value="status_background">Background only</button>',
                    '<button name="action" value="status_not_relevant">Not relevant</button>',
                    "</form>",
                    "</article>",
                ]
            )
        )
    content = "\n".join(cards) if cards else '<p class="empty">No papers found in the configured papers.json.</p>'
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="zh-CN">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>Scholar Alert Feedback</title>",
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
            .reports {
              color: var(--muted);
              font-size: 14px;
            }
            .reports a { margin-right: 8px; }
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
            .badges { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
            .feedback-badges { margin-top: -2px; }
            .badge {
              border-radius: 999px;
              background: #eef2f7;
              color: #334e68;
              padding: 3px 8px;
              font-size: 12px;
            }
            form { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
            .note-input {
              flex: 1 0 100%;
              display: grid;
              gap: 4px;
              color: var(--muted);
              font-size: 13px;
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
            a { color: #0b5cad; text-decoration: none; }
            a:hover { text-decoration: underline; }
            @media (max-width: 640px) {
              .toolbar { grid-template-columns: 1fr; }
            }
            """,
            "</style>",
            "</head>",
            "<body>",
            "<header>",
            "<h1>Scholar Alert Feedback</h1>",
            f'<div class="meta">Profile: {html.escape(str(config.profile_path))}</div>',
            f'<div class="meta">Papers: {html.escape(str(config.papers_json))}</div>',
            f'<div class="meta">Knowledge base: {html.escape(str(config.kb_dir))}</div>',
            '<div class="toolbar">',
            '<input id="search" type="search" placeholder="Search title, alert, term, source">',
            '<select id="tier"><option value="">All tiers</option><option>Must read</option><option>Skim</option><option>Archive</option></select>',
            '<select id="status"><option value="">All statuses</option><option>unread</option><option>reading</option><option>read</option><option>must-cite</option><option>method-reference</option><option>background-only</option><option>not-relevant</option></select>',
            "</div>",
            f'<div class="message">{html.escape(message)}</div>' if message else "",
            "</header>",
            "<main>",
            content,
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
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path != "/":
                self.send_error(404)
                return
            papers = core.load_papers_json(config.papers_json)
            feedback = core.load_feedback(core.default_feedback_file(config.kb_dir))
            body = render_page(papers, config, feedback=feedback).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if self.path != "/feedback":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            form = parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"))
            paper_id = (form.get("paper_id") or [""])[0]
            action = (form.get("action") or [""])[0]
            user_note = (form.get("note") or [""])[0].strip()
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
                note = "Queued for deep reading from feedback UI."
            elif action == "workup":
                mark = "interested"
                more_like_this = True
                reading_status = "reading"
                note = "Queued for workup from feedback UI."
            elif action == "review_pack":
                mark = "interested"
                more_like_this = True
                reading_status = "reading"
                note = "Queued for review pack from feedback UI."
            elif action == "review_workflow":
                mark = "interested"
                more_like_this = True
                reading_status = "reading"
                note = "Queued for full review workflow from feedback UI."
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
                note = "Marked as background only from feedback UI."
            elif action == "status_not_relevant":
                mark = "archive"
                less_like_this = True
                reading_status = "not-relevant"
                note = "Marked as not relevant from feedback UI."

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
                append_feedback_note(record, note)
                append_feedback_note(record, user_note)
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

            papers = core.load_papers_json(config.papers_json)
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
            body = render_page(papers, config, message, feedback=feedback).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return FeedbackHandler


def serve(config: ServerConfig) -> None:
    server = ThreadingHTTPServer((config.host, config.port), make_handler(config))
    url = f"http://{config.host}:{config.port}/"
    print(f"Scholar Alert feedback UI: {url}")
    print("Press Ctrl-C to stop.")
    if config.open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped feedback UI.")
    finally:
        server.server_close()
