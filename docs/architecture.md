# Architecture for Phase 2-4 (Refactor Baseline)

Phase 2-4 focuses on separating ranking and standalone-library concerns from legacy ingestion/UI code, while keeping CLI behavior stable.

## Current Structural Intent

```text
scholar_alert_reader/
├── core.py               # command wiring + compatibility surface
├── models.py             # canonical shared dataclasses
├── library/
│   ├── __init__.py
│   └── store.py          # retained-library settings, load/save, merge
├── ranking/
│   ├── __init__.py
│   └── scorer.py         # profile scoring + feedback similarity + explanation generation
├── enrich.py             # optional OpenAlex/Crossref enrichment
├── export.py             # current export helpers (CSV/JSON/Markdown/BibTeX/RIS)
├── diagnostics.py        # health checks and readiness reporting
├── server.py             # browser dashboard entry point
├── weekly.py             # weekly review generation
├── copilot.py            # experimental report workflows
└── resources/            # bundled defaults and examples
```

## Phase-2 Responsibilities

- `core.py` keeps command/API compatibility for existing scripts and tests.
- `ranking/scorer.py` owns:
  - profile term parsing,
  - feedback adjustments,
  - adaptive ranking adjustments,
  - structured score components and reasons.
- `library/store.py` owns:
  - standalone knowledge-base settings,
  - retained library persistence (`library.json`),
  - merge semantics across reruns/imports,
  - direction derivation for lightweight browsing outputs.
- All ranking outputs are still mirrored back into legacy `Paper` fields (`score`, `tier`, `tags`, `reasons`) for compatibility.

## Flow

Core dependency path (standalone):

`ingest/*` → `ranking.scorer` → `ranking.format` → `library.store` / `library.render` → `digest` / `search_index` / exports.

Notes:

- `ranking.format` exposes both:
  - developer/debug lines (`score_component_lines`)
  - user-facing lines (`human_score_component_lines`)
- `library.status` is the shared feedback/reading-state helper used by core and experimental layers.
- `copilot.py` and related workflows are optional/experimental; they are outside the core dependency path above.

Standalone outputs now include:

- `knowledge_base/index.md` and `knowledge_base/index.html`
- `knowledge_base/search_index.json`
- `knowledge_base/papers/*.md`
- existing `foundation.md`, `interested.md`, and direction pages

## Future Target (Phase 3+) Alignment

The above decoupling is the base for the recommended target split:

```text
scholar_alert_reader/
├── ingest/
│   ├── gmail.py
│   ├── mail_app.py
│   ├── mbox.py
│   ├── bibtex.py
│   ├── ris.py
│   ├── rss.py
│   ├── arxiv.py
│   └── web.py
├── normalize/
│   ├── clean.py
│   ├── metadata.py
│   ├── dedupe.py
│   └── enrich.py
├── ranking/
│   ├── profile.py
│   ├── scorer.py
│   ├── explain.py
│   └── feedback.py
├── library/
│   ├── query.py
│   ├── status.py
│   └── render.py
├── export/
│   ├── obsidian.py
│   ├── zotero.py
│   └── markdown.py
└── optional/
    ├── copilot.py
    ├── scheduler.py
    └── server.py
```

This is intentionally aspirational in Phase 2 to avoid overreach before module-by-module extraction.
