"""Local Review Workspace for Scholar Alert Reader."""

from __future__ import annotations

import html
import json
import re
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

DEFAULT_WORKSPACE_CARD_LIMIT = 160


@dataclass
class ServerConfig:
    profile_path: Path
    kb_dir: Path
    papers_json: Path
    host: str = "127.0.0.1"
    port: int = 8765
    open_browser: bool = False
    language: str = "en"


UI_TEXT = {
    "en": {
        "all_statuses": "All statuses",
        "all_tiers": "All tiers",
        "answers": "Answers",
        "append_note": "Append typed note",
        "archive": "Archive",
        "archive_review": "Archive review",
        "ask_library": "Ask library",
        "ask_library_placeholder": "Ask your library, e.g. which papers are closest to my current project?",
        "ask_paper": "Ask about this paper",
        "ask_paper_placeholder": "Ask about this paper against your foundation/interested library",
        "auto": "Auto",
        "back_to_workspace": "Back to review workspace",
        "batch_review": "Batch review",
        "clear_metadata_action": "Clear metadata action",
        "clear_report": "Clear report",
        "clear_saved_note": "Clear saved note",
        "clear_signal": "Clear signal",
        "current_digest": "Current digest",
        "daily_digest": "Daily digest",
        "dashboard": "Dashboard",
        "decision": "Decision",
        "decision_help": "Keep/archive decision.",
        "demo_review": "Demo review",
        "digest_papers": "Digest papers",
        "domain": "Source domain",
        "doi": "DOI",
        "evidence_pdf_link_ready": "An open PDF URL or local PDF path is known, but no local full-text brief is cached yet.",
        "evidence_full_text_backed": "Local full-text cache or full-text brief exists for closer reading.",
        "evidence_local_pdf_ready": "A local PDF path exists; run full-text or review-workflow to extract evidence.",
        "evidence_metadata_enriched": "Includes public metadata enrichment, but not paper full text.",
        "evidence_metadata_only": "Uses title, source line, snippet, alert/import metadata, profile terms, and feedback signals.",
        "fetch_abstract": "Fetch abstract",
        "feedback_none": "feedback none",
        "foundation": "Foundation",
        "foundation_digest": "Foundation digest",
        "foundation_review": "Foundation review",
        "full_review": "Full review",
        "full_review_set": "Full review set",
        "generate_report": "Generate report on save",
        "improve_metadata": "Improve metadata on save",
        "interested": "Interested",
        "interested_file": "Interested",
        "issue": "Issue",
        "journal": "Journal / venue",
        "kb": "Knowledge base",
        "learning_help": "Optional ranking feedback for future runs.",
        "learning_signal": "Learning signal",
        "library_index": "Library index",
        "load_all": "Load all cards",
        "metadata_enrichment": "Metadata enrichment",
        "metadata_help": "Looks up public OpenAlex/Crossref metadata for this paper only. It may take a few seconds.",
        "mode": "Mode",
        "more_like": "More like this",
        "must_read": "Must read",
        "must_read_only": "Must read only",
        "neutral": "Neutral",
        "no_change": "No change",
        "no_papers_title": "No papers in this run",
        "note": "Note",
        "note_help": "Blank text with the default mode leaves existing notes unchanged.",
        "note_placeholder": "Optional note; choose Replace to overwrite, or Clear saved note to remove the current note.",
        "open_paper": "Open paper",
        "open_workspace": "Open workspace",
        "pages": "Pages",
        "papers": "Papers",
        "paper_workspace": "Scholar Alert Paper Workspace",
        "priority": "Priority",
        "priority_help": "Manual tier override.",
        "profile": "Profile",
        "publication_details": "Publication details",
        "read": "Read",
        "reading": "Reading",
        "reading_plan": "Reading plan",
        "reading_status": "Reading status",
        "reading_status_file": "Reading status",
        "reading_status_help": "Reading progress or use.",
        "recent_review": "Recent review",
        "retained_library": "Retained library",
        "replace_note": "Replace saved note",
        "reports": "Reports",
        "review_pack": "Review pack",
        "review_workflow": "Review workflow",
        "save_selected": "Save selected changes",
        "search_placeholder": "Search title, alert, term, source",
        "showing": "Showing",
        "skim": "Skim",
        "skim_only": "Skim only",
        "source": "Source",
        "source_items": "Source items",
        "source_line": "Scholar source line",
        "status_unread": "unread",
        "view": "View",
        "weekly_review": "Weekly review",
        "workup": "Workup",
        "workspace": "Scholar Alert Review Workspace",
        "year": "Year",
        "volume": "Volume",
        "unavailable": "Unavailable from current alert/metadata",
        "abstract": "Abstract",
        "abstract_or_snippet": "Abstract / snippet",
        "no_abstract": "No abstract or alert snippet is available.",
        "full_snippet": "Showing the full abstract/snippet text available in this source record.",
        "truncated_snippet": "The source record already ends with an ellipsis; the UI is showing all text available from the alert/source item.",
        "enriched_abstract": "Showing an enriched public metadata abstract from {provider}; the Scholar Alert snippet may be shorter or truncated.",
    },
    "zh": {
        "all_statuses": "全部阅读状态",
        "all_tiers": "全部层级",
        "answers": "问答记录",
        "append_note": "追加新笔记",
        "archive": "归档",
        "archive_review": "归档复查",
        "ask_library": "询问文献库",
        "ask_library_placeholder": "询问当前文献库，例如：哪些论文最接近我的当前项目？",
        "ask_paper": "询问这篇论文",
        "ask_paper_placeholder": "结合 foundation/interested library 询问这篇论文",
        "auto": "自动",
        "back_to_workspace": "返回 Review Workspace",
        "batch_review": "批量筛选",
        "clear_metadata_action": "清除元数据操作",
        "clear_report": "清除报告选择",
        "clear_saved_note": "清除已保存笔记",
        "clear_signal": "清除学习信号",
        "current_digest": "当前 digest",
        "daily_digest": "Daily digest",
        "dashboard": "Dashboard",
        "decision": "处理决定",
        "decision_help": "保留或归档这篇论文。",
        "demo_review": "Demo 筛选",
        "digest_papers": "Digest 论文数",
        "domain": "来源域名",
        "doi": "DOI",
        "evidence_pdf_link_ready": "已知道开放 PDF 链接或本地 PDF 路径，但还没有本地全文缓存。",
        "evidence_full_text_backed": "已有本地全文缓存或全文 brief，可用于更深入阅读。",
        "evidence_local_pdf_ready": "已有本地 PDF 路径；可运行 full-text 或 review-workflow 提取证据。",
        "evidence_metadata_enriched": "包含公开元数据补全，但还不是论文全文证据。",
        "evidence_metadata_only": "基于标题、来源行、摘要片段、alert/import 元数据、profile 词和反馈信号。",
        "fetch_abstract": "补全摘要",
        "feedback_none": "未反馈",
        "foundation": "Foundation",
        "foundation_digest": "Foundation digest",
        "foundation_review": "Foundation 复查",
        "full_review": "完整复查",
        "full_review_set": "完整列表",
        "generate_report": "保存时生成报告",
        "improve_metadata": "保存时补全元数据",
        "interested": "感兴趣",
        "interested_file": "Interested",
        "issue": "期",
        "journal": "期刊 / 会议 / 来源",
        "kb": "知识库",
        "learning_help": "给未来排序使用的可选反馈。",
        "learning_signal": "学习信号",
        "library_index": "文献库首页",
        "load_all": "加载全部卡片",
        "metadata_enrichment": "元数据补全",
        "metadata_help": "只为这篇论文查询公开 OpenAlex/Crossref 元数据，可能需要几秒。",
        "mode": "模式",
        "more_like": "以后多推荐类似",
        "must_read": "重点阅读",
        "must_read_only": "只看重点阅读",
        "neutral": "中立",
        "no_change": "不修改",
        "no_papers_title": "本次没有论文",
        "note": "笔记",
        "note_help": "默认模式下，空白文本不会修改已有笔记。",
        "note_placeholder": "可选笔记；选择“替换”可覆盖，选择“清除”可删除当前笔记。",
        "open_paper": "打开原文",
        "open_workspace": "打开单篇工作区",
        "pages": "页码",
        "papers": "论文",
        "paper_workspace": "Scholar Alert 单篇论文工作区",
        "priority": "阅读优先级",
        "priority_help": "手动覆盖 Must read / Skim / Archive。",
        "profile": "研究画像",
        "publication_details": "出版信息",
        "read": "已读",
        "reading": "在读",
        "reading_plan": "阅读计划",
        "reading_status": "阅读状态",
        "reading_status_file": "阅读状态",
        "reading_status_help": "阅读进度或用途。",
        "recent_review": "最近邮件复查",
        "retained_library": "保留文献库",
        "replace_note": "替换已保存笔记",
        "reports": "报告",
        "review_pack": "Review pack",
        "review_workflow": "Review workflow",
        "save_selected": "保存选中修改",
        "search_placeholder": "搜索标题、alert、关键词、来源",
        "showing": "显示",
        "skim": "略读",
        "skim_only": "只看略读",
        "source": "来源",
        "source_items": "来源条目",
        "source_line": "Scholar 来源行",
        "status_unread": "未读",
        "view": "视图",
        "weekly_review": "周回顾",
        "workup": "Workup",
        "workspace": "Scholar Alert 文献分诊",
        "year": "年份",
        "volume": "卷",
        "unavailable": "当前 alert/元数据未提供",
        "abstract": "摘要",
        "abstract_or_snippet": "摘要 / 片段",
        "no_abstract": "当前没有摘要或 alert 片段。",
        "full_snippet": "当前显示的是这个来源记录中可获得的完整摘要/片段。",
        "truncated_snippet": "来源记录本身已经以省略号结尾；这里显示的是 alert/source item 提供的全部文本。",
        "enriched_abstract": "显示来自 {provider} 的公开元数据摘要；Scholar Alert 片段可能更短或被截断。",
    },
}


def normalize_ui_language(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    return "zh" if raw.startswith("zh") else "en"


def ui_language(config: ServerConfig) -> str:
    return normalize_ui_language(config.language)


def ui_text(config: ServerConfig, key: str) -> str:
    lang = ui_language(config)
    return UI_TEXT.get(lang, UI_TEXT["en"]).get(key, UI_TEXT["en"].get(key, key))


def tier_display(config: ServerConfig, tier: str) -> str:
    mapping = {"Must read": "must_read", "Skim": "skim", "Archive": "archive"}
    key = mapping.get(str(tier), "")
    return ui_text(config, key) if key else str(tier)


def status_display(config: ServerConfig, status: str) -> str:
    mapping = {
        "unread": "status_unread",
        "reading": "reading",
        "read": "read",
        "must-cite": "Must cite",
        "method-reference": "Method ref",
        "background-only": "Background only",
        "not-relevant": "Not relevant",
    }
    value = mapping.get(str(status), str(status))
    if ui_language(config) != "zh" or value not in {"Must cite", "Method ref", "Background only", "Not relevant"}:
        return ui_text(config, value) if value in UI_TEXT["en"] else value
    return {
        "Must cite": "必须引用",
        "Method ref": "方法参考",
        "Background only": "背景阅读",
        "Not relevant": "不相关",
    }[value]


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


def feedback_badges(paper: Any, feedback: dict[str, Any] | None, config: ServerConfig | None = None) -> str:
    config = config or ServerConfig(profile_path=Path("."), kb_dir=Path("."), papers_json=Path("."))
    item = paper_feedback_item(feedback, str(getattr(paper, "id", "")))
    if not item:
        return (
            '<div class="badges feedback-badges">'
            + render_badge(ui_text(config, "feedback_none"))
            + render_badge(f'{ui_text(config, "reading_status")} {status_display(config, "unread")}')
            + "</div>"
        )
    values = [
        f'{ui_text(config, "decision")} {item.get("status", "neutral")}',
        f'{ui_text(config, "reading_status")} {status_display(config, paper_reading_status(paper, feedback))}',
    ]
    priority_override = paper_priority_override(paper, feedback)
    if priority_override:
        values.append(f'{ui_text(config, "priority")} {priority_override.replace("_", " ")}')
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


def paper_feedback_note_html(paper: Any, feedback: dict[str, Any] | None, config: ServerConfig | None = None) -> str:
    config = config or ServerConfig(profile_path=Path("."), kb_dir=Path("."), papers_json=Path("."))
    item = paper_feedback_item(feedback, str(getattr(paper, "id", "")))
    note = str(item.get("note", "") or "").strip()
    if not note:
        return ""
    return f'<div class="note"><strong>{html.escape(ui_text(config, "note"))}</strong><pre>' + html.escape(note) + "</pre></div>"


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


def localized_system_note(config: ServerConfig, note: str | None) -> str | None:
    if ui_language(config) != "zh" or not note:
        return note
    mapping = {
        "Queued for deep reading from Review Workspace.": "已从 Review Workspace 加入 deep read 队列。",
        "Queued for workup from Review Workspace.": "已从 Review Workspace 加入 workup 队列。",
        "Queued for review pack from Review Workspace.": "已从 Review Workspace 加入 review pack 队列。",
        "Queued for full review workflow from Review Workspace.": "已从 Review Workspace 加入完整复查 workflow。",
        "Marked as background only from Review Workspace.": "已从 Review Workspace 标记为背景阅读。",
        "Marked as not relevant from Review Workspace.": "已从 Review Workspace 标记为不相关。",
    }
    return mapping.get(note, note)


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


def publication_metadata_html(paper: Any, config: ServerConfig | None = None) -> str:
    config = config or ServerConfig(profile_path=Path("."), kb_dir=Path("."), papers_json=Path("."))
    values = publication_metadata_values(paper)
    unavailable = ui_text(config, "unavailable")
    core_fields = [
        (ui_text(config, "journal"), values["venue"] or unavailable),
        (ui_text(config, "year"), values["year"] or unavailable),
        (ui_text(config, "volume"), values["volume"] or unavailable),
        (ui_text(config, "issue"), values["issue"] or unavailable),
    ]
    optional_fields = [
        (ui_text(config, "pages"), values["pages"]),
        (ui_text(config, "doi"), values["doi"]),
        (ui_text(config, "domain"), values["domain"]),
    ]
    fields = core_fields + [(label, value) for label, value in optional_fields if value]
    items = "".join(
        f'<div class="pub-field"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>'
        for label, value in fields
    )
    return f'<div class="publication-meta"><strong>{html.escape(ui_text(config, "publication_details"))}</strong><div class="pub-grid">{items}</div></div>'


def scholar_source_line_html(paper: Any, config: ServerConfig | None = None) -> str:
    config = config or ServerConfig(profile_path=Path("."), kb_dir=Path("."), papers_json=Path("."))
    source_line = str(getattr(paper, "authors_source", "") or "").strip()
    if not source_line:
        return ""
    return (
        f'<p class="source-line"><strong>{html.escape(ui_text(config, "source_line"))}</strong>'
        f"<span>{html.escape(source_line)}</span></p>"
    )


def _metadata_abstract_candidates(paper: Any) -> list[tuple[str, str]]:
    metadata = getattr(paper, "metadata", {}) or {}
    if not isinstance(metadata, dict):
        return []
    candidates: list[tuple[str, str]] = []
    for provider, label in [
        ("openalex", "OpenAlex abstract"),
        ("crossref", "Crossref abstract"),
        ("web", "webpage abstract"),
        ("bibtex", "BibTeX abstract"),
        ("ris", "RIS abstract"),
        ("arxiv", "arXiv abstract"),
        ("feed", "feed abstract"),
    ]:
        item = metadata.get(provider)
        if not isinstance(item, dict):
            continue
        for key in ["abstract", "citation_abstract", "description", "summary"]:
            value = str(item.get(key, "") or "").strip()
            if value:
                candidates.append((label, value))
                break
    return candidates


def best_abstract_or_snippet(paper: Any, config: ServerConfig | None = None) -> tuple[str, str, str]:
    config = config or ServerConfig(profile_path=Path("."), kb_dir=Path("."), papers_json=Path("."))
    snippet = str(getattr(paper, "snippet", "") or "").strip()
    source_truncated = snippet.endswith("…") or snippet.endswith("...")
    for label, abstract in _metadata_abstract_candidates(paper):
        if len(abstract) > max(len(snippet) + 80, 300) or source_truncated:
            provider = label.split()[0]
            hint = ui_text(config, "enriched_abstract").format(provider=provider)
            return ui_text(config, "abstract"), abstract, hint
    if not snippet:
        return ui_text(config, "abstract_or_snippet"), "", ui_text(config, "no_abstract")
    hint = (
        ui_text(config, "truncated_snippet")
        if source_truncated
        else ui_text(config, "full_snippet")
    )
    return ui_text(config, "abstract_or_snippet"), snippet, hint


def _render_latex_fragment(fragment: str) -> str:
    text = " ".join(fragment.strip().split())
    replacements = {
        r"\leq": "≤",
        r"\geq": "≥",
        r"\times": "×",
        r"\pm": "±",
        r"\alpha": "α",
        r"\beta": "β",
        r"\gamma": "γ",
        r"\delta": "δ",
        r"\lambda": "λ",
        r"\mu": "μ",
        r"\sigma": "σ",
    }
    for raw, rendered in replacements.items():
        text = text.replace(raw, rendered)
    rendered = html.escape(text)
    rendered = re.sub(r"\^\{([^{}]+)\}", r"<sup>\1</sup>", rendered)
    rendered = re.sub(r"\^([A-Za-z0-9.+\-]+)", r"<sup>\1</sup>", rendered)
    rendered = re.sub(r"_\{([^{}]+)\}", r"<sub>\1</sub>", rendered)
    rendered = re.sub(r"_([A-Za-z0-9.+\-]+)", r"<sub>\1</sub>", rendered)
    return f'<span class="math-inline">{rendered}</span>'


def render_academic_inline_text(value: str) -> str:
    text = html.unescape(str(value or "").strip())
    if not text:
        return ""
    parts: list[str] = []
    index = 0
    for match in re.finditer(r"\$([^$\n]{1,160})\$", text):
        parts.append(html.escape(text[index : match.start()]))
        parts.append(_render_latex_fragment(match.group(1)))
        index = match.end()
    parts.append(html.escape(text[index:]))
    return "".join(parts)


def abstract_snippet_html(paper: Any, config: ServerConfig | None = None) -> str:
    label, text, hint = best_abstract_or_snippet(paper, config)
    if not text:
        return f'<div class="snippet-block missing"><strong>{html.escape(label)}</strong><p>{html.escape(hint)}</p></div>'
    rendered_text = render_academic_inline_text(text)
    return f'<div class="snippet-block"><strong>{html.escape(label)}</strong><p>{rendered_text}</p><div class="snippet-hint">{html.escape(hint)}</div></div>'


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
    description = {
        "metadata-only": ui_text(config, "evidence_metadata_only"),
        "metadata-enriched": ui_text(config, "evidence_metadata_enriched"),
        "PDF-link-ready": ui_text(config, "evidence_pdf_link_ready"),
        "local-PDF-ready": ui_text(config, "evidence_local_pdf_ready"),
        "full-text-backed": ui_text(config, "evidence_full_text_backed"),
    }.get(str(summary.get("level", "")), str(summary["description"]))
    return (
        '<div class="badges evidence-badges">'
        + "".join(render_badge(value) for value in badges)
        + "</div>"
        + f'<p class="evidence-note">{html.escape(description)}</p>'
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
        ("current_digest", ui_text(config, "current_digest"), out_dir / "digest.html"),
        ("library_index", ui_text(config, "library_index"), config.kb_dir / "index.html"),
        ("reading_plan", ui_text(config, "reading_plan"), config.kb_dir / "reading_plan.html"),
        ("foundation", ui_text(config, "foundation"), config.kb_dir / "foundation.md"),
        ("interested", ui_text(config, "interested_file"), config.kb_dir / "interested.md"),
        ("reading_status", ui_text(config, "reading_status_file"), config.kb_dir / "reading_status.md"),
        ("weekly_review", ui_text(config, "weekly_review"), config.kb_dir / "weekly_review.md"),
        ("answers", ui_text(config, "answers"), config.kb_dir / "answers_index.md"),
    ]
    if project_dir:
        candidates.insert(0, ("dashboard", ui_text(config, "dashboard"), project_dir / "DASHBOARD.html"))
        candidates.extend(
            [
                ("daily_digest", ui_text(config, "daily_digest"), project_dir / "reader_out" / "daily" / "digest.html"),
                ("foundation_digest", ui_text(config, "foundation_digest"), project_dir / "reader_out" / "foundation" / "digest.html"),
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
        return ui_text(config, "foundation_review")
    if "daily" in parts:
        return ui_text(config, "daily_digest")
    if "recent" in parts:
        return ui_text(config, "recent_review")
    if "demo" in parts:
        return ui_text(config, "demo_review")
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
    paper_path_parts = {part.lower() for part in config.papers_json.parts}
    if "foundation" in paper_path_parts:
        note = (
            "你正在复查 foundation 文献库。这里的反馈会更新 interested/foundation 输出，并影响后续 daily ranking。"
            if ui_language(config) == "zh"
            else "You are reviewing the foundation library. Feedback here updates interested/foundation outputs and tunes future daily ranking."
        )
    elif len(papers) == 0:
        note = (
            "本次运行没有可筛选论文。可以从顶部链接打开 Foundation，或不设置 PAPERS_JSON 运行 ./serve_reader.sh 自动回退到 foundation。"
            if ui_language(config) == "zh"
            else "This run has no reviewable papers. Open Foundation review from the top links, or run ./serve_reader.sh without PAPERS_JSON to fall back automatically."
        )
    else:
        note = (
            "你正在筛选当前运行结果。这里的操作会刷新 Foundation、Interested、Reading Plan 和未来排序信号。"
            if ui_language(config) == "zh"
            else "You are reviewing the current run. Paper actions here refresh Foundation, Interested, Reading Plan, and future ranking signals."
        )
    question_html = (
        '<div class="question-strip">'
        + "".join(f'<div class="question-pill">{html.escape(question)}</div>' for question in questions)
        + "</div>"
        if questions
        else ""
    )
    view_labels = {
        "active": "当前筛选队列" if ui_language(config) == "zh" else "Active review queue",
        "must-read": ui_text(config, "must_read_only"),
        "skim": ui_text(config, "skim_only"),
        "archive": ui_text(config, "archive_review"),
        "all": ui_text(config, "full_review_set"),
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
            f'<a class="digest-panel" href="#must-read"><strong>{tier_counts.get("Must read", 0)}</strong><span>{html.escape(ui_text(config, "must_read"))}</span></a>',
            f'<a class="digest-panel" href="#skim"><strong>{tier_counts.get("Skim", 0)}</strong><span>{html.escape(ui_text(config, "skim"))}</span></a>',
            f'<a class="digest-panel" href="#archive"><strong>{tier_counts.get("Archive", 0)}</strong><span>{html.escape(ui_text(config, "archive"))}</span></a>',
            f'<div class="digest-panel"><strong>{status_counts.get("unread", 0)}</strong><span>{html.escape(status_display(config, "unread"))}</span></div>',
            "</div>",
            '<div class="run-details">',
            f"<span>{html.escape(ui_text(config, 'view'))}: {html.escape(view_labels.get(view, view))}</span>",
            f"<span>{html.escape(ui_text(config, 'showing'))}: {visible} / {len(papers)}</span>" if ui_language(config) == "zh" else f"<span>Showing: {visible} of {len(papers)}</span>",
            f"<span>{html.escape(ui_text(config, 'mode'))}: {html.escape(mode)}</span>",
            f"<span>{html.escape(ui_text(config, 'source'))}: {html.escape(source)}</span>",
            f"<span>{html.escape(ui_text(config, 'source_items'))}: {html.escape(source_items)}</span>",
            f"<span>{html.escape(ui_text(config, 'digest_papers'))}: {html.escape(papers_in_digest or str(len(papers)))}</span>",
            f"<span>{html.escape(ui_text(config, 'retained_library'))}: {html.escape(retained)}</span>",
            "</div>",
            question_html,
            '<nav class="workspace-tabs">',
            f'<a href="/?view=active#overview">{html.escape(view_labels["active"])}</a>',
            f'<a href="/?view=must-read#must-read">{html.escape(ui_text(config, "must_read"))}</a>',
            f'<a href="/?view=skim#skim">{html.escape(ui_text(config, "skim"))}</a>',
            f'<a href="/?view=archive#archive">{html.escape(ui_text(config, "archive"))}</a>',
            f'<a href="/?view=all#all-papers">{html.escape(ui_text(config, "load_all"))}</a>',
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


def workspace_limit_from_query(query: dict[str, list[str]]) -> int | None:
    raw = (query.get("limit") or [""])[0].strip().lower()
    if raw in {"all", "full", "none", "0"}:
        return None
    if raw.isdigit():
        limit = int(raw)
        return limit if limit > 0 else None
    return DEFAULT_WORKSPACE_CARD_LIMIT


def limit_workspace_papers(papers: list[Any], view: str, limit: int | None, config: ServerConfig | None = None) -> tuple[list[Any], str]:
    config = config or ServerConfig(profile_path=Path("."), kb_dir=Path("."), papers_json=Path("."))
    if limit is None or view == "all" or len(papers) <= limit:
        return papers, ""
    if view == "active":
        must_read = [paper for paper in papers if str(getattr(paper, "tier", "")) == "Must read"]
        others = [paper for paper in papers if str(getattr(paper, "tier", "")) != "Must read"]
        selected = must_read + others[: max(limit - len(must_read), 0)]
        if not selected:
            selected = papers[:limit]
        elif len(selected) < min(limit, len(papers)):
            selected_ids = {str(getattr(paper, "id", "")) for paper in selected}
            for paper in papers:
                if str(getattr(paper, "id", "")) not in selected_ids:
                    selected.append(paper)
                if len(selected) >= limit:
                    break
    else:
        selected = papers[:limit]
    if ui_language(config) == "zh":
        notice = (
            f"当前只加载较轻量的筛选批次（本视图 {len(selected)} / {len(papers)} 张卡片），这样反馈控件会更流畅。"
            '用 <a href="/?view=all#all-papers">加载全部卡片</a> 查看完整列表。'
        )
    else:
        notice = (
            f"Showing a lighter review batch ({len(selected)} of {len(papers)} cards in this view) so feedback controls stay responsive. "
            'Use <a href="/?view=all#all-papers">Load all cards</a> for the complete set.'
        )
    return selected, notice


def render_grouped_cards(card_rows: list[tuple[str, str]], tier_counts: dict[str, int], config: ServerConfig | None = None) -> str:
    config = config or ServerConfig(profile_path=Path("."), kb_dir=Path("."), papers_json=Path("."))
    if not card_rows:
        return (
            '<section class="empty-panel">'
            f"<h2>{html.escape(ui_text(config, 'no_papers_title'))}</h2>"
            + (
                '<p class="empty">这个 papers.json 为空。可以用顶部链接打开 Foundation / Interested / 历史 digest，或对 foundation papers 运行 workspace。</p>'
                if ui_language(config) == "zh"
                else '<p class="empty">This papers.json is empty. Use the navigation above to open Foundation, Interested, or a previous digest, or run the workspace against foundation papers.</p>'
            )
            + "</section>"
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
                    f'<h2 class="section-heading">{html.escape(tier_display(config, tier))} <span>{tier_counts.get(tier, len(cards))}</span></h2>',
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
                    f'<h2 class="section-heading">{html.escape(tier_display(config, tier))} <span>{len(cards)}</span></h2>',
                    *cards,
                    "</section>",
                ]
            )
        )
    return "\n".join(sections)


def batch_save_bar(position: str = "top", config: ServerConfig | None = None) -> str:
    config = config or ServerConfig(profile_path=Path("."), kb_dir=Path("."), papers_json=Path("."))
    label = ui_text(config, "save_selected")
    pending = "无待保存修改" if ui_language(config) == "zh" else "No pending changes"
    return "\n".join(
        [
            f'<div class="batch-save-bar batch-save-bar-{html.escape(position, quote=True)}">',
            f'<div><strong>{html.escape(ui_text(config, "batch_review"))}</strong><span class="pending-count">{html.escape(pending)}</span></div>',
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
    limit_notice_html: str = "",
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
                        + render_badge(tier_display(config, str(paper.tier)))
                        + render_badge(f"score {paper.score}")
                        + "</div>",
                        paper_evidence_html(paper, config),
                        feedback_badges(paper, feedback, config),
                        paper_feedback_note_html(paper, feedback, config),
                        scholar_source_line_html(paper, config),
                        f'<p class="meta enrichment-line"><strong>{html.escape(ui_text(config, "metadata_enrichment"))}</strong><span>{html.escape(metadata_summary)}</span></p>'
                        if metadata_summary
                        else "",
                        publication_metadata_html(paper, config),
                        abstract_snippet_html(paper, config),
                        '<p class="paper-links">'
                        + (
                            f'<a href="/paper?id={quote(paper.id, safe="")}">{html.escape(ui_text(config, "open_workspace"))}</a>'
                            if focused_paper is None
                            else f'<a href="/">{html.escape(ui_text(config, "back_to_workspace"))}</a>'
                        )
                        + (f' · <a href="{html.escape(paper.url, quote=True)}">{html.escape(ui_text(config, "open_paper"))}</a>' if paper.url else "")
                        + "</p>",
                        report_links(paper.id, config),
                        selected_answer_links(paper.id, config),
                        f"<ul>{reasons}</ul>" if reasons else "",
                        '<div class="review-controls">',
                        f'<input type="hidden" name="paper_id" value="{html.escape(paper.id, quote=True)}">',
                        f'<input type="hidden" class="report-action" name="report_action__{html.escape(paper.id, quote=True)}" value="">',
                        f'<input type="hidden" class="metadata-action" name="metadata_action__{html.escape(paper.id, quote=True)}" value="">',
                        '<div class="review-grid">',
                        review_select(
                            f"decision__{paper.id}",
                            ui_text(config, "decision"),
                            [
                                ("", ui_text(config, "no_change")),
                                ("interested", ui_text(config, "interested")),
                                ("neutral", ui_text(config, "neutral")),
                                ("archive", ui_text(config, "archive")),
                            ],
                            ui_text(config, "decision_help"),
                        ),
                        review_select(
                            f"priority__{paper.id}",
                            ui_text(config, "priority"),
                            [
                                ("", ui_text(config, "no_change")),
                                ("auto", ui_text(config, "auto")),
                                ("must_read", ui_text(config, "must_read")),
                                ("skim", ui_text(config, "skim")),
                                ("archive", ui_text(config, "archive")),
                            ],
                            ui_text(config, "priority_help"),
                        ),
                        review_select(
                            f"reading__{paper.id}",
                            ui_text(config, "reading_status"),
                            [
                                ("", ui_text(config, "no_change")),
                                ("unread", status_display(config, "unread")),
                                ("reading", status_display(config, "reading")),
                                ("read", status_display(config, "read")),
                                ("must-cite", status_display(config, "must-cite")),
                                ("method-reference", status_display(config, "method-reference")),
                                ("background-only", status_display(config, "background-only")),
                                ("not-relevant", status_display(config, "not-relevant")),
                            ],
                            ui_text(config, "reading_status_help"),
                        ),
                        "</div>",
                        f'<div class="review-field learning-field"><span>{html.escape(ui_text(config, "learning_signal"))}</span><div class="checkbox-row">',
                        review_checkbox(f"signal_more__{paper.id}", ui_text(config, "more_like"), "signal-more"),
                        review_checkbox(f"signal_less__{paper.id}", "以后少推荐类似" if ui_language(config) == "zh" else "Less like this", "signal-less"),
                        review_checkbox(f"signal_clear__{paper.id}", ui_text(config, "clear_signal"), "signal-clear"),
                        f'</div><span class="control-help">{html.escape(ui_text(config, "learning_help"))}</span></div>',
                        '<div class="combo-warning" hidden></div>',
                        f'<div class="review-field report-field"><span>{html.escape(ui_text(config, "generate_report"))}</span>',
                        '<div class="action-row">',
                        '<button type="button" class="action-chip" data-set-report="deep" value="deep">Deep read</button>',
                        f'<button type="button" class="action-chip" data-set-report="review_workflow" value="review_workflow">{html.escape(ui_text(config, "full_review"))}</button>',
                        f'<button type="button" class="action-chip" data-set-report="workup" value="workup">{html.escape(ui_text(config, "workup"))}</button>',
                        f'<button type="button" class="action-chip" data-set-report="review_pack" value="review_pack">{html.escape(ui_text(config, "review_pack"))}</button>',
                        f'<button type="button" class="action-chip clear-action" data-set-report="" value="">{html.escape(ui_text(config, "clear_report"))}</button>',
                        "</div></div>",
                        f'<div class="review-field metadata-field"><span>{html.escape(ui_text(config, "improve_metadata"))}</span>',
                        '<div class="action-row">',
                        f'<button type="button" class="action-chip" data-set-metadata="abstract" value="abstract">{html.escape(ui_text(config, "fetch_abstract"))}</button>',
                        f'<button type="button" class="action-chip clear-action" data-set-metadata="" value="">{html.escape(ui_text(config, "clear_metadata_action"))}</button>',
                        f'</div><span class="control-help">{html.escape(ui_text(config, "metadata_help"))}</span></div>',
                        f'<label class="note-input"><span>{html.escape(ui_text(config, "note"))}</span>'
                        + '<div class="note-tools">'
                        + f'<select class="review-select note-mode" name="note_mode__{html.escape(paper.id, quote=True)}">'
                        + select_options(
                            [
                                ("", ui_text(config, "append_note")),
                                ("replace", ui_text(config, "replace_note")),
                                ("clear", ui_text(config, "clear_saved_note")),
                            ]
                        )
                        + "</select>"
                        + f'<span class="control-help">{html.escape(ui_text(config, "note_help"))}</span>'
                        + "</div>"
                        + f'<textarea class="paper-note" name="note__{html.escape(paper.id, quote=True)}" rows="2" placeholder="{html.escape(ui_text(config, "note_placeholder"), quote=True)}"></textarea></label>',
                        "</div>",
                        "</article>",
                    ]
                ),
            )
        )
    content = render_grouped_cards(card_rows, visible_tier_counts, config)
    context = load_workspace_context(config)
    overview = "" if focused_paper is not None else render_workspace_overview(all_papers, config, context, tier_counts, status_counts, view=view, visible_count=len(papers))
    stat_items = [
        f"{ui_text(config, 'showing')} {len(papers)} / {len(all_papers)}" if ui_language(config) == "zh" else f"Showing {len(papers)} of {len(all_papers)}",
        f"{ui_text(config, 'must_read')} {tier_counts.get('Must read', 0)}",
        f"{ui_text(config, 'skim')} {tier_counts.get('Skim', 0)}",
        f"{ui_text(config, 'archive')} {tier_counts.get('Archive', 0)}",
        f"{status_display(config, 'unread')} {status_counts.get('unread', 0)}",
        f"{status_display(config, 'reading')} {status_counts.get('reading', 0)}",
        f"{status_display(config, 'read')} {status_counts.get('read', 0)}",
    ]
    js_labels = {
        "noPending": "无待保存修改" if ui_language(config) == "zh" else "No pending changes",
        "pendingSingular": "项待保存修改" if ui_language(config) == "zh" else "pending change",
        "pendingPlural": "项待保存修改" if ui_language(config) == "zh" else "pending changes",
        "nothingToSave": "没有选中操作或笔记需要保存。" if ui_language(config) == "zh" else "No selected actions or notes to save.",
        "unusualIntro": "有些反馈组合不太常见：" if ui_language(config) == "zh" else "Some feedback combinations are unusual:",
        "saveAnyway": "仍然保存？" if ui_language(config) == "zh" else "Save anyway?",
        "warnInterestedLess": "感兴趣 + 以后少推荐类似：这篇会保留，但相似论文后续会降权。" if ui_language(config) == "zh" else "Interested + Less like this keeps this paper but downranks similar future papers.",
        "warnArchiveMore": "归档 + 以后多推荐类似：这篇会归档，但相似论文后续会加权。" if ui_language(config) == "zh" else "Archive + More like this archives this paper but boosts similar future papers.",
        "warnPriorityArchiveMore": "优先级归档 + 以后多推荐类似不常见；这篇论文以归档优先。" if ui_language(config) == "zh" else "Priority Archive + More like this is unusual; archive priority wins for this paper.",
        "warnMustLess": "重点阅读 + 以后少推荐类似不常见；这篇保留重点阅读，但相似论文会降权。" if ui_language(config) == "zh" else "Must read + Less like this is unusual; this paper stays prioritized but similar papers are downranked.",
        "warnNotRelevantMore": "不相关 + 以后多推荐类似不常见；不相关会归档这篇论文。" if ui_language(config) == "zh" else "Not relevant + More like this is unusual; not-relevant archives this paper.",
        "warnBackgroundMore": "背景阅读 + 以后多推荐类似不常见；背景阅读通常会清除排序信号。" if ui_language(config) == "zh" else "Background only + More like this is unusual; background-only usually clears ranking signals.",
        "warnArchivePriority": "归档决定和阅读优先级冲突；归档会优先生效。" if ui_language(config) == "zh" else "Archive decision conflicts with a reading priority; Archive wins for ranking.",
    }
    return "\n".join(
        [
            "<!doctype html>",
            f'<html lang="{"zh-CN" if ui_language(config) == "zh" else "en"}">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{html.escape(ui_text(config, 'workspace'))}</title>",
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
            .math-inline {
              font-family: ui-serif, Georgia, "Times New Roman", serif;
              white-space: nowrap;
            }
            .math-inline sup,
            .math-inline sub {
              line-height: 0;
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
            .report-field,
            .metadata-field {
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
            .action-chip.selected-report,
            .action-chip.selected-metadata {
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
            f"<h1>{html.escape(ui_text(config, 'paper_workspace'))}</h1>" if focused_paper is not None else f"<h1>{html.escape(ui_text(config, 'workspace'))}</h1>",
            f'<div class="meta">{html.escape(ui_text(config, "profile"))}: {html.escape(str(config.profile_path))}</div>',
            f'<div class="meta">{html.escape(ui_text(config, "papers"))}: {html.escape(str(config.papers_json))}</div>',
            f'<div class="meta">{html.escape(ui_text(config, "kb"))}: {html.escape(str(config.kb_dir))}</div>',
            local_nav_links(config),
            '<div class="run-stats">' + "".join(f'<span class="run-stat">{html.escape(item)}</span>' for item in stat_items) + "</div>",
            '<div class="toolbar">',
            f'<input id="search" type="search" placeholder="{html.escape(ui_text(config, "search_placeholder"), quote=True)}">',
            f'<select id="tier"><option value="">{html.escape(ui_text(config, "all_tiers"))}</option><option value="Must read">{html.escape(ui_text(config, "must_read"))}</option><option value="Skim">{html.escape(ui_text(config, "skim"))}</option><option value="Archive">{html.escape(ui_text(config, "archive"))}</option></select>',
            f'<select id="status"><option value="">{html.escape(ui_text(config, "all_statuses"))}</option><option value="unread">{html.escape(status_display(config, "unread"))}</option><option value="reading">{html.escape(status_display(config, "reading"))}</option><option value="read">{html.escape(status_display(config, "read"))}</option><option value="must-cite">{html.escape(status_display(config, "must-cite"))}</option><option value="method-reference">{html.escape(status_display(config, "method-reference"))}</option><option value="background-only">{html.escape(status_display(config, "background-only"))}</option><option value="not-relevant">{html.escape(status_display(config, "not-relevant"))}</option></select>',
            "</div>",
            '<form class="ask-form" method="post" action="/ask">',
            f'<input type="hidden" name="view" value="{html.escape(view, quote=True)}">',
            f'<input type="hidden" name="paper_id" value="{html.escape(str(getattr(focused_paper, "id", "")), quote=True)}">'
            if focused_paper is not None
            else "",
            f'<input name="question" type="search" placeholder="{html.escape(ui_text(config, "ask_paper_placeholder"), quote=True)}">'
            if focused_paper is not None
            else f'<input name="question" type="search" placeholder="{html.escape(ui_text(config, "ask_library_placeholder"), quote=True)}">',
            f"<button>{html.escape(ui_text(config, 'ask_paper'))}</button>" if focused_paper is not None else f"<button>{html.escape(ui_text(config, 'ask_library'))}</button>",
            "</form>",
            f'<div class="message">{message_html}</div>'
            if message_html
            else f'<div class="message">{html.escape(message)}</div>' if message else "",
            f'<div class="message limit-notice">{limit_notice_html}</div>' if limit_notice_html else "",
            overview,
            "</header>",
            "<main>",
            f'<form class="batch-feedback-form" method="post" action="/feedback-batch">',
            f'<input type="hidden" name="view" value="{html.escape(view, quote=True)}">',
            batch_save_bar("top", config),
            content,
            batch_save_bar("bottom", config),
            "</form>",
            "</main>",
            "<script>",
            f"const UI = {json.dumps(js_labels, ensure_ascii=False)};",
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
                warnings.push(UI.warnInterestedLess);
              }
              if (decision === 'archive' && more) {
                warnings.push(UI.warnArchiveMore);
              }
              if (priority === 'archive' && more) {
                warnings.push(UI.warnPriorityArchiveMore);
              }
              if (priority === 'must_read' && less) {
                warnings.push(UI.warnMustLess);
              }
              if (reading === 'not-relevant' && more) {
                warnings.push(UI.warnNotRelevantMore);
              }
              if (reading === 'background-only' && more) {
                warnings.push(UI.warnBackgroundMore);
              }
              if (decision === 'archive' && (priority === 'must_read' || priority === 'skim')) {
                warnings.push(UI.warnArchivePriority);
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
              const metadata = card.querySelector('.metadata-action');
              const selects = card.querySelectorAll('.review-select');
              const checks = card.querySelectorAll('.review-checkbox input');
              if (report && report.value) return true;
              if (metadata && metadata.value) return true;
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
              const text = changed.size === 0 ? UI.noPending : `${changed.size} ${changed.size === 1 ? UI.pendingSingular : UI.pendingPlural}`;
              document.querySelectorAll('.pending-count').forEach(el => { el.textContent = text; });
            }
            if (batchForm) {
              batchForm.addEventListener('click', event => {
                const rawTarget = event.target;
                const target = rawTarget && rawTarget.closest ? rawTarget : rawTarget?.parentElement;
                const button = target?.closest('.action-chip[data-set-report]');
                if (!button || !batchForm.contains(button)) return;
                const card = button.closest('.paper');
                if (!card) return;
                const actionInput = card.querySelector('.report-action');
                if (!actionInput) return;
                actionInput.value = button.dataset.setReport || '';
                card.querySelectorAll('.action-chip[data-set-report]').forEach(item => item.classList.remove('selected-report'));
                if (actionInput.value) button.classList.add('selected-report');
                markCardDirty(card);
                updatePendingCount();
                return;
              });
              batchForm.addEventListener('click', event => {
                const rawTarget = event.target;
                const target = rawTarget && rawTarget.closest ? rawTarget : rawTarget?.parentElement;
                const button = target?.closest('.action-chip[data-set-metadata]');
                if (!button || !batchForm.contains(button)) return;
                const card = button.closest('.paper');
                if (!card) return;
                const actionInput = card.querySelector('.metadata-action');
                if (!actionInput) return;
                actionInput.value = button.dataset.setMetadata || '';
                card.querySelectorAll('.action-chip[data-set-metadata]').forEach(item => item.classList.remove('selected-metadata'));
                if (actionInput.value) button.classList.add('selected-metadata');
                markCardDirty(card);
                updatePendingCount();
              });
              batchForm.addEventListener('change', event => {
                const target = event.target;
                if (!target || !target.closest) return;
                const card = target.closest('.paper');
                if (!card) return;
                if (target.matches('.review-checkbox input')) {
                  if (target.checked && target.closest('.signal-more')) {
                    card.querySelectorAll('.signal-less input, .signal-clear input').forEach(item => { item.checked = false; });
                  } else if (target.checked && target.closest('.signal-less')) {
                    card.querySelectorAll('.signal-more input, .signal-clear input').forEach(item => { item.checked = false; });
                  } else if (target.checked && target.closest('.signal-clear')) {
                    card.querySelectorAll('.signal-more input, .signal-less input').forEach(item => { item.checked = false; });
                  }
                  markCardDirty(card);
                  updatePendingCount();
                } else if (target.matches('.review-select')) {
                  markCardDirty(card);
                  updatePendingCount();
                }
              });
              batchForm.addEventListener('input', event => {
                const target = event.target;
                if (!target || !target.matches) return;
                if (!target.matches('.paper-note')) return;
                markCardDirty(target.closest('.paper'));
                updatePendingCount();
              });
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
                  alert(UI.nothingToSave);
                  return;
                }
                const warnings = refreshAllCombinationWarnings();
                if (warnings.length) {
                  const uniqueWarnings = [...new Set(warnings)].slice(0, 5).join('\\n');
                  if (!confirm(`${UI.unusualIntro}\n\n${uniqueWarnings}\n\n${UI.saveAnyway}`)) {
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

        def enrich_selected_metadata(self, paper: Any) -> tuple[bool, bool, dict[str, int]]:
            from . import enrich as enrich_module

            record = core.asdict(paper)
            before = dict(getattr(paper, "metadata", {}) or {})
            updated, counts = enrich_module.enrich_record(
                record,
                {"openalex", "crossref"},
                email=None,
                user_agent="scholar-alert-reader/0.2 review-workspace",
                timeout=6,
            )
            metadata = updated.get("metadata") if isinstance(updated.get("metadata"), dict) else {}
            if metadata != before:
                paper.metadata = metadata
            has_abstract = False
            for provider in ["openalex", "crossref"]:
                item = metadata.get(provider)
                if isinstance(item, dict) and str(item.get("abstract", "") or "").strip():
                    has_abstract = True
                    break
            return metadata != before, has_abstract, counts

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
            update_feedback_note(record, localized_system_note(config, state.get("note")), user_note, note_mode)
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
                generated_note = localized_system_note(config, str(report_state.get("note") or "").strip() or None)

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
                generated_note = generated_note or localized_system_note(config, "Marked as background only from Review Workspace.")
            elif reading_status == "not-relevant":
                mark = "archive"
                less_like_this = True
                generated_note = generated_note or localized_system_note(config, "Marked as not relevant from Review Workspace.")

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
            if parsed.path not in {"/", "/feedback-batch"}:
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
                        message=(f"单篇工作区：{paper_id}" if ui_language(config) == "zh" else f"Focused workspace for {paper_id}"),
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
            papers, limit_notice = limit_workspace_papers(papers, view, workspace_limit_from_query(query), config)
            body = render_page(
                papers,
                config,
                feedback=feedback,
                all_papers=all_papers,
                view=view,
                limit_notice_html=limit_notice,
            ).encode("utf-8")
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
                limit_notice = ""
                if not selected:
                    papers, limit_notice = limit_workspace_papers(papers, view, DEFAULT_WORKSPACE_CARD_LIMIT, config)
                answer_link = f'<a href="/answer?name={quote(output.name, safe="")}">{html.escape(output.name)}</a>'
                if ui_language(config) == "zh":
                    ask_message = (
                        f"已回答论文 {html.escape(paper_id)} 的问题：{html.escape(question)}；答案：{answer_link}"
                        if paper_id
                        else f"已回答文献库问题：{html.escape(question)}；答案：{answer_link}"
                    )
                else:
                    ask_message = (
                        f"Answered paper question for {html.escape(paper_id)}: {html.escape(question)}; answer: {answer_link}"
                        if paper_id
                        else f"Answered library question: {html.escape(question)}; answer: {answer_link}"
                    )
                body = render_page(
                    papers,
                    config,
                    feedback=feedback,
                    message_html=ask_message,
                    focused_paper=selected[0] if selected else None,
                    all_papers=selected or all_papers,
                    view="focused" if selected else view,
                    limit_notice_html=limit_notice,
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
                metadata_requests: list[Any] = []
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
                    metadata_action = (form.get(f"metadata_action__{paper_id}") or [""])[0].strip()
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
                    if metadata_action == "abstract":
                        metadata_requests.append(paper)
                metadata_checked = 0
                metadata_updated = 0
                metadata_abstracts = 0
                metadata_errors: list[str] = []
                for paper in metadata_requests:
                    metadata_checked += 1
                    try:
                        updated, has_abstract, _counts = self.enrich_selected_metadata(paper)
                    except Exception as exc:  # pragma: no cover - defensive UI boundary for network/API surprises.
                        metadata_errors.append(f"{paper.id}: {exc}")
                        continue
                    if updated:
                        metadata_updated += 1
                    if has_abstract:
                        metadata_abstracts += 1
                if metadata_updated:
                    core.save_json(config.papers_json, [core.asdict(paper) for paper in all_papers])
                    core.merge_record_metadata_into_library(config.kb_dir, [core.asdict(paper) for paper in metadata_requests], profile)

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
                    message = (
                        f"已保存 {len(changed)} 项选中修改。"
                        if ui_language(config) == "zh"
                        else f"Saved {len(changed)} selected change{'s' if len(changed) != 1 else ''}."
                    )
                else:
                    refreshed = {}
                    review_artifacts = []
                    message = (
                        "已保存元数据请求。"
                        if metadata_checked and ui_language(config) == "zh"
                        else "Saved metadata request."
                        if metadata_checked
                        else "没有选中操作或笔记需要保存。"
                        if ui_language(config) == "zh"
                        else "No selected actions or notes to save."
                    )
                if metadata_checked:
                    if ui_language(config) == "zh":
                        message += f"；公开元数据检查：{metadata_checked}，更新：{metadata_updated}，可用摘要：{metadata_abstracts}"
                    else:
                        message += (
                            f"; public metadata checked: {metadata_checked}, updated: {metadata_updated}, "
                            f"abstracts available: {metadata_abstracts}"
                        )
                if metadata_errors:
                    message += f"；元数据查询错误：{len(metadata_errors)}" if ui_language(config) == "zh" else f"; metadata lookup errors: {len(metadata_errors)}"
                if refreshed.get("reading_plan_html"):
                    message += f"；阅读计划：{refreshed['reading_plan_html']}" if ui_language(config) == "zh" else f"; reading plan: {refreshed['reading_plan_html']}"
                if refreshed.get("dashboard_html"):
                    message += f"；Dashboard：{refreshed['dashboard_html']}" if ui_language(config) == "zh" else f"; dashboard: {refreshed['dashboard_html']}"
                if combination_warnings:
                    message += f"；不常见反馈组合：{len(combination_warnings)}" if ui_language(config) == "zh" else f"; unusual combinations noted: {len(combination_warnings)}"
                for paper_id, label, artifact in review_artifacts:
                    message += f"；{paper_id} {label}: {artifact}" if ui_language(config) == "zh" else f"; {paper_id} {label}: {artifact}"
                all_papers = core.load_papers_json(config.papers_json)
                papers = filter_papers_for_view(all_papers, view, feedback)
                papers, limit_notice = limit_workspace_papers(papers, view, DEFAULT_WORKSPACE_CARD_LIMIT, config)
                featured_papers = [*changed, *metadata_requests]
                for paper in featured_papers:
                    if not any(getattr(item, "id", "") == getattr(paper, "id", "") for item in papers):
                        papers = [paper] + papers
                body = render_page(
                    papers,
                    config,
                    message,
                    feedback=feedback,
                    all_papers=all_papers,
                    view=view,
                    limit_notice_html=limit_notice,
                ).encode("utf-8")
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
                update_feedback_note(record, localized_system_note(config, note), user_note, note_mode)
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
            papers, limit_notice = limit_workspace_papers(papers, view, DEFAULT_WORKSPACE_CARD_LIMIT, config)
            if selected and not any(getattr(paper, "id", "") == paper_id for paper in papers):
                papers = selected + papers
            message = f"已保存 {paper_id} 的反馈：{action}" if ui_language(config) == "zh" else f"Saved feedback for {paper_id}: {action}"
            if refreshed.get("reading_plan_html"):
                message += f"；阅读计划：{refreshed['reading_plan_html']}" if ui_language(config) == "zh" else f"; reading plan: {refreshed['reading_plan_html']}"
            if refreshed.get("dashboard_html"):
                message += f"；Dashboard：{refreshed['dashboard_html']}" if ui_language(config) == "zh" else f"; dashboard: {refreshed['dashboard_html']}"
            if deep_report:
                message += f"; deep-read report: {deep_report}"
            if workflow_report:
                message += f"; review workflow: {workflow_report}"
            if workup_report:
                message += f"; workup report: {workup_report}"
            if review_pack_report:
                message += f"; review pack: {review_pack_report}"
            body = render_page(
                papers,
                config,
                message,
                feedback=feedback,
                all_papers=all_papers,
                view=view,
                limit_notice_html=limit_notice,
            ).encode("utf-8")
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
