"""Scoring engine extracted from core ranking path.

The goal in this phase is architectural separation, not semantic redesign.
`core.py` keeps its public surface (`score_paper`, `feedback_adjustment`,
`adaptive_ranking_adjustment`, `build_reasons`) while the implementation now
lives in this module with a structured, explainable score breakdown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Any

from ..models import ScoreComponent


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


@dataclass
class ScoreComputation:
    """Structured output for one paper scoring run."""

    total: int
    matched_terms: list[str] = field(default_factory=list)
    tags: set[str] = field(default_factory=set)
    reasons: list[str] = field(default_factory=list)
    forced_tier: str | None = None
    components: list[ScoreComponent] = field(default_factory=list)


ScoreBreakdown = ScoreComputation


@dataclass
class _TermHit:
    term: str
    weight: int
    section: str
    field: str
    tags: list[str] = field(default_factory=list)
    overlap: list[str] = field(default_factory=list)


@dataclass
class _SeedPaper:
    """Lean fallback paper-like object used for adaptive scoring."""

    id: str
    title: str
    authors_source: str = ""
    snippet: str = ""
    alerts: list[str] = field(default_factory=list)
    url: str = ""
    scholar_url: str = ""
    matched_terms: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    tier: str = "Skim"
    occurrences: int = 1
    first_seen: str = ""
    last_seen: str = ""



def _text_fields(paper: Any) -> dict[str, str]:
    return {
        "title": str(getattr(paper, "title", "")).lower(),
        "authors_source": str(getattr(paper, "authors_source", "")).lower(),
        "snippet": str(getattr(paper, "snippet", "")).lower(),
        "alerts": " ".join(getattr(paper, "alerts", [])).lower(),
    }


def _coerce_terms(items: Any, section: str, default_weight: int = 1) -> list[dict[str, Any]]:
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
                terms.append(
                    {
                        "term": term,
                        "weight": default_weight,
                        "section": section,
                        "tags": fallback_tags.get(section, []),
                    }
                )
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


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def profile_terms(profile: dict[str, Any], boost: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build positive/negative term banks from profile + boost string."""

    positive: list[dict[str, Any]] = []
    negative: list[dict[str, Any]] = []
    for section, default_weight in [
        ("focus_terms", 2),
        ("regions", 2),
        ("methods", 2),
        ("semantic_queries", 3),
        ("watch_authors", 2),
    ]:
        positive.extend(_coerce_terms(profile.get(section, []), section, default_weight))
    negative.extend(_coerce_terms(profile.get("exclude_terms", []), "exclude_terms", 3))

    for term in split_csv(boost):
        positive.append({"term": term, "weight": 6, "section": "runtime_boost", "tags": ["boost"]})
    return positive, negative


def _semantic_token(value: str) -> str:
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


def _semantic_tokens(value: str) -> set[str]:
    found = re.findall(r"[a-z0-9]+", value.lower())
    tokens = {_semantic_token(token) for token in found}
    return {token for token in tokens if token and token not in TITLE_STOPWORDS and len(token) > 2}


def _paper_affinity_tokens(paper: Any) -> set[str]:
    text = " ".join(
        [
            str(getattr(paper, "title", "")),
            str(getattr(paper, "snippet", "")),
            str(getattr(paper, "authors_source", "")),
            " ".join(getattr(paper, "alerts", [])),
            " ".join(getattr(paper, "matched_terms", [])),
            " ".join(getattr(paper, "tags", [])),
        ]
    )
    return _semantic_tokens(text)


def _semantic_term_hit(item: dict[str, Any], fields: dict[str, str]) -> tuple[int, str, list[str]] | None:
    term_tokens = _semantic_tokens(str(item.get("term", "")))
    if len(term_tokens) < 2:
        return None
    field_tokens = {field_name: _semantic_tokens(field_text) for field_name, field_text in fields.items()}
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
        field_name = "semantic:title"
    else:
        field_name = "semantic"
    return weight, field_name, overlap[:8]


def _component_name(section: str) -> str:
    return {
        "focus_terms": "topical_relevance",
        "regions": "domain_relevance",
        "methods": "method_relevance",
        "watch_authors": "authority_signal",
        "semantic_queries": "semantic_similarity",
        "runtime_boost": "topical_relevance",
        "exclude_terms": "exclusion_penalty",
    }.get(section, section)


def _record_hit(
    components: list[ScoreComponent],
    section: str,
    delta: float,
    field: str,
    matched_term: str,
    explanation: str,
    evidence_field: str,
) -> None:
    if delta == 0:
        return
    components.append(
        ScoreComponent(
            name=_component_name(section),
            value=float(delta),
            matched_terms=[matched_term],
            explanation=explanation,
            evidence_field=evidence_field,
        )
    )


def feedback_adjustment(
    paper: Any,
    feedback: dict[str, Any] | None,
) -> tuple[int, list[str], set[str], list[str], str | None]:
    """Apply direct feedback overrides and term-weight signals."""

    if not feedback:
        return 0, [], set(), [], None

    delta = 0
    matched_terms: list[str] = []
    tags: set[str] = set()
    reasons: list[str] = []
    forced_tier: str | None = None
    fields = _text_fields(paper)
    haystack = "\n".join(fields.values())

    paper_feedback = feedback.get("papers", {}).get(str(getattr(paper, "id", "")))
    if isinstance(paper_feedback, dict):
        status = paper_feedback.get("status")
        if status == "interested":
            delta += 6
            forced_tier = "Skim"
            tags.add("feedback")
            reasons.append("用户反馈：这篇已标为 interested，至少进入保留阅读队列。")
        elif status == "archive":
            delta -= 100
            forced_tier = "Archive"
            tags.add("feedback")
            reasons.append("用户反馈：这篇已标为 archive，强制归档。")

        priority_override = str(paper_feedback.get("priority_override", "") or "").strip().lower().replace("-", "_")
        if priority_override == "must_read" and status != "archive":
            delta += 12
            forced_tier = "Must read"
            tags.add("feedback")
            reasons.append("用户反馈：priority override = Must read，强制进入重点阅读。")
        elif priority_override == "skim" and status != "archive":
            delta += 6
            forced_tier = "Skim"
            tags.add("feedback")
            reasons.append("用户反馈：priority override = Skim，强制进入略读队列。")
        elif priority_override == "archive":
            delta -= 100
            forced_tier = "Archive"
            tags.add("feedback")
            reasons.append("用户反馈：priority override = Archive，强制归档。")

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

    return delta, matched_terms, tags, reasons[:5], forced_tier


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


def _feedback_record_to_seed(seed_id: str, record: dict[str, Any]) -> _SeedPaper:
    return _SeedPaper(
        id=str(seed_id),
        title=str(record.get("title", "") or seed_id),
        snippet=str(record.get("note", "") or ""),
        url=str(record.get("url", "") or ""),
    )


def _feedback_paper_record(feedback: dict[str, Any] | None, paper_id: str) -> dict[str, Any]:
    if not isinstance(feedback, dict):
        return {}
    return feedback.get("papers", {}).get(paper_id, {}) if isinstance(feedback.get("papers", {}), dict) else {}


def _is_positive_seed(seed: Any, feedback: dict[str, Any] | None, seed_tiers: set[str]) -> bool:
    record = _feedback_paper_record(feedback, seed.id)
    signals = record.get("signals", {}) if isinstance(record.get("signals", {}), dict) else {}
    reading_status = str(record.get("reading_status", "") or "")
    if record.get("status") == "archive" or reading_status in {"background-only", "not-relevant"} or signals.get("less_like_this"):
        return False
    if record.get("status") == "interested" or signals.get("more_like_this"):
        return True
    if reading_status in {"reading", "read", "must-cite", "method-reference"}:
        return True
    return str(getattr(seed, "tier", "")) in seed_tiers


def _is_negative_seed(record: dict[str, Any]) -> bool:
    signals = record.get("signals", {}) if isinstance(record.get("signals", {}), dict) else {}
    return record.get("status") == "archive" or record.get("reading_status") == "not-relevant" or signals.get("less_like_this")


def adaptive_ranking_adjustment(
    paper: Any,
    profile: dict[str, Any],
    feedback: dict[str, Any] | None,
    library: list[Any] | None,
) -> tuple[int, list[str], set[str], list[str]]:
    """Score by similarity to positive/negative seed papers from feedback and library."""

    settings = adaptive_ranking_settings(profile)
    if not settings["enabled"]:
        return 0, [], set(), []

    seed_tiers = set(settings["seed_tiers"])
    library_by_id = {seed.id: seed for seed in library or [] if str(seed.id) != str(paper.id)}

    positive_seeds: list[Any] = []
    feedback_positive_seeds: list[Any] = []
    negative_seeds: list[Any] = []

    for seed in library_by_id.values():
        if _is_positive_seed(seed, feedback, seed_tiers):
            positive_seeds.append(seed)

    for paper_id, record in (feedback or {}).get("papers", {}).items():
        if not isinstance(record, dict) or str(paper_id) == str(paper.id):
            continue
        seed = library_by_id.get(str(paper_id)) or _feedback_record_to_seed(str(paper_id), record)
        if _is_negative_seed(record):
            negative_seeds.append(seed)
        elif str(record.get("status", "")) == "interested" or str((record.get("signals", {}) or {}).get("more_like_this")) == "True":
            feedback_positive_seeds.append(seed)

    positive_seeds = list({seed.id: seed for seed in feedback_positive_seeds + positive_seeds}.values())[: settings["max_seed_papers"]]
    negative_seeds = negative_seeds[: settings["max_seed_papers"]]

    if not positive_seeds and not negative_seeds:
        return 0, [], set(), []

    target_tokens = _paper_affinity_tokens(paper)
    if len(target_tokens) < settings["min_overlap"]:
        return 0, [], set(), []

    def _best(seed_candidates: list[Any]) -> tuple[Any | None, list[str], int]:
        best_seed: Any | None = None
        best_overlap: list[str] = []
        best_score = 0
        for seed in seed_candidates:
            seed_tokens = _paper_affinity_tokens(seed)
            overlap = sorted(target_tokens & seed_tokens)
            overlap_count = len(overlap)
            if overlap_count < settings["min_overlap"]:
                continue
            score = overlap_count * 100 + (50 if str(getattr(seed, "tier", "")) == "Must read" else 0)
            if score > best_score:
                best_seed = seed
                best_overlap = overlap
                best_score = score
        return best_seed, best_overlap, best_score

    positive_seed, positive_overlap, _ = _best(positive_seeds)
    negative_seed, negative_overlap, _ = _best(negative_seeds)

    delta = 0
    matched_terms: list[str] = []
    tags: set[str] = set()
    reasons: list[str] = []
    if positive_seed:
        strength = min(1.5, len(positive_overlap) / settings["min_overlap"])
        boost = max(1, round(settings["positive_weight"] * strength))
        delta += boost
        matched_terms.append(f"similar:{getattr(positive_seed, 'title', '')}")
        tags.add("adaptive")
        reasons.append(
            f"反馈相似度加权：和已关注论文 `{getattr(positive_seed, 'title', '')}` 共享 {len(positive_overlap)} 个关键词"
            f"（{', '.join(positive_overlap[:6])}）。"
        )
    if negative_seed:
        strength = min(1.5, len(negative_overlap) / settings["min_overlap"])
        penalty = max(1, round(settings["negative_weight"] * strength))
        delta -= penalty
        matched_terms.append(f"dissimilar:{getattr(negative_seed, 'title', '')}")
        tags.add("adaptive")
        reasons.append(
            f"反馈相似度降权：和已归档论文 `{getattr(negative_seed, 'title', '')}` 共享 {len(negative_overlap)} 个关键词"
            f"（{', '.join(negative_overlap[:6])}）。"
        )

    return delta, matched_terms, tags, reasons[:3]


def build_reasons(hits: list[_TermHit], paper: Any) -> list[str]:
    if not hits:
        return ["没有命中当前 profile 的重点词，默认归档或低优先级。"]
    top_hits = sorted(hits, key=lambda h: abs(h.weight), reverse=True)[:4]
    reasons: list[str] = []
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
    if getattr(paper, "occurrences", 0) > 1:
        reasons.append(f"同一论文在 {paper.occurrences} 个 alert 记录中出现。")
    return reasons


def score_paper(
    paper: Any,
    profile: dict[str, Any],
    boost: str | None,
    feedback: dict[str, Any] | None = None,
    library: list[Any] | None = None,
) -> ScoreComputation:
    """Compute score + tier + reasons for one paper.

    Behavior mirrors the legacy scoring in `core.py` and updates the paper object in
    place so existing CLI, dashboard, and tests remain compatible.
    """

    positive, negative = profile_terms(profile, boost)
    fields = _text_fields(paper)
    hits: list[_TermHit] = []
    components: list[ScoreComponent] = []
    score = 0

    for item in positive:
        if item["section"] == "watch_authors":
            continue
        term = item["term"]
        needle = str(term).lower()
        if not needle:
            continue
        exact_match = False
        for field_name, field_text in fields.items():
            if needle in field_text:
                weight = int(item.get("weight", 1))
                if field_name == "title":
                    weight *= 2
                elif field_name == "alerts" and item["section"] == "watch_authors":
                    weight *= 2
                score += weight
                hits.append(_TermHit(term, weight, item["section"], field_name, item.get("tags", [])))
                _record_hit(
                    components,
                    item["section"],
                    weight,
                    field_name,
                    term,
                    f"标题/摘要命中：`{term}`。",
                    field_name,
                )
                exact_match = True
                break
        if not exact_match:
            semantic = _semantic_term_hit(item, fields)
            if semantic:
                weight, field_name, overlap = semantic
                score += weight
                tags = sorted(set(item.get("tags", [])) | {"semantic"})
                hits.append(_TermHit(term, weight, item["section"], field_name, tags, overlap))
                _record_hit(
                    components,
                    item["section"],
                    weight,
                    field_name,
                    term,
                    f"语义匹配 `{term}`，字段 `{field_name}`。",
                    field_name,
                )

    topical_score = score
    for item in positive:
        if item["section"] != "watch_authors":
            continue
        term = item["term"]
        needle = str(term).lower()
        if not needle:
            continue
        for field_name, field_text in fields.items():
            if needle not in field_text:
                continue
            weight = int(item.get("weight", 1))
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
            hits.append(_TermHit(term, weight, item["section"], field_name, item.get("tags", [])))
            _record_hit(
                components,
                item["section"],
                weight,
                field_name,
                term,
                f"watch_authors 命中 `{term}`。",
                field_name,
            )
            break

    for item in negative:
        term = item["term"]
        needle = str(term).lower()
        if not needle:
            continue
        for field_name, field_text in fields.items():
            if needle in field_text:
                weight = int(item.get("weight", 1))
                score -= weight
                hits.append(_TermHit(f"-{term}", -weight, "exclude_terms", field_name, []))
                _record_hit(
                    components,
                    "exclude_terms",
                    -weight,
                    field_name,
                    term,
                    f"排除词 `{term}` 触发降权。",
                    field_name,
                )
                break

    if getattr(paper, "occurrences", 0) > 1:
        novelty = min(3, getattr(paper, "occurrences") - 1)
        score += novelty
        _record_hit(
            components,
            "novelty_signal",
            novelty,
            "paper",
            "occurrence",
            f"重复出现 {getattr(paper, 'occurrences')} 次，叠加多源出现信号。",
            "occurrences",
        )

    current_year = datetime.now().year
    if str(current_year) in fields["authors_source"] or str(current_year - 1) in fields["authors_source"]:
        score += 1
        _record_hit(
            components,
            "novelty_signal",
            1,
            "metadata",
            "year",
            f"年份信号包含 {current_year}/{current_year - 1}，给予新近性加权。",
            "authors_source",
        )

    if re.search(r"\b(review|survey|perspective|benchmark|dataset)\b", str(getattr(paper, "title", "")), re.I):
        score += 1
        _record_hit(
            components,
            "method_relevance",
            1,
            "title",
            "review",
            "命中 `review/survey/benchmark/dataset` 等术语，给予 review 信号加权。",
            "title",
        )

    feedback_delta, feedback_terms, feedback_tags, feedback_reasons, forced_tier = feedback_adjustment(paper, feedback)
    score += feedback_delta
    _record_hit(components, "feedback_similarity", feedback_delta, "feedback", "feedback", "反馈信号影响。", "feedback")

    adaptive_delta, adaptive_terms, adaptive_tags, adaptive_reasons = adaptive_ranking_adjustment(
        paper,
        profile,
        feedback,
        library,
    )
    score += adaptive_delta
    _record_hit(components, "feedback_similarity", adaptive_delta, "adaptive", "adaptive", "反馈学习相似度影响。", "adaptive")

    thresholds = profile.get("tier_thresholds", {})
    must = int(thresholds.get("must_read", 8))
    skim = int(thresholds.get("skim", 3))

    tier = "Must read" if score >= must else "Skim" if score >= skim else "Archive"
    enforced_tier = None
    if forced_tier == "Must read":
        score = max(score, must)
        tier = "Must read"
        enforced_tier = "Must read"
    elif forced_tier == "Skim":
        tier = "Skim"
        enforced_tier = "Skim"
    elif forced_tier == "Archive":
        score = min(score, -20)
        tier = "Archive"
        enforced_tier = "Archive"

    matched_terms = sorted(
        {hit.term for hit in hits} | set(feedback_terms) | set(adaptive_terms),
        key=lambda t: t.lower(),
    )
    tags = sorted(
        {tag for hit in hits for tag in hit.tags} | set(feedback_tags) | set(adaptive_tags),
    )
    reasons = feedback_reasons + adaptive_reasons
    reasons.extend(build_reasons(hits, paper) if hits or not (feedback_reasons or adaptive_reasons) else [])
    if not reasons:
        reasons = ["没有命中当前 profile 的重点词，默认归档或低优先级。"]

    # Backward-compatible mutation for existing pipeline consumers.
    paper.score = score
    paper.tier = tier
    paper.matched_terms = matched_terms
    paper.tags = tags
    paper.reasons = reasons[:8]

    return ScoreComputation(
        total=score,
        matched_terms=matched_terms,
        tags=set(tags),
        reasons=reasons,
        forced_tier=forced_tier,
        components=components,
    )
