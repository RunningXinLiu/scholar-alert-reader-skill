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
import importlib.util
import json
import mailbox
import os
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import webbrowser
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from email import message_from_binary_file, message_from_bytes
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

from . import __version__


SCHOLAR_SENDER = "scholaralerts-noreply@google.com"
SCRIPT_DIR = Path(__file__).resolve().parent
RESOURCE_DIR = SCRIPT_DIR / "resources"


def resource_path(*parts: str) -> Path:
    repo_path = SCRIPT_DIR.parent.joinpath(*parts)
    if repo_path.exists():
        return repo_path
    return RESOURCE_DIR.joinpath(*parts)


DEFAULT_PROFILE = resource_path("assets", "default_profile.json")
PROFILE_TEMPLATE_DIR = resource_path("assets", "profile_templates")
DEFAULT_PROFILE_TEMPLATE = "general-geophysics"
PROJECT_ENV_NAME = "reader.env"
DEFAULT_PRIVATE_DIR = Path.home() / ".codex" / "scholar-alert-reader"
DEFAULT_GMAIL_CREDENTIALS = DEFAULT_PRIVATE_DIR / "gmail_credentials.json"
DEFAULT_GMAIL_TOKEN = DEFAULT_PRIVATE_DIR / "gmail_token.json"
SOURCE_CHOICES = ["auto", "gmail", "mail-app", "mbox", "bibtex", "ris", "web", "rss", "arxiv"]
MODE_CHOICES = ["daily", "foundation", "run"]
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
FEEDBACK_VERSION = 1

TITLE_STOPWORDS = {
    "about",
    "across",
    "after",
    "among",
    "and",
    "analysis",
    "are",
    "based",
    "before",
    "between",
    "can",
    "case",
    "could",
    "data",
    "during",
    "earth",
    "effects",
    "evidence",
    "for",
    "from",
    "global",
    "had",
    "has",
    "have",
    "her",
    "high",
    "his",
    "implications",
    "into",
    "its",
    "large",
    "may",
    "might",
    "model",
    "models",
    "new",
    "not",
    "onto",
    "our",
    "over",
    "paper",
    "per",
    "regional",
    "results",
    "shall",
    "should",
    "study",
    "system",
    "that",
    "the",
    "their",
    "this",
    "through",
    "toward",
    "towards",
    "under",
    "using",
    "via",
    "was",
    "were",
    "where",
    "which",
    "while",
    "will",
    "with",
    "within",
    "without",
    "would",
    "your",
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
    overlap: list[str] = field(default_factory=list)


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
    metadata: dict[str, Any] = field(default_factory=dict)
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


def available_profile_templates() -> list[str]:
    if not PROFILE_TEMPLATE_DIR.exists():
        return []
    return sorted(path.stem for path in PROFILE_TEMPLATE_DIR.glob("*.json"))


def resolve_profile_template(template: str | Path | None) -> Path:
    if not template:
        template = DEFAULT_PROFILE_TEMPLATE
    template_text = str(template)
    if template_text in {"default", DEFAULT_PROFILE_TEMPLATE}:
        candidate = PROFILE_TEMPLATE_DIR / f"{DEFAULT_PROFILE_TEMPLATE}.json"
        return candidate if candidate.exists() else DEFAULT_PROFILE
    path_candidate = Path(template_text).expanduser()
    if path_candidate.exists():
        return path_candidate
    slug_candidate = PROFILE_TEMPLATE_DIR / f"{template_text}.json"
    if slug_candidate.exists():
        return slug_candidate
    names = ", ".join(available_profile_templates()) or "none"
    raise SystemExit(f"Unknown profile template: {template_text}. Available templates: {names}. You can also pass a JSON file path.")


def copy_profile_template(profile_path: Path, template: str | Path | None, force: bool) -> Path:
    if profile_path.exists() and not force:
        raise SystemExit(f"Profile already exists: {profile_path}. Use --force to overwrite.")
    source = resolve_profile_template(template)
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, profile_path)
    return source


def coerce_terms(items: Iterable[Any], section: str, default_weight: int = 1) -> list[dict[str, Any]]:
    terms: list[dict[str, Any]] = []
    fallback_tags = {
        "focus_terms": ["focus"],
        "regions": ["region"],
        "methods": ["method"],
        "semantic_queries": ["semantic"],
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
        ("semantic_queries", 3),
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


def semantic_token(value: str) -> str:
    token = value.lower().strip("-_")
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith(("ing", "ers")):
        return token[:-3]
    if len(token) > 3 and token.endswith(("ed", "es")):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def semantic_tokens(value: str) -> set[str]:
    found = re.findall(r"[a-z0-9]+", value.lower())
    tokens = {semantic_token(token) for token in found}
    return {token for token in tokens if token and token not in TITLE_STOPWORDS and len(token) > 2}


def paper_affinity_tokens(paper: Paper) -> set[str]:
    text = " ".join(
        [
            paper.title,
            paper.snippet,
            paper.authors_source,
            " ".join(paper.alerts),
            " ".join(paper.matched_terms),
            " ".join(paper.tags),
        ]
    )
    return semantic_tokens(text)


def semantic_term_hit(item: dict[str, Any], fields: dict[str, str]) -> tuple[int, str, list[str]] | None:
    term_tokens = semantic_tokens(str(item.get("term", "")))
    if len(term_tokens) < 2:
        return None
    field_tokens = {field_name: semantic_tokens(field_text) for field_name, field_text in fields.items()}
    haystack_tokens = set().union(*field_tokens.values()) if field_tokens else set()
    overlap = sorted(term_tokens & haystack_tokens)
    required = max(2, (len(term_tokens) * 3 + 4) // 5)
    if len(overlap) < required:
        return None
    ratio = len(overlap) / len(term_tokens)
    base_weight = int(item.get("weight", 1))
    weight = max(1, round(base_weight * ratio))
    if field_tokens.get("title", set()) & set(overlap):
        weight += 1
        field = "semantic:title"
    else:
        field = "semantic"
    return weight, field, overlap[:8]


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


def adaptive_ranking_settings(profile: dict[str, Any]) -> dict[str, Any]:
    configured = profile.get("adaptive_ranking", {})
    if not isinstance(configured, dict):
        configured = {}
    return {
        "enabled": bool(configured.get("enabled", True)),
        "positive_weight": int(configured.get("positive_weight", 4)),
        "negative_weight": int(configured.get("negative_weight", 5)),
        "min_overlap": max(2, int(configured.get("min_overlap", 3))),
        "max_seed_papers": max(1, int(configured.get("max_seed_papers", 40))),
        "seed_tiers": [str(tier) for tier in configured.get("seed_tiers", ["Must read"])],
    }


def feedback_paper_record(feedback: dict[str, Any] | None, paper_id: str) -> dict[str, Any]:
    if not isinstance(feedback, dict):
        return {}
    record = feedback.get("papers", {}).get(paper_id, {})
    return record if isinstance(record, dict) else {}


def positive_seed_paper(paper: Paper, feedback: dict[str, Any] | None, seed_tiers: set[str]) -> bool:
    record = feedback_paper_record(feedback, paper.id)
    signals = record.get("signals", {}) if isinstance(record.get("signals", {}), dict) else {}
    reading_status = str(record.get("reading_status", "") or "")
    if record.get("status") == "archive" or reading_status == "not-relevant" or signals.get("less_like_this"):
        return False
    if record.get("status") == "interested" or signals.get("more_like_this"):
        return True
    if reading_status in {"reading", "read", "must-cite", "method-reference"}:
        return True
    return paper.tier in seed_tiers


def negative_seed_paper(record: dict[str, Any]) -> bool:
    signals = record.get("signals", {}) if isinstance(record.get("signals", {}), dict) else {}
    return record.get("status") == "archive" or record.get("reading_status") == "not-relevant" or signals.get("less_like_this")


def feedback_record_to_paper(paper_id: str, record: dict[str, Any]) -> Paper:
    return Paper(
        id=paper_id,
        title=str(record.get("title", "") or paper_id),
        authors_source="",
        snippet=str(record.get("note", "") or ""),
        url=str(record.get("url", "") or ""),
        scholar_url="",
        first_seen="",
        last_seen="",
        alerts=[],
        occurrences=1,
    )


def adaptive_ranking_adjustment(
    paper: Paper,
    profile: dict[str, Any],
    feedback: dict[str, Any] | None,
    library: list[Paper] | None,
) -> tuple[int, list[str], set[str], list[str]]:
    settings = adaptive_ranking_settings(profile)
    if not settings["enabled"]:
        return 0, [], set(), []

    seed_tiers = set(settings["seed_tiers"])
    library_positive_seeds: list[Paper] = []
    feedback_positive_seeds: list[Paper] = []
    negative_seeds: list[Paper] = []
    library_by_id = {seed.id: seed for seed in library or [] if seed.id != paper.id}
    for seed in library_by_id.values():
        if positive_seed_paper(seed, feedback, seed_tiers):
            library_positive_seeds.append(seed)

    for paper_id, record in (feedback or {}).get("papers", {}).items():
        if not isinstance(record, dict) or str(paper_id) == paper.id:
            continue
        signals = record.get("signals", {}) if isinstance(record.get("signals", {}), dict) else {}
        seed = library_by_id.get(str(paper_id)) or feedback_record_to_paper(str(paper_id), record)
        if negative_seed_paper(record):
            negative_seeds.append(seed)
        elif record.get("status") == "interested" or signals.get("more_like_this"):
            feedback_positive_seeds.append(seed)

    positive_seeds = list({seed.id: seed for seed in feedback_positive_seeds + library_positive_seeds}.values())[
        : settings["max_seed_papers"]
    ]
    negative_seeds = negative_seeds[: settings["max_seed_papers"]]
    if not positive_seeds and not negative_seeds:
        return 0, [], set(), []

    target_tokens = paper_affinity_tokens(paper)
    if len(target_tokens) < settings["min_overlap"]:
        return 0, [], set(), []

    def best(seed_papers: list[Paper]) -> tuple[Paper | None, list[str], int]:
        best_seed: Paper | None = None
        best_overlap: list[str] = []
        best_score = 0
        for seed in seed_papers:
            seed_tokens = paper_affinity_tokens(seed)
            overlap = sorted(target_tokens & seed_tokens)
            overlap_count = len(overlap)
            if overlap_count < settings["min_overlap"]:
                continue
            score = overlap_count * 100 + (50 if seed.tier == "Must read" else 0)
            if score > best_score:
                best_seed = seed
                best_overlap = overlap
                best_score = score
        return best_seed, best_overlap, best_score

    positive_seed, positive_overlap, _ = best(positive_seeds)
    negative_seed, negative_overlap, _ = best(negative_seeds)

    delta = 0
    matched_terms: list[str] = []
    tags: set[str] = set()
    reasons: list[str] = []
    if positive_seed:
        strength = min(1.5, len(positive_overlap) / settings["min_overlap"])
        boost = max(1, round(settings["positive_weight"] * strength))
        delta += boost
        matched_terms.append(f"similar:{positive_seed.title}")
        tags.add("adaptive")
        reasons.append(
            f"反馈相似度加权：和已关注论文 `{positive_seed.title}` 共享 {len(positive_overlap)} 个关键词"
            f"（{', '.join(positive_overlap[:6])}）。"
        )
    if negative_seed:
        strength = min(1.5, len(negative_overlap) / settings["min_overlap"])
        penalty = max(1, round(settings["negative_weight"] * strength))
        delta -= penalty
        matched_terms.append(f"dissimilar:{negative_seed.title}")
        tags.add("adaptive")
        reasons.append(
            f"反馈相似度降权：和已归档论文 `{negative_seed.title}` 共享 {len(negative_overlap)} 个关键词"
            f"（{', '.join(negative_overlap[:6])}）。"
        )

    return delta, matched_terms, tags, reasons[:3]


def score_paper(
    paper: Paper,
    profile: dict[str, Any],
    boost: str | None,
    feedback: dict[str, Any] | None = None,
    library: list[Paper] | None = None,
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
        exact_match = False
        for field_name, field_text in fields.items():
            if needle in field_text:
                weight = item["weight"]
                if field_name == "title":
                    weight *= 2
                elif field_name == "alerts" and item["section"] == "watch_authors":
                    weight *= 2
                score += weight
                hits.append(TermHit(term, weight, item["section"], field_name, item.get("tags", [])))
                exact_match = True
                break
        if not exact_match:
            semantic = semantic_term_hit(item, fields)
            if semantic:
                weight, field_name, overlap = semantic
                score += weight
                tags = sorted(set(item.get("tags", [])) | {"semantic"})
                hits.append(TermHit(term, weight, item["section"], field_name, tags, overlap))

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
    adaptive_delta, adaptive_terms, adaptive_tags, adaptive_reasons = adaptive_ranking_adjustment(
        paper, profile, feedback, library
    )
    score += adaptive_delta

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
    paper.matched_terms = sorted(
        {hit.term for hit in hits} | set(feedback_terms) | set(adaptive_terms),
        key=lambda t: t.lower(),
    )
    paper.tags = sorted({tag for hit in hits for tag in hit.tags} | set(feedback_tags) | set(adaptive_tags))
    profile_reasons = build_reasons(hits, paper) if hits or not (feedback_reasons or adaptive_reasons) else []
    paper.reasons = feedback_reasons + adaptive_reasons + profile_reasons


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
        elif hit.field.startswith("semantic"):
            overlap = f"；重叠词：{', '.join(hit.overlap[:6])}" if hit.overlap else ""
            reasons.append(f"语义匹配 `{hit.term}`，与 `{hit.section}` 相关{overlap}。")
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


def file_seen_date(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()
    except OSError:
        return datetime.now().date().isoformat()


def strip_wrapping_pairs(value: str) -> str:
    value = value.strip()
    changed = True
    while changed and len(value) >= 2:
        changed = False
        if (value[0], value[-1]) in {("{", "}"), ("\"", "\"")}:
            value = value[1:-1].strip()
            changed = True
    return value


def clean_bibliography_value(value: str) -> str:
    value = strip_wrapping_pairs(value)
    replacements = {
        "\\&": "&",
        "\\%": "%",
        "\\_": "_",
        "\\textendash": "-",
        "\\textemdash": "-",
        "---": "-",
        "--": "-",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    value = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{([^{}]*)\})", r"\1", value)
    value = value.replace("{", "").replace("}", "")
    return " ".join(html.unescape(value).split())


def bibliography_paths(path: Path, suffix: str) -> list[Path]:
    path = path.expanduser()
    if not path.exists():
        raise SystemExit(f"Cannot find bibliography source: {path}")
    if path.is_dir():
        paths = sorted(path.glob(f"*{suffix}"))
        if not paths:
            raise SystemExit(f"No {suffix} files found in directory: {path}")
        return paths
    return [path]


def read_balanced_value(text: str, start: int, opener: str, closer: str) -> tuple[str, int]:
    depth = 1
    pos = start + 1
    value_chars: list[str] = []
    while pos < len(text):
        char = text[pos]
        previous = text[pos - 1] if pos > 0 else ""
        if char == opener and previous != "\\":
            depth += 1
            value_chars.append(char)
        elif char == closer and previous != "\\":
            depth -= 1
            if depth == 0:
                return "".join(value_chars), pos + 1
            value_chars.append(char)
        else:
            value_chars.append(char)
        pos += 1
    return "".join(value_chars), pos


def split_top_level_comma(text: str) -> tuple[str, str]:
    brace_depth = 0
    quote_open = False
    for pos, char in enumerate(text):
        previous = text[pos - 1] if pos > 0 else ""
        if char == '"' and previous != "\\":
            quote_open = not quote_open
        elif not quote_open:
            if char == "{":
                brace_depth += 1
            elif char == "}":
                brace_depth = max(0, brace_depth - 1)
            elif char == "," and brace_depth == 0:
                return text[:pos], text[pos + 1 :]
    return text, ""


def read_bibtex_field_value(text: str, start: int) -> tuple[str, int]:
    pos = start
    while pos < len(text) and text[pos].isspace():
        pos += 1
    if pos >= len(text):
        return "", pos
    if text[pos] == "{":
        return read_balanced_value(text, pos, "{", "}")
    if text[pos] == '"':
        pos += 1
        value_chars: list[str] = []
        while pos < len(text):
            char = text[pos]
            previous = text[pos - 1] if pos > 0 else ""
            if char == '"' and previous != "\\":
                return "".join(value_chars), pos + 1
            value_chars.append(char)
            pos += 1
        return "".join(value_chars), pos

    start_value = pos
    while pos < len(text) and text[pos] != ",":
        pos += 1
    return text[start_value:pos], pos


def parse_bibtex_fields(body: str) -> dict[str, str]:
    key_part, fields_part = split_top_level_comma(body)
    fields: dict[str, str] = {"_key": clean_bibliography_value(key_part)}
    pos = 0
    while pos < len(fields_part):
        while pos < len(fields_part) and fields_part[pos] in ", \n\r\t":
            pos += 1
        match = re.match(r"([A-Za-z][A-Za-z0-9_-]*)\s*=", fields_part[pos:])
        if not match:
            break
        field_name = match.group(1).lower()
        pos += match.end()
        raw_value, pos = read_bibtex_field_value(fields_part, pos)
        fields[field_name] = clean_bibliography_value(raw_value)
        while pos < len(fields_part) and fields_part[pos].isspace():
            pos += 1
        if pos < len(fields_part) and fields_part[pos] == ",":
            pos += 1
    return fields


def parse_bibtex_entries(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    pos = 0
    while True:
        at = text.find("@", pos)
        if at == -1:
            break
        match = re.match(r"@([A-Za-z]+)\s*([\{\(])", text[at:])
        if not match:
            pos = at + 1
            continue
        entry_type = match.group(1).lower()
        opener = match.group(2)
        closer = "}" if opener == "{" else ")"
        body_start = at + match.end()
        body, next_pos = read_balanced_value(text, body_start - 1, opener, closer)
        if entry_type not in {"comment", "preamble", "string"}:
            fields = parse_bibtex_fields(body)
            fields["_type"] = entry_type
            entries.append(fields)
        pos = max(next_pos, at + 1)
    return entries


def coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [text]


def split_authors(value: str) -> list[str]:
    return [
        clean_bibliography_value(part)
        for part in re.split(r"\s+\band\b\s+|;\s*", value)
        if clean_bibliography_value(part)
    ]


def split_keywords(value: Any) -> list[str]:
    keywords: list[str] = []
    for item in coerce_list(value):
        for part in re.split(r"\s*;\s*|\s*,\s*", item):
            cleaned = clean_bibliography_value(part)
            if cleaned and cleaned not in keywords:
                keywords.append(cleaned)
    return keywords


def first_value(fields: dict[str, Any], names: list[str]) -> str:
    for name in names:
        value = fields.get(name)
        if isinstance(value, list):
            if value:
                return clean_bibliography_value(str(value[0]))
        elif value:
            return clean_bibliography_value(str(value))
    return ""


def year_from_fields(fields: dict[str, Any], names: list[str]) -> str:
    for name in names:
        value = first_value(fields, [name])
        match = re.search(r"\b(18|19|20|21)\d{2}\b", value)
        if match:
            return match.group(0)
    return ""


def bibliography_authors_source(authors: list[str], source: str, year: str) -> str:
    parts: list[str] = []
    if authors:
        parts.append(", ".join(authors[:6]) + (" et al." if len(authors) > 6 else ""))
    if source:
        parts.append(source)
    if year:
        parts.append(year)
    return " - ".join(parts)


def doi_url(doi: str) -> str:
    doi = doi.strip()
    if not doi:
        return ""
    if doi.lower().startswith(("http://", "https://")):
        return doi
    return f"https://doi.org/{doi}"


def normalize_doi(doi: str) -> str:
    doi = clean_bibliography_value(doi)
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    doi = doi.replace("doi:", "")
    return doi.strip().lower()


def unquote_file_url(value: str) -> str:
    value = value.strip()
    if value.lower().startswith("file://"):
        parsed = urlparse(value)
        return unquote(parsed.path)
    return value


def extract_pdf_paths(value: str) -> list[str]:
    paths: list[str] = []
    if not value:
        return paths
    for item in re.split(r"\s*;\s*", value):
        remaining = item
        for match in re.finditer(r"file://[^\s;]+?\.pdf", item, flags=re.IGNORECASE):
            path = unquote_file_url(match.group(0))
            if path and path not in paths:
                paths.append(path)
            remaining = remaining.replace(match.group(0), " ")
        for pattern in [
            r"(?<![A-Za-z0-9])(?:~|/)[^;]+?\.pdf",
            r"(?<![A-Za-z])[A-Za-z]:[\\/][^;]+?\.pdf",
        ]:
            for match in re.finditer(pattern, remaining, flags=re.IGNORECASE):
                path = unquote_file_url(match.group(0))
                if path and path not in paths:
                    paths.append(path)
    return paths


def first_nonempty_field(fields: dict[str, str], names: list[str]) -> str:
    for name in names:
        value = fields.get(name)
        if value:
            return value
    return ""


def zotero_item_key_from_fields(fields: dict[str, str]) -> str:
    direct = first_nonempty_field(fields, ["zotero-key", "zoterokey", "item-key", "itemkey"])
    if direct:
        return direct
    for name in ["uri", "zotero-select", "zotero-uri"]:
        value = fields.get(name, "")
        match = re.search(r"/items/([A-Za-z0-9]+)", value)
        if match:
            return match.group(1)
    return ""


def zotero_metadata_from_bibtex_fields(fields: dict[str, str], source_path: Path) -> dict[str, Any]:
    pdf_paths: list[str] = []
    for name, value in fields.items():
        if name == "file" or name.startswith("bdsk-file") or "attachment" in name or name in {"pdf", "local-url"}:
            for path in extract_pdf_paths(value):
                if path not in pdf_paths:
                    pdf_paths.append(path)
    return {
        "citation_key": fields.get("_key", ""),
        "item_key": zotero_item_key_from_fields(fields),
        "doi": first_value(fields, ["doi"]),
        "title": first_value(fields, ["title"]),
        "pdf_paths": pdf_paths,
        "uri": first_nonempty_field(fields, ["uri", "zotero-select", "zotero-uri"]),
        "source_files": [str(source_path)],
        "synced_at": datetime.now().isoformat(timespec="seconds"),
    }


def merge_bibliography_paper(papers_by_key: dict[str, Paper], paper: Paper) -> None:
    key = normalize_title(paper.title)
    existing = papers_by_key.get(key)
    if existing is None:
        papers_by_key[key] = paper
        return
    existing.occurrences += paper.occurrences
    for alert in paper.alerts:
        if alert not in existing.alerts:
            existing.alerts.append(alert)
    dates = [date for date in [existing.first_seen, existing.last_seen, paper.first_seen, paper.last_seen] if date]
    if dates:
        existing.first_seen = min(dates)
        existing.last_seen = max(dates)
    if len(paper.snippet) > len(existing.snippet):
        existing.snippet = paper.snippet
    if not existing.url and paper.url:
        existing.url = paper.url
    if not existing.authors_source and paper.authors_source:
        existing.authors_source = paper.authors_source
    existing.metadata = {**existing.metadata, **paper.metadata}


def paper_from_bibtex_entry(fields: dict[str, str], source_path: Path) -> Paper | None:
    title = first_value(fields, ["title"])
    if not title:
        return None
    authors = split_authors(first_value(fields, ["author", "editor"]))
    source = first_value(fields, ["journal", "journaltitle", "booktitle", "publisher", "school", "institution"])
    year = year_from_fields(fields, ["year", "date"])
    doi = first_value(fields, ["doi"])
    url = first_value(fields, ["url", "link"]) or doi_url(doi)
    keywords = split_keywords(first_value(fields, ["keywords", "keyword"]))
    abstract = first_value(fields, ["abstract", "annote", "note"])
    snippet = abstract or ("Keywords: " + ", ".join(keywords) if keywords else "Imported from BibTeX.")
    seen_date = file_seen_date(source_path)
    metadata = {
        "bibtex": {
            "entry_type": fields.get("_type", ""),
            "key": fields.get("_key", ""),
            "doi": doi,
            "year": year,
            "source": source,
            "authors": authors,
            "keywords": keywords,
        }
    }
    return Paper(
        id=stable_id(title),
        title=title,
        authors_source=bibliography_authors_source(authors, source, year),
        snippet=snippet,
        url=url,
        scholar_url="",
        first_seen=seen_date,
        last_seen=seen_date,
        alerts=[source_path.name, "BibTeX import"],
        occurrences=1,
        metadata=metadata,
    )


def parse_bibtex_source(bibtex_path: Path) -> tuple[list[Paper], dict[str, int]]:
    papers_by_key: dict[str, Paper] = {}
    counts = Counter()
    for path in bibliography_paths(bibtex_path, ".bib"):
        counts["bibliography_files"] += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        entries = parse_bibtex_entries(text)
        counts["bibliography_entries"] += len(entries)
        for entry in entries:
            paper = paper_from_bibtex_entry(entry, path)
            if paper is None:
                counts["bibliography_skipped_no_title"] += 1
                continue
            merge_bibliography_paper(papers_by_key, paper)
    counts["bibliography_unique_papers"] = len(papers_by_key)
    return list(papers_by_key.values()), dict(counts)


def parse_ris_entries(text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    last_tag = ""
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        tag_match = re.match(r"^([A-Z0-9]{2})\s{2}-\s?(.*)$", raw_line)
        if tag_match:
            tag = tag_match.group(1)
            value = clean_bibliography_value(tag_match.group(2))
            if tag == "TY":
                current = {"TY": value}
            elif tag == "ER":
                if current:
                    entries.append(current)
                current = {}
            elif current:
                existing = current.get(tag)
                if existing is None:
                    current[tag] = value
                elif isinstance(existing, list):
                    existing.append(value)
                else:
                    current[tag] = [existing, value]
            last_tag = tag
        elif current and last_tag:
            continuation = clean_bibliography_value(raw_line)
            existing = current.get(last_tag)
            if isinstance(existing, list) and existing:
                existing[-1] = " ".join([existing[-1], continuation]).strip()
            elif isinstance(existing, str):
                current[last_tag] = " ".join([existing, continuation]).strip()
    if current:
        entries.append(current)
    return entries


def paper_from_ris_entry(fields: dict[str, Any], source_path: Path) -> Paper | None:
    title = first_value(fields, ["TI", "T1", "CT"])
    if not title:
        return None
    authors = coerce_list(fields.get("AU") or fields.get("A1") or fields.get("A2"))
    source = first_value(fields, ["JO", "JF", "JA", "T2", "PB"])
    year = year_from_fields(fields, ["PY", "Y1", "DA"])
    doi = first_value(fields, ["DO"])
    url = first_value(fields, ["UR", "L1", "LK"]) or doi_url(doi)
    keywords = split_keywords(fields.get("KW"))
    abstract = first_value(fields, ["AB", "N2"])
    snippet = abstract or ("Keywords: " + ", ".join(keywords) if keywords else "Imported from RIS.")
    seen_date = file_seen_date(source_path)
    metadata = {
        "ris": {
            "type": first_value(fields, ["TY"]),
            "doi": doi,
            "year": year,
            "source": source,
            "authors": authors,
            "keywords": keywords,
        }
    }
    return Paper(
        id=stable_id(title),
        title=title,
        authors_source=bibliography_authors_source(authors, source, year),
        snippet=snippet,
        url=url,
        scholar_url="",
        first_seen=seen_date,
        last_seen=seen_date,
        alerts=[source_path.name, "RIS import"],
        occurrences=1,
        metadata=metadata,
    )


def parse_ris_source(ris_path: Path) -> tuple[list[Paper], dict[str, int]]:
    papers_by_key: dict[str, Paper] = {}
    counts = Counter()
    for path in bibliography_paths(ris_path, ".ris"):
        counts["bibliography_files"] += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        entries = parse_ris_entries(text)
        counts["bibliography_entries"] += len(entries)
        for entry in entries:
            paper = paper_from_ris_entry(entry, path)
            if paper is None:
                counts["bibliography_skipped_no_title"] += 1
                continue
            merge_bibliography_paper(papers_by_key, paper)
    counts["bibliography_unique_papers"] = len(papers_by_key)
    return list(papers_by_key.values()), dict(counts)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def child_text(element: ET.Element, name: str) -> str:
    for child in list(element):
        if local_name(child.tag) == name:
            return clean_html("".join(child.itertext()))
    return ""


def children_named(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(element) if local_name(child.tag) == name]


def feed_date(value: str) -> str:
    value = value.strip()
    if not value:
        return datetime.now().date().isoformat()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.date().isoformat()
    except ValueError:
        pass
    parsed_email_date = parse_message_date(value)
    if parsed_email_date:
        return parsed_email_date.date().isoformat()
    match = re.search(r"\b(18|19|20|21)\d{2}-\d{2}-\d{2}\b", value)
    if match:
        return match.group(0)
    return datetime.now().date().isoformat()


def is_url(value: str) -> bool:
    return urlparse(value).scheme in {"http", "https"}


def read_feed_text(source: str, timeout: int) -> str:
    source = source.strip()
    if is_url(source):
        request = Request(source, headers={"User-Agent": f"ScholarAlertReader/{__version__}"})
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    return Path(source).expanduser().read_text(encoding="utf-8", errors="replace")


def rss_sources(source: str) -> list[str]:
    source = source.strip()
    if not source:
        raise SystemExit("RSS/Atom source is empty.")
    path = Path(source).expanduser()
    if path.exists():
        if path.is_dir():
            files = sorted(
                item
                for item in path.iterdir()
                if item.is_file() and item.suffix.lower() in {".xml", ".rss", ".atom"}
            )
            if not files:
                raise SystemExit(f"No .xml/.rss/.atom feed files found in directory: {path}")
            return [str(item) for item in files]
        if path.suffix.lower() in {".txt", ".list"}:
            lines: list[str] = []
            for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw_line.strip()
                if not line or line.lstrip().startswith("#"):
                    continue
                line_path = Path(line).expanduser()
                if not is_url(line) and not line_path.is_absolute():
                    line = str(path.parent / line_path)
                lines.append(line)
            if not lines:
                raise SystemExit(f"No feed URLs or paths found in: {path}")
            return lines
        return [str(path)]
    return split_csv(source) or [source]


def atom_link(entry: ET.Element) -> str:
    fallback = ""
    for link in children_named(entry, "link"):
        href = link.attrib.get("href", "").strip()
        rel = link.attrib.get("rel", "alternate")
        if href and rel == "alternate":
            return href
        if href and not fallback:
            fallback = href
    return fallback or child_text(entry, "id")


def feed_authors(entry: ET.Element) -> list[str]:
    authors: list[str] = []
    for author in children_named(entry, "author"):
        name = child_text(author, "name") or clean_html("".join(author.itertext()))
        if name and name not in authors:
            authors.append(name)
    creator = child_text(entry, "creator")
    if creator:
        for part in re.split(r"\s*;\s*|\s*,\s*", creator):
            if part and part not in authors:
                authors.append(part)
    return authors


def paper_from_atom_entry(entry: ET.Element, feed_title: str, source_name: str) -> Paper | None:
    title = child_text(entry, "title")
    if not title:
        return None
    authors = feed_authors(entry)
    summary = child_text(entry, "summary") or child_text(entry, "content")
    published = child_text(entry, "published") or child_text(entry, "updated")
    date = feed_date(published)
    url = atom_link(entry)
    categories = [
        category.attrib.get("term", "").strip()
        for category in children_named(entry, "category")
        if category.attrib.get("term", "").strip()
    ]
    arxiv_id = ""
    if "arxiv.org" in url:
        arxiv_id = re.sub(r"^https?://arxiv\.org/(abs|pdf)/", "", url).replace(".pdf", "")
    source = feed_title or source_name
    metadata_key = "arxiv" if arxiv_id else "feed"
    metadata = {
        metadata_key: {
            "id": arxiv_id or child_text(entry, "id"),
            "published": published,
            "updated": child_text(entry, "updated"),
            "source": source,
            "categories": categories,
            "authors": authors,
        }
    }
    return Paper(
        id=stable_id(title),
        title=title,
        authors_source=bibliography_authors_source(authors, source, date[:4]),
        snippet=summary or "Imported from Atom/RSS feed.",
        url=url,
        scholar_url="",
        first_seen=date,
        last_seen=date,
        alerts=[source, "Atom/RSS import"],
        occurrences=1,
        metadata=metadata,
    )


def paper_from_rss_item(item: ET.Element, feed_title: str, source_name: str) -> Paper | None:
    title = child_text(item, "title")
    if not title:
        return None
    link = child_text(item, "link") or child_text(item, "guid")
    summary = child_text(item, "description") or child_text(item, "summary") or child_text(item, "encoded")
    published = child_text(item, "pubDate") or child_text(item, "date") or child_text(item, "updated")
    date = feed_date(published)
    authors = coerce_list(child_text(item, "author") or child_text(item, "creator"))
    categories = [clean_html("".join(category.itertext())) for category in children_named(item, "category")]
    source = feed_title or source_name
    metadata = {
        "feed": {
            "id": child_text(item, "guid") or link,
            "published": published,
            "source": source,
            "categories": [category for category in categories if category],
            "authors": authors,
        }
    }
    return Paper(
        id=stable_id(title),
        title=title,
        authors_source=bibliography_authors_source(authors, source, date[:4]),
        snippet=summary or "Imported from RSS feed.",
        url=link,
        scholar_url="",
        first_seen=date,
        last_seen=date,
        alerts=[source, "RSS import"],
        occurrences=1,
        metadata=metadata,
    )


def parse_feed_xml(text: str, source_name: str) -> tuple[list[Paper], dict[str, int]]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise SystemExit(f"Cannot parse RSS/Atom feed {source_name}: {exc}") from exc
    papers_by_key: dict[str, Paper] = {}
    counts = Counter()
    root_name = local_name(root.tag).lower()
    if root_name == "feed":
        feed_title = child_text(root, "title") or source_name
        entries = children_named(root, "entry")
        counts["feed_entries"] = len(entries)
        for entry in entries:
            paper = paper_from_atom_entry(entry, feed_title, source_name)
            if paper is None:
                counts["feed_skipped_no_title"] += 1
                continue
            merge_bibliography_paper(papers_by_key, paper)
    else:
        channel = next((child for child in children_named(root, "channel")), root)
        feed_title = child_text(channel, "title") or source_name
        items = children_named(channel, "item") or [item for item in root.iter() if local_name(item.tag) == "item"]
        counts["feed_entries"] = len(items)
        for item in items:
            paper = paper_from_rss_item(item, feed_title, source_name)
            if paper is None:
                counts["feed_skipped_no_title"] += 1
                continue
            merge_bibliography_paper(papers_by_key, paper)
    counts["feed_unique_papers"] = len(papers_by_key)
    return list(papers_by_key.values()), dict(counts)


def parse_rss_source(source: str, timeout: int = 20, limit: int = 0) -> tuple[list[Paper], dict[str, int]]:
    papers_by_key: dict[str, Paper] = {}
    counts = Counter()
    for feed_source in rss_sources(source):
        counts["feed_sources"] += 1
        text = read_feed_text(feed_source, timeout)
        papers, feed_counts = parse_feed_xml(text, feed_source)
        counts.update(feed_counts)
        for paper in papers:
            merge_bibliography_paper(papers_by_key, paper)
    papers = list(papers_by_key.values())
    papers.sort(key=lambda paper: (paper.last_seen, paper.title.lower()), reverse=True)
    if limit > 0:
        papers = papers[:limit]
    counts["feed_unique_papers"] = len(papers_by_key)
    counts["feed_returned_papers"] = len(papers)
    return papers, dict(counts)


def parse_html_attrs(tag: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in re.finditer(r"([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", tag):
        key = match.group(1).lower()
        value = match.group(2).strip().strip("\"'")
        attrs[key] = html.unescape(value)
    return attrs


def web_meta_fields(page_html: str) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for tag in re.findall(r"<meta\b[^>]*>", page_html, flags=re.IGNORECASE | re.DOTALL):
        attrs = parse_html_attrs(tag)
        key = (attrs.get("name") or attrs.get("property") or attrs.get("itemprop") or "").strip().lower()
        content = attrs.get("content", "").strip()
        if key and content:
            fields.setdefault(key, []).append(content)
    title_match = re.search(r"<title\b[^>]*>(.*?)</title>", page_html, flags=re.IGNORECASE | re.DOTALL)
    if title_match:
        title = clean_html(title_match.group(1))
        if title:
            fields.setdefault("html:title", []).append(title)
    return fields


def first_web_value(fields: dict[str, list[str]], names: list[str]) -> str:
    for name in names:
        values = fields.get(name.lower(), [])
        for value in values:
            cleaned = clean_html(str(value))
            if cleaned:
                return cleaned
    return ""


def web_values(fields: dict[str, list[str]], names: list[str]) -> list[str]:
    values: list[str] = []
    for name in names:
        for value in fields.get(name.lower(), []):
            cleaned = clean_html(str(value))
            if cleaned and cleaned not in values:
                values.append(cleaned)
    return values


def jsonld_items(value: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if isinstance(value, dict):
        graph = value.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                items.extend(jsonld_items(item))
        item_type = value.get("@type", "")
        types = item_type if isinstance(item_type, list) else [item_type]
        normalized = {str(item).lower() for item in types}
        if normalized & {"scholarlyarticle", "article", "report", "techarticle"}:
            items.append(value)
    elif isinstance(value, list):
        for item in value:
            items.extend(jsonld_items(item))
    return items


def jsonld_authors(value: Any) -> list[str]:
    if not isinstance(value, list):
        value = [value] if value else []
    authors: list[str] = []
    for item in value:
        if isinstance(item, dict):
            name = clean_html(str(item.get("name", "")))
        else:
            name = clean_html(str(item))
        if name and name not in authors:
            authors.append(name)
    return authors


def jsonld_source(value: dict[str, Any]) -> str:
    for key in ["isPartOf", "publisher", "sourceOrganization"]:
        item = value.get(key)
        if isinstance(item, dict):
            name = clean_html(str(item.get("name", "")))
            if name:
                return name
        elif isinstance(item, str) and item.strip():
            return clean_html(item)
    return ""


def jsonld_text_values(value: Any) -> list[str]:
    values: list[str] = []
    if isinstance(value, list):
        for item in value:
            values.extend(jsonld_text_values(item))
    elif isinstance(value, dict):
        for key in ["value", "name", "@id", "url"]:
            item = value.get(key)
            if item:
                values.extend(jsonld_text_values(item))
                break
    elif value:
        text = clean_html(str(value))
        if text:
            values.append(text)
    return values


def jsonld_to_web_fields(item: dict[str, Any]) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    mapping = {
        "citation_title": ["headline", "name"],
        "citation_abstract": ["abstract", "description"],
        "citation_publication_date": ["datePublished", "dateCreated", "dateModified"],
        "citation_public_url": ["url", "mainEntityOfPage"],
        "citation_doi": ["doi", "identifier"],
    }
    for target, keys in mapping.items():
        for key in keys:
            values = jsonld_text_values(item.get(key))
            if values:
                fields.setdefault(target, []).extend(values)
                break
    for author in jsonld_authors(item.get("author") or item.get("creator")):
        fields.setdefault("citation_author", []).append(author)
    source = jsonld_source(item)
    if source:
        fields.setdefault("citation_journal_title", []).append(source)
    return fields


def paper_from_web_fields(fields: dict[str, list[str]], source_name: str) -> Paper | None:
    title = first_web_value(fields, ["citation_title", "dc.title", "dcterms.title", "og:title", "twitter:title", "html:title"])
    if not title:
        return None
    authors = web_values(fields, ["citation_author", "dc.creator", "dcterms.creator", "author"])
    source = first_web_value(fields, ["citation_journal_title", "citation_conference_title", "dc.source", "og:site_name"])
    date_value = first_web_value(fields, ["citation_publication_date", "citation_date", "dc.date", "dcterms.date", "article:published_time"])
    date = feed_date(date_value)
    doi = normalize_doi(first_web_value(fields, ["citation_doi", "dc.identifier", "doi"]))
    url = first_web_value(fields, ["citation_public_url", "citation_fulltext_html_url", "og:url", "twitter:url"]) or doi_url(doi) or source_name
    snippet = first_web_value(fields, ["citation_abstract", "dc.description", "dcterms.description", "description", "og:description", "twitter:description"])
    keywords = web_values(fields, ["citation_keywords", "keywords", "dc.subject", "article:tag"])
    if not snippet and keywords:
        snippet = "Keywords: " + ", ".join(keywords)
    metadata = {
        "web": {
            "source": source_name,
            "doi": doi,
            "published": date_value,
            "authors": authors,
            "keywords": keywords,
        }
    }
    return Paper(
        id=stable_id(title),
        title=title,
        authors_source=bibliography_authors_source(authors, source or source_name, date[:4]),
        snippet=snippet or "Imported from webpage metadata.",
        url=url,
        scholar_url="",
        first_seen=date,
        last_seen=date,
        alerts=[source or source_name, "Web metadata import"],
        occurrences=1,
        metadata=metadata,
    )


def parse_web_page(page_html: str, source_name: str) -> tuple[list[Paper], dict[str, int]]:
    papers_by_key: dict[str, Paper] = {}
    counts = Counter()
    meta_fields = web_meta_fields(page_html)
    jsonld_count = 0
    for raw_script in re.findall(
        r"<script\b[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        raw_json = html.unescape(raw_script).strip()
        if not raw_json:
            continue
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            counts["web_jsonld_parse_errors"] += 1
            continue
        for item in jsonld_items(parsed):
            jsonld_count += 1
            paper = paper_from_web_fields({**meta_fields, **jsonld_to_web_fields(item)}, source_name)
            if paper is None:
                counts["web_skipped_no_title"] += 1
                continue
            merge_bibliography_paper(papers_by_key, paper)
    if not papers_by_key:
        paper = paper_from_web_fields(meta_fields, source_name)
        if paper:
            merge_bibliography_paper(papers_by_key, paper)
        else:
            counts["web_skipped_no_title"] += 1
    counts["web_jsonld_items"] = jsonld_count
    counts["web_unique_papers"] = len(papers_by_key)
    return list(papers_by_key.values()), dict(counts)


def read_web_text(source: str, timeout: int) -> str:
    return read_feed_text(source, timeout)


def web_sources(source: str) -> list[str]:
    source = source.strip()
    if not source:
        raise SystemExit("Web source is empty.")
    path = Path(source).expanduser()
    if path.exists():
        if path.is_dir():
            files = sorted(
                item
                for item in path.iterdir()
                if item.is_file() and item.suffix.lower() in {".html", ".htm"}
            )
            if not files:
                raise SystemExit(f"No .html/.htm files found in directory: {path}")
            return [str(item) for item in files]
        if path.suffix.lower() in {".txt", ".list"}:
            lines: list[str] = []
            for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw_line.strip()
                if not line or line.lstrip().startswith("#"):
                    continue
                line_path = Path(line).expanduser()
                if not is_url(line) and not line_path.is_absolute():
                    line = str(path.parent / line_path)
                lines.append(line)
            if not lines:
                raise SystemExit(f"No webpage URLs or paths found in: {path}")
            return lines
        return [str(path)]
    return split_csv(source) or [source]


def parse_web_source(source: str, timeout: int = 20, limit: int = 0) -> tuple[list[Paper], dict[str, int]]:
    papers_by_key: dict[str, Paper] = {}
    counts = Counter()
    for web_source in web_sources(source):
        counts["web_sources"] += 1
        text = read_web_text(web_source, timeout)
        papers, page_counts = parse_web_page(text, web_source)
        counts.update(page_counts)
        for paper in papers:
            merge_bibliography_paper(papers_by_key, paper)
    papers = list(papers_by_key.values())
    papers.sort(key=lambda paper: (paper.last_seen, paper.title.lower()), reverse=True)
    if limit > 0:
        papers = papers[:limit]
    counts["web_unique_papers"] = len(papers_by_key)
    counts["web_returned_papers"] = len(papers)
    return papers, dict(counts)


def arxiv_api_url(query: str, limit: int, sort_by: str = "submittedDate", sort_order: str = "descending") -> str:
    params = {
        "search_query": query,
        "start": "0",
        "max_results": str(max(1, int(limit or 50))),
        "sortBy": sort_by,
        "sortOrder": sort_order,
    }
    return "https://export.arxiv.org/api/query?" + urlencode(params)


def parse_arxiv_source(query: str, limit: int = 50, timeout: int = 20) -> tuple[list[Paper], dict[str, int]]:
    url = arxiv_api_url(query, limit)
    papers, counts = parse_rss_source(url, timeout=timeout, limit=limit)
    counts["arxiv_query"] = query
    counts["arxiv_api_url"] = url
    return papers, counts


def apple_script_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def fetch_mail_app_scholar_alerts(out_dir: Path, since_days: int | None, limit: int, timeout_seconds: int = 600) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    since_value = int(since_days or 0)
    limit_value = int(limit or 0)
    timeout_value = max(1, int(timeout_seconds or 600))
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

with timeout of {timeout_value} seconds
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
    timeout_seconds: int = 600,
) -> tuple[list[Paper], dict[str, int]]:
    with tempfile.TemporaryDirectory(prefix="scholar-mail-app-") as tmp:
        eml_dir = Path(tmp)
        exported = fetch_mail_app_scholar_alerts(eml_dir, since_days, mail_limit, timeout_seconds=timeout_seconds)
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


def python_module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except ModuleNotFoundError:
        return False


def gmail_dependencies_available() -> bool:
    return all(
        python_module_available(module_name)
        for module_name in [
            "googleapiclient",
            "google.oauth2.credentials",
            "google_auth_oauthlib.flow",
        ]
    )


def mail_app_available() -> bool:
    return sys.platform == "darwin" and shutil.which("osascript") is not None


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
    library: list[Paper] | None = None,
) -> list[Paper]:
    for paper in papers:
        score_paper(paper, profile, boost, feedback, library)
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
    row["metadata"] = json.dumps(paper.metadata, ensure_ascii=False) if paper.metadata else ""
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
        "metadata",
        "is_new",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for paper in papers:
            writer.writerow(paper_to_row(paper))


def counts_by_tier(papers: list[Paper]) -> Counter:
    return Counter(p.tier for p in papers)


def source_item_count(summary: dict[str, Any]) -> int:
    counts = summary.get("source_counts", {})
    if not isinstance(counts, dict):
        return 0
    for key in [
        "scholar_messages",
        "bibliography_entries",
        "feed_entries",
        "web_sources",
        "gmail_raw_messages",
        "mail_app_exported",
        "messages",
    ]:
        value = counts.get(key)
        if isinstance(value, int):
            return value
    return 0


def empty_run_diagnosis(summary: dict[str, Any]) -> dict[str, Any]:
    papers_in_digest = int(summary.get("papers_in_digest") or 0)
    if papers_in_digest > 0:
        return {}

    counts = summary.get("source_counts", {})
    counts = counts if isinstance(counts, dict) else {}
    source_items = int(summary.get("source_items") or source_item_count(summary))
    unique_before = int(summary.get("unique_papers_before_state_filter") or 0)
    filtered_seen = int(summary.get("seen_papers_filtered_out") or 0)
    source = str(summary.get("source", "the configured source"))

    if summary.get("only_new") and unique_before > 0:
        return {
            "reason": "all_seen",
            "title": "No new papers after the seen-state filter",
            "summary": (
                f"The source produced {unique_before} unique papers, but {filtered_seen or unique_before} "
                "were already in the foundation/seen state."
            ),
            "next_steps": [
                "This is normal after a foundation run or when alerts repeat the same papers.",
                "To inspect recent already-seen papers, run `./review_recent.sh` or rerun with `MODE=run NO_KB_UPDATE=1`.",
                "If this is your first real run, build the baseline intentionally with `MODE=foundation ./run_reader.sh`, then use daily mode afterward.",
            ],
        }

    if unique_before == 0 and source_items > 0:
        next_steps = [
            "Run `./source_check.sh --source auto --live` to confirm the selected source and item counts.",
            "Open the source file/feed/email and confirm it contains scholarly paper titles, not only notification text or unrelated mail.",
            "If this is a Scholar Alert email source, Google may have changed the alert HTML; generate `./support_bundle.sh` and report sanitized counts, not raw mail.",
        ]
        if int(counts.get("messages", 0)) > 0 and int(counts.get("scholar_messages", 0)) == 0:
            next_steps.insert(1, "The mailbox had messages, but none from `scholaralerts-noreply@google.com`; check the folder, Gmail query, or exported mbox.")
        if int(counts.get("scholar_messages", 0)) > 0 and int(counts.get("entries", 0)) == 0:
            next_steps.insert(1, "Scholar Alert messages were found, but no paper entries matched the parser; keep a sanitized sample for parser maintenance.")
        if int(counts.get("bibliography_entries", 0)) > 0 and int(counts.get("bibliography_unique_papers", 0)) == 0:
            next_steps.insert(1, "The bibliography file had entries but no usable titles; export BibTeX/RIS again with title fields included.")
        if int(counts.get("web_sources", 0)) > 0 and int(counts.get("web_unique_papers", 0)) == 0:
            next_steps.insert(1, "The webpage source was read, but no citation metadata/JSON-LD title was found; use article pages or RSS feeds instead of search-result pages.")
        return {
            "reason": "parsed_no_papers",
            "title": "Source was readable, but no paper records were parsed",
            "summary": f"`{source}` returned {source_items} source items, but none became paper records.",
            "next_steps": next_steps,
        }

    if unique_before == 0 and source_items == 0:
        return {
            "reason": "source_no_items",
            "title": "Source returned no items",
            "summary": f"`{source}` did not return Scholar Alert messages, bibliography entries, feed entries, or webpage sources.",
            "next_steps": [
                "Run `./source_check.sh --source auto --live` before expecting daily digests.",
                "Check `reader.env`, source paths, Gmail OAuth token, Gmail query, feed URLs, arXiv query, and any `SINCE_DAYS` window.",
                "Run `./demo_reader.sh` or `./demo_sources.sh` to verify the installation with bundled non-private data.",
            ],
        }

    return {
        "reason": "empty_unknown",
        "title": "No papers were written",
        "summary": "The run completed but did not produce paper records. Inspect `summary.json` and run source-check live.",
        "next_steps": [
            "Run `./source_check.sh --source auto --live`.",
            "Open `summary.json` and compare `source_counts`, `unique_papers_before_state_filter`, and `papers_in_digest`.",
        ],
    }


def empty_run_markdown(summary: dict[str, Any]) -> list[str]:
    diagnosis = summary.get("empty_run_diagnosis")
    if not isinstance(diagnosis, dict) or not diagnosis:
        diagnosis = empty_run_diagnosis(summary)
    if not diagnosis:
        return []
    lines = [
        "## No-paper diagnosis",
        "",
        f"**{diagnosis.get('title', 'No papers were written')}**",
        "",
        str(diagnosis.get("summary", "")),
        "",
        "Next steps:",
        "",
    ]
    for step in diagnosis.get("next_steps", []):
        lines.append(f"- {step}")
    lines.append("")
    return lines


def limits(profile: dict[str, Any]) -> dict[str, int]:
    configured = profile.get("limits", {})
    return {
        "must_read": int(configured.get("must_read", 8)),
        "skim": int(configured.get("skim", 15)),
        "deep_read": int(configured.get("deep_read", 5)),
    }


def papers_for_tier(papers: list[Paper], tier: str) -> list[Paper]:
    return [paper for paper in papers if paper.tier == tier]


def project_dir_from_output(path: Path) -> Path | None:
    out_dir = path.parent.resolve()
    if out_dir.parent.name == "reader_out":
        return out_dir.parent.parent
    return None


def feedback_commands(path: Path, summary: dict[str, Any]) -> list[str]:
    papers_json = path.parent.resolve() / "papers.json"
    project_dir = project_dir_from_output(path)
    if project_dir and (project_dir / "serve_reader.sh").exists() and (project_dir / "feedback_reader.sh").exists():
        serve_prefix = f"PAPERS_JSON={shlex.quote(str(papers_json))} {shlex.quote(str(project_dir / 'serve_reader.sh'))}"
        feedback_prefix = f"PAPERS_JSON={shlex.quote(str(papers_json))} {shlex.quote(str(project_dir / 'feedback_reader.sh'))}"
    else:
        profile_arg = shlex.quote(str(summary.get("profile", "<profile.json>")))
        kb_arg = shlex.quote(str(summary.get("knowledge_base_dir", "knowledge_base")))
        script_arg = shlex.quote(str(skill_wrapper_path()))
        papers_arg = shlex.quote(str(papers_json))
        serve_prefix = f"python3 {script_arg} serve --profile {profile_arg} --papers-json {papers_arg} --kb-dir {kb_arg} --open"
        feedback_prefix = f"python3 {script_arg} feedback --profile {profile_arg} --papers-json {papers_arg}"

    return [
        serve_prefix,
        f"{feedback_prefix} --paper-id <ID> --mark interested --more-like-this",
        f"{feedback_prefix} --paper-id <ID> --mark archive --less-like-this",
    ]


def recent_review_command(path: Path) -> str | None:
    project_dir = project_dir_from_output(path)
    if project_dir and (project_dir / "review_recent.sh").exists():
        return shlex.quote(str(project_dir / "review_recent.sh"))
    return None


def write_digest(path: Path, papers: list[Paper], profile: dict[str, Any], summary: dict[str, Any]) -> None:
    lim = limits(profile)
    tier_counts = counts_by_tier(papers)
    commands = feedback_commands(path, summary)
    lines: list[str] = [
        "# Scholar Alert 文献分诊",
        "",
        f"- Profile: {profile.get('name', 'unnamed')}",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Papers in digest: {len(papers)}",
        f"- Must read: {tier_counts.get('Must read', 0)}; Skim: {tier_counts.get('Skim', 0)}; Archive: {tier_counts.get('Archive', 0)}",
        f"- Source items: {source_item_count(summary)}",
        f"- Feedback file: {summary.get('feedback_file', '')}",
        "",
        "## 反馈入口",
        "",
        "Use the `ID` shown under each paper to tune future runs:",
        "",
        "```bash",
        *commands,
        "```",
        "",
    ]

    recent_cmd = recent_review_command(path)
    if not papers:
        lines.extend(empty_run_markdown(summary))
        if recent_cmd:
            lines.extend(["", "To review recent alerts again for testing:", "", "```bash", recent_cmd, "```"])
        lines.append("")

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
        f'<div class="stat">Source items: {source_item_count(summary)}</div>',
        "</div>",
        "</header>",
        "<main>",
    ]

    if questions:
        parts.extend(['<section class="questions">'])
        for question in questions:
            parts.append(f'<div class="question">{html.escape(str(question))}</div>')
        parts.append("</section>")

    commands = feedback_commands(path, summary)
    parts.extend(
        [
            '<section class="feedback-help">',
            "<strong>反馈入口</strong>",
            '<div class="meta">Use a paper ID from the badges below to tune future runs.</div>',
            *(f"<code>{html.escape(command)}</code>" for command in commands),
            "</section>",
        ]
    )

    recent_cmd = recent_review_command(path)
    if not papers:
        diagnosis = summary.get("empty_run_diagnosis")
        if not isinstance(diagnosis, dict) or not diagnosis:
            diagnosis = empty_run_diagnosis(summary)
        parts.extend(
            [
                '<section class="feedback-help">',
                f"<strong>{html.escape(str(diagnosis.get('title', 'No papers were written')))}</strong>",
                f'<div class="meta">{html.escape(str(diagnosis.get("summary", "")))}</div>',
            ]
        )
        for step in diagnosis.get("next_steps", []):
            parts.append(f'<div class="meta">- {html.escape(str(step))}</div>')
        if recent_cmd:
            parts.append(f"<code>{html.escape(recent_cmd)}</code>")
        parts.append("</section>")

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
    directions = [tag for tag in paper.tags if tag not in {"adaptive", "boost", "feedback", "watchlist"}]
    if not directions:
        directions = ["uncategorized"]
    return sorted(set(directions))


def paper_md_line(paper: Paper) -> str:
    terms = ", ".join(paper.matched_terms[:8]) if paper.matched_terms else "no matched terms"
    metadata_note = ""
    openalex = paper.metadata.get("openalex") if paper.metadata else None
    if isinstance(openalex, dict) and openalex.get("cited_by_count") is not None:
        metadata_note = f"; cited by {openalex.get('cited_by_count')}"
    return (
        f"- **[{paper.title}]({paper.url})** "
        f"({paper.score}, {paper.tier}; {terms}{metadata_note}) - {paper.authors_source}"
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
        "- `feedback.json` stores explicit user paper marks and more-like-this / less-like-this ranking signals; later runs can also use retained/interested papers as adaptive ranking seeds.",
        f"- `library.json` is the cumulative retained library for tiers: {', '.join(settings['foundation_tiers'])}.",
        "- `foundation.md` is rendered from cumulative `library.json`, grouped by direction.",
        f"- `interested.md` is rendered from cumulative `library.json` for tiers: {', '.join(settings['interested_tiers'])}.",
        "- `daily_additions.md` keeps the latest new-paper-only additions.",
        "- `reading_plan.md` and `reading_plan.html` prioritize retained and recent papers for the next reading session.",
        "- `runs/` keeps timestamped reports from individual runs.",
        "",
        "## Files",
        "",
        "- [foundation.md](foundation.md)",
        "- [interested.md](interested.md)",
        "- [library.json](library.json)",
        "- [feedback.json](feedback.json)",
        "- [papers/](papers/)",
        "- [directions/](directions/)",
        "- [weekly_review.md](weekly_review.md)",
        "- [reading_plan.md](reading_plan.md)",
        "- [reading_plan.html](reading_plan.html)",
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


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "uncategorized"


def metadata_lines(paper: Paper) -> list[str]:
    lines: list[str] = []
    zotero = paper.metadata.get("zotero") if paper.metadata else None
    openalex = paper.metadata.get("openalex") if paper.metadata else None
    crossref = paper.metadata.get("crossref") if paper.metadata else None
    if isinstance(zotero, dict):
        lines.extend(
            [
                "## Zotero",
                "",
                f"- Citation key: {zotero.get('citation_key', '')}",
                f"- Item key: {zotero.get('item_key', '')}",
                f"- DOI: {zotero.get('doi', '')}",
            ]
        )
        for path in coerce_list(zotero.get("pdf_paths")):
            lines.append(f"- Local PDF: {path}")
        lines.append("")
    if isinstance(openalex, dict):
        lines.extend(
            [
                "## OpenAlex",
                "",
                f"- Year: {openalex.get('publication_year', '')}",
                f"- Cited by: {openalex.get('cited_by_count', '')}",
                f"- Source: {openalex.get('source', '')}",
                f"- DOI: {openalex.get('doi', '')}",
                f"- PDF: {openalex.get('pdf_url', '')}",
                "",
            ]
        )
    if isinstance(crossref, dict):
        lines.extend(
            [
                "## Crossref",
                "",
                f"- DOI: {crossref.get('doi', '')}",
                f"- Journal/source: {crossref.get('container_title', '')}",
                f"- Publisher: {crossref.get('publisher', '')}",
                f"- Referenced by: {crossref.get('is_referenced_by_count', '')}",
                "",
            ]
        )
    return lines


def write_kb_paper_pages(kb_dir: Path, papers: list[Paper]) -> None:
    paper_dir = kb_dir / "papers"
    paper_dir.mkdir(parents=True, exist_ok=True)
    for paper in papers:
        lines = [
            f"# {paper.title}",
            "",
            f"- ID: {paper.id}",
            f"- Tier: {paper.tier}",
            f"- Score: {paper.score}",
            f"- Link: {paper.url}",
            f"- Source: {paper.authors_source}",
            f"- First seen: {paper.first_seen}",
            f"- Last seen: {paper.last_seen}",
            f"- Directions: {', '.join(paper_directions(paper))}",
            f"- Matched: {', '.join(paper.matched_terms)}",
            "",
            "## Snippet",
            "",
            paper.snippet or "No snippet available.",
            "",
            "## Why It Was Ranked This Way",
            "",
        ]
        lines.extend(f"- {reason}" for reason in paper.reasons[:8])
        lines.append("")
        lines.extend(metadata_lines(paper))
        lines.extend(
            [
                "## Notes",
                "",
                "- ",
                "",
            ]
        )
        (paper_dir / f"{paper.id}.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_kb_direction_pages(kb_dir: Path, papers: list[Paper], profile: dict[str, Any]) -> None:
    direction_dir = kb_dir / "directions"
    direction_dir.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[Paper]] = {}
    for paper in papers:
        for direction in paper_directions(paper):
            grouped.setdefault(direction, []).append(paper)

    index_lines = ["# Directions", ""]
    for direction in sorted(grouped):
        filename = f"{slugify(direction)}.md"
        items = sorted(grouped[direction], key=lambda p: (-p.score, p.title.lower()))
        index_lines.append(f"- [{direction}]({filename}) ({len(items)})")
        lines = [
            f"# {direction}",
            "",
            f"Profile: {profile.get('name', 'unnamed')}",
            "",
        ]
        for paper in items:
            lines.append(paper_md_line(paper) + f" [notes](../papers/{paper.id}.md)")
        (direction_dir / filename).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    if not grouped:
        index_lines.append("No retained directions yet.")
    (direction_dir / "index.md").write_text("\n".join(index_lines).rstrip() + "\n", encoding="utf-8")


def write_weekly_review(kb_dir: Path, papers: list[Paper], profile: dict[str, Any], days: int = 7) -> None:
    from .weekly import render_weekly_review

    records = [asdict(paper) for paper in papers]
    (kb_dir / "weekly_review.md").write_text(
        render_weekly_review(records, profile, days=days),
        encoding="utf-8",
    )


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


def inline_markdown_to_html(value: str) -> str:
    escaped = html.escape(value)

    def link_repl(match: re.Match[str]) -> str:
        label = match.group(1)
        url = html.escape(match.group(2), quote=True)
        return f'<a href="{url}">{label}</a>'

    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_repl, escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def markdown_to_basic_html(markdown_text: str, title: str) -> str:
    body: list[str] = []
    in_ul = False
    in_ol = False
    in_code = False
    code_lines: list[str] = []

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            body.append("</ul>")
            in_ul = False
        if in_ol:
            body.append("</ol>")
            in_ol = False

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("```"):
            if in_code:
                body.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
                code_lines = []
                in_code = False
            else:
                close_lists()
                in_code = True
            continue
        if in_code:
            code_lines.append(raw_line)
            continue
        if not line.strip():
            close_lists()
            continue
        if line.startswith("### "):
            close_lists()
            body.append(f"<h3>{inline_markdown_to_html(line[4:])}</h3>")
            continue
        if line.startswith("## "):
            close_lists()
            body.append(f"<h2>{inline_markdown_to_html(line[3:])}</h2>")
            continue
        if line.startswith("# "):
            close_lists()
            body.append(f"<h1>{inline_markdown_to_html(line[2:])}</h1>")
            continue
        ordered = re.match(r"^\d+\.\s+(.*)$", line)
        if ordered:
            if in_ul:
                body.append("</ul>")
                in_ul = False
            if not in_ol:
                body.append("<ol>")
                in_ol = True
            body.append(f"<li>{inline_markdown_to_html(ordered.group(1))}</li>")
            continue
        bullet = re.match(r"^\s*-\s+(.*)$", line)
        if bullet:
            if in_ol:
                body.append("</ol>")
                in_ol = False
            if not in_ul:
                body.append("<ul>")
                in_ul = True
            body.append(f"<li>{inline_markdown_to_html(bullet.group(1))}</li>")
            continue
        close_lists()
        body.append(f"<p>{inline_markdown_to_html(line)}</p>")
    if in_code:
        body.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
    close_lists()
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{html.escape(title)}</title>",
            "<style>",
            "body{margin:0;background:#f6f8fb;color:#16202d;font:16px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}",
            "main{max-width:980px;margin:0 auto;padding:34px 24px 64px}",
            "h1{font-size:34px;margin:0 0 18px}h2{font-size:24px;margin:34px 0 12px;border-top:1px solid #d8e0eb;padding-top:22px}h3{font-size:18px;margin:22px 0 10px}",
            "p,li{color:#334256}ul,ol{background:#fff;border:1px solid #d8e0eb;border-radius:10px;padding:14px 24px;margin:12px 0}li{margin:7px 0}",
            "a{color:#145bd7;text-decoration:none}a:hover{text-decoration:underline}code{background:#eef3f9;border:1px solid #d9e2ef;border-radius:5px;padding:1px 5px}",
            "pre{background:#0f1724;color:#e7eef8;border-radius:10px;padding:16px;overflow:auto}pre code{background:transparent;border:0;color:inherit;padding:0}",
            "</style>",
            "</head>",
            "<body><main>",
            *body,
            "</main></body></html>",
        ]
    )


def write_markdown_html(markdown_path: Path, html_path: Path, title: str) -> Path:
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(markdown_to_basic_html(markdown_path.read_text(encoding="utf-8"), title), encoding="utf-8")
    return html_path


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
        write_kb_paper_pages(kb_dir, library)
        write_kb_direction_pages(kb_dir, library, profile)
        write_weekly_review(kb_dir, library, profile)
    if summary.get("mode") == "daily":
        write_kb_daily_additions(kb_dir, papers, profile)
    write_kb_archive_index(kb_dir, papers, profile)
    write_run_snapshot(kb_dir, papers, summary)


def write_auto_reading_plan(kb_dir: Path, out_dir: Path, profile: dict[str, Any], limit: int = 10) -> tuple[Path, Path]:
    from .copilot import render_reading_plan

    records = merged_paper_records(kb_dir, out_dir / "papers.json")
    feedback = load_feedback(default_feedback_file(kb_dir))
    output = kb_dir / "reading_plan.md"
    write_report(
        output,
        render_reading_plan(
            records,
            profile,
            feedback=feedback,
            limit=limit,
            full_text_ids=available_full_text_ids(kb_dir),
        ),
    )
    html_output = write_markdown_html(output, kb_dir / "reading_plan.html", "Scholar Alert Reading Plan")
    return output, html_output


def write_outputs(
    out_dir: Path,
    kb_dir: Path,
    papers: list[Paper],
    profile: dict[str, Any],
    summary: dict[str, Any],
    update_knowledge_base: bool = True,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    save_json(out_dir / "papers.json", [asdict(paper) for paper in papers])
    write_csv(out_dir / "papers.csv", papers)
    write_digest(out_dir / "digest.md", papers, profile, summary)
    write_html_digest(out_dir / "digest.html", papers, profile, summary)
    write_deep_read_queue(out_dir / "deep_read_queue.md", papers, profile)
    if update_knowledge_base:
        summary["knowledge_base_updated"] = True
        write_knowledge_base(kb_dir, papers, profile, summary)
        reading_plan, reading_plan_html = write_auto_reading_plan(kb_dir, out_dir, profile)
        summary["reading_plan"] = str(reading_plan)
        summary["reading_plan_html"] = str(reading_plan_html)
    else:
        summary["knowledge_base_updated"] = False
        summary["library_papers"] = len(load_paper_library(kb_dir))
        summary["library_additions"] = 0
        summary["reading_plan"] = ""
        summary["reading_plan_html"] = ""
    save_json(out_dir / "summary.json", summary)


def init_profile(profile_path: Path, force: bool, template: str | Path | None = None) -> None:
    source = copy_profile_template(profile_path, template, force)
    print(f"Profile written: {profile_path}")
    print(f"Template: {source}")


def shell_double_default(value: Path | str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$")


def skill_wrapper_path() -> Path:
    return SCRIPT_DIR.parent / "scripts" / "scholar_reader.py"


def generated_script_header() -> str:
    return "#!/usr/bin/env bash\nset -euo pipefail\n\n"


def project_script_common(project_dir: Path, profile_path: Path, kb_dir: Path) -> str:
    return "\n".join(
        [
            f"PROJECT_DIR=\"${{PROJECT_DIR:-{shell_double_default(project_dir)}}}\"",
            f"PROJECT_ENV=\"${{PROJECT_ENV:-$PROJECT_DIR/{PROJECT_ENV_NAME}}}\"",
            'if [[ -f "$PROJECT_ENV" ]]; then',
            '  while IFS= read -r config_line; do',
            '    [[ "$config_line" =~ ^[[:space:]]*(#|$) ]] && continue',
            '    config_line="${config_line#export }"',
            '    config_key="${config_line%%=*}"',
            '    if [[ "$config_key" =~ ^[A-Z0-9_]+$ && -z "${!config_key+x}" ]]; then',
            '      eval "export $config_line"',
            "    fi",
            '  done < "$PROJECT_ENV"',
            "fi",
            f"PROFILE_PATH=\"${{PROFILE_PATH:-{shell_double_default(profile_path)}}}\"",
            f"KB_DIR=\"${{KB_DIR:-{shell_double_default(kb_dir)}}}\"",
            f"SKILL_SCRIPT=\"${{SKILL_SCRIPT:-{shell_double_default(skill_wrapper_path())}}}\"",
            f"PYTHON_FALLBACK=\"${{PYTHON_FALLBACK:-{shell_double_default(sys.executable)}}}\"",
            'SKILL_MODULE="${SKILL_MODULE:-scholar_alert_reader}"',
            'if [[ -z "${PYTHON_BIN:-}" ]]; then',
            '  if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then',
            '    PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"',
            '  elif [[ -x "$PYTHON_FALLBACK" ]]; then',
            '    PYTHON_BIN="$PYTHON_FALLBACK"',
            "  else",
            '    PYTHON_BIN="python3"',
            "  fi",
            "fi",
            'if [[ -f "$SKILL_SCRIPT" ]]; then',
            '  SKILL_CMD=("$PYTHON_BIN" "$SKILL_SCRIPT")',
            "else",
            '  SKILL_CMD=("$PYTHON_BIN" -m "$SKILL_MODULE")',
            "fi",
            "",
        ]
    )


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    try:
        os.chmod(path, 0o755)
    except OSError:
        pass


def project_env_path(project_dir: Path) -> Path:
    return project_dir / PROJECT_ENV_NAME


def env_quote(value: str | Path | int | bool) -> str:
    if isinstance(value, bool):
        return shlex.quote("1" if value else "0")
    return shlex.quote(str(value).replace("\n", " ").strip())


def read_project_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    assignment_re = re.compile(r"^(?:export\s+)?([A-Z0-9_]+)=(.*)$")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = assignment_re.match(line)
        if not match:
            continue
        key, raw_value = match.groups()
        try:
            parsed = shlex.split(raw_value, comments=False, posix=True)
        except ValueError:
            parsed = []
        values[key] = parsed[0] if parsed else raw_value.strip().strip("'\"")
    return values


SAFE_ENV_VALUE_KEYS = {
    "ARXIV_QUERY",
    "MODE",
    "SCHEDULE_DAYS",
    "SCHEDULE_TIME",
    "SCHEDULE_TIMEZONE",
    "SOURCE",
}

PRIVATE_ENV_VALUE_KEYS = {
    "BIBTEX_PATH",
    "GMAIL_CREDENTIALS",
    "GMAIL_TOKEN",
    "MBOX_PATH",
    "OBSIDIAN_EXPORT_DIR",
    "RIS_PATH",
    "RSS_SOURCE",
    "WEB_SOURCE",
    "ZOTERO_BIBTEX_PATH",
    "ZOTERO_OUTPUT_DIR",
}


def safe_display_path(value: str | Path, project_dir: Path | None = None) -> str:
    text_value = str(value).strip()
    if not text_value:
        return ""
    if is_url(text_value):
        return "<url configured>"
    path = Path(text_value).expanduser()
    try:
        resolved = path.resolve(strict=False)
    except Exception:
        resolved = path
    if project_dir:
        try:
            project_resolved = project_dir.expanduser().resolve(strict=False)
            relative = resolved.relative_to(project_resolved)
            return "<project>" if str(relative) == "." else f"<project>/{relative}"
        except Exception:
            pass
    try:
        home = Path.home().resolve(strict=False)
        relative_home = resolved.relative_to(home)
        if len(relative_home.parts) <= 2:
            return f"~/{relative_home}"
        return f"~/.../{relative_home.name}"
    except Exception:
        pass
    if resolved.name:
        return f"<external>/{resolved.name}"
    return "<external path>"


def path_status(value: str, project_dir: Path | None = None) -> str:
    if not value:
        return "not configured"
    if is_url(value):
        return "url configured"
    path = Path(value).expanduser()
    marker = "exists" if path.exists() else "missing"
    return f"{safe_display_path(path, project_dir)} ({marker})"


def sanitize_report_line(line: str, project_dir: Path | None = None) -> str:
    value = line
    if project_dir:
        value = value.replace(str(project_dir.expanduser()), "<project>")
        try:
            value = value.replace(str(project_dir.expanduser().resolve(strict=False)), "<project>")
        except Exception:
            pass
    home = str(Path.home())
    value = value.replace(home, "~")
    value = re.sub(r"file://\S+", "<file-url>", value)
    value = re.sub(r"https?://\S+", "<url>", value)
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "<email>", value)
    value = re.sub(r"(?<![\w<])/(?:[^`\s:;,)]+/?)+", "<path>", value)
    value = re.sub(r"~/(?:[^`\s:;,)]+/?)+", "~/.../<path>", value)
    return value


def support_env_value(key: str, value: str, project_dir: Path) -> str:
    if key in SAFE_ENV_VALUE_KEYS:
        return value or "not configured"
    if key in PRIVATE_ENV_VALUE_KEYS or any(token in key for token in ["TOKEN", "CREDENTIAL", "SECRET", "PASSWORD"]):
        return path_status(value, project_dir)
    return "<configured>" if value else "not configured"


def file_count(path: Path, pattern: str = "*") -> int:
    if not path.exists() or not path.is_dir():
        return 0
    return sum(1 for item in path.glob(pattern) if item.exists())


def json_summary(path: Path) -> str:
    if not path.exists():
        return "missing"
    try:
        data = load_json(path)
    except Exception as exc:
        return f"invalid JSON: {exc}"
    if isinstance(data, list):
        return f"{len(data)} list items"
    if isinstance(data, dict):
        if "seen_ids" in data and isinstance(data.get("seen_ids"), list):
            return f"{len(data['seen_ids'])} seen ids"
        if "papers" in data and isinstance(data.get("papers"), dict):
            return f"{len(data['papers'])} paper feedback records"
        return f"{len(data)} object keys"
    return type(data).__name__


def sanitized_file_excerpt(path: Path, project_dir: Path, max_lines: int = 60) -> list[str]:
    if not path.exists():
        return [f"- Missing: `{safe_display_path(path, project_dir)}`"]
    lines = [f"- Source: `{safe_display_path(path, project_dir)}`", ""]
    try:
        raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        return lines + [f"- Could not read report: {exc}"]
    for raw_line in raw_lines[:max_lines]:
        lines.append(sanitize_report_line(raw_line, project_dir))
    if len(raw_lines) > max_lines:
        lines.append(f"... truncated after {max_lines} lines ...")
    return lines


def render_support_bundle(args: argparse.Namespace) -> str:
    project_dir = args.project_dir.expanduser().resolve(strict=False)
    profile = (args.profile or project_dir / "profiles" / "research_profile.json").expanduser()
    kb_dir = (args.kb_dir or project_dir / "knowledge_base").expanduser()
    out_dir = (args.out_dir or project_dir / "reader_out" / "daily").expanduser()
    env_file = (args.env_file or project_dir / PROJECT_ENV_NAME).expanduser()
    source_check = (args.source_check or project_dir / "SOURCE_CHECK.md").expanduser()
    doctor_report = (args.doctor_report or project_dir / "DOCTOR.md").expanduser()
    summary_json = out_dir / "summary.json"

    lines = [
        "# Scholar Alert Reader Support Bundle",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Version: {__version__}",
        f"- Python: {sys.version.split()[0]}",
        f"- Platform: {sys.platform}",
        f"- Project: `{safe_display_path(project_dir, project_dir)}`",
        "",
        "## Privacy Boundary",
        "",
        "This report is intended for public GitHub issues after review. It does not include raw emails, OAuth JSON contents, Gmail token contents, raw bibliography exports, feedback contents, or generated knowledge-base text.",
        "Paths and URLs are redacted to project-relative or generic placeholders. Review this file before posting it publicly.",
        "",
        "## Key Files",
        "",
        f"- Profile: {path_status(str(profile), project_dir)}",
        f"- Persistent config: {path_status(str(env_file), project_dir)}",
        f"- Knowledge base: {path_status(str(kb_dir), project_dir)}",
        f"- Daily output: {path_status(str(out_dir), project_dir)}",
        f"- SOURCE_CHECK.md: {path_status(str(source_check), project_dir)}",
        f"- DOCTOR.md: {path_status(str(doctor_report), project_dir)}",
        "",
        "## Optional Tools",
        "",
        f"- pdftotext: {'installed' if shutil.which('pdftotext') else 'not found'}",
        f"- osascript: {'installed' if shutil.which('osascript') else 'not found'}",
        "",
        "## Config Summary",
        "",
    ]

    env_values = read_project_env(env_file)
    if env_values:
        for key in sorted(env_values):
            lines.append(f"- {key}: {support_env_value(key, env_values[key], project_dir)}")
    else:
        lines.append("- No reader.env values found.")

    lines.extend(["", "## Data Counts", ""])
    lines.extend(
        [
            f"- library.json: {json_summary(kb_dir / 'library.json')}",
            f"- feedback.json: {json_summary(kb_dir / 'feedback.json')}",
            f"- seen_papers.json: {json_summary(profile.parent / 'seen_papers.json')}",
            f"- paper notes: {file_count(kb_dir / 'papers', '*.md')}",
            f"- direction notes: {file_count(kb_dir / 'directions', '*.md')}",
            f"- full-text caches: {file_count(kb_dir / 'full_text', '*.txt')}",
            f"- analysis reports: {file_count(kb_dir / 'analysis', '*.md')}",
        ]
    )

    if summary_json.exists():
        try:
            summary = load_json(summary_json)
        except Exception as exc:
            lines.extend(["", "## Latest Run Summary", "", f"- Could not parse summary.json: {exc}"])
        else:
            safe_source = sanitize_report_line(str(summary.get("source", "")), project_dir)
            safe_counts = {
                key: value
                for key, value in (summary.get("source_counts", {}) or {}).items()
                if not any(private in key.lower() for private in ["query", "token", "credential", "raw"])
            }
            lines.extend(
                [
                    "",
                    "## Latest Run Summary",
                    "",
                    f"- Source: {safe_source or 'not recorded'}",
                    f"- Mode: {summary.get('mode', '')}",
                    f"- Papers in digest: {summary.get('papers_in_digest', '')}",
                    f"- Tier counts: `{json.dumps(summary.get('tier_counts', {}), ensure_ascii=False)}`",
                    f"- Source counts: `{json.dumps(safe_counts, ensure_ascii=False)}`",
                    f"- Feedback terms: {summary.get('feedback_terms', '')}",
                    f"- Feedback papers: {summary.get('feedback_papers', '')}",
                ]
            )

    if not args.no_report_excerpts:
        lines.extend(["", "## SOURCE_CHECK.md Excerpt", ""])
        lines.extend(sanitized_file_excerpt(source_check, project_dir))
        lines.extend(["", "## DOCTOR.md Excerpt", ""])
        lines.extend(sanitized_file_excerpt(doctor_report, project_dir))

    lines.extend(
        [
            "",
            "## Before Posting Publicly",
            "",
            "- Confirm no private paths, emails, feed URLs, raw paper titles from private libraries, token names, or institution-specific secrets remain.",
            "- Do not attach `reader.env`, raw `.mbox`, OAuth JSON, Gmail token JSON, `feedback.json`, `seen_papers.json`, Zotero exports, full-text caches, or generated knowledge-base folders.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def write_project_env(path: Path, values: dict[str, str | Path | int | bool]) -> None:
    ordered_keys = [
        "SOURCE",
        "MODE",
        "PROFILE_PATH",
        "KB_DIR",
        "MBOX_PATH",
        "BIBTEX_PATH",
        "RIS_PATH",
        "WEB_SOURCE",
        "RSS_SOURCE",
        "ARXIV_QUERY",
        "GMAIL_CREDENTIALS",
        "GMAIL_TOKEN",
        "AUTO_ALLOW_MAIL_APP",
        "SINCE_DAYS",
        "BOOST",
        "OBSIDIAN_EXPORT_DIR",
        "ZOTERO_OUTPUT_DIR",
        "SCHEDULE_TIME",
        "SCHEDULE_DAYS",
        "SCHEDULE_TIMEZONE",
    ]
    lines = [
        "# Scholar Alert Reader local configuration",
        f"# Generated: {datetime.now().isoformat(timespec='seconds')}",
        "# This file is local/private because it may contain personal paths and research preferences.",
        "",
    ]
    for key in ordered_keys:
        value = values.get(key)
        if value is None or str(value) == "":
            continue
        lines.append(f"export {key}={env_quote(value)}")
    extra_keys = sorted(key for key in values if key not in ordered_keys and values[key] not in {None, ""})
    for key in extra_keys:
        lines.append(f"export {key}={env_quote(values[key])}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def project_relative_path(project_dir: Path, value: Path | None, default_name: str) -> Path:
    path = value.expanduser() if value else project_dir / default_name
    if not path.is_absolute():
        path = project_dir / path
    return path


def render_env_summary(values: dict[str, str]) -> list[str]:
    if not values:
        return ["- Persistent config: not configured yet. Run `./setup_reader.sh --source <source>` to create `reader.env`."]
    lines = ["- Persistent config: `reader.env`"]
    for key in [
        "SOURCE",
        "MODE",
        "SCHEDULE_TIME",
        "SCHEDULE_DAYS",
        "SCHEDULE_TIMEZONE",
        "OBSIDIAN_EXPORT_DIR",
        "ZOTERO_OUTPUT_DIR",
    ]:
        value = values.get(key)
        if value:
            lines.append(f"- {key}: `{value}`")
    return lines


def count_json_items(path: Path) -> tuple[int, str]:
    if not path.exists():
        return 0, "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return 0, f"invalid JSON: {exc}"
    if isinstance(data, list):
        return len(data), "records"
    if isinstance(data, dict):
        if isinstance(data.get("seen_ids"), list):
            return len(data["seen_ids"]), "seen IDs"
        if isinstance(data.get("papers"), dict):
            return len(data["papers"]), "paper feedback records"
        return len(data), "object keys"
    return 0, type(data).__name__


def status_marker(path: Path, required: bool = False) -> str:
    if path.exists():
        return f"OK: `{path}`"
    if required:
        return f"Missing: `{path}`"
    return f"Optional missing: `{path}`"


def count_marker(path: Path) -> str:
    count, kind = count_json_items(path)
    if kind == "missing":
        return f"Optional missing: `{path}`"
    if kind.startswith("invalid JSON"):
        return f"WARN: {kind} at `{path}`"
    return f"{count} {kind}"


def render_project_guide(
    project_dir: Path,
    profile_path: Path,
    kb_dir: Path,
    out_dir: Path,
    obsidian_dir: Path | None = None,
    zotero_dir: Path | None = None,
) -> str:
    daily_dir = out_dir / "daily"
    recent_dir = out_dir / "recent"
    foundation_dir = out_dir / "foundation"
    zotero_dir = zotero_dir or (kb_dir / "zotero")
    profile_name = "unknown"
    if profile_path.exists():
        try:
            profile_name = str(load_json(profile_path).get("name", "unnamed"))
        except Exception:
            profile_name = "invalid profile JSON"
    template_names = available_profile_templates()
    template_line = ", ".join(f"`{name}`" for name in template_names) if template_names else "No bundled templates found."
    env_file = project_env_path(project_dir)
    env_values = read_project_env(env_file)
    lines = [
        "# Scholar Alert Reader Start Here",
        "",
        "This project can run as a standalone Codex skill. Obsidian and Zotero are optional integrations, not required dependencies.",
        "",
        "Capability boundary: ranking and deep-read reports use available alert metadata, bibliography fields, snippets, profile terms, local feedback similarity, and retained-library context. They are triage aids until a full paper/PDF has been read.",
        "",
        "## Product Modes",
        "",
        "1. Codex-only: read Scholar Alert emails, rank papers, write HTML/Markdown digests, maintain `knowledge_base/`, and use the local copilot commands.",
        "2. Codex + Obsidian: sync generated paper notes, maps, reading status, answers, comparisons, and deep reads into an Obsidian vault folder.",
        "3. Codex + Zotero + Obsidian: export BibTeX/RIS for Zotero while Obsidian stores human-written reading notes and synthesis.",
        "",
        "## First Run",
        "",
        "Open `DASHBOARD.html` first after each run. It is the project home page for the latest digest, reading plan, review queue, retained library, and setup reports.",
        "",
        "0. Verify the install with bundled sample data: `./self_test.sh`.",
        "1. Try the demo without Gmail, Obsidian, or Zotero: `./demo_reader.sh`, then open `reader_out/demo/digest.html`.",
        "   - To test every bundled non-private source path, run `./demo_sources.sh`.",
        "2. Read the product boundary and best workflow with `./capabilities.sh`.",
        "3. Configure your local defaults once with `./setup_wizard.sh`, or non-interactively with `./setup_reader.sh --source auto --profile-template ai-seismology`.",
        "4. Edit `profiles/research_profile.json` so the focus terms, methods, regions, and research questions match your work.",
        f"   - Current profile: `{profile_name}`.",
        f"   - Bundled templates copied to `profiles/templates/`: {template_line}.",
        "   - To reset from a template, run for example: `./copy_profile_template.sh --template ai-seismology --force`.",
        "5. Choose an input source:",
        "   - Gmail API: run OAuth once, then use `SOURCE=auto ./run_reader.sh`.",
        "   - Exported mailbox: place `INBOX.mbox` in this project and run `SOURCE=mbox ./run_reader.sh`.",
        "   - Bibliography import: place `import.bib` or `import.ris` in this project, then run `./bibtex_import.sh` or `./ris_import.sh`.",
        "   - Structured web sources: place webpage URLs or saved HTML paths in `web_sources.txt` and run `./web_import.sh`, feed URLs in `feeds.txt` and run `./rss_import.sh`, or set `ARXIV_QUERY='cat:physics.geo-ph AND all:tomography' ./arxiv_search.sh`.",
        "6. Build the baseline with `MODE=foundation ./run_reader.sh`.",
        "7. Run daily triage with `./run_reader.sh`.",
        "8. Open `reader_out/daily/digest.html` or run `./serve_reader.sh` for feedback.",
        "",
        "## Persistent Configuration",
        "",
        *render_env_summary(env_values),
        "",
        "## Daily Loop",
        "",
        "- `./run_reader.sh`: fetch and rank new alert papers.",
        "- `./schedule_reader.sh --action write`: render a macOS LaunchAgent plist from `reader.env` schedule settings.",
        "- `./dashboard_reader.sh --open`: open the project dashboard with links to current outputs.",
        "- `./source_check.sh --source auto`: check Gmail, mbox, BibTeX/RIS, webpage metadata, RSS/arXiv, or optional Mail.app source readiness.",
        "- `./serve_reader.sh`: mark interested/archive and tune future ranking.",
        "- `./deep_read_paper.sh --paper-id <ID>`: analyze one selected paper against your foundation.",
        "- `./workup_paper.sh --paper-id <ID>`: decide how a selected paper fits your foundation, interested papers, and manuscript needs.",
        "- `./ask_library.sh --question \"...\"`: query your retained literature base.",
        "- `./reading_plan.sh`: choose what to read next and which paper IDs to send into review packs.",
        "- `./advice_reader.sh`: generate reading strategy and gap advice.",
        "",
        "## Optional Integrations",
        "",
        "- `./zotero_export.sh`: writes BibTeX/RIS to `knowledge_base/zotero/` for Zotero import.",
        "- `./zotero_sync.sh`: reads a Better BibTeX/BibTeX export back into `library.json` so citation keys and local PDF paths are retained.",
        "- `./sync_obsidian_vault.sh`: writes generated Markdown into an Obsidian literature folder.",
        "- Keep user-authored Obsidian notes outside the generated export folder so reruns never overwrite your writing.",
        "",
        "## Current Setup Status",
        "",
        f"- Project directory: `{project_dir}`",
        f"- Local config: {status_marker(env_file)}",
        f"- Profile: {status_marker(profile_path, required=True)}",
        f"- Gmail credentials: {status_marker(DEFAULT_GMAIL_CREDENTIALS)}",
        f"- Gmail token: {status_marker(DEFAULT_GMAIL_TOKEN)}",
        f"- Local mbox: {status_marker(project_dir / 'INBOX.mbox')}",
        f"- BibTeX import: {status_marker(project_dir / 'import.bib')}",
        f"- RIS import: {status_marker(project_dir / 'import.ris')}",
        f"- Web metadata source list: {status_marker(project_dir / 'web_sources.txt')}",
        f"- RSS/Atom feed list: {status_marker(project_dir / 'feeds.txt')}",
        f"- Daily digest HTML: {status_marker(daily_dir / 'digest.html')}",
        f"- Project dashboard HTML: {status_marker(project_dir / 'DASHBOARD.html')}",
        f"- Schedule report: {status_marker(project_dir / 'SCHEDULE.md')}",
        f"- Daily papers JSON: {count_marker(daily_dir / 'papers.json')}",
        f"- Foundation digest HTML: {status_marker(foundation_dir / 'digest.html')}",
        f"- Recent review JSON: {status_marker(recent_dir / 'papers.json')}",
        f"- Retained library: {count_marker(kb_dir / 'library.json')}",
        f"- Feedback: {count_marker(kb_dir / 'feedback.json')}",
        f"- Zotero export directory: {status_marker(zotero_dir)}",
    ]
    if obsidian_dir:
        lines.append(f"- Obsidian export directory: {status_marker(obsidian_dir)}")
    else:
        lines.append("- Obsidian export directory: not configured; Codex-only mode is still complete.")
    lines.extend(
        [
            "",
            "## Safety Contract",
            "",
            "- Do not commit raw mailbox exports, OAuth credentials, Gmail tokens, `seen_papers.json`, `feedback.json`, or generated knowledge bases unless they are intentionally sanitized.",
            "- The generated Obsidian folder may be overwritten. Personal reading notes, topic notes, and writing drafts should live in sibling folders.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def write_project_guide(project_dir: Path, profile_path: Path, kb_dir: Path, out_dir: Path, force: bool) -> None:
    start_here = project_dir / "START_HERE.md"
    if not start_here.exists() or force:
        start_here.write_text(
            render_project_guide(project_dir, profile_path, kb_dir, out_dir),
            encoding="utf-8",
        )


def dashboard_link(label: str, path: Path, base_dir: Path) -> str:
    if path.exists():
        try:
            target = os.path.relpath(path, base_dir)
        except ValueError:
            target = str(path)
        return f"[{label}]({target})"
    return f"{label} - missing (`{path}`)"


def dashboard_json_count(path: Path) -> str:
    count, kind = count_json_items(path)
    if kind == "missing":
        return "missing"
    if kind.startswith("invalid JSON"):
        return kind
    return f"{count} {kind}"


def dashboard_latest_summary(summary_path: Path) -> dict[str, Any]:
    if not summary_path.exists():
        return {}
    try:
        data = load_json(summary_path)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def render_project_dashboard(project_dir: Path, profile_path: Path, kb_dir: Path, out_dir: Path) -> str:
    base_dir = project_dir
    profile_name = "unknown"
    if profile_path.exists():
        try:
            profile_name = str(load_json(profile_path).get("name", "unnamed"))
        except Exception:
            profile_name = "invalid profile JSON"

    summary_path = out_dir / "summary.json"
    summary = dashboard_latest_summary(summary_path)
    tier_counts = summary.get("tier_counts", {}) if isinstance(summary.get("tier_counts", {}), dict) else {}
    source_counts = summary.get("source_counts", {}) if isinstance(summary.get("source_counts", {}), dict) else {}
    daily_dir = project_dir / "reader_out" / "daily"
    recent_dir = project_dir / "reader_out" / "recent"
    analysis_dir = kb_dir / "analysis"

    lines = [
        "# Scholar Alert Reader Dashboard",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Version: `{__version__}`",
        f"- Profile: `{profile_name}`",
        f"- Project: `{project_dir}`",
        "",
        "## Open First",
        "",
        f"- {dashboard_link('Latest digest HTML', out_dir / 'digest.html', base_dir)}",
        f"- {dashboard_link('Reading plan HTML', kb_dir / 'reading_plan.html', base_dir)}",
        f"- {dashboard_link('Review queue HTML', analysis_dir / 'review_queue.html', base_dir)}",
        f"- {dashboard_link('Feedback UI source JSON', out_dir / 'papers.json', base_dir)}",
        "",
        "## Latest Run",
        "",
    ]
    if summary:
        diagnosis = summary.get("empty_run_diagnosis")
        diagnosis = diagnosis if isinstance(diagnosis, dict) else {}
        lines.extend(
            [
                f"- Summary file: {dashboard_link('summary.json', summary_path, base_dir)}",
                f"- Mode: `{summary.get('mode', 'unknown')}`",
                f"- Source: `{summary.get('source', 'unknown')}`",
                f"- Source items: {summary.get('source_items', source_item_count(summary))}",
                f"- Unique papers before seen-state filter: {summary.get('unique_papers_before_state_filter', 'unknown')}",
                f"- Seen-state filtered out: {summary.get('seen_papers_filtered_out', 'unknown')}",
                f"- Papers in digest: {summary.get('papers_in_digest', 'unknown')}",
                f"- Library additions: {summary.get('library_additions', 'unknown')}",
                f"- Knowledge base updated: {summary.get('knowledge_base_updated', 'unknown')}",
                f"- Tier counts: `{json.dumps(tier_counts, ensure_ascii=False)}`",
                f"- Source counts: `{json.dumps(source_counts, ensure_ascii=False)}`",
            ]
        )
        if diagnosis:
            lines.extend(
                [
                    "",
                    "## No-Paper Diagnosis",
                    "",
                    f"- Reason: `{diagnosis.get('reason', 'unknown')}`",
                    f"- {diagnosis.get('title', 'No papers were written')}: {diagnosis.get('summary', '')}",
                    "",
                    "Next steps:",
                    "",
                ]
            )
            lines.extend(f"- {step}" for step in diagnosis.get("next_steps", []))
    else:
        lines.extend(
            [
                f"- No run summary found at `{summary_path}`.",
                "- Run `./demo_reader.sh` for a private-data-free preview, then `./setup_wizard.sh` and `./run_reader.sh` for real sources.",
            ]
        )

    lines.extend(
        [
            "",
            "## Knowledge Base",
            "",
            f"- Retained library: {dashboard_json_count(kb_dir / 'library.json')}",
            f"- Feedback records: {dashboard_json_count(kb_dir / 'feedback.json')}",
            f"- Paper notes: {file_count(kb_dir / 'papers', '*.md')}",
            f"- Direction notes: {file_count(kb_dir / 'directions', '*.md')}",
            f"- Full-text caches: {file_count(kb_dir / 'full_text', '*.txt')}",
            f"- Analysis reports: {file_count(analysis_dir, '*.md')}",
            "",
            "## Library Files",
            "",
            f"- {dashboard_link('Foundation library', kb_dir / 'foundation.md', base_dir)}",
            f"- {dashboard_link('Interested queue', kb_dir / 'interested.md', base_dir)}",
            f"- {dashboard_link('Daily additions', kb_dir / 'daily_additions.md', base_dir)}",
            f"- {dashboard_link('Latest run note', kb_dir / 'latest_run.md', base_dir)}",
            f"- {dashboard_link('Weekly review', kb_dir / 'weekly_review.md', base_dir)}",
            f"- {dashboard_link('Research map', kb_dir / 'research_map.md', base_dir)}",
            f"- {dashboard_link('Research advice', kb_dir / 'research_advice.md', base_dir)}",
            f"- {dashboard_link('Reading status', kb_dir / 'reading_status.md', base_dir)}",
            "",
            "## Review Workflow",
            "",
            f"- {dashboard_link('Reading plan markdown', kb_dir / 'reading_plan.md', base_dir)}",
            f"- {dashboard_link('Review queue markdown', analysis_dir / 'review_queue.md', base_dir)}",
            f"- {dashboard_link('Recent review papers JSON', recent_dir / 'papers.json', base_dir)}",
            f"- {dashboard_link('Daily papers JSON', daily_dir / 'papers.json', base_dir)}",
            "",
            "Recommended flow:",
            "",
            "1. Open the latest digest and mark obvious interested/archive papers in `./serve_reader.sh`.",
            "2. Open the reading plan to choose the next few IDs.",
            "3. Run `./workup_paper.sh --paper-id ID` for a human-readable decision brief on one paper.",
            "4. Run `./review_queue.sh --paper-id ID1,ID2` for batch review packs.",
            "5. If Zotero has local PDFs, run `./zotero_sync.sh` first so review packs can include full-text briefs.",
            "6. Sync to Obsidian/Zotero only after the retained library looks right.",
            "",
            "## Setup And Diagnostics",
            "",
            f"- {dashboard_link('Start Here guide', project_dir / 'START_HERE.md', base_dir)}",
            f"- {dashboard_link('Source check', project_dir / 'SOURCE_CHECK.md', base_dir)}",
            f"- {dashboard_link('Doctor report', project_dir / 'DOCTOR.md', base_dir)}",
            f"- {dashboard_link('Schedule report', project_dir / 'SCHEDULE.md', base_dir)}",
            f"- {dashboard_link('Capabilities report', project_dir / 'CAPABILITIES.md', base_dir)}",
            f"- {dashboard_link('Troubleshooting guide', project_dir / 'TROUBLESHOOTING.md', base_dir)}",
            "",
            "Refresh this page with `./dashboard_reader.sh`. Successful `./run_reader.sh` runs refresh it automatically unless `REFRESH_DASHBOARD=0` is set.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def open_local_path(path: Path) -> None:
    webbrowser.open(path.expanduser().resolve().as_uri())


def dashboard_command(args: argparse.Namespace) -> None:
    project_dir = args.project_dir.expanduser().resolve()
    profile_path = (args.profile or project_dir / "profiles" / "research_profile.json").expanduser()
    kb_dir = (args.kb_dir or project_dir / "knowledge_base").expanduser()
    out_dir = (args.out_dir or project_dir / "reader_out" / "daily").expanduser()
    output = (args.output or project_dir / "DASHBOARD.md").expanduser()
    html_output = args.html_output or output.with_suffix(".html")
    report = render_project_dashboard(project_dir, profile_path, kb_dir, out_dir)
    write_report(output, report)
    if not args.no_html:
        write_markdown_html(output, html_output, "Scholar Alert Reader Dashboard")
    if args.open:
        open_local_path(html_output if not args.no_html else output)
    print(f"Dashboard: {output}")
    if not args.no_html:
        print(f"Dashboard HTML: {html_output}")


def init_project(args: argparse.Namespace) -> None:
    project_dir = args.project_dir.expanduser().resolve()
    profile_path = project_dir / "profiles" / "research_profile.json"
    kb_dir = project_dir / "knowledge_base"
    out_dir = project_dir / "reader_out"
    if project_dir.exists() and any(project_dir.iterdir()) and not args.force:
        raise SystemExit(f"Project directory is not empty: {project_dir}. Use --force to add/update scaffold files.")

    for directory in [
        project_dir,
        project_dir / "profiles",
        project_dir / "profiles" / "templates",
        project_dir / "examples",
        kb_dir,
        out_dir / "daily",
        out_dir / "foundation",
        out_dir / "manual",
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    if not profile_path.exists() or args.force:
        copy_profile_template(profile_path, args.profile_template, True)
    if PROFILE_TEMPLATE_DIR.exists():
        for template_source in PROFILE_TEMPLATE_DIR.glob("*.json"):
            template_target = project_dir / "profiles" / "templates" / template_source.name
            if not template_target.exists() or args.force:
                shutil.copyfile(template_source, template_target)
    sample_mbox = resource_path("examples", "sample_scholar_alerts.mbox.sample")
    if sample_mbox.exists():
        sample_target = project_dir / "examples" / "sample_scholar_alerts.mbox"
        if not sample_target.exists() or args.force:
            shutil.copyfile(sample_mbox, sample_target)
    for sample_name in [
        "sample_import.bib",
        "sample_import.ris",
        "sample_web_article.html",
        "web_sources.example.txt",
        "sample_feed.atom",
        "feeds.example.txt",
    ]:
        sample_source = resource_path("examples", sample_name)
        if sample_source.exists():
            sample_target = project_dir / "examples" / sample_name
            if not sample_target.exists() or args.force:
                shutil.copyfile(sample_source, sample_target)
    troubleshooting_source = resource_path("TROUBLESHOOTING.md")
    if troubleshooting_source.exists():
        troubleshooting_target = project_dir / "TROUBLESHOOTING.md"
        if not troubleshooting_target.exists() or args.force:
            shutil.copyfile(troubleshooting_source, troubleshooting_target)

    common = project_script_common(project_dir, profile_path, kb_dir)
    run_reader = generated_script_header() + common + """MODE="${MODE:-daily}"
SOURCE="${SOURCE:-auto}"
MBOX_PATH="${MBOX_PATH:-$PROJECT_DIR/INBOX.mbox}"
BIBTEX_PATH="${BIBTEX_PATH:-$PROJECT_DIR/import.bib}"
RIS_PATH="${RIS_PATH:-$PROJECT_DIR/import.ris}"
WEB_SOURCE="${WEB_SOURCE:-$PROJECT_DIR/web_sources.txt}"
RSS_SOURCE="${RSS_SOURCE:-$PROJECT_DIR/feeds.txt}"
ARXIV_QUERY="${ARXIV_QUERY:-}"
GMAIL_CREDENTIALS="${GMAIL_CREDENTIALS:-$HOME/.codex/scholar-alert-reader/gmail_credentials.json}"
GMAIL_TOKEN="${GMAIL_TOKEN:-$HOME/.codex/scholar-alert-reader/gmail_token.json}"
GMAIL_DEPS_READY="$("$PYTHON_BIN" - <<'PY'
import importlib.util
mods = ["googleapiclient", "google.oauth2.credentials", "google_auth_oauthlib.flow"]
try:
    ok = all(importlib.util.find_spec(mod) is not None for mod in mods)
except ModuleNotFoundError:
    ok = False
print("1" if ok else "0")
PY
)"

if [[ "$SOURCE" == "auto" ]]; then
  if [[ -f "$GMAIL_TOKEN" && "$GMAIL_DEPS_READY" == "1" ]]; then
    SOURCE="gmail"
  elif [[ -f "$MBOX_PATH" || -d "$MBOX_PATH" ]]; then
    SOURCE="mbox"
  elif [[ -f "$BIBTEX_PATH" || -d "$BIBTEX_PATH" ]]; then
    SOURCE="bibtex"
  elif [[ -f "$RIS_PATH" || -d "$RIS_PATH" ]]; then
    SOURCE="ris"
  elif [[ -f "$WEB_SOURCE" || -d "$WEB_SOURCE" || "$WEB_SOURCE" == http://* || "$WEB_SOURCE" == https://* ]]; then
    SOURCE="web"
  elif [[ -f "$RSS_SOURCE" || -d "$RSS_SOURCE" ]]; then
    SOURCE="rss"
  elif [[ -n "$ARXIV_QUERY" ]]; then
    SOURCE="arxiv"
  elif [[ "${AUTO_ALLOW_MAIL_APP:-0}" == "1" && "$(uname -s)" == "Darwin" && -x "/usr/bin/osascript" ]]; then
    SOURCE="mail-app"
  elif [[ -f "$GMAIL_TOKEN" && "$GMAIL_DEPS_READY" != "1" ]]; then
    echo "Gmail token exists, but this Python is missing Gmail API dependencies." >&2
    echo "Install with: $PYTHON_BIN -m pip install -r requirements-gmail.txt" >&2
    echo "Or set SOURCE=mbox, bibtex, ris, web, rss, arxiv, or mail-app explicitly." >&2
    exit 2
  else
    echo "No Scholar Alert source is ready." >&2
    echo "Set up Gmail OAuth, place INBOX.mbox/import.bib/import.ris/web_sources.txt/feeds.txt in this project, set ARXIV_QUERY, or run SOURCE=mail-app AUTO_ALLOW_MAIL_APP=1 after granting macOS Automation permission." >&2
    exit 2
  fi
fi

if [[ -z "${OUT_DIR:-}" ]]; then
  if [[ "$MODE" == "foundation" ]]; then
    OUT_DIR="$PROJECT_DIR/reader_out/foundation"
  elif [[ "$MODE" == "daily" ]]; then
    OUT_DIR="$PROJECT_DIR/reader_out/daily"
  else
    OUT_DIR="$PROJECT_DIR/reader_out/manual"
  fi
fi

cmd=("${SKILL_CMD[@]}" "$MODE" --profile "$PROFILE_PATH" --out-dir "$OUT_DIR" --kb-dir "$KB_DIR")

if [[ "$SOURCE" == "gmail" ]]; then
  cmd+=(--source-gmail --gmail-credentials "$GMAIL_CREDENTIALS" --gmail-token "$GMAIL_TOKEN")
elif [[ "$SOURCE" == "mail-app" ]]; then
  cmd+=(--source-mail-app)
  if [[ -n "${MAIL_TIMEOUT:-}" ]]; then cmd+=(--mail-timeout "$MAIL_TIMEOUT"); fi
elif [[ "$SOURCE" == "bibtex" ]]; then
  cmd+=(--source-bibtex "$BIBTEX_PATH")
elif [[ "$SOURCE" == "ris" ]]; then
  cmd+=(--source-ris "$RIS_PATH")
elif [[ "$SOURCE" == "web" ]]; then
  cmd+=(--source-web "$WEB_SOURCE")
elif [[ "$SOURCE" == "rss" ]]; then
  cmd+=(--source-rss "$RSS_SOURCE")
elif [[ "$SOURCE" == "arxiv" ]]; then
  if [[ -z "$ARXIV_QUERY" ]]; then
    echo "Set ARXIV_QUERY before using SOURCE=arxiv." >&2
    exit 2
  fi
  cmd+=(--source-arxiv-query "$ARXIV_QUERY")
else
  cmd+=(--source-mbox "$MBOX_PATH")
fi

if [[ -n "${BOOST:-}" ]]; then cmd+=(--boost "$BOOST"); fi
if [[ -n "${GMAIL_LIMIT:-}" ]]; then cmd+=(--gmail-limit "$GMAIL_LIMIT"); fi
if [[ -n "${GMAIL_QUERY:-}" ]]; then cmd+=(--gmail-query "$GMAIL_QUERY"); fi
if [[ -n "${RSS_LIMIT:-}" ]]; then cmd+=(--rss-limit "$RSS_LIMIT"); fi
if [[ -n "${RSS_TIMEOUT:-}" ]]; then cmd+=(--rss-timeout "$RSS_TIMEOUT"); fi
if [[ -n "${WEB_LIMIT:-}" ]]; then cmd+=(--web-limit "$WEB_LIMIT"); fi
if [[ -n "${WEB_TIMEOUT:-}" ]]; then cmd+=(--web-timeout "$WEB_TIMEOUT"); fi
if [[ -n "${ARXIV_LIMIT:-}" ]]; then cmd+=(--arxiv-limit "$ARXIV_LIMIT"); fi
if [[ "$MODE" != "foundation" && -n "${SINCE_DAYS:-}" ]]; then cmd+=(--since-days "$SINCE_DAYS"); fi
if [[ "$MODE" == "run" && "${ONLY_NEW:-0}" == "1" ]]; then cmd+=(--only-new); fi
if [[ "$MODE" == "run" && "${UPDATE_STATE:-0}" == "1" ]]; then cmd+=(--update-state); fi
if [[ "$MODE" == "run" && "${NO_KB_UPDATE:-0}" == "1" ]]; then cmd+=(--no-kb-update); fi

"${cmd[@]}"
run_status=$?
if [[ "$run_status" -eq 0 && "${REFRESH_DASHBOARD:-1}" == "1" ]]; then
  "${SKILL_CMD[@]}" dashboard --project-dir "$PROJECT_DIR" --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" --out-dir "$OUT_DIR" >/dev/null || true
fi
exit "$run_status"
"""
    write_executable(project_dir / "run_reader.sh", run_reader)

    helper_specs = {
        "demo_reader.sh": 'SOURCE=mbox MBOX_PATH="$PROJECT_DIR/examples/sample_scholar_alerts.mbox" MODE=run OUT_DIR="$PROJECT_DIR/reader_out/demo" NO_KB_UPDATE=1 "$PROJECT_DIR/run_reader.sh"\n',
        "demo_sources.sh": """echo "Running sanitized source demos. No Gmail, Mail.app, private mailbox, Zotero, or Obsidian data is read."
SOURCE=mbox MBOX_PATH="$PROJECT_DIR/examples/sample_scholar_alerts.mbox" MODE=run OUT_DIR="$PROJECT_DIR/reader_out/demo_sources/mbox" NO_KB_UPDATE=1 "$PROJECT_DIR/run_reader.sh"
SOURCE=bibtex BIBTEX_PATH="$PROJECT_DIR/examples/sample_import.bib" MODE=run OUT_DIR="$PROJECT_DIR/reader_out/demo_sources/bibtex" NO_KB_UPDATE=1 "$PROJECT_DIR/run_reader.sh"
SOURCE=ris RIS_PATH="$PROJECT_DIR/examples/sample_import.ris" MODE=run OUT_DIR="$PROJECT_DIR/reader_out/demo_sources/ris" NO_KB_UPDATE=1 "$PROJECT_DIR/run_reader.sh"
SOURCE=web WEB_SOURCE="$PROJECT_DIR/examples/web_sources.example.txt" MODE=run OUT_DIR="$PROJECT_DIR/reader_out/demo_sources/web" NO_KB_UPDATE=1 "$PROJECT_DIR/run_reader.sh"
SOURCE=rss RSS_SOURCE="$PROJECT_DIR/examples/feeds.example.txt" MODE=run OUT_DIR="$PROJECT_DIR/reader_out/demo_sources/rss" NO_KB_UPDATE=1 "$PROJECT_DIR/run_reader.sh"
echo
echo "Demo digests:"
echo " - $PROJECT_DIR/reader_out/demo_sources/mbox/digest.html"
echo " - $PROJECT_DIR/reader_out/demo_sources/bibtex/digest.html"
echo " - $PROJECT_DIR/reader_out/demo_sources/ris/digest.html"
echo " - $PROJECT_DIR/reader_out/demo_sources/web/digest.html"
echo " - $PROJECT_DIR/reader_out/demo_sources/rss/digest.html"
""",
        "bibtex_import.sh": 'SOURCE=bibtex BIBTEX_PATH="${BIBTEX_PATH:-$PROJECT_DIR/import.bib}" MODE=run OUT_DIR="${OUT_DIR:-$PROJECT_DIR/reader_out/bibtex}" "$PROJECT_DIR/run_reader.sh"\n',
        "ris_import.sh": 'SOURCE=ris RIS_PATH="${RIS_PATH:-$PROJECT_DIR/import.ris}" MODE=run OUT_DIR="${OUT_DIR:-$PROJECT_DIR/reader_out/ris}" "$PROJECT_DIR/run_reader.sh"\n',
        "web_import.sh": 'SOURCE=web WEB_SOURCE="${WEB_SOURCE:-$PROJECT_DIR/web_sources.txt}" MODE=run OUT_DIR="${OUT_DIR:-$PROJECT_DIR/reader_out/web}" "$PROJECT_DIR/run_reader.sh"\n',
        "rss_import.sh": 'SOURCE=rss RSS_SOURCE="${RSS_SOURCE:-$PROJECT_DIR/feeds.txt}" MODE=run OUT_DIR="${OUT_DIR:-$PROJECT_DIR/reader_out/rss}" "$PROJECT_DIR/run_reader.sh"\n',
        "arxiv_search.sh": 'if [[ -z "${ARXIV_QUERY:-}" ]]; then echo "Set ARXIV_QUERY before running arxiv_search.sh" >&2; exit 2; fi\nSOURCE=arxiv MODE=run OUT_DIR="${OUT_DIR:-$PROJECT_DIR/reader_out/arxiv}" "$PROJECT_DIR/run_reader.sh"\n',
        "source_check.sh": 'exec "${SKILL_CMD[@]}" source-check --project-dir "$PROJECT_DIR" --mbox-path "${MBOX_PATH:-$PROJECT_DIR/INBOX.mbox}" --bibtex-path "${BIBTEX_PATH:-$PROJECT_DIR/import.bib}" --ris-path "${RIS_PATH:-$PROJECT_DIR/import.ris}" --web-source "${WEB_SOURCE:-$PROJECT_DIR/web_sources.txt}" --rss-source "${RSS_SOURCE:-$PROJECT_DIR/feeds.txt}" --arxiv-query "${ARXIV_QUERY:-}" --gmail-credentials "${GMAIL_CREDENTIALS:-$HOME/.codex/scholar-alert-reader/gmail_credentials.json}" --gmail-token "${GMAIL_TOKEN:-$HOME/.codex/scholar-alert-reader/gmail_token.json}" "$@"\n',
        "self_test.sh": 'exec "${SKILL_CMD[@]}" self-test --project-dir "${SELF_TEST_PROJECT_DIR:-$PROJECT_DIR/.self_test}" --force "$@"\n',
        "setup_reader.sh": 'exec "${SKILL_CMD[@]}" setup --project-dir "$PROJECT_DIR" "$@"\n',
        "setup_wizard.sh": 'exec "${SKILL_CMD[@]}" setup-wizard --project-dir "$PROJECT_DIR" "$@"\n',
        "schedule_reader.sh": 'exec "${SKILL_CMD[@]}" schedule --project-dir "$PROJECT_DIR" "$@"\n',
        "copy_profile_template.sh": 'exec "${SKILL_CMD[@]}" init-profile --profile "$PROFILE_PATH" "$@"\n',
        "feedback_reader.sh": 'exec "${SKILL_CMD[@]}" feedback --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" --papers-json "${PAPERS_JSON:-$PROJECT_DIR/reader_out/daily/papers.json}" "$@"\n',
        "serve_reader.sh": 'exec "${SKILL_CMD[@]}" serve --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" --papers-json "${PAPERS_JSON:-$PROJECT_DIR/reader_out/daily/papers.json}" --port "${PORT:-8765}" --open "$@"\n',
        "review_recent.sh": 'export SINCE_DAYS="${SINCE_DAYS:-7}"\nexport OUT_DIR="${OUT_DIR:-$PROJECT_DIR/reader_out/recent}"\nNO_KB_UPDATE=1 MODE=run "$PROJECT_DIR/run_reader.sh"\n',
        "serve_recent.sh": 'PAPERS_JSON="${PAPERS_JSON:-$PROJECT_DIR/reader_out/recent/papers.json}" exec "$PROJECT_DIR/serve_reader.sh" "$@"\n',
        "deep_read_paper.sh": 'exec "${SKILL_CMD[@]}" deep-read --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" --papers-json "${PAPERS_JSON:-$PROJECT_DIR/reader_out/recent/papers.json}" "$@"\n',
        "workup_paper.sh": 'exec "${SKILL_CMD[@]}" workup --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" --papers-json "${PAPERS_JSON:-$PROJECT_DIR/reader_out/recent/papers.json}" "$@"\n',
        "full_text_paper.sh": 'exec "${SKILL_CMD[@]}" full-text --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" --papers-json "${PAPERS_JSON:-$PROJECT_DIR/reader_out/recent/papers.json}" "$@"\n',
        "review_paper.sh": 'exec "${SKILL_CMD[@]}" review-pack --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" --papers-json "${PAPERS_JSON:-$PROJECT_DIR/reader_out/recent/papers.json}" "$@"\n',
        "review_queue.sh": 'exec "${SKILL_CMD[@]}" review-queue --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" --papers-json "${PAPERS_JSON:-$PROJECT_DIR/reader_out/recent/papers.json}" "$@"\n',
        "tune_profile.sh": 'exec "${SKILL_CMD[@]}" profile-tune --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" --papers-json "${PAPERS_JSON:-$PROJECT_DIR/reader_out/recent/papers.json}" "$@"\n',
        "ask_library.sh": 'exec "${SKILL_CMD[@]}" ask --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" "$@"\n',
        "reading_plan.sh": 'exec "${SKILL_CMD[@]}" reading-plan --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" --papers-json "${PAPERS_JSON:-$PROJECT_DIR/reader_out/recent/papers.json}" "$@"\n',
        "advice_reader.sh": 'exec "${SKILL_CMD[@]}" advice --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" "$@"\n',
        "dashboard_reader.sh": 'exec "${SKILL_CMD[@]}" dashboard --project-dir "$PROJECT_DIR" --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" --out-dir "${OUT_DIR:-$PROJECT_DIR/reader_out/daily}" "$@"\n',
        "guide_reader.sh": 'exec "${SKILL_CMD[@]}" guide --project-dir "$PROJECT_DIR" --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" --out-dir "$PROJECT_DIR/reader_out" "$@"\n',
        "status_reader.sh": 'exec "${SKILL_CMD[@]}" status --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" --papers-json "${PAPERS_JSON:-$PROJECT_DIR/reader_out/recent/papers.json}" "$@"\n',
        "compare_papers.sh": 'exec "${SKILL_CMD[@]}" compare --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" --papers-json "${PAPERS_JSON:-$PROJECT_DIR/reader_out/recent/papers.json}" "$@"\n',
        "map_reader.sh": 'exec "${SKILL_CMD[@]}" map --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" "$@"\n',
        "zotero_export.sh": 'exec "${SKILL_CMD[@]}" zotero --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" --output-dir "${ZOTERO_OUTPUT_DIR:-$KB_DIR/zotero}" "$@"\n',
        "zotero_sync.sh": 'exec "${SKILL_CMD[@]}" zotero-sync --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" --bibtex "${ZOTERO_BIBTEX_PATH:-$PROJECT_DIR/zotero.bib}" "$@"\n',
        "obsidian_export.sh": 'exec "${SKILL_CMD[@]}" obsidian --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" --vault-dir "${OBSIDIAN_EXPORT_DIR:-$KB_DIR/obsidian}" "$@"\n',
        "sync_obsidian_vault.sh": 'OBSIDIAN_LITERATURE_DIR="${OBSIDIAN_LITERATURE_DIR:-$HOME/Documents/Obsidian Vault/01_Literatures}"\nOBSIDIAN_EXPORT_DIR="${OBSIDIAN_EXPORT_DIR:-$OBSIDIAN_LITERATURE_DIR/10_Scholar_Alert_Reader}"\nexec "$PROJECT_DIR/obsidian_export.sh" --vault-dir "$OBSIDIAN_EXPORT_DIR" "$@"\n',
        "enrich_reader.sh": 'exec "${SKILL_CMD[@]}" enrich --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" --limit "${LIMIT:-20}" --providers "${PROVIDERS:-openalex,crossref}" --update-library "$@"\n',
        "weekly_reader.sh": 'exec "${SKILL_CMD[@]}" weekly --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" --days "${DAYS:-7}" "$@"\n',
        "export_reader.sh": 'exec "${SKILL_CMD[@]}" export --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" --format "${FORMAT:-bibtex}" --tiers "${TIERS:-Must read,Skim}" "$@"\n',
        "doctor_reader.sh": 'exec "${SKILL_CMD[@]}" doctor --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" --out-dir "${OUT_DIR:-$PROJECT_DIR/reader_out/daily}" --gmail-deps "$@"\n',
        "support_bundle.sh": 'exec "${SKILL_CMD[@]}" support-bundle --project-dir "$PROJECT_DIR" --profile "$PROFILE_PATH" --kb-dir "$KB_DIR" --out-dir "${OUT_DIR:-$PROJECT_DIR/reader_out/daily}" "$@"\n',
        "capabilities.sh": 'exec "${SKILL_CMD[@]}" capabilities --project-dir "$PROJECT_DIR" "$@"\n',
    }
    for filename, body in helper_specs.items():
        write_executable(project_dir / filename, generated_script_header() + common + body)

    gitignore = project_dir / ".gitignore"
    if not gitignore.exists() or args.force:
        gitignore.write_text(
            "\n".join(
                [
                    ".DS_Store",
                    "__pycache__/",
                    "*.pyc",
                    ".venv/",
                    "venv/",
                    "",
                    "# Private mailbox/auth/local state",
                    "*.mbox",
                    "*.mbox/",
                    "*.eml",
                    "import.bib",
                    "import.ris",
                    "zotero.bib",
                    "web_sources.txt",
                    "feeds.txt",
                    "gmail_credentials.json",
                    "gmail_token.json",
                    "client_secret*.json",
                    "reader.env",
                    "profiles/*.bak",
                    ".self_test/",
                    "seen_papers.json",
                    "knowledge_base/feedback.json",
                    "DASHBOARD.md",
                    "DASHBOARD.html",
                    "SCHEDULE.md",
                    "LaunchAgents/",
                    "logs/",
                    "",
                    "# Generated outputs",
                    "reader_out/",
                    "knowledge_base/",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    readme = project_dir / "README.md"
    if not readme.exists() or args.force:
        readme.write_text(
            "\n".join(
                [
                    "# Scholar Alert Reader Project",
                    "",
                    "Start with [DASHBOARD.html](DASHBOARD.html), then [START_HERE.md](START_HERE.md). Refresh both with:",
                    "",
                    "```bash",
                    "./dashboard_reader.sh",
                    "./guide_reader.sh --output START_HERE.md",
                    "```",
                    "",
                    "## First run",
                    "",
                    "```bash",
                    "./self_test.sh",
                    "./demo_reader.sh",
                    "./demo_sources.sh",
                    "./setup_wizard.sh",
                    "./setup_reader.sh --source auto --profile-template ai-seismology",
                    "./schedule_reader.sh --action write",
                    "./source_check.sh --source auto",
                    "./run_reader.sh",
                    "./dashboard_reader.sh --open",
                    "```",
                    "",
                    "`setup_wizard.sh` and `setup_reader.sh` write `reader.env`, which is read automatically by the generated shell scripts.",
                    "",
                    "If a source returns no papers or setup fails, read [TROUBLESHOOTING.md](TROUBLESHOOTING.md).",
                    "",
                    "## Choose a profile template",
                    "",
                    "Bundled templates are copied to `profiles/templates/`. Reset the active profile with:",
                    "",
                    "```bash",
                    "./copy_profile_template.sh --template ai-seismology --force",
                    "```",
                    "",
                    "## Import from bibliography files",
                    "",
                    "Place Zotero/Scholar/publisher exports at `import.bib` or `import.ris`, then run:",
                    "",
                    "```bash",
                    "./bibtex_import.sh",
                    "./ris_import.sh",
                    "BIBTEX_PATH=examples/sample_import.bib ./bibtex_import.sh",
                    "RIS_PATH=examples/sample_import.ris ./ris_import.sh",
                    "```",
                    "",
                    "## Import from web metadata, RSS/Atom, or arXiv",
                    "",
                    "Place webpage URLs or saved scholarly HTML pages in `web_sources.txt`, then run:",
                    "",
                    "```bash",
                    "WEB_SOURCE=examples/sample_web_article.html ./web_import.sh",
                    "./web_import.sh",
                    "```",
                    "",
                    "Place feed URLs in `feeds.txt` or point `RSS_SOURCE` at a feed file:",
                    "",
                    "```bash",
                    "RSS_SOURCE=examples/sample_feed.atom ./rss_import.sh",
                    "ARXIV_QUERY='cat:physics.geo-ph AND all:tomography' ./arxiv_search.sh",
                    "```",
                    "",
                    "## Review recent alerts",
                    "",
                    "```bash",
                    "./review_recent.sh",
                    "./serve_recent.sh",
                    "```",
                    "",
                    "## Feedback UI",
                    "",
                    "```bash",
                    "./serve_reader.sh",
                    "```",
                    "",
                    "## Literature Copilot",
                    "",
                    "```bash",
                    "./deep_read_paper.sh --paper-id <ID>",
                    "./workup_paper.sh --paper-id <ID>",
                    "./full_text_paper.sh --paper-id <ID>",
                    "./review_paper.sh --paper-id <ID>",
                    "./review_queue.sh --tiers \"Must read\" --limit 5",
                    "./tune_profile.sh",
                    "./reading_plan.sh",
                    "./ask_library.sh --question \"receiver function + Tibet 有什么关键论文？\"",
                    "./advice_reader.sh",
                    "```",
                    "",
                    "## Reading System And Integrations",
                    "",
                    "```bash",
                    "./status_reader.sh --paper-id <ID> --status reading --label must-cite",
                    "./compare_papers.sh --paper-id <ID1>,<ID2>",
                    "./map_reader.sh",
                    "./zotero_export.sh",
                    "ZOTERO_BIBTEX_PATH=~/Downloads/My_Library.bib ./zotero_sync.sh",
                    "./sync_obsidian_vault.sh",
                    "```",
                    "",
                    "## Useful commands",
                    "",
                    "```bash",
                    "./capabilities.sh",
                    "./dashboard_reader.sh",
                    "./doctor_reader.sh",
                    "./support_bundle.sh",
                    "./guide_reader.sh",
                    "./weekly_reader.sh",
                    "FORMAT=bibtex ./export_reader.sh",
                    "```",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    write_project_guide(project_dir, profile_path, kb_dir, out_dir, args.force)

    if not getattr(args, "quiet", False):
        print(f"Project initialized: {project_dir}")
        print(f"Profile: {profile_path}")
        print(f"Run: {project_dir / 'run_reader.sh'}")


def default_schedule_values(profile: dict[str, Any]) -> tuple[str, str, str]:
    schedule = profile.get("schedule", {}) if isinstance(profile.get("schedule", {}), dict) else {}
    default_days = schedule.get("default_days", [])
    if isinstance(default_days, list):
        days = ",".join(str(day) for day in default_days)
    else:
        days = str(default_days or "")
    return (
        str(schedule.get("default_time", "09:00")),
        days or "Monday,Tuesday,Wednesday,Thursday,Friday",
        str(schedule.get("timezone", "Asia/Shanghai")),
    )


def prompt_text(label: str, default: str = "", assume_default: bool = False) -> str:
    if assume_default:
        return default
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{label}{suffix}: ").strip()
    except EOFError as exc:
        raise SystemExit("setup-wizard needs an interactive terminal. Pass --defaults or use the non-interactive setup command.") from exc
    return answer or default


def prompt_choice(label: str, choices: list[str], default: str, assume_default: bool = False) -> str:
    if assume_default:
        return default
    print(label)
    for index, choice in enumerate(choices, start=1):
        marker = " default" if choice == default else ""
        print(f"  {index}. {choice}{marker}")
    while True:
        answer = prompt_text("Choose number or value", default)
        if answer in choices:
            return answer
        if answer.isdigit():
            index = int(answer)
            if 1 <= index <= len(choices):
                return choices[index - 1]
        print(f"Please choose one of: {', '.join(choices)}")


def prompt_yes_no(label: str, default: bool = False, assume_default: bool = False) -> bool:
    if assume_default:
        return default
    while True:
        suffix = " [Y/n]" if default else " [y/N]"
        try:
            answer = input(f"{label}{suffix}: ").strip().lower()
        except EOFError as exc:
            raise SystemExit("setup-wizard needs an interactive terminal. Pass --defaults or use the non-interactive setup command.") from exc
        if not answer:
            return default
        if answer in {"y", "yes", "1", "true"}:
            return True
        if answer in {"n", "no", "0", "false"}:
            return False
        print("Please answer yes or no.")


def optional_path(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    return Path(text).expanduser() if text else None


def optional_int(value: str | int | None, label: str) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise SystemExit(f"{label} must be an integer.") from exc


def setup_wizard(args: argparse.Namespace) -> None:
    assume_default = args.defaults
    if not assume_default and not sys.stdin.isatty():
        raise SystemExit("setup-wizard needs an interactive terminal. Pass --defaults or use the non-interactive setup command.")

    project_dir = args.project_dir.expanduser().resolve()
    print("Scholar Alert Reader setup wizard")
    print("- Writes reader.env and refreshes START_HERE.md.")
    print("- Runs a readiness check after setup unless --skip-check is passed.")
    print("- Use --live-check when you want to test the selected source immediately.")
    env_values = read_project_env(project_env_path(project_dir)) if project_dir.exists() else {}
    templates = available_profile_templates()
    default_template = args.profile_template or DEFAULT_PROFILE_TEMPLATE
    if args.profile_template:
        profile_template = args.profile_template
    else:
        profile_template = prompt_choice("Research profile template", templates, default_template, assume_default) if templates else default_template

    initialized = False
    needs_init = not project_dir.exists() or not (project_dir / "run_reader.sh").exists()
    if needs_init:
        if args.no_init:
            raise SystemExit(f"Project is not initialized: {project_dir}. Run init-project first or omit --no-init.")
        init_project(
            argparse.Namespace(
                project_dir=project_dir,
                profile_template=profile_template,
                force=args.force_init,
                quiet=True,
            )
        )
        initialized = True

    profile_path = project_relative_path(project_dir, args.profile, "profiles/research_profile.json")
    if profile_path.exists():
        try:
            profile = load_profile(profile_path)
        except SystemExit:
            profile = load_json(resolve_profile_template(profile_template))
    else:
        profile = load_json(resolve_profile_template(profile_template))
    default_time, default_days, default_timezone = default_schedule_values(profile)

    default_source = args.source or env_values.get("SOURCE", "auto")
    if default_source not in SOURCE_CHOICES:
        default_source = "auto"
    source = args.source or prompt_choice("Input source", SOURCE_CHOICES, default_source, assume_default)
    default_mode = args.mode or env_values.get("MODE", "daily")
    if default_mode not in MODE_CHOICES:
        default_mode = "daily"
    mode = args.mode or prompt_choice("Run mode", MODE_CHOICES, default_mode, assume_default)
    print(f"Source note: {source_hint(source, project_dir)}")

    mbox_path = args.mbox_path
    bibtex_path = args.bibtex_path
    ris_path = args.ris_path
    web_source = args.web_source
    rss_source = args.rss_source
    arxiv_query = args.arxiv_query

    if source == "mbox":
        mbox_path = optional_path(prompt_text("mbox path", str(mbox_path or env_values.get("MBOX_PATH", project_dir / "INBOX.mbox")), assume_default))
    elif source == "bibtex":
        bibtex_path = optional_path(prompt_text("BibTeX import path", str(bibtex_path or env_values.get("BIBTEX_PATH", project_dir / "import.bib")), assume_default))
    elif source == "ris":
        ris_path = optional_path(prompt_text("RIS import path", str(ris_path or env_values.get("RIS_PATH", project_dir / "import.ris")), assume_default))
    elif source == "web":
        web_source = prompt_text("Web URL, saved HTML, directory, or source list", str(web_source or env_values.get("WEB_SOURCE", project_dir / "web_sources.txt")), assume_default)
    elif source == "rss":
        rss_source = prompt_text("RSS/Atom URL, file, directory, or feed list", str(rss_source or env_values.get("RSS_SOURCE", project_dir / "feeds.txt")), assume_default)
    elif source == "arxiv":
        arxiv_query = prompt_text("arXiv query", str(arxiv_query or env_values.get("ARXIV_QUERY", "cat:physics.geo-ph")), assume_default)

    allow_mail_app = bool(args.auto_allow_mail_app or source == "mail-app")
    if source == "auto" and not args.auto_allow_mail_app:
        allow_mail_app = prompt_yes_no("Allow Mail.app fallback on macOS", False, assume_default)

    schedule_time = args.schedule_time or prompt_text("Preferred run time", env_values.get("SCHEDULE_TIME", default_time), assume_default)
    schedule_days = args.schedule_days or prompt_text("Preferred run days", env_values.get("SCHEDULE_DAYS", default_days), assume_default)
    timezone = args.timezone or prompt_text("Timezone", env_values.get("SCHEDULE_TIMEZONE", default_timezone), assume_default)
    since_days = args.since_days
    if since_days is None:
        since_days = optional_int(prompt_text("Recent-window days for manual/recent runs (blank to skip)", env_values.get("SINCE_DAYS", ""), assume_default), "since-days")
    boost = args.boost or prompt_text("Temporary boost terms, comma-separated (blank to skip)", env_values.get("BOOST", ""), assume_default)
    obsidian_dir = args.obsidian_dir
    if obsidian_dir is None:
        obsidian_dir = optional_path(prompt_text("Generated Obsidian export folder (blank to skip)", env_values.get("OBSIDIAN_EXPORT_DIR", ""), assume_default))
    zotero_dir = args.zotero_dir
    if zotero_dir is None:
        zotero_dir = optional_path(prompt_text("Zotero export folder (blank to skip)", env_values.get("ZOTERO_OUTPUT_DIR", ""), assume_default))

    setup_args = argparse.Namespace(
        project_dir=project_dir,
        source=source,
        mode=mode,
        profile=args.profile,
        kb_dir=args.kb_dir,
        profile_template=None if initialized else profile_template,
        force_profile=args.force_profile,
        mbox_path=mbox_path,
        bibtex_path=bibtex_path,
        ris_path=ris_path,
        web_source=web_source,
        rss_source=rss_source,
        arxiv_query=arxiv_query,
        gmail_credentials=args.gmail_credentials,
        gmail_token=args.gmail_token,
        auto_allow_mail_app=allow_mail_app,
        obsidian_dir=obsidian_dir,
        zotero_dir=zotero_dir,
        schedule_time=schedule_time,
        schedule_days=schedule_days,
        timezone=timezone,
        since_days=since_days,
        boost=boost,
        output=args.output,
        no_guide=args.no_guide,
    )
    setup_project(setup_args)
    if not args.skip_check:
        check_output = args.check_output.expanduser() if args.check_output else project_dir / "SOURCE_CHECK.md"
        source_check_command(
            argparse.Namespace(
                source=source,
                project_dir=project_dir,
                mbox_path=mbox_path,
                bibtex_path=bibtex_path,
                ris_path=ris_path,
                web_source=web_source,
                rss_source=rss_source,
                arxiv_query=arxiv_query,
                arxiv_limit=args.check_limit,
                web_limit=args.check_limit,
                web_timeout=args.check_timeout,
                gmail_credentials=args.gmail_credentials,
                gmail_token=args.gmail_token,
                gmail_query=None,
                since_days=since_days,
                limit=args.check_limit,
                timeout=args.check_timeout,
                live=args.live_check,
                allow_mail_app=allow_mail_app,
                strict=args.check_strict,
                output=check_output,
            )
        )
    print("Wizard complete.")
    if args.live_check:
        print("Source check completed with live read.")
    else:
        print("Next: ./source_check.sh --source auto --live")


def setup_project(args: argparse.Namespace) -> None:
    project_dir = args.project_dir.expanduser().resolve()
    if not project_dir.exists():
        raise SystemExit(f"Project directory does not exist: {project_dir}. Run init-project first.")
    profile_path = project_relative_path(project_dir, args.profile, "profiles/research_profile.json")
    kb_dir = project_relative_path(project_dir, args.kb_dir, "knowledge_base")

    profile_backup: Path | None = None
    if args.profile_template:
        if profile_path.exists() and not args.force_profile:
            profile_backup = profile_path.with_suffix(profile_path.suffix + ".bak")
            shutil.copyfile(profile_path, profile_backup)
        copy_profile_template(profile_path, args.profile_template, True)
    elif not profile_path.exists():
        copy_profile_template(profile_path, DEFAULT_PROFILE_TEMPLATE, True)
    profile = load_profile(profile_path)
    default_time, default_days, default_timezone = default_schedule_values(profile)

    source = args.source
    if source == "arxiv" and not args.arxiv_query:
        raise SystemExit("--source arxiv requires --arxiv-query.")

    values: dict[str, str | Path | int | bool] = {
        "SOURCE": source,
        "MODE": args.mode,
        "PROFILE_PATH": profile_path,
        "KB_DIR": kb_dir,
        "SCHEDULE_TIME": args.schedule_time or default_time,
        "SCHEDULE_DAYS": args.schedule_days or default_days,
        "SCHEDULE_TIMEZONE": args.timezone or default_timezone,
    }
    if args.boost:
        values["BOOST"] = args.boost
    if args.since_days is not None:
        values["SINCE_DAYS"] = args.since_days
    if args.auto_allow_mail_app or source == "mail-app":
        values["AUTO_ALLOW_MAIL_APP"] = True

    values["MBOX_PATH"] = project_relative_path(project_dir, args.mbox_path, "INBOX.mbox")
    values["BIBTEX_PATH"] = project_relative_path(project_dir, args.bibtex_path, "import.bib")
    values["RIS_PATH"] = project_relative_path(project_dir, args.ris_path, "import.ris")
    web_source = args.web_source or str(project_dir / "web_sources.txt")
    if not is_url(web_source):
        web_path = Path(web_source).expanduser()
        if not web_path.is_absolute():
            web_source = str(project_dir / web_path)
    values["WEB_SOURCE"] = web_source
    rss_source = args.rss_source or str(project_dir / "feeds.txt")
    if not is_url(rss_source):
        rss_path = Path(rss_source).expanduser()
        if not rss_path.is_absolute():
            rss_source = str(project_dir / rss_path)
    values["RSS_SOURCE"] = rss_source
    if args.arxiv_query:
        values["ARXIV_QUERY"] = args.arxiv_query
    values["GMAIL_CREDENTIALS"] = args.gmail_credentials.expanduser()
    values["GMAIL_TOKEN"] = args.gmail_token.expanduser()
    if args.obsidian_dir:
        values["OBSIDIAN_EXPORT_DIR"] = project_relative_path(project_dir, args.obsidian_dir, "knowledge_base/obsidian")
    if args.zotero_dir:
        values["ZOTERO_OUTPUT_DIR"] = project_relative_path(project_dir, args.zotero_dir, "knowledge_base/zotero")

    config_path = args.output.expanduser() if args.output else project_env_path(project_dir)
    write_project_env(config_path, values)
    if not args.no_guide:
        write_project_guide(project_dir, profile_path, kb_dir, project_dir / "reader_out", True)

    print(f"Project config: {config_path}")
    print(f"Source: {source}")
    print(f"Profile: {profile_path}")
    print(f"Schedule: {values['SCHEDULE_TIME']} {values['SCHEDULE_DAYS']} ({values['SCHEDULE_TIMEZONE']})")
    if args.profile_template:
        print(f"Profile template: {args.profile_template}")
    if profile_backup:
        print(f"Previous profile backup: {profile_backup}")
    print("Next: ./source_check.sh --source auto")
    print("Run: ./run_reader.sh")


WEEKDAY_ALIASES = {
    "sun": 0,
    "sunday": 0,
    "mon": 1,
    "monday": 1,
    "tue": 2,
    "tues": 2,
    "tuesday": 2,
    "wed": 3,
    "wednesday": 3,
    "thu": 4,
    "thur": 4,
    "thurs": 4,
    "thursday": 4,
    "fri": 5,
    "friday": 5,
    "sat": 6,
    "saturday": 6,
}


def parse_schedule_time(value: str) -> tuple[int, int]:
    text = (value or "09:00").strip()
    match = re.match(r"^(\d{1,2}):(\d{2})$", text)
    if not match:
        raise SystemExit(f"Schedule time must be HH:MM, got: {value}")
    hour = int(match.group(1))
    minute = int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise SystemExit(f"Schedule time out of range: {value}")
    return hour, minute


def parse_schedule_days(value: str) -> list[int] | None:
    text = (value or "weekdays").strip()
    normalized = re.sub(r"\s+", "", text.lower())
    if normalized in {"daily", "everyday", "every-day", "all", "*"}:
        return None
    if normalized in {"weekday", "weekdays", "workdays"}:
        return [1, 2, 3, 4, 5]
    if normalized in {"weekend", "weekends"}:
        return [0, 6]

    days: list[int] = []
    for part in re.split(r"[,/;]+", text):
        token = part.strip().lower()
        if not token:
            continue
        if token.isdigit():
            day = int(token)
            if day == 7:
                day = 0
            if not 0 <= day <= 6:
                raise SystemExit(f"Schedule weekday must be 0-7 or a day name, got: {part}")
        else:
            day = WEEKDAY_ALIASES.get(token)
            if day is None:
                raise SystemExit(f"Unknown schedule day: {part}")
        if day not in days:
            days.append(day)
    if not days:
        raise SystemExit(f"No schedule days parsed from: {value}")
    return days


def calendar_intervals(schedule_time: str, schedule_days: str) -> dict[str, int] | list[dict[str, int]]:
    hour, minute = parse_schedule_time(schedule_time)
    days = parse_schedule_days(schedule_days)
    base = {"Hour": hour, "Minute": minute}
    if days is None:
        return base
    return [{**base, "Weekday": day} for day in days]


def launch_agent_label(project_dir: Path, requested: str | None = None) -> str:
    if requested:
        return requested
    slug = slugify(project_dir.name)[:36] or "scholar-alert-reader"
    digest = hashlib.sha1(str(project_dir).encode("utf-8")).hexdigest()[:8]
    return f"com.scholar-alert-reader.{slug}.{digest}"


def default_launch_agent_path(label: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def project_launch_agent_path(project_dir: Path, label: str) -> Path:
    return project_dir / "LaunchAgents" / f"{label}.plist"


def render_launch_agent_plist(
    project_dir: Path,
    label: str,
    schedule_time: str,
    schedule_days: str,
    run_at_load: bool = False,
) -> dict[str, Any]:
    logs_dir = project_dir / "logs"
    plist: dict[str, Any] = {
        "Label": label,
        "ProgramArguments": [str(project_dir / "run_reader.sh")],
        "WorkingDirectory": str(project_dir),
        "StartCalendarInterval": calendar_intervals(schedule_time, schedule_days),
        "StandardOutPath": str(logs_dir / "scholar-alert-reader.out.log"),
        "StandardErrorPath": str(logs_dir / "scholar-alert-reader.err.log"),
    }
    if run_at_load:
        plist["RunAtLoad"] = True
    return plist


def launchctl_target() -> str:
    return f"gui/{os.getuid()}"


def schedule_status(label: str, plist_path: Path) -> tuple[bool, str]:
    if sys.platform != "darwin" or not shutil.which("launchctl"):
        return plist_path.exists(), "launchctl status unavailable on this platform"
    result = subprocess.run(
        ["launchctl", "print", f"{launchctl_target()}/{label}"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return True, "loaded"
    return plist_path.exists(), "plist exists but job is not loaded" if plist_path.exists() else "not installed"


def render_schedule_report(
    action: str,
    project_dir: Path,
    label: str,
    plist_path: Path,
    schedule_time: str,
    schedule_days: str,
    timezone_name: str,
    run_at_load: bool,
    dry_run: bool,
    status_text: str,
) -> str:
    logs_dir = project_dir / "logs"
    lines = [
        "# Scholar Alert Reader Schedule",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Action: `{action}`",
        f"- Project: `{project_dir}`",
        f"- Label: `{label}`",
        f"- Plist: `{plist_path}`",
        f"- Run script: `{project_dir / 'run_reader.sh'}`",
        f"- Schedule: `{schedule_time}` on `{schedule_days}`",
        f"- Configured timezone note: `{timezone_name}`",
        f"- LaunchAgent timezone: macOS launchd uses the Mac's current system timezone.",
        f"- Run at load: `{run_at_load}`",
        f"- Dry run: `{dry_run}`",
        f"- Status: {status_text}",
        f"- stdout log: `{logs_dir / 'scholar-alert-reader.out.log'}`",
        f"- stderr log: `{logs_dir / 'scholar-alert-reader.err.log'}`",
        "",
        "## Commands",
        "",
        "```bash",
        "./schedule_reader.sh --action write",
        "./schedule_reader.sh --action install",
        "./schedule_reader.sh --action status",
        "./schedule_reader.sh --action uninstall",
        "```",
        "",
        "## Notes",
        "",
        "- Run `./source_check.sh --source auto --live` before installing a daily schedule.",
        "- `run_reader.sh` reads `reader.env`, so schedule changes made with `./setup_reader.sh --schedule-time ... --schedule-days ...` should be followed by `./schedule_reader.sh --action install`.",
        "- Keep Gmail OAuth tokens, mailbox exports, private feed lists, and generated knowledge-base files out of Git.",
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def write_schedule_report(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def schedule_command(args: argparse.Namespace) -> None:
    project_dir = args.project_dir.expanduser().resolve()
    if not (project_dir / "run_reader.sh").exists():
        raise SystemExit(f"Project is not initialized or missing run_reader.sh: {project_dir}")
    env_values = read_project_env(project_env_path(project_dir))
    schedule_time = args.time or env_values.get("SCHEDULE_TIME", "09:00")
    schedule_days = args.days or env_values.get("SCHEDULE_DAYS", "weekdays")
    timezone_name = args.timezone or env_values.get("SCHEDULE_TIMEZONE", "system")
    label = launch_agent_label(project_dir, args.label)
    plist_path = (args.output.expanduser() if args.output else None) or (
        default_launch_agent_path(label) if args.action in {"install", "uninstall", "status"} else project_launch_agent_path(project_dir, label)
    )
    report_path = (args.report.expanduser() if args.report else project_dir / "SCHEDULE.md")
    run_at_load = bool(args.run_at_load)
    dry_run = bool(args.dry_run)
    status_text = ""

    parse_schedule_time(schedule_time)
    parse_schedule_days(schedule_days)

    if args.action in {"install", "uninstall"} and sys.platform != "darwin" and not dry_run:
        raise SystemExit("LaunchAgent install/uninstall is macOS-only. Use --action write to generate the plist, then schedule run_reader.sh with your OS scheduler.")

    if args.action in {"write", "install"}:
        plist = render_launch_agent_plist(project_dir, label, schedule_time, schedule_days, run_at_load=run_at_load)
        if not dry_run:
            plist_path.parent.mkdir(parents=True, exist_ok=True)
            (project_dir / "logs").mkdir(parents=True, exist_ok=True)
            plist_path.write_bytes(plistlib.dumps(plist, sort_keys=True))
        status_text = "plist rendered" if dry_run else f"plist written to {plist_path}"
        if args.action == "install":
            if not dry_run and not shutil.which("launchctl"):
                raise SystemExit("launchctl not found; cannot install LaunchAgent.")
            if not dry_run:
                subprocess.run(["launchctl", "bootout", launchctl_target(), str(plist_path)], text=True, capture_output=True, check=False)
                result = subprocess.run(
                    ["launchctl", "bootstrap", launchctl_target(), str(plist_path)],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if result.returncode != 0:
                    raise SystemExit(result.stderr.strip() or "launchctl bootstrap failed")
                status_text = "installed with launchctl"
            else:
                status_text = "dry-run install; plist not written and launchctl not called"
    elif args.action == "uninstall":
        if not dry_run and shutil.which("launchctl"):
            subprocess.run(["launchctl", "bootout", launchctl_target(), str(plist_path)], text=True, capture_output=True, check=False)
        if not dry_run and plist_path.exists():
            plist_path.unlink()
            status_text = "uninstalled and plist removed"
        else:
            status_text = "dry-run uninstall; no changes" if dry_run else "not installed"
    elif args.action == "status":
        _, status_text = schedule_status(label, plist_path)
    else:
        raise SystemExit(f"Unknown schedule action: {args.action}")

    write_schedule_report(
        report_path,
        render_schedule_report(
            args.action,
            project_dir,
            label,
            plist_path,
            schedule_time,
            schedule_days,
            timezone_name,
            run_at_load,
            dry_run,
            status_text,
        ),
    )
    print(f"Schedule report: {report_path}")
    print(f"Label: {label}")
    print(f"Plist: {plist_path}")
    print(f"Status: {status_text}")


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
        if not cleaned or cleaned.startswith("-") or cleaned.startswith(("similar:", "dissimilar:")):
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
        score_paper(paper, profile, None, feedback, existing_library)
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
    write_kb_paper_pages(kb_dir, library)
    write_kb_direction_pages(kb_dir, library, profile)
    write_weekly_review(kb_dir, library, profile)
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


def profile_tune_command(args: argparse.Namespace) -> None:
    from .tuning import apply_profile_suggestions, render_profile_tuning_report, suggest_profile_updates

    profile = load_profile(args.profile)
    report_profile = json.loads(json.dumps(profile))
    kb_dir = args.kb_dir or default_kb_dir(args.profile, Path("out"))
    feedback = load_feedback(args.feedback_file or default_feedback_file(kb_dir))
    records = merged_paper_records(kb_dir, args.papers_json)
    output = args.output or (kb_dir / "profile_tuning.md")
    suggestions = suggest_profile_updates(profile, records, feedback, limit=args.limit)
    changed = 0
    if args.apply:
        changed = apply_profile_suggestions(
            profile,
            suggestions,
            focus_weight=args.focus_weight,
            exclude_weight=args.exclude_weight,
            semantic_weight=args.semantic_weight,
        )
        if changed:
            save_json(args.profile, profile)
    write_report(output, render_profile_tuning_report(report_profile, records, feedback, args.profile, limit=args.limit))
    print(f"Profile tuning report: {output}")
    if args.apply:
        print(f"Profile updated: {args.profile} ({changed} additions)")


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


def choose_auto_source(
    project_dir: Path,
    mbox_path: Path,
    bibtex_path: Path,
    ris_path: Path,
    web_source: str,
    rss_source: str,
    arxiv_query: str | None,
    gmail_token: Path,
    allow_mail_app: bool,
) -> tuple[str, str]:
    if gmail_token.exists() and gmail_dependencies_available():
        return "gmail", f"Gmail token found at {gmail_token}"
    if mbox_path.exists():
        return "mbox", f"mbox file found at {mbox_path}"
    if bibtex_path.exists():
        return "bibtex", f"BibTeX file or directory found at {bibtex_path}"
    if ris_path.exists():
        return "ris", f"RIS file or directory found at {ris_path}"
    web_path = Path(web_source).expanduser()
    if is_url(web_source) or web_path.exists():
        return "web", f"Web metadata source found at {web_source}"
    rss_path = Path(rss_source).expanduser()
    if is_url(rss_source) or rss_path.exists():
        return "rss", f"RSS/Atom source found at {rss_source}"
    if arxiv_query:
        return "arxiv", "ARXIV_QUERY is configured"
    if allow_mail_app and mail_app_available():
        return "mail-app", "Mail.app fallback allowed and osascript is available"
    if gmail_token.exists() and not gmail_dependencies_available():
        return "gmail", "Gmail token exists but Python Gmail dependencies are missing"
    return "none", (
        "No automatic source is ready. Configure Gmail OAuth, place an INBOX.mbox/import.bib/import.ris/web_sources.txt/feeds.txt "
        "in the project, or run SOURCE=mail-app AUTO_ALLOW_MAIL_APP=1 on macOS after granting Mail Automation permission."
    )


def source_hint(source: str, project_dir: Path) -> str:
    hints = {
        "auto": "Auto tries Gmail, mbox, BibTeX, RIS, web metadata, RSS/Atom, arXiv, then optional Mail.app in that order.",
        "gmail": "Gmail needs one local Desktop OAuth client JSON plus one browser authorization; it stores a read-only token locally.",
        "mail-app": "Mail.app is macOS-only and needs Automation permission for the terminal or agent process that runs the tool.",
        "mbox": f"mbox expects an exported mailbox at `{project_dir / 'INBOX.mbox'}` unless you pass another path.",
        "bibtex": f"BibTeX expects a Zotero, Scholar, publisher, or database export at `{project_dir / 'import.bib'}` by default.",
        "ris": f"RIS expects a Zotero, EndNote, publisher, or database export at `{project_dir / 'import.ris'}` by default.",
        "web": f"Web metadata can be a URL, saved HTML file, directory, or one-item-per-line list at `{project_dir / 'web_sources.txt'}`.",
        "rss": f"RSS/Atom can be a feed URL, feed file, directory, or one-item-per-line list at `{project_dir / 'feeds.txt'}`.",
        "arxiv": "arXiv uses the public Atom API; precise category/topic queries work better than broad text searches.",
    }
    return hints.get(source, "Choose one source first, then run source-check with --live before scheduling automation.")


def web_source_instruction(web_source: str, default_list: Path) -> str:
    if is_url(web_source):
        return f"- The configured webpage URL will be read directly. For multiple pages, create `{default_list}` with one URL or saved HTML path per line."
    path = Path(web_source).expanduser()
    suffix = path.suffix.lower()
    if path.is_dir():
        return f"- The configured directory `{path}` will be scanned for saved scholarly HTML files. For mixed URLs and files, use `{default_list}` as a one-item-per-line list."
    if suffix in {".txt", ".list"} or not suffix:
        return f"- Add publisher/article URLs or saved HTML file paths to `{path}`, one source per line."
    if suffix in {".html", ".htm"}:
        return f"- The configured saved HTML file `{path}` will be read directly. For multiple pages, create `{default_list}` with one URL or file path per line."
    return f"- The configured web source `{path}` will be read as a file or list. Use `{default_list}` for a clearer one-item-per-line source list."


def rss_source_instruction(rss_source: str, default_list: Path) -> str:
    if is_url(rss_source):
        return f"- The configured feed URL will be read directly. For multiple feeds, create `{default_list}` with one feed URL or feed file path per line."
    path = Path(rss_source).expanduser()
    suffix = path.suffix.lower()
    if path.is_dir():
        return f"- The configured directory `{path}` will be scanned for feed files. For mixed URLs and files, use `{default_list}` as a one-item-per-line list."
    if suffix in {".txt", ".list"} or not suffix:
        return f"- Add journal feeds, saved-search feeds, publisher feeds, or feed file paths to `{path}`, one source per line."
    if suffix in {".atom", ".rss", ".xml"}:
        return f"- The configured feed file `{path}` will be read directly. For multiple feeds, create `{default_list}` with one feed URL or file path per line."
    return f"- The configured RSS/Atom source `{path}` will be read as a feed file or list. Use `{default_list}` for a clearer one-item-per-line source list."


def source_setup_guidance(
    source: str,
    project_dir: Path,
    mbox_path: Path,
    bibtex_path: Path,
    ris_path: Path,
    web_source: str,
    rss_source: str,
    arxiv_query: str | None,
    gmail_credentials: Path,
    gmail_token: Path,
) -> list[str]:
    lines = [
        f"- Source meaning: {source_hint(source, project_dir)}",
        "- This check only validates readiness. It does not update `knowledge_base/` or import papers unless you run the reader workflow.",
    ]
    if source == "gmail":
        lines.extend(
            [
                f"- Put your Desktop OAuth client JSON at `{gmail_credentials}` or pass `--gmail-credentials`.",
                f"- Install Gmail dependencies with `python3 -m pip install -r requirements-gmail.txt`, then run `python3 -m scholar_alert_reader auth-gmail --gmail-credentials {gmail_credentials} --gmail-token {gmail_token}`.",
                "- Use the Gmail read-only scope. Do not commit OAuth client JSON or token files.",
            ]
        )
    elif source == "mail-app":
        lines.extend(
            [
                "- Open Mail.app once, make sure Scholar Alert messages are visible, then run `./source_check.sh --source mail-app --live`.",
                "- If macOS blocks access, grant Automation permission to Terminal, Codex, or the process running this command in System Settings.",
            ]
        )
    elif source == "mbox":
        lines.extend(
            [
                f"- Export Scholar Alert mail from Gmail or Apple Mail and place it at `{mbox_path}` unless you pass `--mbox-path`.",
                "- Run `./source_check.sh --source mbox --live` before using it as the daily source.",
            ]
        )
    elif source == "bibtex":
        lines.extend(
            [
                f"- Export BibTeX from Zotero, Google Scholar library, a publisher page, or an academic database to `{bibtex_path}`.",
                "- Use `./bibtex_import.sh` for one-off imports or set `SOURCE=bibtex` in `reader.env` for repeated runs.",
            ]
        )
    elif source == "ris":
        lines.extend(
            [
                f"- Export RIS from Zotero, EndNote, a publisher page, or an academic database to `{ris_path}`.",
                "- Use `./ris_import.sh` for one-off imports or set `SOURCE=ris` in `reader.env` for repeated runs.",
            ]
        )
    elif source == "web":
        lines.extend(
            [
                web_source_instruction(web_source, project_dir / "web_sources.txt"),
                "- Web metadata reads citation meta tags, JSON-LD, Dublin Core, and OpenGraph. It is not a deep crawler.",
            ]
        )
    elif source == "rss":
        lines.extend(
            [
                rss_source_instruction(rss_source, project_dir / "feeds.txt"),
                "- RSS/Atom is usually the most stable non-email source for ongoing monitoring.",
            ]
        )
    elif source == "arxiv":
        query = arxiv_query or "cat:physics.geo-ph AND all:tomography"
        lines.extend(
            [
                f"- Current/default query: `{query}`.",
                "- Try precise queries such as `cat:physics.geo-ph AND all:\"ambient noise\"` or `cat:cs.LG AND all:seismology`.",
            ]
        )
    else:
        lines.extend(
            [
                "- Configure at least one source, then rerun `./source_check.sh --source auto --live`.",
                "- Fastest private-data-free check: `./demo_sources.sh`, then open the generated demo digests.",
            ]
        )
    lines.append("- After a successful live check, run `./run_reader.sh`; open `reader_out/daily/digest.html` and `knowledge_base/reading_plan.html`.")
    return lines


def render_source_check(args: argparse.Namespace) -> tuple[str, bool]:
    project_dir = args.project_dir.expanduser().resolve()
    source = args.source
    mbox_path = (args.mbox_path or (project_dir / "INBOX.mbox")).expanduser()
    bibtex_path = (args.bibtex_path or (project_dir / "import.bib")).expanduser()
    ris_path = (args.ris_path or (project_dir / "import.ris")).expanduser()
    web_source = args.web_source or str(project_dir / "web_sources.txt")
    rss_source = args.rss_source or str(project_dir / "feeds.txt")
    gmail_credentials = args.gmail_credentials.expanduser()
    gmail_token = args.gmail_token.expanduser()
    checks: list[tuple[str, bool, str]] = []
    notes: list[str] = []

    def exc_detail(exc: BaseException) -> str:
        return str(exc) or exc.__class__.__name__

    if source == "auto":
        source, reason = choose_auto_source(
            project_dir,
            mbox_path,
            bibtex_path,
            ris_path,
            web_source,
            rss_source,
            args.arxiv_query,
            gmail_token,
            args.allow_mail_app,
        )
        notes.append(f"Auto selected `{source}`: {reason}")

    if source == "gmail":
        checks.append(("Gmail Python dependencies", gmail_dependencies_available(), "google-api-python-client / oauth libraries"))
        checks.append(("Gmail OAuth credentials", gmail_credentials.exists(), str(gmail_credentials)))
        checks.append(("Gmail token", gmail_token.exists(), str(gmail_token)))
        if args.live and gmail_dependencies_available() and gmail_token.exists():
            try:
                papers, counts = parse_gmail_source(
                    gmail_credentials,
                    gmail_token,
                    args.since_days,
                    args.limit,
                    args.gmail_query,
                    allow_auth=False,
                )
                checks.append(("Gmail live read", True, f"{len(papers)} papers from {counts.get('gmail_raw_messages', 0)} raw messages"))
                notes.append(f"Gmail query: `{counts.get('gmail_query', '')}`")
            except (SystemExit, Exception) as exc:
                checks.append(("Gmail live read", False, exc_detail(exc)))
        elif args.live:
            checks.append(("Gmail live read", False, "Skipped because dependencies or token are missing."))
    elif source == "mail-app":
        checks.append(("Platform is macOS", sys.platform == "darwin", sys.platform))
        checks.append(("osascript available", shutil.which("osascript") is not None, shutil.which("osascript") or "not found"))
        if args.live and mail_app_available():
            try:
                papers, counts = parse_mail_app_source(args.since_days, args.limit, timeout_seconds=args.timeout)
                checks.append(("Mail.app live read", True, f"{len(papers)} papers from {counts.get('mail_app_exported', 0)} exported messages"))
            except (SystemExit, Exception) as exc:
                checks.append(("Mail.app live read", False, exc_detail(exc)))
        elif args.live:
            checks.append(("Mail.app live read", False, "Skipped because this is not macOS or osascript is unavailable."))
        notes.append("Mail.app source is macOS-only and requires Automation permission for the process running Codex or the shell.")
    elif source == "mbox":
        checks.append(("mbox path", mbox_path.exists(), str(mbox_path)))
        if args.live and mbox_path.exists():
            try:
                papers, counts = parse_mbox(mbox_path, args.since_days)
                checks.append(("mbox parse", True, f"{len(papers)} papers from {counts.get('scholar_messages', 0)} Scholar messages"))
            except (SystemExit, Exception) as exc:
                checks.append(("mbox parse", False, exc_detail(exc)))
    elif source == "bibtex":
        checks.append(("BibTeX path", bibtex_path.exists(), str(bibtex_path)))
        if args.live and bibtex_path.exists():
            try:
                papers, counts = parse_bibtex_source(bibtex_path)
                checks.append(("BibTeX parse", True, f"{len(papers)} papers from {counts.get('bibliography_entries', 0)} entries"))
            except (SystemExit, Exception) as exc:
                checks.append(("BibTeX parse", False, exc_detail(exc)))
        notes.append("BibTeX import is useful for Zotero, Google Scholar library exports, and publisher bibliography downloads.")
    elif source == "ris":
        checks.append(("RIS path", ris_path.exists(), str(ris_path)))
        if args.live and ris_path.exists():
            try:
                papers, counts = parse_ris_source(ris_path)
                checks.append(("RIS parse", True, f"{len(papers)} papers from {counts.get('bibliography_entries', 0)} entries"))
            except (SystemExit, Exception) as exc:
                checks.append(("RIS parse", False, exc_detail(exc)))
        notes.append("RIS import is useful for Zotero, EndNote, publisher exports, and many academic databases.")
    elif source == "web":
        web_path = Path(web_source).expanduser()
        checks.append(("Web metadata source", is_url(web_source) or web_path.exists(), web_source))
        if args.live and (is_url(web_source) or web_path.exists()):
            try:
                papers, counts = parse_web_source(web_source, timeout=args.web_timeout or args.timeout, limit=args.web_limit or args.limit)
                checks.append(("Web metadata live read", True, f"{len(papers)} papers from {counts.get('web_sources', 0)} page sources"))
            except (SystemExit, Exception) as exc:
                checks.append(("Web metadata live read", False, exc_detail(exc)))
        notes.append("Web metadata import reads citation meta tags, JSON-LD, Dublin Core, and OpenGraph from configured URLs or saved HTML; it is not a deep crawler.")
    elif source == "rss":
        rss_path = Path(rss_source).expanduser()
        checks.append(("RSS/Atom source", is_url(rss_source) or rss_path.exists(), rss_source))
        if args.live and (is_url(rss_source) or rss_path.exists()):
            try:
                papers, counts = parse_rss_source(rss_source, timeout=args.timeout, limit=args.limit)
                checks.append(("RSS/Atom live read", True, f"{len(papers)} papers from {counts.get('feed_entries', 0)} entries"))
            except (SystemExit, Exception) as exc:
                checks.append(("RSS/Atom live read", False, exc_detail(exc)))
        notes.append("RSS/Atom import is best for journal feeds, saved-search feeds, and publisher/database feeds.")
    elif source == "arxiv":
        checks.append(("arXiv query", bool(args.arxiv_query), args.arxiv_query or "missing --arxiv-query"))
        if args.live and args.arxiv_query:
            try:
                papers, counts = parse_arxiv_source(args.arxiv_query, limit=args.arxiv_limit or args.limit, timeout=args.timeout)
                checks.append(("arXiv live read", True, f"{len(papers)} papers from {counts.get('feed_entries', 0)} entries"))
                notes.append(f"arXiv API URL: `{counts.get('arxiv_api_url', '')}`")
            except (SystemExit, Exception) as exc:
                checks.append(("arXiv live read", False, exc_detail(exc)))
        notes.append("arXiv import uses the public arXiv Atom API; use precise category/topic queries for better ranking.")
    else:
        checks.append(("source selection", False, "No source could be selected automatically."))

    ok = all(check_ok for _, check_ok, _ in checks)
    lines = [
        "# Scholar Alert Reader Source Check",
        "",
        f"- Project: `{project_dir}`",
        f"- Requested source: `{args.source}`",
        f"- Effective source: `{source}`",
        f"- Platform: `{sys.platform}`",
        f"- Live check: `{bool(args.live)}`",
        "",
        "## Checks",
        "",
    ]
    for name, check_ok, detail in checks:
        marker = "OK" if check_ok else "WARN"
        lines.append(f"- [{marker}] {name}: {detail}")
    if notes:
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in notes)
    lines.extend(["", "## Setup Guidance", ""])
    lines.extend(
        source_setup_guidance(
            source,
            project_dir,
            mbox_path,
            bibtex_path,
            ris_path,
            web_source,
            rss_source,
            args.arxiv_query,
            gmail_credentials,
            gmail_token,
        )
    )
    return "\n".join(lines).rstrip() + "\n", ok


def source_check_command(args: argparse.Namespace) -> None:
    report, ok = render_source_check(args)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"Source check report: {args.output}")
    else:
        print(report.rstrip())
    if args.strict and not ok:
        raise SystemExit(1)


def self_test_run_command(cmd: list[str], cwd: Path) -> tuple[bool, str]:
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    detail = result.stdout.strip() or result.stderr.strip() or f"exit {result.returncode}"
    if result.returncode != 0 and result.stderr.strip():
        detail = result.stderr.strip()
    return result.returncode == 0, detail.splitlines()[-1] if detail else f"exit {result.returncode}"


def self_test_command(args: argparse.Namespace) -> None:
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if args.project_dir:
        project_dir = args.project_dir.expanduser().resolve()
        if project_dir.exists() and any(project_dir.iterdir()) and not args.force:
            raise SystemExit(f"Self-test project directory is not empty: {project_dir}. Use --force or choose another path.")
        project_dir.mkdir(parents=True, exist_ok=True)
        keep_project = True
    elif args.keep:
        project_dir = Path(tempfile.mkdtemp(prefix="scholar-alert-reader-self-test-")) / "project"
        keep_project = True
    else:
        temp_dir = tempfile.TemporaryDirectory()
        project_dir = Path(temp_dir.name) / "scholar-alert-reader-self-test"
        keep_project = False

    checks: list[tuple[str, bool, str]] = []
    script = skill_wrapper_path()
    profile = project_dir / "profiles" / "research_profile.json"
    kb_dir = project_dir / "knowledge_base"
    demo_out = project_dir / "reader_out" / "self_test_demo"
    mbox = project_dir / "examples" / "sample_scholar_alerts.mbox"
    web_page = project_dir / "examples" / "sample_web_article.html"
    rss = project_dir / "examples" / "sample_feed.atom"

    try:
        init_project(argparse.Namespace(project_dir=project_dir, profile_template=args.profile_template, force=True, quiet=True))
        checks.append(("init-project", True, str(project_dir)))
    except Exception as exc:
        checks.append(("init-project", False, str(exc) or exc.__class__.__name__))

    if checks[-1][1]:
        ok, detail = self_test_run_command(
            [
                sys.executable,
                str(script),
                "run",
                "--source-mbox",
                str(mbox),
                "--profile",
                str(profile),
                "--out-dir",
                str(demo_out),
                "--kb-dir",
                str(kb_dir),
                "--no-kb-update",
            ],
            project_dir,
        )
        checks.append(("sample mbox run", ok, detail))

        summary_path = demo_out / "summary.json"
        digest_path = demo_out / "digest.html"
        papers_path = demo_out / "papers.json"
        if summary_path.exists():
            summary = load_json(summary_path)
            checks.append(("summary.json", True, f"{summary.get('papers_in_digest', 0)} papers in digest"))
        else:
            checks.append(("summary.json", False, str(summary_path)))
        checks.append(("digest.html", digest_path.exists(), str(digest_path)))
        checks.append(("papers.json", papers_path.exists(), str(papers_path)))

        ok, detail = self_test_run_command(
            [
                sys.executable,
                str(script),
                "source-check",
                "--project-dir",
                str(project_dir),
                "--source",
                "web",
                "--web-source",
                str(web_page),
                "--live",
            ],
            project_dir,
        )
        checks.append(("sample web source-check", ok, detail))

        ok, detail = self_test_run_command(
            [
                sys.executable,
                str(script),
                "source-check",
                "--project-dir",
                str(project_dir),
                "--source",
                "rss",
                "--rss-source",
                str(rss),
                "--live",
            ],
            project_dir,
        )
        checks.append(("sample RSS source-check", ok, detail))

        ok, detail = self_test_run_command(
            [
                sys.executable,
                str(script),
                "doctor",
                "--profile",
                str(profile),
                "--kb-dir",
                str(kb_dir),
                "--out-dir",
                str(demo_out),
            ],
            project_dir,
        )
        checks.append(("doctor", ok, detail))

    passed = all(ok for _, ok, _ in checks)
    lines = [
        "# Scholar Alert Reader Self-Test",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Result: {'PASS' if passed else 'WARN'}",
        f"- Project: `{project_dir}`",
        f"- Project retained: `{bool(keep_project or args.project_dir)}`",
        "",
        "## Checks",
        "",
    ]
    for name, ok, detail in checks:
        marker = "OK" if ok else "WARN"
        lines.append(f"- [{marker}] {name}: {detail}")
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            f"- Demo digest: `{digest_path}`",
            f"- Demo papers JSON: `{papers_path}`",
            f"- Demo summary: `{summary_path}`",
            "",
            "This command uses bundled sample data only. It does not read Gmail, Mail.app, user mailboxes, Zotero, Obsidian, or external private files.",
        ]
    )
    report = "\n".join(lines).rstrip() + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"Self-test report: {args.output}")
    else:
        print(report.rstrip())
    if temp_dir is None and keep_project:
        print(f"Self-test project retained: {project_dir}")
    if args.strict and not passed:
        raise SystemExit(1)


def run(args: argparse.Namespace) -> None:
    profile = load_profile(args.profile)
    state_file = args.state_file or default_state_file(args.profile, args.out_dir)
    kb_dir = args.kb_dir or default_kb_dir(args.profile, args.out_dir)
    feedback_file = args.feedback_file or default_feedback_file(kb_dir)
    feedback = empty_feedback() if args.no_feedback else load_feedback(feedback_file)
    ranking_library = [] if args.no_feedback else load_paper_library(kb_dir)
    seen = load_seen(state_file)

    if getattr(args, "source_mail_app", False):
        papers, source_counts = parse_mail_app_source(args.since_days, args.mail_limit, timeout_seconds=args.mail_timeout)
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
    elif getattr(args, "source_bibtex", None):
        papers, source_counts = parse_bibtex_source(args.source_bibtex)
        source_label = f"BibTeX: {args.source_bibtex}"
    elif getattr(args, "source_ris", None):
        papers, source_counts = parse_ris_source(args.source_ris)
        source_label = f"RIS: {args.source_ris}"
    elif getattr(args, "source_web", None):
        papers, source_counts = parse_web_source(args.source_web, timeout=args.web_timeout, limit=args.web_limit)
        source_label = f"Web metadata: {args.source_web}"
    elif getattr(args, "source_rss", None):
        papers, source_counts = parse_rss_source(args.source_rss, timeout=args.rss_timeout, limit=args.rss_limit)
        source_label = f"RSS/Atom: {args.source_rss}"
    elif getattr(args, "source_arxiv_query", None):
        papers, source_counts = parse_arxiv_source(args.source_arxiv_query, limit=args.arxiv_limit, timeout=args.rss_timeout)
        source_label = f"arXiv: {args.source_arxiv_query}"
    else:
        papers, source_counts = parse_mbox(args.source_mbox, args.since_days)
        source_label = str(args.source_mbox)
    total_unique = len(papers)
    source_items = source_item_count({"source_counts": source_counts})
    papers = apply_state(papers, seen, args.only_new)
    papers_after_state = len(papers)
    papers = rank_papers(papers, profile, args.boost, feedback, ranking_library)

    tier_counts = counts_by_tier(papers)
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "profile": str(args.profile or DEFAULT_PROFILE),
        "source": source_label,
        "source_mbox": str(args.source_mbox) if getattr(args, "source_mbox", None) else "",
        "source_mail_app": bool(getattr(args, "source_mail_app", False)),
        "source_gmail": bool(getattr(args, "source_gmail", False)),
        "source_bibtex": str(args.source_bibtex) if getattr(args, "source_bibtex", None) else "",
        "source_ris": str(args.source_ris) if getattr(args, "source_ris", None) else "",
        "source_web": str(args.source_web) if getattr(args, "source_web", None) else "",
        "source_rss": str(args.source_rss) if getattr(args, "source_rss", None) else "",
        "source_arxiv_query": str(args.source_arxiv_query) if getattr(args, "source_arxiv_query", None) else "",
        "source_counts": source_counts,
        "source_items": source_items,
        "unique_papers_before_state_filter": total_unique,
        "papers_after_state_filter": papers_after_state,
        "seen_papers_before_run": len(seen),
        "seen_papers_filtered_out": max(0, total_unique - papers_after_state),
        "papers_in_digest": len(papers),
        "tier_counts": dict(tier_counts),
        "only_new": args.only_new,
        "mode": getattr(args, "mode", "run"),
        "state_file": str(state_file),
        "knowledge_base_dir": str(kb_dir),
        "feedback_file": "" if args.no_feedback else str(feedback_file),
        "feedback_terms": len(feedback.get("terms", [])) if not args.no_feedback else 0,
        "feedback_papers": len(feedback.get("papers", {})) if not args.no_feedback else 0,
        "adaptive_ranking": adaptive_ranking_settings(profile)["enabled"] and not args.no_feedback,
        "adaptive_seed_papers": len(ranking_library),
        "boost": args.boost or "",
    }
    summary["empty_run_diagnosis"] = empty_run_diagnosis(summary)
    write_outputs(args.out_dir, kb_dir, papers, profile, summary, update_knowledge_base=not getattr(args, "no_kb_update", False))
    if args.update_state:
        update_seen(state_file, papers)

    print(f"Papers in digest: {len(papers)}")
    print(f"Tier counts: {dict(tier_counts)}")
    if summary.get("empty_run_diagnosis"):
        diagnosis = summary["empty_run_diagnosis"]
        print(f"No-paper diagnosis: {diagnosis.get('title', 'No papers were written')}")
        for step in diagnosis.get("next_steps", [])[:2]:
            print(f"Next step: {step}")
    print(f"Digest: {args.out_dir / 'digest.md'}")
    print(f"HTML: {args.out_dir / 'digest.html'}")
    print(f"Deep-read queue: {args.out_dir / 'deep_read_queue.md'}")
    if summary.get("reading_plan"):
        print(f"Reading plan: {summary['reading_plan']}")
    if summary.get("reading_plan_html"):
        print(f"Reading plan HTML: {summary['reading_plan_html']}")
    print(f"JSON: {args.out_dir / 'papers.json'}")
    print(f"CSV: {args.out_dir / 'papers.csv'}")
    print(f"Knowledge base: {kb_dir}")


def add_source_profile_args(cmd: argparse.ArgumentParser, default_out_dir: str) -> None:
    source = cmd.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-mbox", type=Path, help="Path to mbox file or Apple Mail .mbox package")
    source.add_argument("--source-mail-app", action="store_true", help="Read Google Scholar Alert messages directly from Mail.app Inbox")
    source.add_argument("--source-gmail", action="store_true", help="Read Google Scholar Alert messages through Gmail API")
    source.add_argument("--source-bibtex", type=Path, help="Path to a BibTeX .bib file or a directory of .bib files")
    source.add_argument("--source-ris", type=Path, help="Path to an RIS .ris file or a directory of .ris files")
    source.add_argument("--source-web", help="Scholarly webpage URL, saved HTML file/directory, or text file listing webpage URLs/paths")
    source.add_argument("--source-rss", help="RSS/Atom feed URL, feed file, directory of feed files, or text file listing feed URLs")
    source.add_argument("--source-arxiv-query", help="arXiv API search query, e.g. 'cat:physics.geo-ph AND all:\"receiver function\"'")
    cmd.add_argument("--profile", type=Path, help="JSON research profile")
    cmd.add_argument("--out-dir", type=Path, default=Path(default_out_dir))
    cmd.add_argument("--boost", help="Comma-separated temporary priority terms, e.g. 'Taiwan,receiver function'")
    cmd.add_argument("--state-file", type=Path, help="Seen-paper state JSON. Defaults to profile directory/seen_papers.json")
    cmd.add_argument("--kb-dir", type=Path, help="Knowledge-base output directory. Defaults to profile parent/knowledge_base")
    cmd.add_argument("--feedback-file", type=Path, help="User feedback JSON. Defaults to kb-dir/feedback.json")
    cmd.add_argument("--no-feedback", action="store_true", help="Ignore saved user feedback for this run")
    cmd.add_argument("--mail-limit", type=int, default=0, help="Max Mail.app messages to export; 0 means no limit")
    cmd.add_argument("--mail-timeout", type=int, default=600, help="Mail.app AppleScript timeout in seconds")
    cmd.add_argument("--gmail-limit", type=int, default=0, help="Max Gmail API messages to fetch; 0 means no limit")
    cmd.add_argument("--gmail-query", help="Additional Gmail search query terms")
    cmd.add_argument("--gmail-credentials", type=Path, default=DEFAULT_GMAIL_CREDENTIALS)
    cmd.add_argument("--gmail-token", type=Path, default=DEFAULT_GMAIL_TOKEN)
    cmd.add_argument("--rss-limit", type=int, default=0, help="Max RSS/Atom papers to return after dedupe; 0 means no limit")
    cmd.add_argument("--rss-timeout", type=int, default=20, help="RSS/Atom/arXiv HTTP timeout in seconds")
    cmd.add_argument("--web-limit", type=int, default=0, help="Max webpage metadata papers to return after dedupe; 0 means no limit")
    cmd.add_argument("--web-timeout", type=int, default=20, help="Webpage metadata HTTP timeout in seconds")
    cmd.add_argument("--arxiv-limit", type=int, default=50, help="Max arXiv results to fetch")


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


def serve_feedback_ui(args: argparse.Namespace) -> None:
    from .server import ServerConfig, serve

    kb_dir = args.kb_dir or default_kb_dir(args.profile, Path("out"))
    serve(
        ServerConfig(
            profile_path=args.profile,
            kb_dir=kb_dir,
            papers_json=args.papers_json,
            host=args.host,
            port=args.port,
            open_browser=args.open,
        )
    )


def load_paper_records(path: Path) -> list[dict[str, Any]]:
    data = load_json(path)
    if isinstance(data, dict):
        data = data.get("papers", [])
    if not isinstance(data, list):
        raise SystemExit(f"Expected a paper list in {path}")
    return [item for item in data if isinstance(item, dict)]


def merge_record_metadata_into_library(kb_dir: Path, records: list[dict[str, Any]], profile: dict[str, Any]) -> int:
    metadata_by_id = {
        str(record.get("id")): record.get("metadata")
        for record in records
        if record.get("id") and record.get("metadata")
    }
    if not metadata_by_id:
        return 0
    library = load_paper_library(kb_dir)
    changed = 0
    for paper in library:
        metadata = metadata_by_id.get(paper.id)
        if metadata and paper.metadata != metadata:
            paper.metadata = metadata
            changed += 1
    if changed:
        save_paper_library(kb_dir, library)
        write_kb_paper_pages(kb_dir, library)
        write_kb_direction_pages(kb_dir, library, profile)
        write_weekly_review(kb_dir, library, profile)
    return changed


def paper_best_doi(paper: Paper) -> str:
    metadata = paper.metadata or {}
    for provider in ["zotero", "bibtex", "ris", "openalex", "crossref"]:
        value = metadata.get(provider)
        if isinstance(value, dict):
            doi = normalize_doi(str(value.get("doi", "")))
            if doi:
                return doi
    return ""


def merge_zotero_metadata(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key in ["citation_key", "item_key", "doi", "title", "uri", "synced_at"]:
        value = incoming.get(key)
        if value:
            merged[key] = value
    for key in ["pdf_paths", "source_files"]:
        values: list[str] = []
        for item in coerce_list(merged.get(key)):
            if item not in values:
                values.append(item)
        for item in coerce_list(incoming.get(key)):
            if item not in values:
                values.append(item)
        if values:
            merged[key] = values
    return merged


def zotero_entries_from_bibtex(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for bibtex_path in bibliography_paths(path, ".bib"):
        text = bibtex_path.read_text(encoding="utf-8", errors="replace")
        for fields in parse_bibtex_entries(text):
            metadata = zotero_metadata_from_bibtex_fields(fields, bibtex_path)
            if metadata.get("title"):
                records.append(metadata)
    return records


def zotero_match_index(library: list[Paper]) -> tuple[dict[str, Paper], dict[str, Paper]]:
    by_title: dict[str, Paper] = {}
    by_doi: dict[str, Paper] = {}
    for paper in library:
        title_key = normalize_title(paper.title)
        if title_key:
            by_title[title_key] = paper
        doi = paper_best_doi(paper)
        if doi:
            by_doi[doi] = paper
    return by_title, by_doi


def sync_zotero_command(args: argparse.Namespace) -> None:
    profile = load_profile(args.profile)
    kb_dir = args.kb_dir or default_kb_dir(args.profile, Path("out"))
    library = load_paper_library(kb_dir)
    entries = zotero_entries_from_bibtex(args.bibtex)
    by_title, by_doi = zotero_match_index(library)
    matched = 0
    unmatched: list[str] = []
    pdf_paths = 0
    for entry in entries:
        doi = normalize_doi(str(entry.get("doi", "")))
        title = str(entry.get("title", ""))
        paper = by_doi.get(doi) if doi else None
        if paper is None:
            paper = by_title.get(normalize_title(title))
        if paper is None:
            unmatched.append(title)
            continue
        existing = paper.metadata.get("zotero", {}) if isinstance(paper.metadata.get("zotero"), dict) else {}
        paper.metadata["zotero"] = merge_zotero_metadata(existing, entry)
        matched += 1
        pdf_paths += len(entry.get("pdf_paths", []) or [])

    if matched:
        save_paper_library(kb_dir, library)
        write_kb_paper_pages(kb_dir, library)
        write_kb_direction_pages(kb_dir, library, profile)
        write_weekly_review(kb_dir, library, profile)
    output = args.report or (kb_dir / "zotero" / "zotero_sync.md")
    lines = [
        "# Zotero Sync Report",
        "",
        f"- Source BibTeX: `{args.bibtex}`",
        f"- Library papers: {len(library)}",
        f"- Zotero entries: {len(entries)}",
        f"- Matched papers: {matched}",
        f"- Unmatched entries: {len(unmatched)}",
        f"- PDF paths imported: {pdf_paths}",
        "",
    ]
    if unmatched:
        lines.extend(["## Unmatched Entries", ""])
        lines.extend(f"- {title}" for title in unmatched[:50])
        if len(unmatched) > 50:
            lines.append(f"- ... {len(unmatched) - 50} more")
        lines.append("")
    write_report(output, "\n".join(lines).rstrip() + "\n")
    print(f"Zotero entries: {len(entries)}")
    print(f"Matched papers: {matched}")
    print(f"PDF paths imported: {pdf_paths}")
    print(f"Report: {output}")


def refresh_library_markdown(kb_dir: Path, profile: dict[str, Any]) -> int:
    library = load_paper_library(kb_dir)
    write_kb_paper_pages(kb_dir, library)
    write_kb_direction_pages(kb_dir, library, profile)
    write_weekly_review(kb_dir, library, profile)
    return len(library)


def enrich_metadata(args: argparse.Namespace) -> None:
    from .enrich import enrich_records

    profile = load_profile(args.profile)
    kb_dir = args.kb_dir or default_kb_dir(args.profile, Path("out"))
    input_path = args.papers_json or (kb_dir / "library.json")
    output_path = args.output or input_path
    providers = split_csv(args.providers) or ["openalex", "crossref"]
    records = load_paper_records(input_path)
    enriched, stats = enrich_records(
        records,
        providers=providers,
        limit=args.limit,
        email=args.email,
        timeout=args.timeout,
    )
    save_json(output_path, enriched)
    changed = 0
    if args.update_library:
        library_path = kb_dir / "library.json"
        if output_path.resolve() == library_path.resolve():
            changed = refresh_library_markdown(kb_dir, profile)
        else:
            changed = merge_record_metadata_into_library(kb_dir, enriched, profile)
    print(f"Enriched requested: {stats.requested}")
    print(f"OpenAlex hits: {stats.openalex_hits}; Crossref hits: {stats.crossref_hits}; errors: {stats.errors}")
    print(f"Output: {output_path}")
    if args.update_library:
        print(f"Library markdown refreshed/updated: {changed}")


def write_weekly_command(args: argparse.Namespace) -> None:
    from .weekly import render_weekly_review

    profile = load_profile(args.profile)
    kb_dir = args.kb_dir or default_kb_dir(args.profile, Path("out"))
    library = load_paper_library(kb_dir)
    records = [asdict(paper) for paper in library]
    output = args.output or (kb_dir / "weekly_review.md")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_weekly_review(records, profile, days=args.days, limit=args.limit), encoding="utf-8")
    print(f"Weekly review: {output}")


def filter_records_for_export(records: list[dict[str, Any]], tiers: list[str], limit: int) -> list[dict[str, Any]]:
    tier_set = {tier.lower() for tier in tiers}
    filtered = [
        record
        for record in records
        if not tier_set or str(record.get("tier", "")).lower() in tier_set
    ]
    filtered = sorted(
        filtered,
        key=lambda record: (
            {"Must read": 0, "Skim": 1, "Archive": 2}.get(str(record.get("tier", "")), 9),
            -int(record.get("score", 0) or 0),
            str(record.get("title", "")).lower(),
        ),
    )
    return filtered[:limit] if limit > 0 else filtered


def export_library(args: argparse.Namespace) -> None:
    from .export import export_records

    kb_dir = args.kb_dir or default_kb_dir(args.profile, Path("out"))
    input_path = args.papers_json or (kb_dir / "library.json")
    records = load_paper_records(input_path)
    tiers = split_csv(args.tiers)
    selected = filter_records_for_export(records, tiers, args.limit)
    suffix = {"bibtex": "bib", "ris": "ris", "markdown": "md", "jsonl": "jsonl"}[args.format]
    output = args.output or (kb_dir / f"export.{suffix}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(export_records(selected, args.format), encoding="utf-8")
    print(f"Exported papers: {len(selected)}")
    print(f"Output: {output}")


def paper_records_from_library(kb_dir: Path) -> list[dict[str, Any]]:
    papers = [asdict(paper) for paper in load_paper_library(kb_dir)]
    if papers:
        return papers
    library_path = kb_dir / "library.json"
    if not library_path.exists():
        return []
    try:
        return load_paper_records(library_path)
    except Exception:
        return []


def merged_paper_records(kb_dir: Path, papers_json: Path | None = None) -> list[dict[str, Any]]:
    records_by_id: dict[str, dict[str, Any]] = {}
    for record in paper_records_from_library(kb_dir):
        paper_id = str(record.get("id", ""))
        if paper_id:
            records_by_id[paper_id] = record
    if papers_json and papers_json.exists():
        for record in load_paper_records(papers_json):
            paper_id = str(record.get("id", ""))
            if paper_id:
                records_by_id[paper_id] = {**records_by_id.get(paper_id, {}), **record}
    return sorted(
        records_by_id.values(),
        key=lambda record: (
            {"Must read": 0, "Skim": 1, "Archive": 2}.get(str(record.get("tier", "")), 9),
            -int(record.get("score", 0) or 0),
            str(record.get("title", "")).lower(),
        ),
    )


def select_paper_record(records: list[dict[str, Any]], paper_id: str | None, title: str | None) -> dict[str, Any]:
    requested_ids = set(split_csv(paper_id))
    if requested_ids:
        matches = [record for record in records if str(record.get("id", "")) in requested_ids]
        if matches:
            return matches[0]
    if title:
        needle = title.lower()
        matches = [record for record in records if needle in str(record.get("title", "")).lower()]
        if matches:
            return matches[0]
    raise SystemExit("No matching paper found. Pass --paper-id or --title, and use --papers-json if the paper is from a recent digest.")


def select_paper_records(records: list[dict[str, Any]], paper_id: str | None, title: str | None) -> list[dict[str, Any]]:
    requested_ids = set(split_csv(paper_id))
    selected: list[dict[str, Any]] = []
    if requested_ids:
        selected.extend(record for record in records if str(record.get("id", "")) in requested_ids)
    for title_part in split_csv(title):
        needle = title_part.lower()
        selected.extend(record for record in records if needle in str(record.get("title", "")).lower())
    by_id = {str(record.get("id", "")): record for record in selected if str(record.get("id", ""))}
    if not by_id:
        raise SystemExit("No matching papers found. Pass --paper-id A,B,C or --title substrings.")
    return list(by_id.values())


def write_report(output: Path, content: str) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return output


def write_deep_read_report(
    profile_path: Path,
    kb_dir: Path,
    paper_id: str | None = None,
    title: str | None = None,
    papers_json: Path | None = None,
    output: Path | None = None,
    limit: int = 12,
) -> Path:
    from .copilot import render_deep_read

    profile = load_profile(profile_path)
    library_records = paper_records_from_library(kb_dir)
    records = merged_paper_records(kb_dir, papers_json)
    target = select_paper_record(records, paper_id, title)
    if not library_records:
        library_records = records
    output_path = output or (kb_dir / "analysis" / f"{target.get('id', 'paper')}_deep_read.md")
    return write_report(output_path, render_deep_read(target, library_records, profile, limit=limit))


def deep_read_command(args: argparse.Namespace) -> None:
    kb_dir = args.kb_dir or default_kb_dir(args.profile, Path("out"))
    output = write_deep_read_report(
        profile_path=args.profile,
        kb_dir=kb_dir,
        paper_id=args.paper_id,
        title=args.title,
        papers_json=args.papers_json,
        output=args.output,
        limit=args.limit,
    )
    print(f"Deep-read report: {output}")


def full_text_command(args: argparse.Namespace) -> None:
    from .fulltext import extract_local_text, first_full_text_path, render_full_text_brief

    profile = load_profile(args.profile)
    kb_dir = args.kb_dir or default_kb_dir(args.profile, Path("out"))
    records = merged_paper_records(kb_dir, args.papers_json)
    target = select_paper_record(records, args.paper_id, args.title)
    source_path = first_full_text_path(target, args.pdf_path)
    extracted = extract_local_text(source_path, max_chars=args.max_chars, timeout=args.timeout)
    stem = str(target.get("id", "paper") or "paper")
    text_output = args.text_output or (kb_dir / "full_text" / f"{stem}.txt")
    report_output = args.output or (kb_dir / "analysis" / f"{stem}_full_text_brief.md")
    write_report(text_output, extracted.text)
    write_report(report_output, render_full_text_brief(target, extracted, profile, text_output))
    print(f"Full-text source: {source_path}")
    print(f"Extraction method: {extracted.method}")
    print(f"Text cache: {text_output}")
    print(f"Full-text brief: {report_output}")


def read_context_text(path: Path | None, max_chars: int) -> tuple[str, Path | None]:
    if not path or not path.exists():
        return "", None
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return handle.read(max_chars + 1), path


def review_brief_summary(full_text_brief: str) -> dict[str, str]:
    categories = ["Figures", "Tables", "Supplement", "Data Availability", "Code / Software"]
    signals = [category for category in categories if f"**{category}**" in full_text_brief]
    found = re.search(r"(?m)^- Found: (.+)$", full_text_brief)
    missing = re.search(r"(?m)^- Missing or weak: (.+)$", full_text_brief)
    return {
        "signals": ", ".join(signals) if signals else "none detected",
        "section_coverage": found.group(1).strip() if found else "not summarized",
        "missing_sections": missing.group(1).strip() if missing else "not summarized",
    }


def review_queue_next_action(row: dict[str, str]) -> str:
    if not row.get("full_text"):
        return "Attach or sync a local PDF/text path, then rerun `review-queue` or `full-text`."
    if not row.get("brief"):
        return "Run `full-text` to build a section-aware brief, then rebuild the review pack."
    if row.get("signals") and row["signals"] != "none detected":
        return "Open the review pack and verify the flagged figures/tables/data/code before citing."
    return "Open the review pack and inspect methods, results, and limitations manually."


def write_review_context_pack_report(
    profile_path: Path,
    kb_dir: Path,
    paper_id: str | None = None,
    title: str | None = None,
    papers_json: Path | None = None,
    output: Path | None = None,
    feedback_file: Path | None = None,
    full_text_path: Path | None = None,
    full_text_brief_path: Path | None = None,
    limit: int = 12,
    max_full_text_chars: int = 40000,
    max_full_text_brief_chars: int = 16000,
) -> tuple[Path, Path | None, Path | None]:
    from .copilot import render_review_context_pack

    profile = load_profile(profile_path)
    feedback = load_feedback(feedback_file or default_feedback_file(kb_dir))
    records = merged_paper_records(kb_dir, papers_json)
    target = select_paper_record(records, paper_id, title)
    library = paper_records_from_library(kb_dir) or records
    stem = str(target.get("id", "paper") or "paper")
    full_text_candidate = full_text_path or (kb_dir / "full_text" / f"{stem}.txt")
    full_text, actual_full_text_path = read_context_text(full_text_candidate, max_full_text_chars)
    full_text_brief_candidate = full_text_brief_path or (kb_dir / "analysis" / f"{stem}_full_text_brief.md")
    full_text_brief, actual_full_text_brief_path = read_context_text(full_text_brief_candidate, max_full_text_brief_chars)
    output_path = output or (kb_dir / "analysis" / f"{stem}_review_pack.md")
    write_report(
        output_path,
        render_review_context_pack(
            target,
            library,
            profile,
            feedback=feedback,
            full_text=full_text,
            full_text_path=actual_full_text_path,
            full_text_brief=full_text_brief,
            full_text_brief_path=actual_full_text_brief_path,
            limit=limit,
            max_full_text_chars=max_full_text_chars,
            max_full_text_brief_chars=max_full_text_brief_chars,
        ),
    )
    return output_path, actual_full_text_brief_path, actual_full_text_path


def review_pack_command(args: argparse.Namespace) -> None:
    kb_dir = args.kb_dir or default_kb_dir(args.profile, Path("out"))
    output, actual_full_text_brief_path, actual_full_text_path = write_review_context_pack_report(
        profile_path=args.profile,
        kb_dir=kb_dir,
        paper_id=args.paper_id,
        title=args.title,
        papers_json=args.papers_json,
        output=args.output,
        feedback_file=args.feedback_file,
        full_text_path=args.full_text_path,
        full_text_brief_path=args.full_text_brief_path,
        limit=args.limit,
        max_full_text_chars=args.max_full_text_chars,
        max_full_text_brief_chars=args.max_full_text_brief_chars,
    )
    print(f"Review context pack: {output}")
    if actual_full_text_brief_path:
        print(f"Included full-text brief: {actual_full_text_brief_path}")
    else:
        print("Included full-text brief: none")
    if actual_full_text_path:
        print(f"Included full-text cache: {actual_full_text_path}")
    else:
        print("Included full-text cache: none")


def write_paper_workup_report(
    profile_path: Path,
    kb_dir: Path,
    paper_id: str | None = None,
    title: str | None = None,
    papers_json: Path | None = None,
    output: Path | None = None,
    feedback_file: Path | None = None,
    full_text_path: Path | None = None,
    full_text_brief_path: Path | None = None,
    limit: int = 10,
    max_full_text_brief_chars: int = 7000,
) -> tuple[Path, Path | None, Path | None]:
    from .copilot import render_paper_workup

    profile = load_profile(profile_path)
    feedback = load_feedback(feedback_file or default_feedback_file(kb_dir))
    records = merged_paper_records(kb_dir, papers_json)
    target = select_paper_record(records, paper_id, title)
    library = paper_records_from_library(kb_dir) or records
    stem = str(target.get("id", "paper") or "paper")
    actual_full_text_path = full_text_path or (kb_dir / "full_text" / f"{stem}.txt")
    actual_full_text_brief_candidate = full_text_brief_path or (kb_dir / "analysis" / f"{stem}_full_text_brief.md")
    full_text_brief, actual_full_text_brief_path = read_context_text(actual_full_text_brief_candidate, max_full_text_brief_chars)
    output_path = output or (kb_dir / "analysis" / f"{stem}_workup.md")
    write_report(
        output_path,
        render_paper_workup(
            target,
            library,
            profile,
            feedback=feedback,
            full_text_brief=full_text_brief,
            full_text_brief_path=actual_full_text_brief_path,
            has_full_text_cache=actual_full_text_path.exists(),
            limit=limit,
            max_full_text_brief_chars=max_full_text_brief_chars,
        ),
    )
    return output_path, actual_full_text_brief_path, actual_full_text_path if actual_full_text_path.exists() else None


def paper_workup_command(args: argparse.Namespace) -> None:
    kb_dir = args.kb_dir or default_kb_dir(args.profile, Path("out"))
    output, actual_full_text_brief_path, actual_full_text_path = write_paper_workup_report(
        profile_path=args.profile,
        kb_dir=kb_dir,
        paper_id=args.paper_id,
        title=args.title,
        papers_json=args.papers_json,
        output=args.output,
        feedback_file=args.feedback_file,
        full_text_path=args.full_text_path,
        full_text_brief_path=args.full_text_brief_path,
        limit=args.limit,
        max_full_text_brief_chars=args.max_full_text_brief_chars,
    )
    print(f"Paper workup: {output}")
    if actual_full_text_brief_path:
        print(f"Included full-text brief: {actual_full_text_brief_path}")
    else:
        print("Included full-text brief: none")
    if actual_full_text_path:
        print(f"Full-text cache: {actual_full_text_path}")
    else:
        print("Full-text cache: none")


def review_queue_command(args: argparse.Namespace) -> None:
    from .copilot import render_review_context_pack
    from .fulltext import extract_local_text, first_full_text_path, render_full_text_brief

    profile = load_profile(args.profile)
    kb_dir = args.kb_dir or default_kb_dir(args.profile, Path("out"))
    feedback = load_feedback(args.feedback_file or default_feedback_file(kb_dir))
    records = merged_paper_records(kb_dir, args.papers_json)
    if args.paper_id or args.title:
        selected = select_paper_records(records, args.paper_id, args.title)
    else:
        selected = filter_records_for_export(records, split_csv(args.tiers), args.limit)
    if not selected:
        raise SystemExit("No papers selected for review queue. Adjust --tiers, --limit, --paper-id, or --title.")

    library = paper_records_from_library(kb_dir) or records
    output = args.output or (kb_dir / "analysis" / "review_queue.md")
    rows: list[dict[str, str]] = []
    failures: list[str] = []
    extracted_count = 0
    review_count = 0

    for target in selected:
        stem = str(target.get("id", "paper") or "paper")
        text_output = kb_dir / "full_text" / f"{stem}.txt"
        brief_output = kb_dir / "analysis" / f"{stem}_full_text_brief.md"
        review_output = kb_dir / "analysis" / f"{stem}_review_pack.md"
        extract_status = "skipped"
        source_path = ""

        if not args.no_extract:
            try:
                if text_output.exists() and not args.force_extract:
                    extract_status = "cached"
                else:
                    resolved_source = first_full_text_path(target, None)
                    source_path = str(resolved_source)
                    extracted = extract_local_text(resolved_source, max_chars=args.max_chars, timeout=args.timeout)
                    write_report(text_output, extracted.text)
                    write_report(brief_output, render_full_text_brief(target, extracted, profile, text_output))
                    extract_status = f"extracted ({extracted.method})"
                    extracted_count += 1
            except Exception as exc:
                extract_status = f"unavailable: {exc}"
                if args.strict_full_text:
                    failures.append(f"{stem}: {exc}")

        full_text, actual_full_text_path = read_context_text(text_output, args.max_full_text_chars)
        full_text_brief, actual_full_text_brief_path = read_context_text(brief_output, args.max_full_text_brief_chars)
        brief_summary = review_brief_summary(full_text_brief) if full_text_brief else {
            "signals": "none detected",
            "section_coverage": "not available",
            "missing_sections": "not available",
        }
        if args.strict_full_text and not actual_full_text_path:
            failures.append(f"{stem}: no full-text cache available")

        write_report(
            review_output,
            render_review_context_pack(
                target,
                library,
                profile,
                feedback=feedback,
                full_text=full_text,
                full_text_path=actual_full_text_path,
                full_text_brief=full_text_brief,
                full_text_brief_path=actual_full_text_brief_path,
                limit=args.related_limit,
                max_full_text_chars=args.max_full_text_chars,
                max_full_text_brief_chars=args.max_full_text_brief_chars,
            ),
        )
        review_count += 1
        rows.append(
            {
                "id": stem,
                "title": str(target.get("title", "")),
                "tier": str(target.get("tier", "")),
                "score": str(target.get("score", 0)),
                "source": source_path,
                "full_text": str(actual_full_text_path or ""),
                "extract_status": extract_status,
                "brief": str(actual_full_text_brief_path or ""),
                "signals": brief_summary["signals"],
                "section_coverage": brief_summary["section_coverage"],
                "missing_sections": brief_summary["missing_sections"],
                "review_pack": str(review_output),
            }
        )

    brief_count = sum(1 for row in rows if row["brief"])
    text_count = sum(1 for row in rows if row["full_text"])
    signal_count = sum(1 for row in rows if row["signals"] != "none detected")
    lines = [
        "# Review Queue",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Profile: {profile.get('name', 'unnamed')}",
        f"- Selected papers: {len(selected)}",
        f"- Full-text caches extracted: {extracted_count}",
        f"- Review packs written: {review_count}",
        f"- Full-text briefs available: {brief_count}",
        f"- Full-text caches available: {text_count}",
        f"- Papers with visual/data/code signals: {signal_count}",
        "",
        "This queue is local-first. Full-text extraction uses local Zotero/PDF/text paths when available; review packs remain markdown files you can paste into Codex, Claude, ChatGPT, or another assistant.",
        "",
        "## Queue Summary",
        "",
        "- Start with papers that have both a full-text brief and visual/data/code signals.",
        "- Use each `Next action` before citing, adding to Zotero/Obsidian notes, or asking another assistant for a detailed review.",
        "",
        "## Papers",
        "",
    ]
    for index, row in enumerate(rows, 1):
        title = row["title"] or row["id"]
        lines.extend(
            [
                f"### {index}. {title}",
                "",
                f"- ID: `{row['id']}`",
                f"- Tier/score: {row['tier']} / {row['score']}",
                f"- Full-text status: {row['extract_status']}",
                f"- Source path: `{row['source']}`" if row["source"] else "- Source path: not linked",
                f"- Text cache: `{row['full_text']}`" if row["full_text"] else "- Text cache: not available",
                f"- Full-text brief: `{row['brief']}`" if row["brief"] else "- Full-text brief: not written",
                f"- Section coverage: {row['section_coverage']}",
                f"- Missing/weak sections: {row['missing_sections']}",
                f"- Signals: {row['signals']}",
                f"- Next action: {review_queue_next_action(row)}",
                f"- Review pack: `{row['review_pack']}`",
                "",
            ]
        )
    if failures:
        lines.extend(["## Strict Full-Text Failures", ""])
        lines.extend(f"- {failure}" for failure in failures)
        lines.append("")

    write_report(output, "\n".join(lines).rstrip() + "\n")
    html_output = args.html_output or output.with_suffix(".html")
    if not args.no_html:
        write_markdown_html(output, html_output, "Scholar Alert Review Queue")
    print(f"Review queue: {output}")
    if not args.no_html:
        print(f"Review queue HTML: {html_output}")
    print(f"Selected papers: {len(selected)}")
    print(f"Full-text caches extracted: {extracted_count}")
    print(f"Review packs written: {review_count}")
    if failures:
        print("Full-text failures: " + str(len(failures)))
        raise SystemExit(1)


def ask_library_command(args: argparse.Namespace) -> None:
    from .copilot import render_literature_answer

    profile = load_profile(args.profile)
    kb_dir = args.kb_dir or default_kb_dir(args.profile, Path("out"))
    records = merged_paper_records(kb_dir, args.papers_json) if args.papers_json else paper_records_from_library(kb_dir)
    stem = slugify(args.question)[:70] or "question"
    output = args.output or (kb_dir / "answers" / f"{datetime.now().strftime('%Y-%m-%d_%H%M')}_{stem}.md")
    write_report(output, render_literature_answer(args.question, records, profile, limit=args.limit))
    print(f"Literature answer: {output}")


def research_advice_command(args: argparse.Namespace) -> None:
    from .copilot import render_research_advice

    profile = load_profile(args.profile)
    kb_dir = args.kb_dir or default_kb_dir(args.profile, Path("out"))
    feedback_file = args.feedback_file or default_feedback_file(kb_dir)
    feedback = load_feedback(feedback_file)
    records = paper_records_from_library(kb_dir)
    output = args.output or (kb_dir / "research_advice.md")
    write_report(output, render_research_advice(records, profile, feedback=feedback, limit=args.limit))
    print(f"Research advice: {output}")


def available_full_text_ids(kb_dir: Path) -> set[str]:
    full_text_dir = kb_dir / "full_text"
    if not full_text_dir.exists():
        return set()
    return {path.stem for path in full_text_dir.glob("*.txt") if path.is_file()}


def reading_plan_command(args: argparse.Namespace) -> None:
    from .copilot import render_reading_plan

    profile = load_profile(args.profile)
    kb_dir = args.kb_dir or default_kb_dir(args.profile, Path("out"))
    feedback_file = args.feedback_file or default_feedback_file(kb_dir)
    feedback = load_feedback(feedback_file)
    records = merged_paper_records(kb_dir, args.papers_json) if args.papers_json else paper_records_from_library(kb_dir)
    output = args.output or (kb_dir / "reading_plan.md")
    html_output = args.html_output or output.with_suffix(".html")
    write_report(
        output,
        render_reading_plan(
            records,
            profile,
            feedback=feedback,
            limit=args.limit,
            full_text_ids=available_full_text_ids(kb_dir),
        ),
    )
    if not args.no_html:
        write_markdown_html(output, html_output, "Scholar Alert Reading Plan")
    print(f"Reading plan: {output}")
    if not args.no_html:
        print(f"Reading plan HTML: {html_output}")
    print(f"Papers considered: {len(records)}")


READING_STATUSES = {
    "unread",
    "reading",
    "read",
    "must-cite",
    "method-reference",
    "background-only",
    "not-relevant",
}


def write_reading_status_report(kb_dir: Path, records: list[dict[str, Any]], feedback: dict[str, Any]) -> Path:
    from .copilot import render_reading_status

    output = kb_dir / "reading_status.md"
    return write_report(output, render_reading_status(records, feedback=feedback))


def update_reading_status_command(args: argparse.Namespace) -> None:
    kb_dir = args.kb_dir or default_kb_dir(args.profile, Path("out"))
    feedback_file = args.feedback_file or default_feedback_file(kb_dir)
    records = merged_paper_records(kb_dir, args.papers_json)
    selected = select_paper_records(records, args.paper_id, args.title)
    feedback = load_feedback(feedback_file)
    now = datetime.now().isoformat(timespec="seconds")
    labels_to_add = split_csv(args.label)
    labels_to_remove = {label.lower() for label in split_csv(args.remove_label)}
    for record in selected:
        paper_id = str(record.get("id", ""))
        item = feedback.setdefault("papers", {}).setdefault(
            paper_id,
            {
                "id": paper_id,
                "title": record.get("title", ""),
                "url": record.get("url", ""),
                "status": "neutral",
                "signals": {},
                "note": "",
                "created_at": now,
            },
        )
        item["title"] = record.get("title", "")
        item["url"] = record.get("url", "")
        item["updated_at"] = now
        if args.status:
            item["reading_status"] = args.status
            if args.status == "not-relevant":
                item["status"] = "archive"
            elif args.status in {"must-cite", "method-reference", "reading", "read"} and item.get("status") != "archive":
                item["status"] = "interested"
        labels = [str(label) for label in item.get("labels", []) if str(label).strip()]
        for label in labels_to_add:
            if label not in labels:
                labels.append(label)
        labels = [label for label in labels if label.lower() not in labels_to_remove]
        item["labels"] = labels
        if args.note:
            previous = str(item.get("note", "") or "")
            item["note"] = (previous + "\n" + args.note).strip() if previous else args.note
    save_feedback(feedback_file, feedback)
    report = write_reading_status_report(kb_dir, paper_records_from_library(kb_dir), feedback)
    print(f"Feedback updated: {feedback_file}")
    print(f"Reading status: {report}")
    print("Papers: " + ", ".join(str(record.get("id", "")) for record in selected))


def compare_papers_command(args: argparse.Namespace) -> None:
    from .copilot import render_compare

    profile = load_profile(args.profile)
    kb_dir = args.kb_dir or default_kb_dir(args.profile, Path("out"))
    feedback = load_feedback(args.feedback_file or default_feedback_file(kb_dir))
    records = merged_paper_records(kb_dir, args.papers_json)
    selected = select_paper_records(records, args.paper_id, args.title)
    stem = "-".join(str(record.get("id", "")) for record in selected[:5]) or "papers"
    output = args.output or (kb_dir / "comparisons" / f"{datetime.now().strftime('%Y-%m-%d_%H%M')}_{stem}.md")
    write_report(output, render_compare(selected, profile, feedback=feedback))
    print(f"Paper comparison: {output}")


def research_map_command(args: argparse.Namespace) -> None:
    from .copilot import render_research_map

    profile = load_profile(args.profile)
    kb_dir = args.kb_dir or default_kb_dir(args.profile, Path("out"))
    feedback = load_feedback(args.feedback_file or default_feedback_file(kb_dir))
    records = paper_records_from_library(kb_dir)
    output = args.output or (kb_dir / "research_map.md")
    write_report(output, render_research_map(records, profile, feedback=feedback, limit=args.limit))
    print(f"Research map: {output}")


def zotero_export_command(args: argparse.Namespace) -> None:
    from .export import export_records

    kb_dir = args.kb_dir or default_kb_dir(args.profile, Path("out"))
    records = load_paper_records(args.papers_json) if args.papers_json else paper_records_from_library(kb_dir)
    selected = filter_records_for_export(records, split_csv(args.tiers), args.limit)
    out_dir = args.output_dir or (kb_dir / "zotero")
    out_dir.mkdir(parents=True, exist_ok=True)
    bib = out_dir / "scholar_alert_reader.bib"
    ris = out_dir / "scholar_alert_reader.ris"
    bib.write_text(export_records(selected, "bibtex"), encoding="utf-8")
    ris.write_text(export_records(selected, "ris"), encoding="utf-8")
    print(f"Zotero BibTeX: {bib}")
    print(f"Zotero RIS: {ris}")
    print(f"Exported papers: {len(selected)}")


def preferred_citation_key(record: dict[str, Any], existing: set[str]) -> str:
    zotero = record.get("metadata", {}).get("zotero") if isinstance(record.get("metadata"), dict) else {}
    key = str(zotero.get("citation_key", "")).strip() if isinstance(zotero, dict) else ""
    if key and key not in existing:
        existing.add(key)
        return key
    from .export import cite_key

    return cite_key(record, existing)


def obsidian_export_command(args: argparse.Namespace) -> None:
    from .copilot import (
        obsidian_note_name,
        render_obsidian_index,
        render_obsidian_paper,
        render_reading_status,
        render_research_map,
    )

    profile = load_profile(args.profile)
    kb_dir = args.kb_dir or default_kb_dir(args.profile, Path("out"))
    feedback = load_feedback(args.feedback_file or default_feedback_file(kb_dir))
    records = paper_records_from_library(kb_dir)
    records = filter_records_for_export(records, split_csv(args.tiers), args.limit)
    vault_dir = args.vault_dir or (kb_dir / "obsidian")
    dashboard_dir = vault_dir / "00_Dashboard"
    papers_dir = vault_dir / "01_Papers"
    maps_dir = vault_dir / "02_Maps"
    reading_dir = vault_dir / "03_Reading"
    answers_dir = vault_dir / "04_Answers"
    comparisons_dir = vault_dir / "05_Comparisons"
    deep_reads_dir = vault_dir / "06_Deep_Reads"
    for directory in [dashboard_dir, papers_dir, maps_dir, reading_dir, answers_dir, comparisons_dir, deep_reads_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    (dashboard_dir / "Scholar Alert Dashboard.md").write_text(
        render_obsidian_index(records, feedback=feedback), encoding="utf-8"
    )
    (maps_dir / "Research Map.md").write_text(render_research_map(records, profile, feedback=feedback), encoding="utf-8")
    (reading_dir / "Reading Status.md").write_text(render_reading_status(records, feedback=feedback), encoding="utf-8")
    existing_citation_keys: set[str] = set()
    for record in records:
        citation_key = preferred_citation_key(record, existing_citation_keys)
        (papers_dir / f"{obsidian_note_name(record)}.md").write_text(
            render_obsidian_paper(record, feedback=feedback, citation_key=citation_key),
            encoding="utf-8",
        )
    copied_answers = copy_markdown_outputs(kb_dir / "answers", answers_dir)
    copied_comparisons = copy_markdown_outputs(kb_dir / "comparisons", comparisons_dir)
    copied_deep_reads = copy_markdown_outputs(kb_dir / "analysis", deep_reads_dir)
    print(f"Obsidian export: {vault_dir}")
    print(f"Paper notes: {len(records)}")
    print(f"Copied answers: {copied_answers}")
    print(f"Copied comparisons: {copied_comparisons}")
    print(f"Copied deep reads: {copied_deep_reads}")


def copy_markdown_outputs(source_dir: Path, target_dir: Path) -> int:
    if not source_dir.exists():
        return 0
    count = 0
    for source in sorted(source_dir.glob("*.md")):
        shutil.copy2(source, target_dir / source.name)
        count += 1
    return count


def doctor_command(args: argparse.Namespace) -> None:
    from .diagnostics import diagnose, render_checks

    kb_dir = args.kb_dir
    if kb_dir is None and args.profile:
        kb_dir = default_kb_dir(args.profile, Path("out"))
    checks, notes = diagnose(
        profile=args.profile,
        kb_dir=kb_dir,
        gmail_credentials=args.gmail_credentials,
        gmail_token=args.gmail_token,
        out_dir=args.out_dir,
        check_gmail_deps=args.gmail_deps,
        obsidian_dir=args.obsidian_dir,
        zotero_dir=args.zotero_dir,
    )
    report = render_checks(checks, notes)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"Doctor report: {args.output}")
    else:
        print(report.rstrip())


def support_bundle_command(args: argparse.Namespace) -> None:
    output = args.output.expanduser() if args.output else args.project_dir.expanduser() / "SUPPORT_BUNDLE.md"
    report = render_support_bundle(args)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"Support bundle: {output}")
    print("Review before posting publicly. Do not attach reader.env, tokens, raw mailboxes, feedback.json, or generated knowledge bases.")


def render_capability_report(project_dir: Path | None = None) -> str:
    project_dir = project_dir.expanduser().resolve(strict=False) if project_dir else None
    lines = [
        "# Scholar Alert Reader Capabilities",
        "",
        f"- Version: {__version__}",
        "- Product shape: local literature triage, reading queues, and research-memory maintenance.",
        "- Privacy shape: local-first files and optional local browser UI; no hosted account or cloud database is required.",
        "",
        "## Good At",
        "",
        "- Reading Scholar Alert emails through Gmail API, Apple Mail, or exported `.mbox` archives.",
        "- Importing BibTeX/RIS exports, structured scholarly webpage metadata, RSS/Atom feeds, and arXiv queries.",
        "- Deduplicating repeated papers across alerts and sources.",
        "- Ranking papers with profile terms, methods, regions, watched authors, exclusions, semantic queries, temporary boosts, and adaptive local feedback similarity.",
        "- Producing HTML/Markdown digests, CSV/JSON outputs, and a retained local knowledge base.",
        "- Capturing feedback such as interested, archive, more-like-this, less-like-this, reading, read, must-cite, and method-reference labels.",
        "- Turning retained/recent papers into a next-reading plan with concrete follow-up commands.",
        "- Producing a selected-paper workup that connects one paper to the user's foundation, interested papers, full-text brief, and possible manuscript role.",
        "- Exporting Zotero-ready BibTeX/RIS and Obsidian-ready Markdown while keeping both integrations optional.",
        "",
        "## Capability Boundary",
        "",
        "- `deep-read`, `workup`, `ask`, `compare`, `map`, and `advice` start from alert metadata, bibliography fields, snippets, local profile terms, retained-library context, and feedback signals.",
        "- `semantic_queries` and adaptive ranking are lightweight local matching features, not a hosted embedding service or a neural reranker.",
        "- `full-text` works when a local PDF/text path is provided directly or synced from Zotero; it does not automatically bypass publisher access or download paywalled PDFs.",
        "- `review-pack` creates a markdown context pack for Codex, Claude, ChatGPT, or another assistant. It does not upload data or claim autonomous expert peer review.",
        "- Web import reads structured scholarly metadata from configured URLs, saved HTML, or URL/path lists. It is not a general-purpose crawler.",
        "",
        "## Not Promised",
        "",
        "- No automatic full-paper understanding unless the user provides local full text and an assistant reviews the generated context pack.",
        "- No guarantee that title-based metadata enrichment from OpenAlex/Crossref is perfect; ambiguous matches still need human review.",
        "- No team server, multi-user permissions, hosted sync, or shared OAuth client in the public repo.",
        "- No need for Obsidian, Zotero, Gmail, or Codex if the user only wants the Python CLI and local files.",
        "",
        "## Best Next Workflow",
        "",
        "1. Run `self-test` or `./self_test.sh` with bundled data.",
        "2. Run `setup-wizard` or `./setup_wizard.sh` to pick source, profile, schedule, and optional integrations.",
        "3. Run `source-check --live` before expecting non-empty daily results.",
        "4. Build an initial `foundation`, then use `daily` for new papers only.",
        "5. Mark interested/archive papers and rerun `profile-tune` after several feedback rounds.",
        "6. Sync Zotero local PDF paths when available, then run `full-text`, `workup`, `review-pack`, or `review-queue` for selected papers.",
        "",
        "## Practical Upgrade Path",
        "",
        "- For better ranking: tune profile terms, add `semantic_queries`, and use more-like-this / less-like-this feedback.",
        "- For closer reading: use Zotero or explicit local PDF paths with `full-text`, then run `workup` for a human decision brief or `review-pack` for an assistant context pack.",
        "- For knowledge management: export generated notes to Obsidian, but keep human-written notes outside generated folders.",
        "- For public support: run `support-bundle` and review the redacted output before posting a GitHub issue.",
        "",
    ]
    if project_dir:
        env_values = read_project_env(project_env_path(project_dir))
        lines.extend(
            [
                "## Local Project Snapshot",
                "",
                f"- Project: `{safe_display_path(project_dir, project_dir)}`",
                f"- Profile: {path_status(str(project_dir / 'profiles' / 'research_profile.json'), project_dir)}",
                f"- Run script: {path_status(str(project_dir / 'run_reader.sh'), project_dir)}",
                f"- Setup wizard: {path_status(str(project_dir / 'setup_wizard.sh'), project_dir)}",
                f"- Source check: {path_status(str(project_dir / 'SOURCE_CHECK.md'), project_dir)}",
                f"- Daily digest: {path_status(str(project_dir / 'reader_out' / 'daily' / 'digest.html'), project_dir)}",
                f"- Retained library: {json_summary(project_dir / 'knowledge_base' / 'library.json')}",
                f"- Feedback records: {json_summary(project_dir / 'knowledge_base' / 'feedback.json')}",
                "",
            ]
        )
        if env_values:
            lines.extend(["### Configured Defaults", ""])
            for key in ["SOURCE", "MODE", "SCHEDULE_TIME", "SCHEDULE_DAYS", "SCHEDULE_TIMEZONE"]:
                if env_values.get(key):
                    lines.append(f"- {key}: {support_env_value(key, env_values[key], project_dir)}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def capabilities_command(args: argparse.Namespace) -> None:
    report = render_capability_report(args.project_dir)
    if args.output:
        output = args.output.expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
        print(f"Capability report: {output}")
    else:
        print(report.rstrip())


def guide_command(args: argparse.Namespace) -> None:
    project_dir = args.project_dir.expanduser().resolve()
    profile_path = (args.profile or (project_dir / "profiles" / "research_profile.json")).expanduser()
    kb_dir = (args.kb_dir or (project_dir / "knowledge_base")).expanduser()
    out_dir = (args.out_dir or (project_dir / "reader_out")).expanduser()
    obsidian_dir = args.obsidian_dir.expanduser() if args.obsidian_dir else None
    zotero_dir = args.zotero_dir.expanduser() if args.zotero_dir else None
    report = render_project_guide(
        project_dir=project_dir,
        profile_path=profile_path,
        kb_dir=kb_dir,
        out_dir=out_dir,
        obsidian_dir=obsidian_dir,
        zotero_dir=zotero_dir,
    )
    if args.output:
        output = args.output.expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
        print(f"Guide written: {output}")
    else:
        print(report.rstrip())


def run_quickstart_step(name: str, cmd: list[str], cwd: Path) -> tuple[str, bool, str]:
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    output = result.stdout.strip() or result.stderr.strip()
    if result.returncode != 0 and result.stderr.strip():
        output = result.stderr.strip()
    detail = output.splitlines()[-1] if output else f"exit {result.returncode}"
    return name, result.returncode == 0, detail


def quickstart_command(args: argparse.Namespace) -> None:
    project_dir = args.project_dir.expanduser().resolve()
    needs_init = not (project_dir / "run_reader.sh").exists()
    if needs_init or args.force:
        init_project(
            argparse.Namespace(
                project_dir=project_dir,
                profile_template=args.profile_template,
                force=args.force,
                quiet=True,
            )
        )
    elif not project_dir.exists():
        raise SystemExit(f"Project directory does not exist: {project_dir}")
    elif not (project_dir / "profiles" / "research_profile.json").exists():
        raise SystemExit(f"Existing project is missing profiles/research_profile.json: {project_dir}")

    checks: list[tuple[str, bool, str]] = []
    if not args.skip_self_test:
        checks.append(run_quickstart_step("self-test", [str(project_dir / "self_test.sh"), "--strict"], project_dir))
    if not args.skip_demos:
        checks.append(run_quickstart_step("multi-source demo", [str(project_dir / "demo_sources.sh")], project_dir))
    checks.append(
        run_quickstart_step(
            "source check",
            [str(project_dir / "source_check.sh"), "--source", "auto", "--output", str(project_dir / "SOURCE_CHECK.md")],
            project_dir,
        )
    )
    checks.append(
        run_quickstart_step(
            "doctor",
            [str(project_dir / "doctor_reader.sh"), "--output", str(project_dir / "DOCTOR.md")],
            project_dir,
        )
    )
    checks.append(
        run_quickstart_step(
            "guide",
            [str(project_dir / "guide_reader.sh"), "--output", str(project_dir / "START_HERE.md")],
            project_dir,
        )
    )
    checks.append(
        run_quickstart_step(
            "dashboard",
            [str(project_dir / "dashboard_reader.sh")],
            project_dir,
        )
    )
    passed = all(ok for _, ok, _ in checks)
    report_path = (args.output.expanduser() if args.output else project_dir / "QUICKSTART_REPORT.md").resolve()
    lines = [
        "# Scholar Alert Reader Quickstart Report",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Result: {'PASS' if passed else 'WARN'}",
        f"- Project: `{project_dir}`",
        f"- Version: `{__version__}`",
        "",
        "## Checks",
        "",
    ]
    for name, ok, detail in checks:
        marker = "OK" if ok else "WARN"
        lines.append(f"- [{marker}] {name}: {detail}")
    lines.extend(
        [
            "",
            "## Open These First",
            "",
            f"- Dashboard: `{project_dir / 'DASHBOARD.html'}`",
            f"- Onboarding guide: `{project_dir / 'START_HERE.md'}`",
            f"- Source check: `{project_dir / 'SOURCE_CHECK.md'}`",
            f"- Doctor report: `{project_dir / 'DOCTOR.md'}`",
            f"- mbox demo digest: `{project_dir / 'reader_out' / 'demo_sources' / 'mbox' / 'digest.html'}`",
            f"- BibTeX demo digest: `{project_dir / 'reader_out' / 'demo_sources' / 'bibtex' / 'digest.html'}`",
            f"- RIS demo digest: `{project_dir / 'reader_out' / 'demo_sources' / 'ris' / 'digest.html'}`",
            f"- Web metadata demo digest: `{project_dir / 'reader_out' / 'demo_sources' / 'web' / 'digest.html'}`",
            f"- RSS demo digest: `{project_dir / 'reader_out' / 'demo_sources' / 'rss' / 'digest.html'}`",
            "",
            "## Next Steps",
            "",
            "1. Edit `profiles/research_profile.json` to match your research directions.",
            "2. Run `./setup_wizard.sh` for guided configuration, or `./setup_reader.sh --source auto --profile-template <template>` for non-interactive setup.",
            "3. Configure one real source: Gmail, Mail.app, mbox, BibTeX/RIS, web metadata, RSS, or arXiv.",
            "4. Run `./source_check.sh --source auto --live` before expecting daily digests.",
            "5. See project `TROUBLESHOOTING.md` if a source returns no papers.",
            "",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Quickstart report: {report_path}")
    print(f"Project: {project_dir}")
    print(f"Result: {'PASS' if passed else 'WARN'}")
    if args.strict and not passed:
        raise SystemExit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-profile", help="Copy the default profile to a writable path")
    init.add_argument("--profile", type=Path, required=True)
    init.add_argument(
        "--template",
        default=DEFAULT_PROFILE_TEMPLATE,
        help="Bundled template slug or JSON path. Use list-profile-templates to inspect bundled choices.",
    )
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=lambda args: init_profile(args.profile, args.force, args.template))

    list_templates = sub.add_parser("list-profile-templates", help="List bundled research profile templates")
    list_templates.set_defaults(func=lambda args: print("\n".join(available_profile_templates())))

    init_project_cmd = sub.add_parser("init-project", help="Create a runnable local Scholar Alert Reader project")
    init_project_cmd.add_argument("--project-dir", type=Path, required=True)
    init_project_cmd.add_argument(
        "--profile-template",
        default=DEFAULT_PROFILE_TEMPLATE,
        help="Bundled template slug or JSON path used for profiles/research_profile.json",
    )
    init_project_cmd.add_argument("--force", action="store_true", help="Add/update scaffold files in a non-empty directory")
    init_project_cmd.set_defaults(func=init_project)

    quickstart = sub.add_parser("quickstart", help="Create a local project and run private-data-free setup checks")
    quickstart.add_argument("--project-dir", type=Path, default=Path("~/scholar_alerts"), help="Local project directory. Defaults to ~/scholar_alerts")
    quickstart.add_argument(
        "--profile-template",
        default=DEFAULT_PROFILE_TEMPLATE,
        help="Bundled template slug or JSON path used for profiles/research_profile.json",
    )
    quickstart.add_argument("--force", action="store_true", help="Add/update scaffold files in a non-empty directory")
    quickstart.add_argument("--skip-self-test", action="store_true", help="Skip generated self_test.sh")
    quickstart.add_argument("--skip-demos", action="store_true", help="Skip generated demo_sources.sh")
    quickstart.add_argument("--strict", action="store_true", help="Exit non-zero if any quickstart check fails")
    quickstart.add_argument("--output", type=Path, help="Write quickstart report to this path. Defaults to project-dir/QUICKSTART_REPORT.md")
    quickstart.set_defaults(func=quickstart_command)

    setup = sub.add_parser("setup", help="Write persistent local project defaults to reader.env")
    setup.add_argument("--project-dir", type=Path, default=Path("."), help="Local Scholar Alert Reader project directory")
    setup.add_argument("--source", choices=SOURCE_CHOICES, default="auto")
    setup.add_argument("--mode", choices=MODE_CHOICES, default="daily")
    setup.add_argument("--profile", type=Path, help="Profile path. Defaults to project-dir/profiles/research_profile.json")
    setup.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to project-dir/knowledge_base")
    setup.add_argument("--profile-template", help="Bundled profile template slug or JSON path to copy into the active profile")
    setup.add_argument("--force-profile", action="store_true", help="Overwrite the profile without creating a .bak copy")
    setup.add_argument("--mbox-path", type=Path, help="Local mbox path. Defaults to project-dir/INBOX.mbox")
    setup.add_argument("--bibtex-path", type=Path, help="BibTeX import path. Defaults to project-dir/import.bib")
    setup.add_argument("--ris-path", type=Path, help="RIS import path. Defaults to project-dir/import.ris")
    setup.add_argument("--web-source", help="Scholarly webpage URL, saved HTML file/directory, or URL/path list. Defaults to project-dir/web_sources.txt")
    setup.add_argument("--rss-source", help="RSS/Atom URL, feed file, directory, or text file. Defaults to project-dir/feeds.txt")
    setup.add_argument("--arxiv-query", help="arXiv API search query, required with --source arxiv")
    setup.add_argument("--gmail-credentials", type=Path, default=DEFAULT_GMAIL_CREDENTIALS)
    setup.add_argument("--gmail-token", type=Path, default=DEFAULT_GMAIL_TOKEN)
    setup.add_argument("--auto-allow-mail-app", action="store_true", help="Allow auto source selection to fall back to Mail.app on macOS")
    setup.add_argument("--obsidian-dir", type=Path, help="Generated Obsidian export folder")
    setup.add_argument("--zotero-dir", type=Path, help="Zotero BibTeX/RIS export folder")
    setup.add_argument("--schedule-time", help="Preferred wall-clock run time, e.g. 09:00")
    setup.add_argument("--schedule-days", help="Preferred schedule days, e.g. Monday,Wednesday,Friday or weekdays")
    setup.add_argument("--timezone", help="Preferred schedule timezone")
    setup.add_argument("--since-days", type=int, help="Default recent-window days for manual/recent runs")
    setup.add_argument("--boost", help="Comma-separated temporary priority terms")
    setup.add_argument("--output", type=Path, help="Config output path. Defaults to project-dir/reader.env")
    setup.add_argument("--no-guide", action="store_true", help="Do not refresh START_HERE.md after writing config")
    setup.set_defaults(func=setup_project)

    schedule = sub.add_parser("schedule", help="Render, install, inspect, or uninstall a local macOS LaunchAgent schedule")
    schedule.add_argument("--project-dir", type=Path, required=True, help="Local Scholar Alert Reader project directory")
    schedule.add_argument("--action", choices=["write", "install", "status", "uninstall"], default="write")
    schedule.add_argument("--time", help="Wall-clock run time, e.g. 09:00. Defaults to reader.env SCHEDULE_TIME")
    schedule.add_argument("--days", help="Run days: weekdays, daily, weekends, or comma-separated day names. Defaults to reader.env SCHEDULE_DAYS")
    schedule.add_argument("--timezone", help="Timezone note for the report. launchd uses the Mac system timezone.")
    schedule.add_argument("--label", help="LaunchAgent label. Defaults to a stable project-specific label")
    schedule.add_argument("--output", type=Path, help="Plist path. Defaults to project LaunchAgents/ for write and ~/Library/LaunchAgents/ for install/status/uninstall")
    schedule.add_argument("--report", type=Path, help="Schedule report path. Defaults to project-dir/SCHEDULE.md")
    schedule.add_argument("--run-at-load", action="store_true", help="Ask launchd to run once when the job is loaded")
    schedule.add_argument("--dry-run", action="store_true", help="Validate and report without writing/removing plist files or calling launchctl")
    schedule.set_defaults(func=schedule_command)

    wizard = sub.add_parser("setup-wizard", aliases=["wizard"], help="Interactively configure a local project and write reader.env")
    wizard.add_argument("--project-dir", type=Path, default=Path("~/scholar_alerts"), help="Local Scholar Alert Reader project directory")
    wizard.add_argument("--source", choices=SOURCE_CHOICES, help="Input source. If omitted, prompt or use reader.env/default.")
    wizard.add_argument("--mode", choices=MODE_CHOICES, help="Run mode. If omitted, prompt or use reader.env/default.")
    wizard.add_argument("--profile", type=Path, help="Profile path. Defaults to project-dir/profiles/research_profile.json")
    wizard.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to project-dir/knowledge_base")
    wizard.add_argument("--profile-template", help="Bundled profile template slug or JSON path")
    wizard.add_argument("--force-profile", action="store_true", help="Overwrite the active profile without creating a .bak copy")
    wizard.add_argument("--force-init", action="store_true", help="Allow initializing or refreshing a non-empty project directory")
    wizard.add_argument("--no-init", action="store_true", help="Require an already initialized project")
    wizard.add_argument("--mbox-path", type=Path, help="Local mbox path")
    wizard.add_argument("--bibtex-path", type=Path, help="BibTeX import path")
    wizard.add_argument("--ris-path", type=Path, help="RIS import path")
    wizard.add_argument("--web-source", help="Scholarly webpage URL, saved HTML file/directory, or URL/path list")
    wizard.add_argument("--rss-source", help="RSS/Atom URL, feed file, directory, or text file")
    wizard.add_argument("--arxiv-query", help="arXiv API search query")
    wizard.add_argument("--gmail-credentials", type=Path, default=DEFAULT_GMAIL_CREDENTIALS)
    wizard.add_argument("--gmail-token", type=Path, default=DEFAULT_GMAIL_TOKEN)
    wizard.add_argument("--auto-allow-mail-app", action="store_true", help="Allow auto source selection to fall back to Mail.app on macOS")
    wizard.add_argument("--obsidian-dir", type=Path, help="Generated Obsidian export folder")
    wizard.add_argument("--zotero-dir", type=Path, help="Zotero BibTeX/RIS export folder")
    wizard.add_argument("--schedule-time", help="Preferred wall-clock run time, e.g. 09:00")
    wizard.add_argument("--schedule-days", help="Preferred schedule days, e.g. Monday,Wednesday,Friday or weekdays")
    wizard.add_argument("--timezone", help="Preferred schedule timezone")
    wizard.add_argument("--since-days", type=int, help="Default recent-window days for manual/recent runs")
    wizard.add_argument("--boost", help="Comma-separated temporary priority terms")
    wizard.add_argument("--output", type=Path, help="Config output path. Defaults to project-dir/reader.env")
    wizard.add_argument("--no-guide", action="store_true", help="Do not refresh START_HERE.md after writing config")
    wizard.add_argument("--defaults", action="store_true", help="Accept defaults and skip prompts; useful for CI or scripted setup")
    wizard.add_argument("--skip-check", action="store_true", help="Do not write SOURCE_CHECK.md after configuration")
    wizard.add_argument("--live-check", action="store_true", help="Attempt a real source read after configuration")
    wizard.add_argument("--check-output", type=Path, help="Source check report path. Defaults to project-dir/SOURCE_CHECK.md")
    wizard.add_argument("--check-strict", action="store_true", help="Exit non-zero when the post-setup source check warns")
    wizard.add_argument("--check-limit", type=int, default=1, help="Max items/messages to read during --live-check")
    wizard.add_argument("--check-timeout", type=int, default=20, help="Source check timeout in seconds")
    wizard.set_defaults(func=setup_wizard)

    guide = sub.add_parser("guide", help="Render a product-oriented setup and status guide for a local project")
    guide.add_argument("--project-dir", type=Path, default=Path("."), help="Local Scholar Alert Reader project directory")
    guide.add_argument("--profile", type=Path, help="Profile path. Defaults to project-dir/profiles/research_profile.json")
    guide.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to project-dir/knowledge_base")
    guide.add_argument("--out-dir", type=Path, help="Output root. Defaults to project-dir/reader_out")
    guide.add_argument("--obsidian-dir", type=Path, help="Optional Obsidian generated export directory")
    guide.add_argument("--zotero-dir", type=Path, help="Optional Zotero export directory. Defaults to kb-dir/zotero")
    guide.add_argument("--output", type=Path, help="Write guide markdown to this path instead of stdout")
    guide.set_defaults(func=guide_command)

    dashboard = sub.add_parser("dashboard", help="Write a local project dashboard linking current outputs and next actions")
    dashboard.add_argument("--project-dir", type=Path, required=True)
    dashboard.add_argument("--profile", type=Path, help="Profile path. Defaults to project-dir/profiles/research_profile.json")
    dashboard.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to project-dir/knowledge_base")
    dashboard.add_argument("--out-dir", type=Path, help="Output directory for the latest run. Defaults to project-dir/reader_out/daily")
    dashboard.add_argument("--output", type=Path, help="Output markdown path. Defaults to project-dir/DASHBOARD.md")
    dashboard.add_argument("--html-output", type=Path, help="Output HTML path. Defaults to markdown output with .html suffix")
    dashboard.add_argument("--no-html", action="store_true", help="Do not write a browser-friendly HTML dashboard")
    dashboard.add_argument("--open", action="store_true", help="Open the dashboard in the default browser")
    dashboard.set_defaults(func=dashboard_command)

    source_check = sub.add_parser("source-check", help="Check Gmail, Mail.app, mbox, BibTeX, RIS, web metadata, RSS/Atom, arXiv, or auto source readiness")
    source_check.add_argument("--source", choices=["auto", "gmail", "mail-app", "mbox", "bibtex", "ris", "web", "rss", "arxiv"], default="auto")
    source_check.add_argument("--project-dir", type=Path, default=Path("."), help="Local Scholar Alert Reader project directory")
    source_check.add_argument("--mbox-path", type=Path, help="mbox path. Defaults to project-dir/INBOX.mbox")
    source_check.add_argument("--bibtex-path", type=Path, help="BibTeX path. Defaults to project-dir/import.bib")
    source_check.add_argument("--ris-path", type=Path, help="RIS path. Defaults to project-dir/import.ris")
    source_check.add_argument("--web-source", help="Scholarly webpage URL, saved HTML file/directory, or URL/path list. Defaults to project-dir/web_sources.txt")
    source_check.add_argument("--rss-source", help="RSS/Atom URL, feed file, directory, or text file. Defaults to project-dir/feeds.txt")
    source_check.add_argument("--arxiv-query", help="arXiv API search query for source-check --source arxiv")
    source_check.add_argument("--arxiv-limit", type=int, help="Max arXiv results to fetch during --live; defaults to --limit")
    source_check.add_argument("--web-limit", type=int, help="Max webpage metadata papers to read during --live; defaults to --limit")
    source_check.add_argument("--web-timeout", type=int, help="Webpage metadata HTTP timeout during --live; defaults to --timeout")
    source_check.add_argument("--gmail-credentials", type=Path, default=DEFAULT_GMAIL_CREDENTIALS)
    source_check.add_argument("--gmail-token", type=Path, default=DEFAULT_GMAIL_TOKEN)
    source_check.add_argument("--gmail-query", help="Additional Gmail search query terms")
    source_check.add_argument("--since-days", type=int, help="Only check messages newer than this many days")
    source_check.add_argument("--limit", type=int, default=1, help="Max messages to fetch/export during --live")
    source_check.add_argument("--timeout", type=int, default=20, help="Mail.app/web/RSS/arXiv live-check timeout in seconds")
    source_check.add_argument("--live", action="store_true", help="Attempt a real read from the selected source")
    source_check.add_argument("--allow-mail-app", action="store_true", help="Allow auto mode to select macOS Mail.app")
    source_check.add_argument("--strict", action="store_true", help="Exit non-zero if any check warns")
    source_check.add_argument("--output", type=Path, help="Write markdown report to this path")
    source_check.set_defaults(func=source_check_command)

    self_test = sub.add_parser("self-test", help="Run a bundled-data end-to-end installation smoke test")
    self_test.add_argument("--project-dir", type=Path, help="Optional self-test project directory. Defaults to a temporary directory.")
    self_test.add_argument("--profile-template", default="ai-seismology", help="Bundled profile template used for the temporary test project")
    self_test.add_argument("--keep", action="store_true", help="Keep the temporary self-test project for inspection")
    self_test.add_argument("--force", action="store_true", help="Allow reusing a non-empty --project-dir")
    self_test.add_argument("--strict", action="store_true", help="Exit non-zero if any self-test check warns")
    self_test.add_argument("--output", type=Path, help="Write markdown report to this path")
    self_test.set_defaults(func=self_test_command)

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
    run_cmd.add_argument("--no-kb-update", action="store_true", help="Write run outputs without modifying the cumulative knowledge base")
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

    profile_tune = sub.add_parser("profile-tune", help="Suggest profile updates from interested/archive feedback")
    profile_tune.add_argument("--profile", type=Path, required=True)
    profile_tune.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to profile parent/knowledge_base")
    profile_tune.add_argument("--feedback-file", type=Path, help="Feedback JSON. Defaults to kb-dir/feedback.json")
    profile_tune.add_argument("--papers-json", type=Path, help="Optional digest papers.json to include recent papers")
    profile_tune.add_argument("--limit", type=int, default=8, help="Maximum suggestions per section")
    profile_tune.add_argument("--apply", action="store_true", help="Write suggested focus/exclude/semantic terms into the profile")
    profile_tune.add_argument("--focus-weight", type=int, default=4)
    profile_tune.add_argument("--exclude-weight", type=int, default=4)
    profile_tune.add_argument("--semantic-weight", type=int, default=4)
    profile_tune.add_argument("--output", type=Path, help="Output markdown path. Defaults to kb-dir/profile_tuning.md")
    profile_tune.set_defaults(func=profile_tune_command)

    serve_cmd = sub.add_parser("serve", help="Start a local browser UI for paper feedback")
    serve_cmd.add_argument("--profile", type=Path, required=True)
    serve_cmd.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to profile parent/knowledge_base")
    serve_cmd.add_argument("--papers-json", type=Path, default=Path("out/daily/papers.json"))
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=8765)
    serve_cmd.add_argument("--open", action="store_true", help="Open the UI in the default browser")
    serve_cmd.set_defaults(func=serve_feedback_ui)

    enrich_cmd = sub.add_parser("enrich", help="Enrich selected papers with OpenAlex/Crossref metadata")
    enrich_cmd.add_argument("--profile", type=Path, required=True)
    enrich_cmd.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to profile parent/knowledge_base")
    enrich_cmd.add_argument("--papers-json", type=Path, help="Paper JSON to enrich. Defaults to kb-dir/library.json")
    enrich_cmd.add_argument("--output", type=Path, help="Output JSON. Defaults to overwriting the input JSON")
    enrich_cmd.add_argument("--providers", default="openalex,crossref", help="Comma-separated providers: openalex,crossref")
    enrich_cmd.add_argument("--limit", type=int, default=20, help="Max top-ranked records to enrich")
    enrich_cmd.add_argument("--email", help="Optional email for polite API user-agent/mailto")
    enrich_cmd.add_argument("--timeout", type=int, default=12)
    enrich_cmd.add_argument("--update-library", action="store_true", help="Merge enriched metadata back into kb-dir/library.json")
    enrich_cmd.set_defaults(func=enrich_metadata)

    weekly_cmd = sub.add_parser("weekly", help="Render a weekly synthesis from the retained library")
    weekly_cmd.add_argument("--profile", type=Path, required=True)
    weekly_cmd.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to profile parent/knowledge_base")
    weekly_cmd.add_argument("--days", type=int, default=7)
    weekly_cmd.add_argument("--limit", type=int, default=12)
    weekly_cmd.add_argument("--output", type=Path, help="Output markdown path. Defaults to kb-dir/weekly_review.md")
    weekly_cmd.set_defaults(func=write_weekly_command)

    export_cmd = sub.add_parser("export", help="Export retained papers to BibTeX, RIS, Markdown, or JSONL")
    export_cmd.add_argument("--profile", type=Path, required=True)
    export_cmd.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to profile parent/knowledge_base")
    export_cmd.add_argument("--papers-json", type=Path, help="Paper JSON to export. Defaults to kb-dir/library.json")
    export_cmd.add_argument("--format", choices=["bibtex", "ris", "markdown", "jsonl"], default="bibtex")
    export_cmd.add_argument("--tiers", default="Must read,Skim", help="Comma-separated tiers to export; empty means all")
    export_cmd.add_argument("--limit", type=int, default=0, help="Max papers to export; 0 means no limit")
    export_cmd.add_argument("--output", type=Path, help="Output path. Defaults to kb-dir/export.<ext>")
    export_cmd.set_defaults(func=export_library)

    deep = sub.add_parser("deep-read", help="Analyze one selected paper against the local foundation/interested library")
    deep.add_argument("--profile", type=Path, required=True)
    deep.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to profile parent/knowledge_base")
    deep.add_argument("--papers-json", type=Path, help="Optional digest papers.json to select a paper that is not yet retained")
    deep.add_argument("--paper-id", help="Paper ID from a digest or paper note")
    deep.add_argument("--title", help="Case-insensitive title substring")
    deep.add_argument("--limit", type=int, default=12, help="Related foundation papers to include")
    deep.add_argument("--output", type=Path, help="Output markdown path. Defaults to kb-dir/analysis/<paper-id>_deep_read.md")
    deep.set_defaults(func=deep_read_command)

    full_text = sub.add_parser("full-text", help="Extract local PDF/text content and write a full-text reading brief")
    full_text.add_argument("--profile", type=Path, required=True)
    full_text.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to profile parent/knowledge_base")
    full_text.add_argument("--papers-json", type=Path, help="Optional digest papers.json to select a paper that is not yet retained")
    full_text.add_argument("--paper-id", help="Paper ID from a digest or paper note")
    full_text.add_argument("--title", help="Case-insensitive title substring")
    full_text.add_argument("--pdf-path", type=Path, help="Explicit local PDF/text path. Defaults to metadata.zotero.pdf_paths")
    full_text.add_argument("--max-chars", type=int, default=120000, help="Maximum extracted text characters to cache")
    full_text.add_argument("--timeout", type=int, default=30, help="PDF extraction timeout in seconds")
    full_text.add_argument("--text-output", type=Path, help="Output text cache. Defaults to kb-dir/full_text/<paper-id>.txt")
    full_text.add_argument("--output", type=Path, help="Output markdown path. Defaults to kb-dir/analysis/<paper-id>_full_text_brief.md")
    full_text.set_defaults(func=full_text_command)

    workup = sub.add_parser("workup", aliases=["paper-workup"], help="Build a human-readable selected-paper workup against the local foundation")
    workup.add_argument("--profile", type=Path, required=True)
    workup.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to profile parent/knowledge_base")
    workup.add_argument("--feedback-file", type=Path, help="Feedback JSON. Defaults to kb-dir/feedback.json")
    workup.add_argument("--papers-json", type=Path, help="Optional digest papers.json to select a paper that is not yet retained")
    workup.add_argument("--paper-id", help="Paper ID from a digest or paper note")
    workup.add_argument("--title", help="Case-insensitive title substring")
    workup.add_argument("--full-text-path", type=Path, help="Optional local text cache path. Defaults to kb-dir/full_text/<paper-id>.txt")
    workup.add_argument("--full-text-brief-path", type=Path, help="Optional full-text brief path. Defaults to kb-dir/analysis/<paper-id>_full_text_brief.md")
    workup.add_argument("--max-full-text-brief-chars", type=int, default=7000, help="Maximum full-text brief characters to include")
    workup.add_argument("--limit", type=int, default=10, help="Related foundation papers to include")
    workup.add_argument("--output", type=Path, help="Output markdown path. Defaults to kb-dir/analysis/<paper-id>_workup.md")
    workup.set_defaults(func=paper_workup_command)

    review_pack = sub.add_parser("review-pack", help="Build an LLM-ready paper review context pack")
    review_pack.add_argument("--profile", type=Path, required=True)
    review_pack.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to profile parent/knowledge_base")
    review_pack.add_argument("--feedback-file", type=Path, help="Feedback JSON. Defaults to kb-dir/feedback.json")
    review_pack.add_argument("--papers-json", type=Path, help="Optional digest papers.json to select a paper that is not yet retained")
    review_pack.add_argument("--paper-id", help="Paper ID from a digest or paper note")
    review_pack.add_argument("--title", help="Case-insensitive title substring")
    review_pack.add_argument("--full-text-path", type=Path, help="Optional local text cache to include. Defaults to kb-dir/full_text/<paper-id>.txt")
    review_pack.add_argument("--full-text-brief-path", type=Path, help="Optional full-text brief to include. Defaults to kb-dir/analysis/<paper-id>_full_text_brief.md")
    review_pack.add_argument("--max-full-text-chars", type=int, default=40000, help="Maximum full-text characters to include")
    review_pack.add_argument("--max-full-text-brief-chars", type=int, default=16000, help="Maximum full-text brief characters to include")
    review_pack.add_argument("--limit", type=int, default=12, help="Related/interested papers to include")
    review_pack.add_argument("--output", type=Path, help="Output markdown path. Defaults to kb-dir/analysis/<paper-id>_review_pack.md")
    review_pack.set_defaults(func=review_pack_command)

    review_queue = sub.add_parser("review-queue", help="Build review packs for a queue of selected papers")
    review_queue.add_argument("--profile", type=Path, required=True)
    review_queue.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to profile parent/knowledge_base")
    review_queue.add_argument("--feedback-file", type=Path, help="Feedback JSON. Defaults to kb-dir/feedback.json")
    review_queue.add_argument("--papers-json", type=Path, help="Optional digest papers.json to include recent papers")
    review_queue.add_argument("--paper-id", help="Comma-separated paper IDs; when omitted, papers are selected by --tiers")
    review_queue.add_argument("--title", help="Comma-separated case-insensitive title substrings")
    review_queue.add_argument("--tiers", default="Must read", help="Comma-separated tiers to queue when --paper-id/--title are omitted")
    review_queue.add_argument("--limit", type=int, default=5, help="Maximum papers to queue when selecting by tier")
    review_queue.add_argument("--no-extract", action="store_true", help="Do not attempt local PDF/text extraction; use existing caches only")
    review_queue.add_argument("--force-extract", action="store_true", help="Regenerate full-text caches even when they already exist")
    review_queue.add_argument("--strict-full-text", action="store_true", help="Exit non-zero if any selected paper has no usable local full-text cache")
    review_queue.add_argument("--max-chars", type=int, default=120000, help="Maximum extracted text characters to cache per paper")
    review_queue.add_argument("--timeout", type=int, default=30, help="PDF extraction timeout in seconds per paper")
    review_queue.add_argument("--max-full-text-chars", type=int, default=40000, help="Maximum cached text characters to include in each review pack")
    review_queue.add_argument("--max-full-text-brief-chars", type=int, default=16000, help="Maximum full-text brief characters to include in each review pack")
    review_queue.add_argument("--related-limit", type=int, default=12, help="Related/interested papers to include in each review pack")
    review_queue.add_argument("--output", type=Path, help="Output queue index. Defaults to kb-dir/analysis/review_queue.md")
    review_queue.add_argument("--html-output", type=Path, help="Output browser-friendly queue path. Defaults to --output with .html suffix")
    review_queue.add_argument("--no-html", action="store_true", help="Do not write a browser-friendly HTML queue")
    review_queue.set_defaults(func=review_queue_command)

    ask = sub.add_parser("ask", help="Ask a question against the retained local literature library")
    ask.add_argument("--profile", type=Path, required=True)
    ask.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to profile parent/knowledge_base")
    ask.add_argument("--papers-json", type=Path, help="Optionally include a digest papers.json in addition to the retained library")
    ask.add_argument("--question", required=True)
    ask.add_argument("--limit", type=int, default=15)
    ask.add_argument("--output", type=Path, help="Output markdown path. Defaults to kb-dir/answers/<timestamp>_<question>.md")
    ask.set_defaults(func=ask_library_command)

    advice = sub.add_parser("advice", help="Generate research-gap and reading-strategy advice from foundation/interested papers")
    advice.add_argument("--profile", type=Path, required=True)
    advice.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to profile parent/knowledge_base")
    advice.add_argument("--feedback-file", type=Path, help="Feedback JSON. Defaults to kb-dir/feedback.json")
    advice.add_argument("--limit", type=int, default=12)
    advice.add_argument("--output", type=Path, help="Output markdown path. Defaults to kb-dir/research_advice.md")
    advice.set_defaults(func=research_advice_command)

    reading_plan = sub.add_parser("reading-plan", help="Prioritize what to read next from retained/recent papers")
    reading_plan.add_argument("--profile", type=Path, required=True)
    reading_plan.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to profile parent/knowledge_base")
    reading_plan.add_argument("--feedback-file", type=Path, help="Feedback JSON. Defaults to kb-dir/feedback.json")
    reading_plan.add_argument("--papers-json", type=Path, help="Optional digest papers.json to include recent papers")
    reading_plan.add_argument("--limit", type=int, default=10, help="Maximum papers to include in the plan")
    reading_plan.add_argument("--output", type=Path, help="Output markdown path. Defaults to kb-dir/reading_plan.md")
    reading_plan.add_argument("--html-output", type=Path, help="Output HTML path. Defaults to the markdown output with .html suffix")
    reading_plan.add_argument("--no-html", action="store_true", help="Do not write a browser-friendly HTML reading plan")
    reading_plan.set_defaults(func=reading_plan_command)

    status_cmd = sub.add_parser("status", help="Update reading status and labels for selected papers")
    status_cmd.add_argument("--profile", type=Path, required=True)
    status_cmd.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to profile parent/knowledge_base")
    status_cmd.add_argument("--feedback-file", type=Path, help="Feedback JSON. Defaults to kb-dir/feedback.json")
    status_cmd.add_argument("--papers-json", type=Path, help="Optional digest papers.json for recently seen papers")
    status_cmd.add_argument("--paper-id", help="Comma-separated paper IDs")
    status_cmd.add_argument("--title", help="Comma-separated title substrings")
    status_cmd.add_argument("--status", choices=sorted(READING_STATUSES), help="Reading status to assign")
    status_cmd.add_argument("--label", help="Comma-separated labels to add, e.g. must cite,method reference")
    status_cmd.add_argument("--remove-label", help="Comma-separated labels to remove")
    status_cmd.add_argument("--note", help="Append a personal note to the feedback record")
    status_cmd.set_defaults(func=update_reading_status_command)

    compare = sub.add_parser("compare", help="Compare selected papers side by side")
    compare.add_argument("--profile", type=Path, required=True)
    compare.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to profile parent/knowledge_base")
    compare.add_argument("--feedback-file", type=Path, help="Feedback JSON. Defaults to kb-dir/feedback.json")
    compare.add_argument("--papers-json", type=Path, help="Optional digest papers.json")
    compare.add_argument("--paper-id", help="Comma-separated paper IDs")
    compare.add_argument("--title", help="Comma-separated title substrings")
    compare.add_argument("--output", type=Path, help="Output markdown path. Defaults to kb-dir/comparisons/<timestamp>_<ids>.md")
    compare.set_defaults(func=compare_papers_command)

    research_map = sub.add_parser("map", help="Generate a topic/research map from the retained literature base")
    research_map.add_argument("--profile", type=Path, required=True)
    research_map.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to profile parent/knowledge_base")
    research_map.add_argument("--feedback-file", type=Path, help="Feedback JSON. Defaults to kb-dir/feedback.json")
    research_map.add_argument("--limit", type=int, default=12)
    research_map.add_argument("--output", type=Path, help="Output markdown path. Defaults to kb-dir/research_map.md")
    research_map.set_defaults(func=research_map_command)

    zotero = sub.add_parser("zotero", help="Export Zotero-ready BibTeX and RIS files")
    zotero.add_argument("--profile", type=Path, required=True)
    zotero.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to profile parent/knowledge_base")
    zotero.add_argument("--papers-json", type=Path, help="Optional papers.json to export instead of the retained library")
    zotero.add_argument("--tiers", default="Must read,Skim", help="Comma-separated tiers to export; empty means all")
    zotero.add_argument("--limit", type=int, default=0, help="Max papers to export; 0 means no limit")
    zotero.add_argument("--output-dir", type=Path, help="Output directory. Defaults to kb-dir/zotero")
    zotero.set_defaults(func=zotero_export_command)

    zotero_sync = sub.add_parser("zotero-sync", help="Read Better BibTeX/BibTeX metadata back into the retained library")
    zotero_sync.add_argument("--profile", type=Path, required=True)
    zotero_sync.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to profile parent/knowledge_base")
    zotero_sync.add_argument("--bibtex", type=Path, required=True, help="Better BibTeX/BibTeX export from Zotero")
    zotero_sync.add_argument("--report", type=Path, help="Markdown report path. Defaults to kb-dir/zotero/zotero_sync.md")
    zotero_sync.set_defaults(func=sync_zotero_command)

    obsidian = sub.add_parser("obsidian", help="Export an Obsidian-ready Markdown vault folder")
    obsidian.add_argument("--profile", type=Path, required=True)
    obsidian.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to profile parent/knowledge_base")
    obsidian.add_argument("--feedback-file", type=Path, help="Feedback JSON. Defaults to kb-dir/feedback.json")
    obsidian.add_argument("--tiers", default="Must read,Skim", help="Comma-separated tiers to export; empty means all")
    obsidian.add_argument("--limit", type=int, default=0, help="Max papers to export; 0 means no limit")
    obsidian.add_argument("--vault-dir", type=Path, help="Output folder. Defaults to kb-dir/obsidian")
    obsidian.set_defaults(func=obsidian_export_command)

    doctor = sub.add_parser("doctor", help="Check local setup, credentials, outputs, and knowledge-base files")
    doctor.add_argument("--profile", type=Path)
    doctor.add_argument("--kb-dir", type=Path)
    doctor.add_argument("--out-dir", type=Path)
    doctor.add_argument("--gmail-credentials", type=Path, default=DEFAULT_GMAIL_CREDENTIALS)
    doctor.add_argument("--gmail-token", type=Path, default=DEFAULT_GMAIL_TOKEN)
    doctor.add_argument("--gmail-deps", action="store_true", help="Also check Gmail API Python dependencies")
    doctor.add_argument("--obsidian-dir", type=Path, help="Optional Obsidian generated export directory to check")
    doctor.add_argument("--zotero-dir", type=Path, help="Optional Zotero export directory to check")
    doctor.add_argument("--output", type=Path, help="Write markdown report to this path")
    doctor.set_defaults(func=doctor_command)

    support = sub.add_parser("support-bundle", help="Write a sanitized support bundle for GitHub issues")
    support.add_argument("--project-dir", type=Path, required=True)
    support.add_argument("--profile", type=Path, help="Profile path. Defaults to project-dir/profiles/research_profile.json")
    support.add_argument("--kb-dir", type=Path, help="Knowledge-base directory. Defaults to project-dir/knowledge_base")
    support.add_argument("--out-dir", type=Path, help="Daily output directory. Defaults to project-dir/reader_out/daily")
    support.add_argument("--env-file", type=Path, help="reader.env path. Defaults to project-dir/reader.env")
    support.add_argument("--source-check", type=Path, help="SOURCE_CHECK.md path. Defaults to project-dir/SOURCE_CHECK.md")
    support.add_argument("--doctor-report", type=Path, help="DOCTOR.md path. Defaults to project-dir/DOCTOR.md")
    support.add_argument("--no-report-excerpts", action="store_true", help="Do not include sanitized SOURCE_CHECK/DOCTOR excerpts")
    support.add_argument("--output", type=Path, help="Output markdown path. Defaults to project-dir/SUPPORT_BUNDLE.md")
    support.set_defaults(func=support_bundle_command)

    capabilities = sub.add_parser("capabilities", help="Explain product capabilities, boundaries, and recommended workflows")
    capabilities.add_argument("--project-dir", type=Path, help="Optional local project directory to include a redacted setup snapshot")
    capabilities.add_argument("--output", type=Path, help="Write markdown report to this path instead of stdout")
    capabilities.set_defaults(func=capabilities_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
