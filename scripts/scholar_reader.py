#!/usr/bin/env python3
"""Google Scholar Alert triage for local literature monitoring.

The script is intentionally dependency-free so it works with the system Python
on macOS. It reads exported .mbox files, ranks papers against a JSON research
profile, and writes a compact digest plus structured outputs.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import html
import json
import mailbox
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from email import message_from_binary_file, message_from_bytes
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, unquote, urlparse


SCHOLAR_SENDER = "scholaralerts-noreply@google.com"
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROFILE = SCRIPT_DIR.parent / "assets" / "default_profile.json"
DEFAULT_PRIVATE_DIR = Path.home() / ".codex" / "scholar-alert-reader"
DEFAULT_GMAIL_CREDENTIALS = DEFAULT_PRIVATE_DIR / "gmail_credentials.json"
DEFAULT_GMAIL_TOKEN = DEFAULT_PRIVATE_DIR / "gmail_token.json"
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
FEEDBACK_VERSION = 1

TITLE_STOPWORDS = {
    "about",
    "after",
    "analysis",
    "based",
    "between",
    "case",
    "data",
    "during",
    "earth",
    "effects",
    "evidence",
    "from",
    "global",
    "high",
    "implications",
    "into",
    "large",
    "model",
    "models",
    "new",
    "paper",
    "regional",
    "results",
    "study",
    "system",
    "through",
    "toward",
    "using",
    "with",
}

ENTRY_RE = re.compile(
    r'<h3\b[^>]*>\s*(?:<span\b.*?</span>\s*)?'
    r'<a\s+href="(?P<href>[^"]+)"[^>]*class="gse_alrt_title"[^>]*>'
    r"(?P<title>.*?)</a>\s*</h3>\s*"
    r'<div\b[^>]*color:#006621[^>]*>(?P<meta>.*?)</div>\s*'
    r'<div\b[^>]*class="gse_alrt_sni"[^>]*>(?P<snippet>.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class TermHit:
    term: str
    weight: int
    section: str
    field: str
    tags: list[str] = field(default_factory=list)


@dataclass
class Paper:
    id: str
    title: str
    authors_source: str
    snippet: str
    url: str
    scholar_url: str
    first_seen: str
    last_seen: str
    alerts: list[str]
    occurrences: int
    score: int = 0
    tier: str = "Archive"
    matched_terms: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    is_new: bool = True


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


def get_html_body(message: Any) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/html":
                return get_part_text(part)
        return ""
    if message.get_content_type() == "text/html":
        return get_part_text(message)
    return ""


def clean_html(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>", " ", fragment, flags=re.IGNORECASE)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    fragment = html.unescape(fragment)
    fragment = fragment.replace("\xa0", " ")
    return " ".join(fragment.split())


def resolve_scholar_url(href: str) -> tuple[str, str]:
    scholar_url = html.unescape(href)
    parsed = urlparse(scholar_url)
    query = parse_qs(parsed.query)
    target = query.get("url", [""])[0]
    return unquote(target) if target else scholar_url, scholar_url


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def stable_id(title: str) -> str:
    return hashlib.sha1(normalize_title(title).encode("utf-8")).hexdigest()[:12]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_profile(profile_path: Path | None) -> dict[str, Any]:
    path = profile_path or DEFAULT_PROFILE
    if not path.exists():
        raise SystemExit(f"Profile not found: {path}")
    return load_json(path)


def coerce_terms(items: Iterable[Any], section: str, default_weight: int = 1) -> list[dict[str, Any]]:
    terms: list[dict[str, Any]] = []
    fallback_tags = {
        "focus_terms": ["focus"],
        "regions": ["region"],
        "methods": ["method"],
        "watch_authors": ["watchlist"],
        "runtime_boost": ["boost"],
    }
    for item in items or []:
        if isinstance(item, str):
            term = item.strip()
            if term:
                terms.append({"term": term, "weight": default_weight, "section": section, "tags": fallback_tags.get(section, [])})
        elif isinstance(item, dict):
            term = str(item.get("term", "")).strip()
            if term:
                tags = [str(tag) for tag in item.get("tags", [])]
                if not tags:
                    tags = fallback_tags.get(section, [])
                terms.append(
                    {
                        "term": term,
                        "weight": int(item.get("weight", default_weight)),
                        "section": section,
                        "tags": tags,
                    }
                )
    return terms


def profile_terms(profile: dict[str, Any], boost: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    positive: list[dict[str, Any]] = []
    negative: list[dict[str, Any]] = []
    for section, default_weight in [
        ("focus_terms", 2),
        ("regions", 2),
        ("methods", 2),
        ("watch_authors", 2),
    ]:
        positive.extend(coerce_terms(profile.get(section, []), section, default_weight))
    negative.extend(coerce_terms(profile.get("exclude_terms", []), "exclude_terms", 3))

    for term in split_csv(boost):
        positive.append({"term": term, "weight": 6, "section": "runtime_boost", "tags": ["boost"]})
    return positive, negative


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def text_fields(paper: Paper) -> dict[str, str]:
    return {
        "title": paper.title.lower(),
        "authors_source": paper.authors_source.lower(),
        "snippet": paper.snippet.lower(),
        "alerts": " ".join(paper.alerts).lower(),
    }


def empty_feedback() -> dict[str, Any]:
    return {
        "version": FEEDBACK_VERSION,
        "updated_at": "",
        "papers": {},
        "terms": [],
    }


def load_feedback(feedback_file: Path | None) -> dict[str, Any]:
    if not feedback_file or not feedback_file.exists():
        return empty_feedback()
    try:
        data = load_json(feedback_file)
    except Exception:
        return empty_feedback()
    if not isinstance(data, dict):
        return empty_feedback()
    data.setdefault("version", FEEDBACK_VERSION)
    data.setdefault("updated_at", "")
    data.setdefault("papers", {})
    data.setdefault("terms", [])
    return data


def save_feedback(feedback_file: Path, feedback: dict[str, Any]) -> None:
    feedback["version"] = FEEDBACK_VERSION
    feedback["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save_json(feedback_file, feedback)


def feedback_adjustment(
    paper: Paper,
    feedback: dict[str, Any] | None,
) -> tuple[int, list[str], set[str], list[str], str | None]:
    if not feedback:
        return 0, [], set(), [], None

    delta = 0
    matched_terms: list[str] = []
    tags: set[str] = set()
    reasons: list[str] = []
    forced_tier: str | None = None
    fields = text_fields(paper)
    haystack = "\n".join(fields.values())

    paper_feedback = feedback.get("papers", {}).get(paper.id)
    if isinstance(paper_feedback, dict):
        status = paper_feedback.get("status")
        if status == "interested":
            delta += 12
            forced_tier = "Must read"
            tags.add("feedback")
            reasons.append("用户反馈：这篇已标为 interested，强制进入重点阅读。")
        elif status == "archive":
            delta -= 100
            forced_tier = "Archive"
            tags.add("feedback")
            reasons.append("用户反馈：这篇已标为 archive，强制归档。")

        signals = paper_feedback.get("signals", {})
        if isinstance(signals, dict) and signals.get("more_like_this"):
            delta += 4
            tags.add("feedback")
            reasons.append("用户反馈：这篇曾被标记为 more-like-this。")
        if isinstance(signals, dict) and signals.get("less_like_this"):
            delta -= 8
            tags.add("feedback")
            reasons.append("用户反馈：这篇曾被标记为 less-like-this。")

    for item in feedback.get("terms", []):
        if not isinstance(item, dict):
            continue
        term = str(item.get("term", "")).strip()
        if not term:
            continue
        if term.lower() not in haystack:
            continue
        weight = int(item.get("weight", 3))
        direction = str(item.get("direction", "positive"))
        tags.add("feedback")
        if direction == "negative":
            delta -= weight
            matched_terms.append(f"user:-{term}")
            reasons.append(f"用户反馈降权：命中 `{term}`。")
        else:
            delta += weight
            matched_terms.append(f"user:{term}")
            reasons.append(f"用户反馈加权：命中 `{term}`。")

    return delta, sorted(set(matched_terms), key=lambda t: t.lower()), tags, reasons[:5], forced_tier


def score_paper(
    paper: Paper,
    profile: dict[str, Any],
    boost: str | None,
    feedback: dict[str, Any] | None = None,
) -> None:
    positive, negative = profile_terms(profile, boost)
    fields = text_fields(paper)
    score = 0
    hits: list[TermHit] = []

    for item in positive:
        if item["section"] == "watch_authors":
            continue
        term = item["term"]
        needle = term.lower()
        if not needle:
            continue
        for field_name, field_text in fields.items():
            if needle in field_text:
                weight = item["weight"]
                if field_name == "title":
                    weight *= 2
                elif field_name == "alerts" and item["section"] == "watch_authors":
                    weight *= 2
                score += weight
                hits.append(TermHit(term, weight, item["section"], field_name, item.get("tags", [])))
                break

    topical_score = score
    for item in positive:
        if item["section"] != "watch_authors":
            continue
        term = item["term"]
        needle = term.lower()
        if not needle:
            continue
        for field_name, field_text in fields.items():
            if needle not in field_text:
                continue
            weight = item["weight"]
            if field_name == "authors_source":
                weight *= 2
            elif field_name == "alerts":
                if topical_score < 4:
                    weight = 0
                else:
                    weight = min(weight, 2)
            elif field_name != "title":
                weight = min(weight, 1)
            if weight == 0:
                break
            score += weight
            hits.append(TermHit(term, weight, item["section"], field_name, item.get("tags", [])))
            break

    for item in negative:
        term = item["term"]
        needle = term.lower()
        if not needle:
            continue
        for field_name, field_text in fields.items():
            if needle in field_text:
                weight = item["weight"]
                score -= weight
                hits.append(TermHit(f"-{term}", -weight, "exclude_terms", field_name, []))
                break

    if paper.occurrences > 1:
        score += min(3, paper.occurrences - 1)

    current_year = datetime.now().year
    if str(current_year) in paper.authors_source or str(current_year - 1) in paper.authors_source:
        score += 1

    if re.search(r"\b(review|survey|perspective|benchmark|dataset)\b", paper.title, re.I):
        score += 1

    feedback_delta, feedback_terms, feedback_tags, feedback_reasons, forced_tier = feedback_adjustment(paper, feedback)
    score += feedback_delta

    thresholds = profile.get("tier_thresholds", {})
    must = int(thresholds.get("must_read", 8))
    skim = int(thresholds.get("skim", 3))

    paper.score = score
    paper.tier = "Must read" if score >= must else "Skim" if score >= skim else "Archive"
    if forced_tier == "Must read":
        paper.score = max(paper.score, must)
        paper.tier = "Must read"
    elif forced_tier == "Archive":
        paper.score = min(paper.score, -20)
        paper.tier = "Archive"
    paper.matched_terms = sorted({hit.term for hit in hits} | set(feedback_terms), key=lambda t: t.lower())
    paper.tags = sorted({tag for hit in hits for tag in hit.tags} | set(feedback_tags))
    paper.reasons = feedback_reasons + build_reasons(hits, paper)


def build_reasons(hits: list[TermHit], paper: Paper) -> list[str]:
    if not hits:
        return ["没有命中当前 profile 的重点词，默认归档或低优先级。"]
    top_hits = sorted(hits, key=lambda h: abs(h.weight), reverse=True)[:4]
    reasons = []
    for hit in top_hits:
        if hit.weight < 0:
            reasons.append(f"降权：命中排除词 `{hit.term[1:]}`。")
        elif hit.field == "title":
            reasons.append(f"标题命中 `{hit.term}`，与 `{hit.section}` 相关。")
        elif hit.field == "alerts":
            reasons.append(f"来自/关联重点 alert `{hit.term}`。")
        else:
            reasons.append(f"摘要或来源命中 `{hit.term}`。")
    if paper.occurrences > 1:
        reasons.append(f"同一论文在 {paper.occurrences} 个 alert 记录中出现。")
    return reasons


def parse_alert_name(subject: str) -> str:
    alert = re.sub(r"\s+-\s+(new related research|new articles|新的相关研究工作)\s*$", "", subject).strip()
    alert = re.sub(r"^Google Scholar Alert:\s*", "", alert, flags=re.I)
    return alert or subject


def collect_papers_from_message(
    message: Message,
    papers_by_key: dict[str, Paper],
    counts: Counter,
    cutoff: datetime | None,
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
        key = normalize_title(title)
        authors_source = clean_html(match.group("meta"))
        snippet = clean_html(match.group("snippet"))
        url, scholar_url = resolve_scholar_url(match.group("href"))
        existing = papers_by_key.get(key)

        if existing is None:
            papers_by_key[key] = Paper(
                id=stable_id(title),
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
) -> tuple[list[Paper], dict[str, int]]:
    if mbox_path.is_dir():
        mbox_path = mbox_path / "mbox"
    if not mbox_path.exists():
        raise SystemExit(f"Cannot find mbox file: {mbox_path}")

    cutoff = None
    if since_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)

    messages = mailbox.mbox(mbox_path)
    papers_by_key: dict[str, Paper] = {}
    counts = Counter()

    for message in messages:
        collect_papers_from_message(message, papers_by_key, counts, cutoff)

    return list(papers_by_key.values()), dict(counts)


def parse_eml_dir(eml_dir: Path, since_days: int | None = None) -> tuple[list[Paper], dict[str, int]]:
    cutoff = None
    if since_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)

    papers_by_key: dict[str, Paper] = {}
    counts = Counter()
    for eml_path in sorted(eml_dir.glob("*.eml")):
        with eml_path.open("rb") as f:
            message = message_from_binary_file(f)
        collect_papers_from_message(message, papers_by_key, counts, cutoff)
    counts["eml_files"] = len(list(eml_dir.glob("*.eml")))
    return list(papers_by_key.values()), dict(counts)


def apple_script_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def fetch_mail_app_scholar_alerts(out_dir: Path, since_days: int | None, limit: int) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    since_value = int(since_days or 0)
    limit_value = int(limit or 0)
    script = f"""
on writeTextToFile(theText, thePath)
  set f to open for access POSIX file thePath with write permission
  set eof of f to 0
  write theText to f as «class utf8»
  close access f
end writeTextToFile

set outDir to {apple_script_string(str(out_dir))}
set sinceDays to {since_value}
set maxCount to {limit_value}
set writtenCount to 0
if sinceDays > 0 then
  set cutoffDate to (current date) - (sinceDays * days)
end if

with timeout of 600 seconds
  tell application "Mail"
    set scholarMessages to messages of inbox whose sender contains "{SCHOLAR_SENDER}"
    repeat with m in scholarMessages
      if sinceDays is 0 or (date received of m) is greater than cutoffDate then
        set writtenCount to writtenCount + 1
        set filePath to outDir & "/" & (writtenCount as text) & ".eml"
        my writeTextToFile(source of m, filePath)
        if maxCount > 0 and writtenCount >= maxCount then exit repeat
      end if
    end repeat
  end tell
end timeout

return writtenCount
"""
    result = subprocess.run(
        ["osascript"],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            "Mail.app export failed. Check macOS Automation permission for Codex/Terminal to control Mail.\n"
            + result.stderr.strip()
        )
    output = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "0"
    try:
        return int(output)
    except ValueError:
        return 0


def parse_mail_app_source(
    since_days: int | None,
    mail_limit: int,
) -> tuple[list[Paper], dict[str, int]]:
    with tempfile.TemporaryDirectory(prefix="scholar-mail-app-") as tmp:
        eml_dir = Path(tmp)
        exported = fetch_mail_app_scholar_alerts(eml_dir, since_days, mail_limit)
        papers, counts = parse_eml_dir(eml_dir, since_days=None)
    counts["mail_app_exported"] = exported
    return papers, counts


def import_gmail_dependencies():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except Exception as exc:
        raise SystemExit(
            "Gmail API dependencies are not installed for this Python. "
            "Install: google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        ) from exc
    return Request, Credentials, InstalledAppFlow, build


def gmail_service(credentials_file: Path, token_file: Path, allow_auth: bool):
    Request, Credentials, InstalledAppFlow, build = import_gmail_dependencies()
    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), GMAIL_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not allow_auth:
                raise SystemExit(
                    f"Gmail token is missing or invalid: {token_file}\n"
                    "Run the auth command once before using Gmail source in automation."
                )
            if not credentials_file.exists():
                raise SystemExit(
                    f"Gmail OAuth credentials not found: {credentials_file}\n"
                    "Download a Desktop OAuth client JSON from Google Cloud and save it there."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json(), encoding="utf-8")
        try:
            os.chmod(token_file, 0o600)
        except OSError:
            pass
    return build("gmail", "v1", credentials=creds)


def gmail_query(since_days: int | None, query: str | None) -> str:
    parts = [f"from:{SCHOLAR_SENDER}"]
    if since_days is not None:
        parts.append(f"newer_than:{max(1, int(since_days))}d")
    if query:
        parts.append(f"({query})")
    return " ".join(parts)


def fetch_gmail_messages(
    credentials_file: Path,
    token_file: Path,
    since_days: int | None,
    limit: int,
    query: str | None,
    allow_auth: bool,
) -> tuple[list[Message], dict[str, int]]:
    service = gmail_service(credentials_file, token_file, allow_auth)
    q = gmail_query(since_days, query)
    counts = Counter()
    messages: list[Message] = []
    page_token = None
    remaining = int(limit or 0)

    while True:
        max_results = 100 if remaining <= 0 else min(100, remaining)
        response = (
            service.users()
            .messages()
            .list(userId="me", q=q, maxResults=max_results, pageToken=page_token)
            .execute()
        )
        ids = response.get("messages", [])
        counts["gmail_message_ids"] += len(ids)
        for item in ids:
            raw_response = (
                service.users()
                .messages()
                .get(userId="me", id=item["id"], format="raw")
                .execute()
            )
            raw = raw_response.get("raw", "")
            if not raw:
                counts["gmail_empty_raw"] += 1
                continue
            data = base64.urlsafe_b64decode(raw.encode("ascii"))
            messages.append(message_from_bytes(data))
            counts["gmail_raw_messages"] += 1
            if remaining > 0:
                remaining -= 1
                if remaining <= 0:
                    page_token = None
                    break
        if remaining == 0 and limit:
            break
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    counts["gmail_query"] = q
    return messages, dict(counts)


def parse_gmail_source(
    credentials_file: Path,
    token_file: Path,
    since_days: int | None,
    limit: int,
    query: str | None,
    allow_auth: bool,
) -> tuple[list[Paper], dict[str, int]]:
    messages, gmail_counts = fetch_gmail_messages(
        credentials_file, token_file, since_days, limit, query, allow_auth
    )
    papers_by_key: dict[str, Paper] = {}
    counts = Counter(gmail_counts)
    for message in messages:
        collect_papers_from_message(message, papers_by_key, counts, cutoff=None)
    return list(papers_by_key.values()), dict(counts)


def load_seen(state_file: Path | None) -> set[str]:
    if not state_file or not state_file.exists():
        return set()
    try:
        data = load_json(state_file)
    except Exception:
        return set()
    return set(data.get("seen_ids", []))


def update_seen(state_file: Path, papers: list[Paper]) -> None:
    seen = load_seen(state_file)
    seen.update(p.id for p in papers)
    save_json(
        state_file,
        {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "seen_ids": sorted(seen),
        },
    )


def apply_state(papers: list[Paper], seen: set[str], only_new: bool) -> list[Paper]:
    for paper in papers:
        paper.is_new = paper.id not in seen
    if only_new:
        return [paper for paper in papers if paper.is_new]
    return papers


def rank_papers(
    papers: list[Paper],
    profile: dict[str, Any],
    boost: str | None,
    feedback: dict[str, Any] | None = None,
) -> list[Paper]:
    for paper in papers:
        score_paper(paper, profile, boost, feedback)
    tier_order = {"Must read": 0, "Skim": 1, "Archive": 2}
    return sorted(
        papers,
        key=lambda p: (tier_order.get(p.tier, 9), -p.score, p.last_seen, p.title.lower()),
    )


def paper_to_row(paper: Paper) -> dict[str, Any]:
    row = asdict(paper)
    row["alerts"] = "; ".join(paper.alerts)
    row["matched_terms"] = "; ".join(paper.matched_terms)
    row["tags"] = "; ".join(paper.tags)
    row["reasons"] = " | ".join(paper.reasons)
    return row


def write_csv(path: Path, papers: list[Paper]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(paper_to_row(papers[0]).keys()) if papers else [
        "id",
        "title",
        "authors_source",
        "snippet",
        "url",
        "scholar_url",
        "first_seen",
        "last_seen",
        "alerts",
        "occurrences",
        "score",
        "tier",
        "matched_terms",
        "tags",
        "reasons",
        "is_new",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for paper in papers:
            writer.writerow(paper_to_row(paper))


def counts_by_tier(papers: list[Paper]) -> Counter:
    return Counter(p.tier for p in papers)


def limits(profile: dict[str, Any]) -> dict[str, int]:
    configured = profile.get("limits", {})
    return {
        "must_read": int(configured.get("must_read", 8)),
        "skim": int(configured.get("skim", 15)),
        "deep_read": int(configured.get("deep_read", 5)),
    }


def papers_for_tier(papers: list[Paper], tier: str) -> list[Paper]:
    return [paper for paper in papers if paper.tier == tier]


def write_digest(path: Path, papers: list[Paper], profile: dict[str, Any], summary: dict[str, Any]) -> None:
    lim = limits(profile)
    tier_counts = counts_by_tier(papers)
    lines: list[str] = [
        "# Scholar Alert 文献分诊",
        "",
        f"- Profile: {profile.get('name', 'unnamed')}",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Papers in digest: {len(papers)}",
        f"- Must read: {tier_counts.get('Must read', 0)}; Skim: {tier_counts.get('Skim', 0)}; Archive: {tier_counts.get('Archive', 0)}",
        f"- Source Scholar messages: {summary.get('source_counts', {}).get('scholar_messages', 0)}",
        f"- Feedback file: {summary.get('feedback_file', '')}",
        "",
        "## 反馈入口",
        "",
        "Use the `ID` shown under each paper to tune future runs:",
        "",
        "```bash",
        f"python3 scripts/scholar_reader.py feedback --profile {shlex.quote(str(summary.get('profile', '<profile.json>')))} --papers-json {shlex.quote(str(path.parent / 'papers.json'))} --paper-id <ID> --mark interested --more-like-this",
        f"python3 scripts/scholar_reader.py feedback --profile {shlex.quote(str(summary.get('profile', '<profile.json>')))} --papers-json {shlex.quote(str(path.parent / 'papers.json'))} --paper-id <ID> --mark archive --less-like-this",
        "```",
        "",
    ]

    questions = profile.get("research_questions", [])
    if questions:
        lines.extend(["## 当前研究问题", ""])
        for question in questions:
            lines.append(f"- {question}")
        lines.append("")

    for tier_name, max_items in [
        ("Must read", lim["must_read"]),
        ("Skim", lim["skim"]),
    ]:
        items = papers_for_tier(papers, tier_name)
        lines.extend([f"## {tier_name} ({len(items)})", ""])
        if not items:
            lines.extend(["None.", ""])
            continue
        for index, paper in enumerate(items[:max_items], 1):
            lines.extend(render_paper(index, paper))

    archive_items = papers_for_tier(papers, "Archive")
    lines.extend(["## Archive quick view", ""])
    for paper in archive_items[:20]:
        new_mark = "NEW " if paper.is_new else ""
        lines.append(f"- {new_mark}{paper.score}: {paper.title}")
    if len(archive_items) > 20:
        lines.append(f"- ... {len(archive_items) - 20} more archived items in papers.csv/json")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


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


def write_html_digest(path: Path, papers: list[Paper], profile: dict[str, Any], summary: dict[str, Any]) -> None:
    lim = limits(profile)
    tier_counts = counts_by_tier(papers)
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = "Scholar Alert 文献分诊"
    questions = profile.get("research_questions", [])
    sections = [
        ("Must read", papers_for_tier(papers, "Must read"), lim["must_read"]),
        ("Skim", papers_for_tier(papers, "Skim"), lim["skim"]),
    ]

    parts = [
        "<!doctype html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{html.escape(title)}</title>",
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
          --accent-soft: #d9f4ef;
          --warn: #9a3412;
          --warn-soft: #ffedd5;
        }
        * { box-sizing: border-box; }
        body {
          margin: 0;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: var(--bg);
          color: var(--ink);
          line-height: 1.55;
        }
        header {
          padding: 32px 24px 20px;
          border-bottom: 1px solid var(--line);
          background: var(--panel);
        }
        main { max-width: 1120px; margin: 0 auto; padding: 24px; }
        h1 { margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }
        h2 { margin: 28px 0 14px; font-size: 21px; letter-spacing: 0; }
        h3 { margin: 0; font-size: 17px; letter-spacing: 0; }
        a { color: #0b5cad; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .meta, .snippet, .reason, .question { color: var(--muted); }
        .stats { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
        .stat {
          border: 1px solid var(--line);
          border-radius: 8px;
          padding: 8px 10px;
          background: #fbfdff;
          font-size: 14px;
        }
        .questions {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
          gap: 10px;
          margin: 16px 0 4px;
        }
        .question {
          border-left: 3px solid var(--accent);
          padding: 8px 10px;
          background: var(--accent-soft);
          border-radius: 6px;
        }
        .grid { display: grid; grid-template-columns: 1fr; gap: 12px; }
        .paper {
          display: grid;
          grid-template-columns: 48px 1fr;
          gap: 14px;
          padding: 16px;
          background: var(--panel);
          border: 1px solid var(--line);
          border-radius: 8px;
        }
        .favicon {
          width: 40px;
          height: 40px;
          border-radius: 8px;
          border: 1px solid var(--line);
          background: #fff;
          padding: 5px;
        }
        .placeholder {
          width: 40px;
          height: 40px;
          border-radius: 8px;
          background: var(--accent-soft);
          color: var(--accent);
          display: grid;
          place-items: center;
          font-weight: 700;
        }
        .badges { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
        .badge {
          border-radius: 999px;
          background: #eef2f7;
          color: #334e68;
          padding: 3px 8px;
          font-size: 12px;
          white-space: nowrap;
        }
        .badge.must { background: var(--warn-soft); color: var(--warn); }
        .badge.new { background: var(--accent-soft); color: var(--accent); }
        .why { margin: 10px 0 0; padding-left: 18px; }
        .why li { margin: 3px 0; color: var(--muted); }
        .archive { columns: 2 320px; padding-left: 18px; }
        .feedback-help {
          margin: 18px 0 4px;
          padding: 12px 14px;
          border: 1px solid var(--line);
          border-radius: 8px;
          background: #fbfdff;
        }
        code {
          display: block;
          overflow-x: auto;
          padding: 8px 0 0;
          font-size: 13px;
          white-space: nowrap;
        }
        @media (max-width: 640px) {
          header { padding: 24px 16px 16px; }
          main { padding: 16px; }
          .paper { grid-template-columns: 1fr; }
        }
        """,
        "</style>",
        "</head>",
        "<body>",
        "<header>",
        f"<h1>{html.escape(title)}</h1>",
        f'<div class="meta">Profile: {html.escape(str(profile.get("name", "unnamed")))} · Generated: {html.escape(generated)}</div>',
        '<div class="stats">',
        f'<div class="stat">Papers: {len(papers)}</div>',
        f'<div class="stat">Must read: {tier_counts.get("Must read", 0)}</div>',
        f'<div class="stat">Skim: {tier_counts.get("Skim", 0)}</div>',
        f'<div class="stat">Archive: {tier_counts.get("Archive", 0)}</div>',
        f'<div class="stat">Scholar emails: {summary.get("source_counts", {}).get("scholar_messages", 0)}</div>',
        "</div>",
        "</header>",
        "<main>",
    ]

    if questions:
        parts.extend(['<section class="questions">'])
        for question in questions:
            parts.append(f'<div class="question">{html.escape(str(question))}</div>')
        parts.append("</section>")

    profile_arg = shlex.quote(str(summary.get("profile", "<profile.json>")))
    papers_arg = shlex.quote(str(path.parent / "papers.json"))
    parts.extend(
        [
            '<section class="feedback-help">',
            "<strong>反馈入口</strong>",
            '<div class="meta">Use a paper ID from the badges below to tune future runs.</div>',
            f"<code>python3 scripts/scholar_reader.py feedback --profile {html.escape(profile_arg)} --papers-json {html.escape(papers_arg)} --paper-id &lt;ID&gt; --mark interested --more-like-this</code>",
            f"<code>python3 scripts/scholar_reader.py feedback --profile {html.escape(profile_arg)} --papers-json {html.escape(papers_arg)} --paper-id &lt;ID&gt; --mark archive --less-like-this</code>",
            "</section>",
        ]
    )

    for tier_name, items, max_items in sections:
        parts.extend([f"<h2>{html.escape(tier_name)} ({len(items)})</h2>", '<section class="grid">'])
        if not items:
            parts.append('<p class="meta">None.</p>')
        for index, paper in enumerate(items[:max_items], 1):
            parts.append(render_paper_html(index, paper))
        parts.append("</section>")

    archive_items = papers_for_tier(papers, "Archive")
    parts.extend([f"<h2>Archive quick view ({len(archive_items)})</h2>", '<ul class="archive">'])
    for paper in archive_items[:40]:
        new_mark = "NEW " if paper.is_new else ""
        parts.append(f"<li>{html.escape(new_mark)}{paper.score}: {html.escape(paper.title)}</li>")
    parts.extend(["</ul>", "</main>", "</body>", "</html>"])
    path.write_text("\n".join(parts), encoding="utf-8")


def render_paper_html(index: int, paper: Paper) -> str:
    icon = favicon_url(paper.url)
    icon_html = (
        f'<img class="favicon" alt="" src="{icon}">'
        if icon
        else f'<div class="placeholder">{html.escape(paper.tier[:1])}</div>'
    )
    terms = paper.matched_terms[:10]
    badges = [
        f'<span class="badge {"must" if paper.tier == "Must read" else ""}">score {paper.score}</span>',
        f'<span class="badge">id {html.escape(paper.id)}</span>',
    ]
    if paper.is_new:
        badges.append('<span class="badge new">new</span>')
    badges.extend(f'<span class="badge">{html.escape(term)}</span>' for term in terms)
    reasons = "".join(f"<li>{html.escape(reason)}</li>" for reason in paper.reasons[:4])
    alerts = "; ".join(paper.alerts[:4])
    if len(paper.alerts) > 4:
        alerts += f"; +{len(paper.alerts) - 4} more"
    return "\n".join(
        [
            '<article class="paper">',
            icon_html,
            "<div>",
            f'<h3>{index}. <a href="{html.escape(paper.url, quote=True)}">{html.escape(paper.title)}</a></h3>',
            f'<div class="meta">{html.escape(paper.authors_source)}</div>',
            f'<div class="badges">{"".join(badges)}</div>',
            f'<p class="snippet">{html.escape(paper.snippet)}</p>',
            f'<div class="reason">Alert: {html.escape(alerts)}</div>',
            f'<ul class="why">{reasons}</ul>',
            "</div>",
            "</article>",
        ]
    )


def render_paper(index: int, paper: Paper) -> list[str]:
    new_mark = "NEW " if paper.is_new else ""
    terms = ", ".join(paper.matched_terms) if paper.matched_terms else "none"
    alerts = "; ".join(paper.alerts[:4])
    if len(paper.alerts) > 4:
        alerts += f"; +{len(paper.alerts) - 4} more"
    lines = [
        f"### {index}. {new_mark}{paper.title}",
        "",
        f"- Score: {paper.score}; terms: {terms}",
        f"- ID: {paper.id}",
        f"- Source: {paper.authors_source}",
        f"- Alert: {alerts}",
        f"- Link: {paper.url}",
        f"- Snippet: {paper.snippet}",
        "- Why:",
    ]
    for reason in paper.reasons[:4]:
        lines.append(f"  - {reason}")
    lines.append("")
    return lines


def write_deep_read_queue(path: Path, papers: list[Paper], profile: dict[str, Any]) -> None:
    lim = limits(profile)
    candidates = [paper for paper in papers if paper.tier == "Must read"][: lim["deep_read"]]
    lines = [
        "# Deep Read Queue",
        "",
        "Use this file as the handoff to deep-research / paper review.",
        "",
    ]
    for index, paper in enumerate(candidates, 1):
        lines.extend(
            [
                f"## {index}. {paper.title}",
                "",
                f"- Link: {paper.url}",
                f"- Source: {paper.authors_source}",
                f"- Score: {paper.score}",
                f"- Matched: {', '.join(paper.matched_terms)}",
                f"- Snippet: {paper.snippet}",
                "- Reading task: summarize contribution, method, data, limitations, and relevance to the active research questions.",
                "",
            ]
        )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def kb_settings(profile: dict[str, Any]) -> dict[str, Any]:
    configured = profile.get("knowledge_base", {})
    return {
        "foundation_tiers": configured.get("foundation_tiers", ["Must read", "Skim"]),
        "interested_tiers": configured.get("interested_tiers", ["Must read"]),
        "interested_limit": int(configured.get("interested_limit", 50)),
        "foundation_limit_per_direction": int(configured.get("foundation_limit_per_direction", 40)),
        "write_archive_index": bool(configured.get("write_archive_index", False)),
    }


def paper_directions(paper: Paper) -> list[str]:
    directions = [tag for tag in paper.tags if tag not in {"boost", "watchlist"}]
    if not directions:
        directions = ["uncategorized"]
    return sorted(set(directions))


def paper_md_line(paper: Paper) -> str:
    terms = ", ".join(paper.matched_terms[:8]) if paper.matched_terms else "no matched terms"
    return (
        f"- **[{paper.title}]({paper.url})** "
        f"({paper.score}, {paper.tier}; {terms}) — {paper.authors_source}"
    )


def retained_for_foundation(papers: list[Paper], profile: dict[str, Any]) -> list[Paper]:
    tiers = set(kb_settings(profile)["foundation_tiers"])
    return [paper for paper in papers if paper.tier in tiers]


def paper_from_dict(data: dict[str, Any]) -> Paper:
    fields = {field_name for field_name in Paper.__dataclass_fields__}
    kwargs = {key: value for key, value in data.items() if key in fields}
    return Paper(**kwargs)


def load_paper_library(kb_dir: Path) -> list[Paper]:
    path = kb_dir / "library.json"
    if not path.exists():
        return []
    try:
        data = load_json(path)
    except Exception:
        return []
    papers = []
    for item in data:
        try:
            papers.append(paper_from_dict(item))
        except Exception:
            continue
    return papers


def merge_papers(existing: list[Paper], additions: list[Paper]) -> list[Paper]:
    by_id = {paper.id: paper for paper in existing}
    for incoming in additions:
        current = by_id.get(incoming.id)
        if current is None:
            by_id[incoming.id] = incoming
            continue

        for alert in incoming.alerts:
            if alert not in current.alerts:
                current.alerts.append(alert)
        current.occurrences = max(current.occurrences, incoming.occurrences)

        dates = [d for d in [current.first_seen, current.last_seen, incoming.first_seen, incoming.last_seen] if d]
        if dates:
            current.first_seen = min(dates)
            current.last_seen = max(dates)

        if incoming.score >= current.score:
            current.title = incoming.title
            current.authors_source = incoming.authors_source
            current.snippet = incoming.snippet
            current.url = incoming.url
            current.scholar_url = incoming.scholar_url
            current.score = incoming.score
            current.tier = incoming.tier

        current.matched_terms = sorted(set(current.matched_terms) | set(incoming.matched_terms), key=lambda t: t.lower())
        current.tags = sorted(set(current.tags) | set(incoming.tags))
        current.reasons = list(dict.fromkeys(current.reasons + incoming.reasons))
        current.is_new = current.is_new or incoming.is_new

    return sorted(by_id.values(), key=lambda p: (-p.score, p.title.lower()))


def save_paper_library(kb_dir: Path, papers: list[Paper]) -> None:
    save_json(kb_dir / "library.json", [asdict(paper) for paper in papers])


def write_kb_index(kb_dir: Path, papers: list[Paper], profile: dict[str, Any], summary: dict[str, Any]) -> None:
    settings = kb_settings(profile)
    tier_counts = counts_by_tier(papers)
    library_count = summary.get("library_papers", len(papers))
    lines = [
        "# Scholar Alert Knowledge Base",
        "",
        f"- Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Profile: {profile.get('name', 'unnamed')}",
        f"- Run mode: {summary.get('mode', 'run')}",
        f"- Papers in current run: {len(papers)}",
        f"- Cumulative retained papers: {library_count}",
        f"- Must read: {tier_counts.get('Must read', 0)}; Skim: {tier_counts.get('Skim', 0)}; Archive: {tier_counts.get('Archive', 0)}",
        f"- Seen-state file: {summary.get('state_file', '')}",
        f"- Feedback file: {summary.get('feedback_file', '')}",
        "",
        "## Layers",
        "",
        "- `seen_papers.json` is the dedupe baseline. It can contain every alert item, including papers you do not want to read.",
        "- `feedback.json` stores explicit user paper marks and more-like-this / less-like-this ranking signals.",
        f"- `library.json` is the cumulative retained library for tiers: {', '.join(settings['foundation_tiers'])}.",
        "- `foundation.md` is rendered from cumulative `library.json`, grouped by direction.",
        f"- `interested.md` is rendered from cumulative `library.json` for tiers: {', '.join(settings['interested_tiers'])}.",
        "- `daily_additions.md` keeps the latest new-paper-only additions.",
        "- `runs/` keeps timestamped reports from individual runs.",
        "",
        "## Files",
        "",
        "- [foundation.md](foundation.md)",
        "- [interested.md](interested.md)",
        "- [library.json](library.json)",
        "- [feedback.json](feedback.json)",
        "- [daily_additions.md](daily_additions.md)",
        "- [latest_run.md](latest_run.md)",
    ]
    if settings["write_archive_index"]:
        lines.append("- [archive_index.md](archive_index.md)")
    kb_dir.mkdir(parents=True, exist_ok=True)
    (kb_dir / "index.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_kb_foundation(kb_dir: Path, papers: list[Paper], profile: dict[str, Any]) -> None:
    settings = kb_settings(profile)
    tiers = set(settings["foundation_tiers"])
    kept = [paper for paper in papers if paper.tier in tiers]
    grouped: dict[str, list[Paper]] = {}
    for paper in kept:
        for direction in paper_directions(paper):
            grouped.setdefault(direction, []).append(paper)

    lines = [
        "# Foundation Library",
        "",
        "Cumulative retained papers after triage. Archive-tier papers are not included here.",
        "",
    ]
    for direction in sorted(grouped):
        items = sorted(grouped[direction], key=lambda p: (-p.score, p.title.lower()))
        lines.extend([f"## {direction} ({len(items)})", ""])
        for paper in items[: settings["foundation_limit_per_direction"]]:
            lines.append(paper_md_line(paper))
        if len(items) > settings["foundation_limit_per_direction"]:
            lines.append(f"- ... {len(items) - settings['foundation_limit_per_direction']} more in papers.json")
        lines.append("")
    if not kept:
        lines.append("No foundation papers in this run.")
    (kb_dir / "foundation.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_kb_interested(kb_dir: Path, papers: list[Paper], profile: dict[str, Any]) -> None:
    settings = kb_settings(profile)
    tiers = set(settings["interested_tiers"])
    kept = [paper for paper in papers if paper.tier in tiers][: settings["interested_limit"]]
    lines = [
        "# Interested Queue",
        "",
        "High-priority papers for active reading and follow-up.",
        "",
    ]
    for index, paper in enumerate(kept, 1):
        lines.extend(
            [
                f"## {index}. {paper.title}",
                "",
                f"- Link: {paper.url}",
                f"- Score: {paper.score}; tier: {paper.tier}",
                f"- Directions: {', '.join(paper_directions(paper))}",
                f"- Source: {paper.authors_source}",
                f"- Matched: {', '.join(paper.matched_terms)}",
                f"- Snippet: {paper.snippet}",
                "- Why:",
            ]
        )
        for reason in paper.reasons[:4]:
            lines.append(f"  - {reason}")
        lines.append("")
    if not kept:
        lines.append("No interested papers in this run.")
    (kb_dir / "interested.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_kb_daily_additions(kb_dir: Path, papers: list[Paper], profile: dict[str, Any]) -> None:
    settings = kb_settings(profile)
    retained = [paper for paper in papers if paper.tier in set(settings["foundation_tiers"])]
    interested = [paper for paper in papers if paper.tier in set(settings["interested_tiers"])]
    lines = [
        "# Daily Additions",
        "",
        f"- Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Retained new papers: {len(retained)}",
        f"- Interested new papers: {len(interested)}",
        "",
    ]
    if interested:
        lines.extend(["## Interested", ""])
        for paper in interested[: settings["interested_limit"]]:
            lines.append(paper_md_line(paper))
        lines.append("")
    if retained:
        lines.extend(["## Foundation Additions", ""])
        for paper in retained:
            lines.append(paper_md_line(paper))
        lines.append("")
    if not retained:
        lines.append("No new papers matched the foundation/interested tiers in this run.")
    (kb_dir / "daily_additions.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_kb_archive_index(kb_dir: Path, papers: list[Paper], profile: dict[str, Any]) -> None:
    if not kb_settings(profile)["write_archive_index"]:
        return
    archived = [paper for paper in papers if paper.tier == "Archive"]
    lines = [
        "# Archive Index",
        "",
        "Low-priority papers. Kept as an index only when explicitly enabled.",
        "",
    ]
    for paper in archived[:200]:
        lines.append(paper_md_line(paper))
    if len(archived) > 200:
        lines.append(f"- ... {len(archived) - 200} more archived papers in papers.json")
    (kb_dir / "archive_index.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_run_snapshot(kb_dir: Path, papers: list[Paper], summary: dict[str, Any]) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    mode = str(summary.get("mode", "run"))
    lines = [
        f"# Scholar Alert Run {stamp}",
        "",
        f"- Mode: {mode}",
        f"- Source: {summary.get('source', '')}",
        f"- Papers: {len(papers)}",
        "",
    ]
    for paper in papers_for_tier(papers, "Must read")[:20]:
        lines.append(paper_md_line(paper))
    if not papers:
        lines.append("No new papers in this run.")
    runs_dir = kb_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    content = "\n".join(lines).rstrip() + "\n"
    (runs_dir / f"{stamp}_{mode}.md").write_text(content, encoding="utf-8")
    (kb_dir / "latest_run.md").write_text(content, encoding="utf-8")


def write_knowledge_base(kb_dir: Path, papers: list[Paper], profile: dict[str, Any], summary: dict[str, Any]) -> None:
    kb_dir.mkdir(parents=True, exist_ok=True)
    additions = retained_for_foundation(papers, profile)
    library_path = kb_dir / "library.json"
    had_library = library_path.exists()
    existing_library = load_paper_library(kb_dir)
    if summary.get("mode") == "daily" or summary.get("only_new"):
        library = merge_papers(existing_library, additions)
    else:
        library = merge_papers([], additions)

    summary["library_papers"] = len(library)
    summary["library_additions"] = len(additions)
    write_kb_index(kb_dir, papers, profile, summary)
    if summary.get("mode") == "daily" and not had_library and not additions:
        pass
    else:
        save_paper_library(kb_dir, library)
        write_kb_foundation(kb_dir, library, profile)
        write_kb_interested(kb_dir, library, profile)
    if summary.get("mode") == "daily":
        write_kb_daily_additions(kb_dir, papers, profile)
    write_kb_archive_index(kb_dir, papers, profile)
    write_run_snapshot(kb_dir, papers, summary)


def write_outputs(out_dir: Path, kb_dir: Path, papers: list[Paper], profile: dict[str, Any], summary: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    save_json(out_dir / "papers.json", [asdict(paper) for paper in papers])
    write_csv(out_dir / "papers.csv", papers)
    write_digest(out_dir / "digest.md", papers, profile, summary)
    write_html_digest(out_dir / "digest.html", papers, profile, summary)
    write_deep_read_queue(out_dir / "deep_read_queue.md", papers, profile)
    write_knowledge_base(kb_dir, papers, profile, summary)
    save_json(out_dir / "summary.json", summary)


def init_profile(profile_path: Path, force: bool) -> None:
    if profile_path.exists() and not force:
        raise SystemExit(f"Profile already exists: {profile_path}. Use --force to overwrite.")
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(DEFAULT_PROFILE, profile_path)
    print(f"Profile written: {profile_path}")


def title_keywords(title: str, limit: int = 8) -> list[str]:
    tokens = re.findall(r"[a-z][a-z0-9-]{3,}", title.lower())
    keywords: list[str] = []
    for token in tokens:
        token = token.strip("-")
        if not token or token in TITLE_STOPWORDS or token.isdigit():
            continue
        if token not in keywords:
            keywords.append(token)
        if len(keywords) >= limit:
            break
    return keywords


def feedback_terms_from_paper(paper: Paper) -> list[tuple[str, int]]:
    terms: list[tuple[str, int]] = []
    for term in paper.matched_terms:
        cleaned = re.sub(r"^user:", "", term).strip()
        if not cleaned or cleaned.startswith("-"):
            continue
        terms.append((cleaned, 4))
    terms.extend((keyword, 2) for keyword in title_keywords(paper.title))

    deduped: dict[str, tuple[str, int]] = {}
    for term, weight in terms:
        key = term.lower()
        current = deduped.get(key)
        if current is None or weight > current[1]:
            deduped[key] = (term, weight)
    return list(deduped.values())


def load_papers_json(path: Path | None) -> list[Paper]:
    if not path:
        return []
    data = load_json(path)
    if isinstance(data, dict):
        data = data.get("papers", [])
    if not isinstance(data, list):
        raise SystemExit(f"Expected a list of papers in {path}")
    papers: list[Paper] = []
    for item in data:
        if isinstance(item, dict):
            papers.append(paper_from_dict(item))
    return papers


def select_feedback_papers(args: argparse.Namespace) -> list[Paper]:
    papers = load_papers_json(args.papers_json)
    requested_ids = set(split_csv(args.paper_id))
    selected: list[Paper] = []

    if requested_ids and papers:
        selected.extend([paper for paper in papers if paper.id in requested_ids])
    if args.title and papers:
        needle = args.title.lower()
        selected.extend([paper for paper in papers if needle in paper.title.lower()])

    if requested_ids and not papers:
        selected.extend(
            Paper(
                id=paper_id,
                title=args.title or paper_id,
                authors_source="",
                snippet="",
                url="",
                scholar_url="",
                first_seen="",
                last_seen="",
                alerts=[],
                occurrences=1,
            )
            for paper_id in requested_ids
        )

    by_id = {paper.id: paper for paper in selected}
    return list(by_id.values())


def add_feedback_term(
    feedback: dict[str, Any],
    term: str,
    direction: str,
    weight: int,
    source: str,
    paper_id: str | None = None,
) -> None:
    term = " ".join(term.split())
    if not term:
        return
    terms = feedback.setdefault("terms", [])
    now = datetime.now().isoformat(timespec="seconds")
    for item in terms:
        if not isinstance(item, dict):
            continue
        if str(item.get("term", "")).lower() == term.lower() and item.get("direction", "positive") == direction:
            item["weight"] = max(int(item.get("weight", 1)), weight)
            item["updated_at"] = now
            sources = item.setdefault("sources", [])
            if source not in sources:
                sources.append(source)
            if paper_id:
                source_ids = item.setdefault("source_paper_ids", [])
                if paper_id not in source_ids:
                    source_ids.append(paper_id)
            return

    record: dict[str, Any] = {
        "term": term,
        "direction": direction,
        "weight": weight,
        "sources": [source],
        "updated_at": now,
    }
    if paper_id:
        record["source_paper_ids"] = [paper_id]
    terms.append(record)


def update_paper_feedback(
    feedback: dict[str, Any],
    paper: Paper,
    mark: str | None,
    more_like_this: bool,
    less_like_this: bool,
    note: str | None,
) -> None:
    papers = feedback.setdefault("papers", {})
    now = datetime.now().isoformat(timespec="seconds")
    record = papers.setdefault(
        paper.id,
        {
            "id": paper.id,
            "title": paper.title,
            "url": paper.url,
            "status": "neutral",
            "signals": {},
            "note": "",
            "created_at": now,
        },
    )
    record["title"] = paper.title
    record["url"] = paper.url
    record["updated_at"] = now
    if mark:
        record["status"] = mark
    signals = record.setdefault("signals", {})
    if more_like_this:
        signals["more_like_this"] = True
        signals["less_like_this"] = False
    if less_like_this:
        signals["less_like_this"] = True
        signals["more_like_this"] = False
    if note is not None:
        record["note"] = note


def paper_feedback_status(feedback: dict[str, Any], paper_id: str) -> str:
    record = feedback.get("papers", {}).get(paper_id, {})
    if isinstance(record, dict):
        return str(record.get("status", "neutral"))
    return "neutral"


def apply_feedback_to_knowledge_base(
    kb_dir: Path,
    target_papers: list[Paper],
    profile: dict[str, Any],
    feedback: dict[str, Any],
    feedback_file: Path,
    profile_path: Path,
) -> int:
    if not target_papers:
        return 0

    existing_library = load_paper_library(kb_dir)
    archive_ids = {
        paper.id
        for paper in target_papers
        if paper_feedback_status(feedback, paper.id) == "archive"
    }
    library = [paper for paper in existing_library if paper.id not in archive_ids]

    reranked: list[Paper] = []
    for paper in target_papers:
        score_paper(paper, profile, None, feedback)
        reranked.append(paper)

    additions = [
        paper
        for paper in retained_for_foundation(reranked, profile)
        if paper_feedback_status(feedback, paper.id) != "archive"
    ]
    library = merge_papers(library, additions)

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "profile": str(profile_path),
        "source": "feedback",
        "source_counts": {},
        "unique_papers_before_state_filter": len(target_papers),
        "papers_in_digest": len(reranked),
        "tier_counts": dict(counts_by_tier(reranked)),
        "only_new": False,
        "mode": "feedback",
        "state_file": "",
        "knowledge_base_dir": str(kb_dir),
        "feedback_file": str(feedback_file),
        "feedback_terms": len(feedback.get("terms", [])),
        "feedback_papers": len(feedback.get("papers", {})),
        "library_papers": len(library),
        "library_additions": len(additions),
    }

    kb_dir.mkdir(parents=True, exist_ok=True)
    save_paper_library(kb_dir, library)
    write_kb_index(kb_dir, library, profile, summary)
    write_kb_foundation(kb_dir, library, profile)
    write_kb_interested(kb_dir, library, profile)
    write_run_snapshot(kb_dir, reranked, summary)
    return len(additions)


def add_terms(profile: dict[str, Any], section: str, terms: list[str], weight: int) -> None:
    existing = profile.setdefault(section, [])
    by_lower = {
        (item["term"] if isinstance(item, dict) else str(item)).lower(): item
        for item in existing
    }
    for term in terms:
        key = term.lower()
        current = by_lower.get(key)
        if isinstance(current, dict):
            current["weight"] = max(int(current.get("weight", 1)), weight)
        elif current is None:
            existing.append({"term": term, "weight": weight})


def update_profile_from_feedback(args: argparse.Namespace) -> None:
    profile = load_profile(args.profile)
    kb_dir = args.kb_dir or default_kb_dir(args.profile, Path("scholar_alerts/out"))
    feedback_file = args.feedback_file or default_feedback_file(kb_dir)
    feedback = load_feedback(feedback_file)

    more_terms = split_csv(args.more)
    less_terms = split_csv(args.less)
    author_terms = split_csv(args.watch_author)
    region_terms = split_csv(args.region)
    method_terms = split_csv(args.method)

    profile_changed = False
    if not args.no_profile_update:
        add_terms(profile, "focus_terms", more_terms, args.more_weight)
        add_terms(profile, "exclude_terms", less_terms, args.less_weight)
        add_terms(profile, "watch_authors", author_terms, args.author_weight)
        add_terms(profile, "regions", region_terms, args.region_weight)
        add_terms(profile, "methods", method_terms, args.method_weight)
        profile_changed = bool(more_terms or less_terms or author_terms or region_terms or method_terms)
        if args.must_read_limit is not None:
            profile.setdefault("limits", {})["must_read"] = args.must_read_limit
            profile_changed = True
        if args.deep_read_limit is not None:
            profile.setdefault("limits", {})["deep_read"] = args.deep_read_limit
            profile_changed = True

    feedback_changed = False
    for terms, weight in [
        (more_terms, args.more_weight),
        (region_terms, args.region_weight),
        (method_terms, args.method_weight),
        (author_terms, args.author_weight),
    ]:
        for term in terms:
            add_feedback_term(feedback, term, "positive", weight, "manual")
            feedback_changed = True
    for term in less_terms:
        add_feedback_term(feedback, term, "negative", args.less_weight, "manual")
        feedback_changed = True

    target_papers = select_feedback_papers(args)
    needs_target = bool(args.mark or args.more_like_this or args.less_like_this or args.note)
    if (args.more_like_this or args.less_like_this) and not args.papers_json:
        raise SystemExit("--more-like-this and --less-like-this require --papers-json so paper terms can be inferred.")
    if needs_target and not target_papers:
        raise SystemExit(
            "No matching paper found. Pass --papers-json with --paper-id or --title, "
            "or pass --paper-id without --papers-json to record an ID-only mark."
        )

    for paper in target_papers:
        update_paper_feedback(feedback, paper, args.mark, args.more_like_this, args.less_like_this, args.note)
        feedback_changed = True
        if args.more_like_this:
            for term, weight in feedback_terms_from_paper(paper):
                add_feedback_term(feedback, term, "positive", weight, "paper", paper.id)
        if args.less_like_this:
            for term, weight in feedback_terms_from_paper(paper):
                add_feedback_term(feedback, term, "negative", weight, "paper", paper.id)

    if profile_changed:
        save_json(args.profile, profile)
        print(f"Profile updated: {args.profile}")
    if feedback_changed:
        save_feedback(feedback_file, feedback)
        print(f"Feedback updated: {feedback_file}")
        if target_papers:
            added = apply_feedback_to_knowledge_base(
                kb_dir,
                target_papers,
                profile,
                feedback,
                feedback_file,
                args.profile,
            )
            print(f"Knowledge base updated: {kb_dir} ({added} retained additions from feedback)")
            print("Papers: " + ", ".join(f"{paper.id} {paper.title}" for paper in target_papers))
    if not profile_changed and not feedback_changed:
        print("No feedback changes requested.")


def default_state_file(profile_path: Path | None, out_dir: Path) -> Path:
    if profile_path:
        return profile_path.parent / "seen_papers.json"
    return out_dir / "seen_papers.json"


def default_kb_dir(profile_path: Path | None, out_dir: Path) -> Path:
    if profile_path:
        return profile_path.parent.parent / "knowledge_base"
    return out_dir / "knowledge_base"


def default_feedback_file(kb_dir: Path) -> Path:
    return kb_dir / "feedback.json"


def run(args: argparse.Namespace) -> None:
    profile = load_profile(args.profile)
    state_file = args.state_file or default_state_file(args.profile, args.out_dir)
    kb_dir = args.kb_dir or default_kb_dir(args.profile, args.out_dir)
    feedback_file = args.feedback_file or default_feedback_file(kb_dir)
    feedback = empty_feedback() if args.no_feedback else load_feedback(feedback_file)
    seen = load_seen(state_file)

    if getattr(args, "source_mail_app", False):
        papers, source_counts = parse_mail_app_source(args.since_days, args.mail_limit)
        source_label = "Mail.app Inbox"
    elif getattr(args, "source_gmail", False):
        papers, source_counts = parse_gmail_source(
            args.gmail_credentials,
            args.gmail_token,
            args.since_days,
            args.gmail_limit,
            args.gmail_query,
            allow_auth=False,
        )
        source_label = "Gmail API"
    else:
        papers, source_counts = parse_mbox(args.source_mbox, args.since_days)
        source_label = str(args.source_mbox)
    total_unique = len(papers)
    papers = apply_state(papers, seen, args.only_new)
    papers = rank_papers(papers, profile, args.boost, feedback)

    tier_counts = counts_by_tier(papers)
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "profile": str(args.profile or DEFAULT_PROFILE),
        "source": source_label,
        "source_mbox": str(args.source_mbox) if getattr(args, "source_mbox", None) else "",
        "source_mail_app": bool(getattr(args, "source_mail_app", False)),
        "source_gmail": bool(getattr(args, "source_gmail", False)),
        "source_counts": source_counts,
        "unique_papers_before_state_filter": total_unique,
        "papers_in_digest": len(papers),
        "tier_counts": dict(tier_counts),
        "only_new": args.only_new,
        "mode": getattr(args, "mode", "run"),
        "state_file": str(state_file),
        "knowledge_base_dir": str(kb_dir),
        "feedback_file": "" if args.no_feedback else str(feedback_file),
        "feedback_terms": len(feedback.get("terms", [])) if not args.no_feedback else 0,
        "feedback_papers": len(feedback.get("papers", {})) if not args.no_feedback else 0,
        "boost": args.boost or "",
    }
    write_outputs(args.out_dir, kb_dir, papers, profile, summary)
    if args.update_state:
        update_seen(state_file, papers)

    print(f"Papers in digest: {len(papers)}")
    print(f"Tier counts: {dict(tier_counts)}")
    print(f"Digest: {args.out_dir / 'digest.md'}")
    print(f"HTML: {args.out_dir / 'digest.html'}")
    print(f"Deep-read queue: {args.out_dir / 'deep_read_queue.md'}")
    print(f"JSON: {args.out_dir / 'papers.json'}")
    print(f"CSV: {args.out_dir / 'papers.csv'}")
    print(f"Knowledge base: {kb_dir}")


def add_source_profile_args(cmd: argparse.ArgumentParser, default_out_dir: str) -> None:
    source = cmd.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-mbox", type=Path, help="Path to mbox file or Apple Mail .mbox package")
    source.add_argument("--source-mail-app", action="store_true", help="Read Google Scholar Alert messages directly from Mail.app Inbox")
    source.add_argument("--source-gmail", action="store_true", help="Read Google Scholar Alert messages through Gmail API")
    cmd.add_argument("--profile", type=Path, help="JSON research profile")
    cmd.add_argument("--out-dir", type=Path, default=Path(default_out_dir))
    cmd.add_argument("--boost", help="Comma-separated temporary priority terms, e.g. 'Taiwan,receiver function'")
    cmd.add_argument("--state-file", type=Path, help="Seen-paper state JSON. Defaults to profile directory/seen_papers.json")
    cmd.add_argument("--kb-dir", type=Path, help="Knowledge-base output directory. Defaults to profile parent/knowledge_base")
    cmd.add_argument("--feedback-file", type=Path, help="User feedback JSON. Defaults to kb-dir/feedback.json")
    cmd.add_argument("--no-feedback", action="store_true", help="Ignore saved user feedback for this run")
    cmd.add_argument("--mail-limit", type=int, default=0, help="Max Mail.app messages to export; 0 means no limit")
    cmd.add_argument("--gmail-limit", type=int, default=0, help="Max Gmail API messages to fetch; 0 means no limit")
    cmd.add_argument("--gmail-query", help="Additional Gmail search query terms")
    cmd.add_argument("--gmail-credentials", type=Path, default=DEFAULT_GMAIL_CREDENTIALS)
    cmd.add_argument("--gmail-token", type=Path, default=DEFAULT_GMAIL_TOKEN)


def run_foundation(args: argparse.Namespace) -> None:
    args.only_new = False
    args.update_state = True
    args.since_days = None
    args.mode = "foundation"
    run(args)


def run_daily(args: argparse.Namespace) -> None:
    args.only_new = True
    args.update_state = True
    args.mode = "daily"
    run(args)


def auth_gmail(args: argparse.Namespace) -> None:
    service = gmail_service(args.gmail_credentials, args.gmail_token, allow_auth=True)
    profile = service.users().getProfile(userId="me").execute()
    print(f"Gmail authorized: {profile.get('emailAddress', 'unknown')}")
    print(f"Token: {args.gmail_token}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-profile", help="Copy the default profile to a writable path")
    init.add_argument("--profile", type=Path, required=True)
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=lambda args: init_profile(args.profile, args.force))

    auth = sub.add_parser("auth-gmail", help="Run the one-time Gmail OAuth browser flow")
    auth.add_argument("--gmail-credentials", type=Path, default=DEFAULT_GMAIL_CREDENTIALS)
    auth.add_argument("--gmail-token", type=Path, default=DEFAULT_GMAIL_TOKEN)
    auth.set_defaults(func=auth_gmail)

    foundation = sub.add_parser("foundation", help="Build the first all-alert baseline and mark papers as seen")
    add_source_profile_args(foundation, "scholar_alerts/foundation_out")
    foundation.set_defaults(func=run_foundation)

    daily = sub.add_parser("daily", help="Report only papers not seen in the foundation/state file")
    add_source_profile_args(daily, "scholar_alerts/daily_out")
    daily.add_argument("--since-days", type=int, default=7, help="Only scan Scholar messages newer than this many days")
    daily.set_defaults(func=run_daily)

    run_cmd = sub.add_parser("run", help="Run Scholar Alert triage with explicit state flags")
    add_source_profile_args(run_cmd, "scholar_alerts/out")
    run_cmd.add_argument("--since-days", type=int, help="Only include Scholar messages newer than this many days")
    run_cmd.add_argument("--only-new", action="store_true", help="Filter out papers already in the state file")
    run_cmd.add_argument("--update-state", action="store_true", help="Record output paper IDs as seen")
    run_cmd.set_defaults(mode="run")
    run_cmd.set_defaults(func=run)

    feedback = sub.add_parser("feedback", help="Record paper-level feedback and update ranking preferences")
    feedback.add_argument("--profile", type=Path, required=True)
    feedback.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to profile parent/knowledge_base")
    feedback.add_argument("--feedback-file", type=Path, help="Feedback JSON. Defaults to kb-dir/feedback.json")
    feedback.add_argument("--papers-json", type=Path, help="papers.json from a previous run, used to resolve paper IDs/titles")
    feedback.add_argument("--paper-id", help="Comma-separated paper IDs to mark")
    feedback.add_argument("--title", help="Case-insensitive title substring to find in --papers-json")
    feedback.add_argument("--mark", choices=["interested", "archive", "neutral"], help="Explicit paper status")
    feedback.add_argument("--more-like-this", action="store_true", help="Use selected paper terms as positive ranking feedback")
    feedback.add_argument("--less-like-this", action="store_true", help="Use selected paper terms as negative ranking feedback")
    feedback.add_argument("--note", help="Free-form note for the selected paper feedback")
    feedback.add_argument("--more", help="Comma-separated terms to prioritize")
    feedback.add_argument("--less", help="Comma-separated terms to suppress")
    feedback.add_argument("--watch-author", help="Comma-separated authors/alert names to prioritize")
    feedback.add_argument("--region", help="Comma-separated regions to prioritize")
    feedback.add_argument("--method", help="Comma-separated methods to prioritize")
    feedback.add_argument("--more-weight", type=int, default=5)
    feedback.add_argument("--less-weight", type=int, default=5)
    feedback.add_argument("--author-weight", type=int, default=4)
    feedback.add_argument("--region-weight", type=int, default=5)
    feedback.add_argument("--method-weight", type=int, default=5)
    feedback.add_argument("--must-read-limit", type=int)
    feedback.add_argument("--deep-read-limit", type=int)
    feedback.add_argument("--no-profile-update", action="store_true", help="Record feedback.json only; do not edit the profile")
    feedback.set_defaults(func=update_profile_from_feedback)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
