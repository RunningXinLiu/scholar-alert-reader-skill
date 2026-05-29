"""Scholar Alert mail parsing adapters."""

from __future__ import annotations

import mailbox
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from email import message_from_binary_file
from email.utils import parsedate_to_datetime
from email.header import decode_header, make_header
from email.message import Message
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse
import html
from . import base

SCHOLAR_SENDER = "scholaralerts-noreply@google.com"

ENTRY_RE = re.compile(
    r'<h3\b[^>]*>\s*(?:<span\b.*?</span>\s*)?'
    r'<a\s+href="(?P<href>[^"]+)"[^>]*class="gse_alrt_title"[^>]*>'
    r'(?P<title>.*?)</a>\s*</h3>\s*'
    r'<div\b[^>]*color:#006621[^>]*>(?P<meta>.*?)</div>\s*'
    r'<div\b[^>]*class="gse_alrt_sni"[^>]*>(?P<snippet>.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)


def clean_html(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>", " ", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    fragment = html.unescape(fragment)
    fragment = fragment.replace("\xa0", " ")
    return " ".join(fragment.split())


def decode_mime_header(value: str | None) -> str:
    if not value:
        return ""
    return str(make_header(decode_header(value)))


def parse_message_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def get_part_text(part: Any) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def get_html_body(message: Message) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/html":
                return get_part_text(part)
        return ""
    if message.get_content_type() == "text/html":
        return get_part_text(message)
    return ""


def resolve_scholar_url(href: str) -> tuple[str, str]:
    scholar_url = html.unescape(href)
    parsed = urlparse(scholar_url)
    query = parse_qs(parsed.query)
    target = query.get("url", [""])[0]
    return unquote(target) if target else scholar_url, scholar_url


def parse_alert_name(subject: str) -> str:
    alert = re.sub(r"\s+-\s+(new related research|new articles|新的相关研究工作)\s*$", "", subject).strip()
    alert = re.sub(r"^Google Scholar Alert:\s*", "", alert, flags=re.I)
    return alert or subject


def _new_paper(
    *,
    title: str,
    authors_source: str,
    snippet: str,
    url: str,
    scholar_url: str,
    date: str,
    alert: str,
    paper_factory: Callable[..., Any] | None = None,
) -> Any:
    if paper_factory is None:
        from ..core import Paper  # Lazy import to avoid cycle when module is imported by core.

        paper_factory = Paper

    return paper_factory(
        id=base.stable_id(title),
        title=title,
        authors_source=authors_source,
        snippet=snippet,
        url=url,
        scholar_url=scholar_url,
        first_seen=date,
        last_seen=date,
        alerts=[alert],
        occurrences=1,
    )


def _normalize_title(title: str) -> str:
    return base.normalize_title(title)


def collect_papers_from_message(
    message: Message,
    papers_by_key: dict[str, Any],
    counts: Counter,
    cutoff: datetime | None,
    paper_factory: Callable[..., Any] | None = None,
) -> None:
    counts["messages"] += 1
    sender = decode_mime_header(message.get("from"))
    if SCHOLAR_SENDER not in sender:
        return
    counts["scholar_messages"] += 1

    message_dt = parse_message_date(message.get("date"))
    if cutoff and message_dt and message_dt < cutoff:
        counts["skipped_by_date"] += 1
        return

    date = message_dt.date().isoformat() if message_dt else ""
    subject = decode_mime_header(message.get("subject"))
    alert = parse_alert_name(subject)
    html_body = get_html_body(message)
    if not html_body:
        counts["empty_html"] += 1
        return

    entry_count = 0
    for match in ENTRY_RE.finditer(html_body):
        title = clean_html(match.group("title"))
        if not title:
            continue
        key = _normalize_title(title)
        authors_source = clean_html(match.group("meta"))
        snippet = clean_html(match.group("snippet"))
        url, scholar_url = resolve_scholar_url(match.group("href"))
        existing = papers_by_key.get(key)

        if existing is None:
            papers_by_key[key] = _new_paper(
                title=title,
                authors_source=authors_source,
                snippet=snippet,
                url=url,
                scholar_url=scholar_url,
                date=date,
                alert=alert,
                paper_factory=paper_factory,
            )
        else:
            existing.occurrences += 1
            if alert not in existing.alerts:
                existing.alerts.append(alert)
            dates = [d for d in [existing.first_seen, existing.last_seen, date] if d]
            if dates:
                existing.first_seen = min(dates)
                existing.last_seen = max(dates)
            if len(snippet) > len(existing.snippet):
                existing.snippet = snippet
            if not existing.url and url:
                existing.url = url
                existing.scholar_url = scholar_url
        entry_count += 1

    counts["entries"] += entry_count


def parse_mbox(
    mbox_path: Path,
    since_days: int | None = None,
    paper_factory: Callable[..., Any] | None = None,
) -> tuple[list[Any], dict[str, int]]:
    mbox_path = mbox_path.expanduser()
    if mbox_path.is_dir():
        mbox_path = mbox_path / "mbox"
    if not mbox_path.exists():
        raise SystemExit(f"Cannot find mbox file: {mbox_path}")

    cutoff = None
    if since_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)

    messages = mailbox.mbox(mbox_path)
    papers_by_key: dict[str, Any] = {}
    counts = Counter()

    try:
        for message in messages:
            collect_papers_from_message(message, papers_by_key, counts, cutoff, paper_factory=paper_factory)
    finally:
        messages.close()

    return list(papers_by_key.values()), dict(counts)


def parse_eml_dir(
    eml_dir: Path,
    since_days: int | None = None,
    paper_factory: Callable[..., Any] | None = None,
) -> tuple[list[Any], dict[str, int]]:
    eml_dir = eml_dir.expanduser()
    cutoff = None
    if since_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)

    papers_by_key: dict[str, Any] = {}
    counts = Counter()
    for eml_path in sorted(eml_dir.glob("*.eml")):
        with eml_path.open("rb") as f:
            message = message_from_binary_file(f)
        collect_papers_from_message(message, papers_by_key, counts, cutoff, paper_factory=paper_factory)
    counts["eml_files"] = len(list(eml_dir.glob("*.eml")))
    return list(papers_by_key.values()), dict(counts)
