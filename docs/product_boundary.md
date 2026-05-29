# Product Boundary v2

## Positioning

`scholar-alert-reader` is positioned as a **local, privacy-first literature triage and lightweight paper library builder**.

Primary job:

- ingest paper candidate metadata from multiple sources,
- normalize and deduplicate records,
- rank with explainable signals,
- maintain a local reading queue/library,
- and export simple downstream artifacts.

It is explicitly **not** a hosted citation manager, full-text AI reviewer, or writing platform.
It should work without Obsidian/Zotero and still deliver standalone value.

## Modes

### Standalone Mode (Core)

Always available; this is the product boundary.

- Multi-source ingest: Gmail / Apple Mail / mbox / BibTeX / RIS / web / RSS / arXiv.
- Metadata normalization + dedupe.
- Score and explain with readable reasons.
- Feedback learning: `interested`, `archive`, `more-like-this`, `less-like-this`, reading statuses and notes.
- Local artifacts:
  - `digest.md / digest.html`
  - `papers.jsonl / scored_papers.jsonl`
  - `knowledge_base/index.md / knowledge_base/index.html`
  - `knowledge_base/search_index.json`
  - `foundation.md`, `interested.md`, `archive.md`
  - `reading_plan.md / reading_plan.html`
  - `knowledge_base/` paper notes
- Lightweight dashboard/search/filter for local library browsing.

### Integrated Mode (Optional)

Available when configured; not required:

- Obsidian: exported Markdown notes, generated index pages.
- Zotero: BibTeX/RIS exports and citation-oriented downstream workflows.

Any feature in standalone mode must keep functioning when these integrations are absent.

## Experimental Layer

- `deep-read`
- `workup`
- `review-pack`
- `compare`
- `ask`
- `map`
- `advice`

These are planning/analysis helpers and should remain non-authoritative.

Evidence level is explicit for every experimental report:

- `metadata-only`
- `metadata-enriched`
- `pdf-link-ready`
- `local-pdf-ready`
- `full-text-backed`

When level is `metadata-only`, the report must state that conclusions are for triage only and not citation-ready.

## Core-vs-Optional Contract

- **Core / Standalone:** everything under Standalone Mode is mandatory.
- **Optional:** Obsidian and Zotero outputs are downstream sinks.
- **Not Core:** full-text validity claims, manuscript drafting, and complete knowledge-graph workflows.
