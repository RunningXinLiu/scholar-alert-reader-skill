"""Personal literature copilot reports for Scholar Alert Reader."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from .export import best_authors, best_doi, best_journal, best_year


STOPWORDS = {
    "and",
    "about",
    "after",
    "analysis",
    "are",
    "article",
    "articles",
    "based",
    "between",
    "case",
    "citation",
    "citations",
    "data",
    "during",
    "earth",
    "effects",
    "evidence",
    "for",
    "from",
    "global",
    "high",
    "implications",
    "into",
    "large",
    "model",
    "models",
    "new",
    "not",
    "our",
    "paper",
    "pdf",
    "regional",
    "reference",
    "references",
    "results",
    "study",
    "system",
    "that",
    "the",
    "their",
    "these",
    "this",
    "through",
    "toward",
    "using",
    "van",
    "der",
    "watchlist",
    "which",
    "with",
}


def text(value: Any) -> str:
    return str(value or "")


def tokens(value: str) -> set[str]:
    found = re.findall(r"[a-z][a-z0-9-]{2,}", value.lower())
    return {token.strip("-") for token in found if token.strip("-") and token not in STOPWORDS}


def record_text(record: dict[str, Any]) -> str:
    fields = [
        record.get("title", ""),
        record.get("authors_source", ""),
        record.get("snippet", ""),
        " ".join(str(term) for term in record.get("matched_terms", [])),
        " ".join(str(tag) for tag in record.get("tags", [])),
        " ".join(str(alert) for alert in record.get("alerts", [])),
    ]
    return " ".join(text(field) for field in fields)


def similarity_text(record: dict[str, Any]) -> str:
    fields = [
        record.get("title", ""),
        record.get("authors_source", ""),
        record.get("snippet", ""),
        " ".join(str(term) for term in record.get("matched_terms", [])),
        " ".join(str(tag) for tag in record.get("tags", []) if str(tag) not in {"adaptive", "watchlist", "feedback", "boost"}),
    ]
    return " ".join(text(field) for field in fields)


def record_terms(record: dict[str, Any]) -> set[str]:
    terms = {str(term).lower() for term in record.get("matched_terms", []) if str(term).strip()}
    terms.update(
        str(tag).lower()
        for tag in record.get("tags", [])
        if str(tag).strip() and str(tag) not in {"adaptive", "watchlist", "feedback", "boost"}
    )
    terms.update(tokens(text(record.get("title", ""))))
    return terms


def paper_line(record: dict[str, Any]) -> str:
    title = text(record.get("title", "Untitled"))
    url = text(record.get("url", ""))
    score = record.get("score", 0)
    tier = text(record.get("tier", ""))
    source = text(record.get("authors_source", ""))
    if url:
        return f"- **[{title}]({url})** ({score}, {tier}; id `{record.get('id', '')}`) - {source}"
    return f"- **{title}** ({score}, {tier}; id `{record.get('id', '')}`) - {source}"


def feedback_record(record: dict[str, Any], feedback: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(feedback, dict):
        return {}
    item = feedback.get("papers", {}).get(str(record.get("id", "")), {})
    return item if isinstance(item, dict) else {}


def reading_status(record: dict[str, Any], feedback: dict[str, Any] | None) -> str:
    item = feedback_record(record, feedback)
    status = str(item.get("reading_status", "") or "")
    if status:
        return status
    if item.get("status") == "archive":
        return "not-relevant"
    if item.get("status") == "interested" or record.get("tier") == "Must read":
        return "unread"
    return "unread"


def reading_labels(record: dict[str, Any], feedback: dict[str, Any] | None) -> list[str]:
    item = feedback_record(record, feedback)
    labels = item.get("labels", [])
    if isinstance(labels, list):
        return [str(label) for label in labels if str(label).strip()]
    return []


def top_counter(values: list[str], limit: int) -> list[tuple[str, int]]:
    return Counter(value for value in values if value).most_common(limit)


def ranked_records_for_question(records: list[dict[str, Any]], question: str, limit: int) -> list[tuple[int, dict[str, Any]]]:
    query_tokens = tokens(question)
    query_lower = question.lower()
    ranked: list[tuple[int, dict[str, Any]]] = []
    for record in records:
        title_tokens = tokens(text(record.get("title", "")))
        all_tokens = tokens(record_text(record))
        matched_terms = {str(term).lower() for term in record.get("matched_terms", [])}
        tags = {str(tag).lower() for tag in record.get("tags", [])}
        alerts = {str(alert).lower() for alert in record.get("alerts", [])}

        score = 0
        score += 5 * len(query_tokens & title_tokens)
        score += 2 * len(query_tokens & all_tokens)
        score += 4 * sum(1 for term in matched_terms if term and term in query_lower)
        score += 2 * sum(1 for tag in tags if tag and tag in query_lower)
        score += sum(1 for alert in alerts if alert and alert in query_lower)
        if not query_tokens and record.get("tier") == "Must read":
            score += 1
        if score > 0:
            ranked.append((score, record))

    ranked.sort(
        key=lambda item: (
            -item[0],
            {"Must read": 0, "Skim": 1, "Archive": 2}.get(text(item[1].get("tier")), 9),
            -int(item[1].get("score", 0) or 0),
            text(item[1].get("title")).lower(),
        )
    )
    return ranked[:limit]


def related_records(target: dict[str, Any], records: list[dict[str, Any]], limit: int) -> list[tuple[int, dict[str, Any], list[str]]]:
    target_terms = record_terms(target)
    target_tokens = tokens(similarity_text(target))
    target_id = text(target.get("id"))
    ranked: list[tuple[int, dict[str, Any], list[str]]] = []
    for record in records:
        if text(record.get("id")) == target_id:
            continue
        shared_terms = sorted(target_terms & record_terms(record))
        shared_tokens = sorted(target_tokens & tokens(similarity_text(record)))
        shared = shared_terms[:8] + [token for token in shared_tokens[:8] if token not in shared_terms]
        score = 4 * len(shared_terms) + len(shared_tokens) + int(record.get("score", 0) or 0) // 8
        if score > 0:
            ranked.append((score, record, shared[:10]))
    ranked.sort(
        key=lambda item: (
            -item[0],
            {"Must read": 0, "Skim": 1, "Archive": 2}.get(text(item[1].get("tier")), 9),
            -int(item[1].get("score", 0) or 0),
            text(item[1].get("title")).lower(),
        )
    )
    return ranked[:limit]


def profile_terms(profile: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for section in ["focus_terms", "regions", "methods", "semantic_queries", "watch_authors"]:
        for item in profile.get(section, []):
            if isinstance(item, dict):
                values.append(text(item.get("term")))
            else:
                values.append(text(item))
    return [value for value in values if value]


def render_deep_read(
    target: dict[str, Any],
    library: list[dict[str, Any]],
    profile: dict[str, Any],
    limit: int = 12,
) -> str:
    related = related_records(target, library, limit)
    matched = [term for term in target.get("matched_terms", []) if str(term).strip()]
    directions = [tag for tag in target.get("tags", []) if str(tag).strip()]
    profile_hits = [term for term in profile_terms(profile) if term.lower() in record_text(target).lower()]
    reasons = [str(reason) for reason in target.get("reasons", []) if str(reason).strip()]

    lines = [
        f"# Deep Read: {text(target.get('title', 'Untitled'))}",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- ID: `{target.get('id', '')}`",
        f"- Tier: {target.get('tier', '')}; score: {target.get('score', 0)}",
        f"- Link: {target.get('url', '')}",
        f"- Source: {target.get('authors_source', '')}",
        f"- Directions: {', '.join(directions) if directions else 'uncategorized'}",
        f"- Matched terms: {', '.join(matched) if matched else 'none'}",
        "",
        "## Working Take",
        "",
        "This is a retrieval-based reading brief from Scholar Alert metadata, your profile, and your local foundation. It should be treated as a triage and discussion scaffold until the full paper is read.",
        "",
        "## Why It Matters For Your Library",
        "",
    ]
    if profile_hits:
        lines.append("- Directly overlaps profile terms: " + ", ".join(profile_hits[:12]))
    if reasons:
        lines.extend(f"- {reason}" for reason in reasons[:6])
    if not (profile_hits or reasons):
        lines.append("- No strong profile-specific rationale was recorded; inspect before adding to active reading.")
    lines.append("")

    lines.extend(["## Paper Signal From Alert", "", text(target.get("snippet", "No snippet available.")), ""])

    lines.extend(["## Closest Foundation Context", ""])
    if not related:
        lines.append("No close retained-paper context found in the current foundation.")
    for score, record, shared in related:
        overlap = ", ".join(shared) if shared else "title/snippet similarity"
        lines.append(f"{paper_line(record)}")
        lines.append(f"  - Relation score: {score}; overlap: {overlap}")
    lines.append("")

    lines.extend(
        [
            "## Reading Protocol",
            "",
            "1. Identify the paper's concrete contribution: method, dataset, region, or interpretation.",
            "2. Compare its assumptions and evidence against the closest foundation papers above.",
            "3. Decide whether it is `must cite`, `method reference`, `background only`, or `not relevant`.",
            "4. Add one personal note: how this changes your current research question, if at all.",
            "",
            "## Questions To Discuss With Codex",
            "",
            f"- How does this paper differ from the closest foundation papers on `{', '.join(matched[:3]) or 'the same topic'}`?",
            "- Is this paper making a new argument, applying a known method to a new region, or mainly confirming existing work?",
            "- If I were writing a literature review, where should this paper be cited?",
            "- What would I need to read in the full paper before trusting the conclusion?",
            "",
            "## Suggested Labels",
            "",
        ]
    )
    if target.get("tier") == "Must read":
        lines.append("- `must cite` or `method reference` if the full paper supports the alert signal.")
    elif target.get("tier") == "Skim":
        lines.append("- `background only` unless the full paper has a method or dataset you can reuse.")
    else:
        lines.append("- `not relevant` unless the title/snippet missed an important connection.")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def markdown_block(value: str) -> str:
    return value.replace("```", "` ` `")


def limited_text(value: str, limit: int) -> str:
    value = value.strip()
    if limit <= 0 or len(value) <= limit:
        return value
    return value[:limit].rstrip() + f"\n\n[Truncated to {limit} characters for this context pack.]"


def render_review_context_pack(
    target: dict[str, Any],
    library: list[dict[str, Any]],
    profile: dict[str, Any],
    feedback: dict[str, Any] | None = None,
    full_text: str = "",
    full_text_path: Path | None = None,
    limit: int = 12,
    max_full_text_chars: int = 40000,
) -> str:
    related = related_records(target, library, limit)
    target_id = text(target.get("id"))
    target_feedback = feedback_record(target, feedback)
    interested = [
        record
        for record in library
        if text(record.get("id")) != target_id
        and (
            record.get("tier") == "Must read"
            or feedback_record(record, feedback).get("status") == "interested"
            or reading_status(record, feedback) in {"reading", "must-cite", "method-reference"}
        )
    ]
    interested = sorted(
        interested,
        key=lambda record: (
            {"must-cite": 0, "method-reference": 1, "reading": 2, "unread": 3}.get(reading_status(record, feedback), 9),
            -int(record.get("score", 0) or 0),
            text(record.get("title")).lower(),
        ),
    )[:limit]
    profile_lines = []
    for section in ["focus_terms", "regions", "methods", "watch_authors", "exclude_terms"]:
        values = []
        for item in profile.get(section, []):
            if isinstance(item, dict):
                term = text(item.get("term"))
                weight = item.get("weight", "")
                values.append(f"{term} ({weight})" if weight != "" else term)
            else:
                values.append(text(item))
        if values:
            profile_lines.append(f"- {section}: " + "; ".join(values[:18]))

    title = text(target.get("title", "Untitled"))
    full_text_excerpt = limited_text(full_text, max_full_text_chars) if full_text else ""
    lines = [
        f"# Paper Review Context Pack: {title}",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Profile: {profile.get('name', 'unnamed')}",
        f"- Target ID: `{target_id}`",
        f"- Intended use: paste this file into Codex, Claude, ChatGPT, or another assistant for a focused paper discussion.",
        "",
        "## Source Boundary",
        "",
        "- This pack is assembled from local Scholar Alert Reader data: alert metadata, bibliography fields, feedback, retained foundation papers, and optional local full-text cache.",
        "- Do not treat missing information as negative evidence. If the full text is absent or truncated, ask for the PDF/text before making final citation decisions.",
        "- The assistant using this pack should separate quoted/observed evidence from inference and should not invent methods, datasets, claims, or results.",
        "",
        "## Review Task For The Assistant",
        "",
        "Use the context below to produce a focused research review for the user:",
        "",
        "1. State the paper's likely contribution and why it may matter to the user's current research profile.",
        "2. Extract the method, data, region, assumptions, and evidence only when supported by the provided text.",
        "3. Compare it against the closest foundation/interested papers and explain whether it is novel, redundant, complementary, or mainly background.",
        "4. Decide whether the user should mark it `must-cite`, `method-reference`, `background-only`, `reading`, or `not-relevant`.",
        "5. List concrete next checks before citing it in a manuscript or proposal.",
        "",
        "## Target Paper",
        "",
        f"- Title: {title}",
        f"- Link: {target.get('url', '')}",
        f"- Source: {target.get('authors_source', '')}",
        f"- Tier: {target.get('tier', '')}; score: {target.get('score', 0)}",
        f"- Matched terms: {', '.join(str(term) for term in target.get('matched_terms', [])) or 'none'}",
        f"- Tags: {', '.join(str(tag) for tag in target.get('tags', [])) or 'none'}",
        f"- Reading status: {reading_status(target, feedback)}",
    ]
    if target_feedback.get("note"):
        lines.append(f"- User note: {target_feedback.get('note')}")
    lines.extend(["", "## User Research Profile", ""])
    lines.extend(profile_lines or ["- No explicit profile terms found."])
    lines.extend(["", "## Alert Or Bibliography Signal", "", text(target.get("snippet", "No snippet available.")), ""])
    reasons = [str(reason) for reason in target.get("reasons", []) if str(reason).strip()]
    if reasons:
        lines.extend(["## Ranking Reasons", ""])
        lines.extend(f"- {reason}" for reason in reasons[:8])
        lines.append("")

    lines.extend(["## Local Full Text", ""])
    if full_text_excerpt:
        source = str(full_text_path) if full_text_path else "provided text"
        lines.extend(
            [
                f"- Source: `{source}`",
                f"- Included characters: {len(full_text_excerpt)} of {len(full_text)}",
                "",
                "```text",
                markdown_block(full_text_excerpt),
                "```",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "No local full text was included. Run `full-text` first, or pass `--full-text-path`, for a stronger review pack.",
                "",
            ]
        )

    lines.extend(["## Closest Foundation Context", ""])
    if related:
        for score, record, shared in related:
            lines.append(paper_line(record))
            lines.append(f"  - Relation score: {score}; overlap: {', '.join(shared) if shared else 'metadata similarity'}")
            snippet = text(record.get("snippet"))
            if snippet:
                lines.append(f"  - Signal: {snippet[:360]}")
    else:
        lines.append("No close retained-paper context found.")
    lines.append("")

    lines.extend(["## Interested / Active Reading Context", ""])
    if interested:
        for record in interested:
            labels = reading_labels(record, feedback)
            suffix = f"; labels: {', '.join(labels)}" if labels else ""
            lines.append(paper_line(record) + f" - status: {reading_status(record, feedback)}{suffix}")
    else:
        lines.append("No separate interested/active-reading papers found yet.")
    lines.extend(
        [
            "",
            "## Suggested Output Format",
            "",
            "Ask the assistant to answer in this structure:",
            "",
            "1. **One-paragraph take**: what this paper appears to contribute and why it matters.",
            "2. **Evidence table**: claim, supporting text/source, confidence, missing check.",
            "3. **Relation to my foundation**: closest papers, novelty/redundancy/complementarity.",
            "4. **Use in my work**: cite in introduction/method/discussion, or do not cite yet.",
            "5. **Next actions**: exact sections/figures/equations/data to inspect.",
            "6. **Feedback command**: suggest the `status`/label command the user should run next.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_literature_answer(
    question: str,
    records: list[dict[str, Any]],
    profile: dict[str, Any],
    limit: int = 15,
) -> str:
    ranked = ranked_records_for_question(records, question, limit)
    selected = [record for _, record in ranked]
    tags = top_counter([str(tag) for record in selected for tag in record.get("tags", [])], 10)
    terms = top_counter([str(term) for record in selected for term in record.get("matched_terms", [])], 12)

    lines = [
        f"# Literature Answer: {question}",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Profile: {profile.get('name', 'unnamed')}",
        f"- Papers searched: {len(records)}",
        f"- Papers retrieved: {len(selected)}",
        "",
        "## Short Answer",
        "",
    ]
    if selected:
        leading_terms = ", ".join(term for term, _ in terms[:6]) or "the retrieved papers"
        lines.append(
            f"Your library has a usable cluster around {leading_terms}. The strongest evidence is concentrated in the papers below; use this as a starting point for a Codex discussion rather than a final scholarly conclusion."
        )
    else:
        lines.append("No strong local-library matches were found. You may need a broader Scholar search or a temporary runtime boost.")
    lines.append("")

    lines.extend(["## Evidence Signals", ""])
    if tags:
        lines.append("- Tags: " + "; ".join(f"{name} ({count})" for name, count in tags))
    if terms:
        lines.append("- Terms: " + "; ".join(f"{name} ({count})" for name, count in terms))
    if not (tags or terms):
        lines.append("- No repeated tags or matched terms in the retrieved set.")
    lines.append("")

    lines.extend(["## Most Relevant Papers", ""])
    for score, record in ranked:
        lines.append(paper_line(record))
        lines.append(f"  - Retrieval score: {score}")
        snippet = text(record.get("snippet"))
        if snippet:
            lines.append(f"  - Alert signal: {snippet[:320]}")
    if not ranked:
        lines.append("No retrieved papers.")
    lines.append("")

    lines.extend(
        [
            "## Follow-Up Prompts",
            "",
            "- Compare the top 3 papers and identify whether they disagree or simply address different subproblems.",
            "- Turn these papers into a literature-review paragraph with claims, evidence, and citations.",
            "- Identify which paper should be read first and what to extract from it.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_research_advice(
    records: list[dict[str, Any]],
    profile: dict[str, Any],
    feedback: dict[str, Any] | None = None,
    limit: int = 12,
) -> str:
    must = [record for record in records if record.get("tier") == "Must read"]
    skim = [record for record in records if record.get("tier") == "Skim"]
    feedback_papers = (feedback or {}).get("papers", {}) if isinstance(feedback, dict) else {}
    explicitly_interested = {
        paper_id
        for paper_id, item in feedback_papers.items()
        if isinstance(item, dict) and item.get("status") == "interested"
    }
    interested = [record for record in records if record.get("tier") == "Must read" or record.get("id") in explicitly_interested]
    all_term_counter = Counter(str(term) for record in records for term in record.get("matched_terms", []) if str(term).strip())
    all_terms = all_term_counter.most_common(18)
    interested_terms = top_counter([str(term) for record in interested for term in record.get("matched_terms", [])], 18)
    tags = top_counter([str(tag) for record in records for tag in record.get("tags", [])], 12)
    alerts = top_counter([str(alert) for record in records for alert in record.get("alerts", [])], 12)
    profile_term_set = {term.lower() for term in profile_terms(profile)}
    repeated_terms = {term.lower() for term, count in all_term_counter.items() if count >= 3}
    profile_gaps = [term for term in profile_terms(profile) if term.lower() not in repeated_terms]

    lines = [
        "# Research Advice From Your Literature Base",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Profile: {profile.get('name', 'unnamed')}",
        f"- Foundation papers: {len(records)}",
        f"- Must read: {len(must)}; Skim: {len(skim)}; Interested signals: {len(interested)}",
        "",
        "## Current Center Of Gravity",
        "",
    ]
    if interested_terms:
        lines.append("- Interested/Must-read terms: " + "; ".join(f"{name} ({count})" for name, count in interested_terms[:10]))
    if tags:
        lines.append("- Direction tags: " + "; ".join(f"{name} ({count})" for name, count in tags[:8]))
    if alerts:
        lines.append("- Repeated alert sources: " + "; ".join(f"{name} ({count})" for name, count in alerts[:8]))
    if not (interested_terms or tags or alerts):
        lines.append("- Not enough retained papers to infer a stable direction yet.")
    lines.append("")

    lines.extend(["## Possible Gaps", ""])
    if profile_gaps:
        for term in profile_gaps[:limit]:
            lines.append(f"- `{term}` is in your profile but is not yet a repeated foundation signal.")
    else:
        lines.append("- Most configured profile terms have at least some repeated coverage in the foundation.")
    emerging = [term for term, count in all_term_counter.most_common() if term.lower() not in profile_term_set and count >= 4]
    for term in emerging[:limit]:
        lines.append(f"- `{term}` appears repeatedly but is not explicitly configured; consider whether it should become a focus term, method, or exclude term.")
    lines.append("")

    lines.extend(["## Reading Strategy", ""])
    for record in sorted(must, key=lambda item: -int(item.get("score", 0) or 0))[:limit]:
        lines.append(paper_line(record))
    if not must:
        lines.append("- No Must read papers in the retained library; lower thresholds or add more precise profile terms.")
    lines.append("")

    lines.extend(
        [
            "## Suggested Research Moves",
            "",
            "- Pick one high-frequency method/region pair and ask `ask-library` for a focused evidence map.",
            "- Run `deep-read` on the top paper before adding it to a manuscript or proposal.",
            "- Archive repeated off-topic clusters so future daily digests become sharper.",
            "- Promote genuinely recurring unconfigured terms into your profile only after they match your active research question.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_reading_status(records: list[dict[str, Any]], feedback: dict[str, Any] | None = None) -> str:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(reading_status(record, feedback), []).append(record)
    order = ["reading", "unread", "read", "must-cite", "method-reference", "background-only", "not-relevant"]
    lines = [
        "# Reading Status",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Papers tracked: {len(records)}",
        "",
    ]
    for status in order:
        items = sorted(
            grouped.get(status, []),
            key=lambda record: (-int(record.get("score", 0) or 0), text(record.get("title")).lower()),
        )
        if not items:
            continue
        lines.extend([f"## {status} ({len(items)})", ""])
        for record in items[:80]:
            labels = reading_labels(record, feedback)
            suffix = f" labels: {', '.join(labels)}" if labels else ""
            lines.append(paper_line(record) + suffix)
        if len(items) > 80:
            lines.append(f"- ... {len(items) - 80} more")
        lines.append("")
    for status, items in grouped.items():
        if status in order:
            continue
        lines.extend([f"## {status} ({len(items)})", ""])
        for record in items[:80]:
            lines.append(paper_line(record))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_compare(records: list[dict[str, Any]], profile: dict[str, Any], feedback: dict[str, Any] | None = None) -> str:
    all_terms = sorted(set.intersection(*(record_terms(record) for record in records))) if len(records) > 1 else sorted(record_terms(records[0])) if records else []
    lines = [
        "# Paper Comparison",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Profile: {profile.get('name', 'unnamed')}",
        f"- Papers compared: {len(records)}",
        "",
        "## At A Glance",
        "",
        "| Paper | Tier | Score | Reading status | Main signals |",
        "|---|---:|---:|---|---|",
    ]
    for record in records:
        signals = ", ".join(str(term) for term in record.get("matched_terms", [])[:8])
        status = reading_status(record, feedback)
        title = text(record.get("title", "Untitled")).replace("|", "\\|")
        url = text(record.get("url", ""))
        title_cell = f"[{title}]({url})" if url else title
        lines.append(f"| {title_cell} | {record.get('tier', '')} | {record.get('score', 0)} | {status} | {signals} |")
    lines.append("")

    lines.extend(["## Shared Context", ""])
    if all_terms:
        lines.append("- Shared terms/signals: " + ", ".join(all_terms[:20]))
    else:
        lines.append("- No strong shared terms; these papers may be useful as contrasts rather than one cluster.")
    lines.append("")

    lines.extend(["## Per-Paper Notes", ""])
    for index, record in enumerate(records, 1):
        lines.extend(
            [
                f"### {index}. {text(record.get('title', 'Untitled'))}",
                "",
                f"- ID: `{record.get('id', '')}`",
                f"- Link: {record.get('url', '')}",
                f"- Source: {record.get('authors_source', '')}",
                f"- Directions: {', '.join(str(tag) for tag in record.get('tags', []))}",
                f"- Matched: {', '.join(str(term) for term in record.get('matched_terms', []))}",
                f"- Reading status: {reading_status(record, feedback)}",
                "",
                text(record.get("snippet", "No snippet available.")),
                "",
            ]
        )
    lines.extend(
        [
            "## Decision Help",
            "",
            "- If one paper has the strongest method signal, mark it `method-reference`.",
            "- If one paper is central to your own argument, mark it `must-cite`.",
            "- If several papers mainly provide background, mark them `background-only` and keep only the best citation.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_research_map(
    records: list[dict[str, Any]],
    profile: dict[str, Any],
    feedback: dict[str, Any] | None = None,
    limit: int = 12,
) -> str:
    tag_groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        tags = [str(tag) for tag in record.get("tags", []) if str(tag).strip() and str(tag) != "watchlist"]
        if not tags:
            tags = ["uncategorized"]
        for tag in tags:
            tag_groups.setdefault(tag, []).append(record)
    term_counts = top_counter([str(term) for record in records for term in record.get("matched_terms", [])], 30)
    lines = [
        "# Research Map",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Profile: {profile.get('name', 'unnamed')}",
        f"- Papers mapped: {len(records)}",
        "",
        "## Topic Signals",
        "",
    ]
    if term_counts:
        lines.append("; ".join(f"`{term}` ({count})" for term, count in term_counts[:20]))
    else:
        lines.append("No repeated term signals yet.")
    lines.append("")

    lines.extend(["## Direction Clusters", ""])
    for tag, items in sorted(tag_groups.items(), key=lambda item: (-len(item[1]), item[0])):
        ranked = sorted(items, key=lambda record: (-int(record.get("score", 0) or 0), text(record.get("title")).lower()))
        status_counts = Counter(reading_status(record, feedback) for record in ranked)
        terms = top_counter([str(term) for record in ranked for term in record.get("matched_terms", [])], 10)
        lines.extend(
            [
                f"### {tag} ({len(ranked)})",
                "",
                "- Reading status: " + "; ".join(f"{name} ({count})" for name, count in status_counts.most_common()),
            ]
        )
        if terms:
            lines.append("- Terms: " + "; ".join(f"{name} ({count})" for name, count in terms[:8]))
        lines.append("")
        for record in ranked[:limit]:
            lines.append(paper_line(record))
        if len(ranked) > limit:
            lines.append(f"- ... {len(ranked) - limit} more")
        lines.append("")

    lines.extend(
        [
            "## How To Use This Map",
            "",
            "- Pick one cluster and use `ask-library` for a focused evidence map.",
            "- Mark the top paper in each important cluster as `must-cite` or `method-reference` after reading.",
            "- Archive clusters that keep appearing but do not support your active research question.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def obsidian_safe_name(value: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|]+", " ", value).strip()
    name = " ".join(name.split())
    return name[:120] or "Untitled"


def obsidian_note_name(record: dict[str, Any]) -> str:
    return f"{obsidian_safe_name(text(record.get('title', 'Untitled')))} [{record.get('id', '')}]"


def yaml_list(values: list[str]) -> str:
    if not values:
        return "[]"
    escaped = [str(value).replace('"', '\\"') for value in values]
    return "[" + ", ".join(f'"{value}"' for value in escaped) + "]"


def yaml_scalar(value: Any) -> str:
    cleaned = " ".join(str(value or "").split())
    if not cleaned:
        return '""'
    return '"' + cleaned.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_obsidian_paper(
    record: dict[str, Any],
    feedback: dict[str, Any] | None = None,
    citation_key: str = "",
) -> str:
    labels = reading_labels(record, feedback)
    status = reading_status(record, feedback)
    doi = best_doi(record)
    year = best_year(record)
    journal = best_journal(record)
    authors = best_authors(record)
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    zotero = metadata.get("zotero") if isinstance(metadata.get("zotero"), dict) else {}
    pdf_paths = [str(path) for path in zotero.get("pdf_paths", [])] if isinstance(zotero, dict) else []
    frontmatter = [
        "---",
        f"id: {record.get('id', '')}",
        f"citation_key: {yaml_scalar(citation_key)}",
        f"tier: {record.get('tier', '')}",
        f"score: {record.get('score', 0)}",
        f"reading_status: {status}",
        f"labels: {yaml_list(labels)}",
        f"tags: {yaml_list([str(tag) for tag in record.get('tags', [])])}",
        f"matched_terms: {yaml_list([str(term) for term in record.get('matched_terms', [])])}",
        f"year: {yaml_scalar(year)}",
        f"journal: {yaml_scalar(journal)}",
        f"doi: {yaml_scalar(doi)}",
        f"url: {yaml_scalar(record.get('url', ''))}",
        f"zotero_item_key: {yaml_scalar(zotero.get('item_key', '') if isinstance(zotero, dict) else '')}",
        f"pdf_paths: {yaml_list(pdf_paths)}",
        "---",
        "",
    ]
    lines = frontmatter + [
        f"# {text(record.get('title', 'Untitled'))}",
        "",
        f"- Citation key: `{citation_key}`" if citation_key else "- Citation key: not assigned",
        f"- DOI: {doi or 'not found'}",
        f"- Local PDF: {pdf_paths[0]}" if pdf_paths else "- Local PDF: not linked",
        f"- Year: {year or 'unknown'}",
        f"- Journal: {journal or 'unknown'}",
        f"- Authors: {', '.join(authors[:8]) if authors else 'unknown'}",
        f"- Source: {record.get('authors_source', '')}",
        f"- Scholar alerts: {', '.join(str(alert) for alert in record.get('alerts', [])[:12])}",
        f"- Reading status: `{status}`",
        f"- Labels: {', '.join(labels) if labels else 'none'}",
        "",
        "## Alert Signal",
        "",
        text(record.get("snippet", "No snippet available.")),
        "",
        "## My Notes",
        "",
        "- Core contribution:",
        "- Method/data:",
        "- Key conclusion:",
        "- Limitation:",
        "- Relation to my work:",
        "- Citation context:",
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def render_obsidian_index(records: list[dict[str, Any]], feedback: dict[str, Any] | None = None) -> str:
    lines = [
        "# Scholar Alert Literature Dashboard",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- Papers: {len(records)}",
        "",
        "## Navigation",
        "",
        "- [[Research Map]]",
        "- [[Reading Status]]",
        "- Paper notes live in `01_Papers/`.",
        "- Deep reads, library answers, and comparisons are synced into sibling generated folders.",
        "- User-written synthesis should live outside this generated folder.",
        "",
        "## Status",
        "",
    ]
    status_counts = Counter(reading_status(record, feedback) for record in records)
    for status, count in status_counts.most_common():
        lines.append(f"- {status}: {count}")
    lines.extend(["", "## Papers", ""])
    for record in sorted(records, key=lambda item: (-int(item.get("score", 0) or 0), text(item.get("title")).lower())):
        lines.append(f"- [[{obsidian_note_name(record)}]]")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"
