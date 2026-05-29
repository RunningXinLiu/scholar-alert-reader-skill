"""Storage and merge logic for the standalone retained paper library."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable


def kb_settings(profile: dict[str, Any]) -> dict[str, Any]:
    configured = profile.get("knowledge_base", {})
    return {
        "foundation_tiers": configured.get("foundation_tiers", ["Must read", "Skim"]),
        "interested_tiers": configured.get("interested_tiers", ["Must read"]),
        "interested_limit": int(configured.get("interested_limit", 50)),
        "foundation_limit_per_direction": int(configured.get("foundation_limit_per_direction", 40)),
        "write_archive_index": bool(configured.get("write_archive_index", False)),
    }


def paper_directions(paper: Any) -> list[str]:
    tags = getattr(paper, "tags", None) or []
    directions = [tag for tag in tags if tag not in {"adaptive", "boost", "feedback", "watchlist"}]
    if not directions:
        directions = ["uncategorized"]
    return sorted(set(directions))


def paper_from_dict(data: dict[str, Any], paper_factory: Callable[..., Any]) -> Any:
    fields = getattr(paper_factory, "__dataclass_fields__", None)
    if fields:
        allowed = set(fields)
        kwargs = {key: value for key, value in data.items() if key in allowed}
    else:
        kwargs = dict(data)
    return paper_factory(**kwargs)


def load_paper_library(
    kb_dir: Path,
    paper_factory: Callable[..., Any],
    load_json: Callable[[Path], Any],
) -> list[Any]:
    path = kb_dir / "library.json"
    if not path.exists():
        return []
    try:
        data = load_json(path)
    except Exception:
        return []
    papers: list[Any] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            papers.append(paper_from_dict(item, paper_factory))
        except Exception:
            continue
    return papers


def merge_papers(existing: list[Any], additions: list[Any]) -> list[Any]:
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

        dates = [
            d
            for d in [current.first_seen, current.last_seen, incoming.first_seen, incoming.last_seen]
            if d
        ]
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

        current.matched_terms = sorted(
            set(current.matched_terms) | set(incoming.matched_terms),
            key=lambda t: t.lower(),
        )
        current.tags = sorted(set(current.tags) | set(incoming.tags))
        current.reasons = list(dict.fromkeys(current.reasons + incoming.reasons))
        current.is_new = current.is_new or incoming.is_new

    return sorted(by_id.values(), key=lambda p: (-p.score, p.title.lower()))


def save_paper_library(
    kb_dir: Path,
    papers: list[Any],
    save_json: Callable[[Path, Any], None],
    asdict_fn: Callable[[Any], dict[str, Any]] | None = None,
) -> None:
    serialize = asdict_fn or asdict
    save_json(kb_dir / "library.json", [serialize(paper) for paper in papers])

