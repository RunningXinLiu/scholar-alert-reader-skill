"""Formatting helpers for score components."""

from __future__ import annotations

from typing import Any


def _coerce_component_value(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def paper_score_components(paper: Any) -> list[dict[str, Any]]:
    """Normalize score components for serialization and downstream rendering."""

    components: list[dict[str, Any]] = []
    for component in getattr(paper, "score_components", []):
        if isinstance(component, dict):
            name = str(component.get("name", "")).strip()
            if not name:
                continue
            terms = [str(term) for term in component.get("matched_terms", []) if str(term).strip()]
            evidence = str(component.get("evidence_field", "") or "")
            explanation = str(component.get("explanation", "")).strip()
            components.append(
                {
                    "name": name,
                    "value": _coerce_component_value(component.get("value", 0.0)),
                    "matched_terms": terms,
                    "evidence_field": evidence,
                    "explanation": explanation,
                }
            )
            continue

        name = str(getattr(component, "name", "")).strip()
        if not name:
            continue
        value = getattr(component, "value", 0.0)
        matched_terms = getattr(component, "matched_terms", [])
        components.append(
            {
                "name": name,
                "value": _coerce_component_value(value),
                "matched_terms": [str(term) for term in matched_terms if str(term).strip()],
                "evidence_field": str(getattr(component, "evidence_field", "") or ""),
                "explanation": str(getattr(component, "explanation", "")).strip(),
            }
        )
    return components


def score_component_lines(paper: Any, include_zero: bool = False) -> list[str]:
    """Format score components as human-readable lines."""

    lines: list[str] = []
    for component in paper_score_components(paper):
        value = _coerce_component_value(component.get("value", 0.0))
        if not include_zero and value == 0.0:
            continue
        matched_terms = ", ".join(component.get("matched_terms", []))
        evidence = component.get("evidence_field") or "unknown"
        explanation = component.get("explanation") or ""
        value_text = f"{value:+.2f}" if value % 1 else f"{value:+.0f}"
        line = f"- `{component.get('name', '')}` {value_text}"
        if matched_terms:
            line += f" | matched: {matched_terms}"
        if explanation:
            line += f" | {explanation}"
        line += f" | evidence: `{evidence}`"
        lines.append(line)
    return lines


def aggregate_score_breakdown(components: list[dict[str, Any]]) -> dict[str, float]:
    """Aggregate component values by name."""

    breakdown: dict[str, float] = {}
    for component in components:
        if not isinstance(component, dict):
            continue
        name = str(component.get("name", "")).strip()
        if not name:
            continue
        value = _coerce_component_value(component.get("value", 0.0))
        breakdown[name] = breakdown.get(name, 0.0) + value
    return breakdown

