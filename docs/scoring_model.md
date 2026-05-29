# Ranking Model (Phase 2)

## Principles

Scoring is the core product value. In this phase it is split into a standalone module
with explainable, per-component contributions.

- Stable legacy behavior for existing CLI paths is kept.
- Internal ranking state is now a structured computation object.
- `core.py` keeps compatibility wrappers.

## Components

The current score decomposition follows these buckets:

- `topical_relevance`: `focus_terms` + `runtime_boost`
- `method_relevance`: `methods`
- `domain_relevance`: `regions` + `semantic_queries`
- `authority_signal`: `watch_authors`
- `novelty_signal`: `occurrence` boosts and recency hints
- `source_signal`: currently implicit/legacy-compatible source boosts
- `semantic_similarity`: fallback semantic token overlap inside profile terms
- `feedback_similarity`: direct feedback terms + adaptive seed-paper similarity
- `exclusion_penalty`: matched `exclude_terms`
- `generic_noise_penalty`: (reserved for future)

Formula (current implementation):

```text
score = topical_relevance
      + method_relevance
      + domain_relevance
      + novelty_signal
      + authority_signal
      + source_signal
      + semantic_similarity
      + feedback_similarity
      + exclusion_penalty
      + generic_noise_penalty
```

## Score output contract

`ranking.score_paper()` returns `ScoreComputation`:

- `total: float` final score
- `components: list[ScoreComponent]`
  - `name` (component bucket)
  - `value`
  - `matched_terms`
  - `explanation`
  - `evidence_field`
- `matched_terms`, `tags`, `reasons`, `forced_tier`

`Paper` fields are still filled for compatibility:

- `paper.score`
- `paper.tier`
- `paper.matched_terms`
- `paper.tags`
- `paper.reasons`

## Experimental evidence boundary

When presenting ranking/explain outputs, clearly state which signals are available:

- metadata-only: title/authors/snippet/alerts/profile/feedback
- metadata-enriched: enriched metadata (DOI/source/year/venue)
- pdf-link-ready: paper has a stable open URL/pdf hint
- full-text-backed: requires local PDF/text extraction and section-aware parse (not default in Phase 2)

## Phase-2 completion check

- Feedback and ranking adjustment functions are implemented in `ranking/scorer.py`.
- Core still exposes the same callable names:
  - `score_paper`
  - `feedback_adjustment`
  - `adaptive_ranking_adjustment`
  - `adaptive_ranking_settings`
- New ranking unit tests validate component breakdown behavior.
