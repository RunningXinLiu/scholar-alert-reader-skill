# Framework Notes

Use this reference when changing the skill implementation rather than a user's personal profile.

## Module Boundaries

- `scripts/scholar_reader.py`: compatibility wrapper only. Keep this path stable for automations.
- `scholar_alert_reader/core.py`: CLI orchestration, email parsing, ranking, output writes, and backward-compatible command behavior.
- `scholar_alert_reader/server.py`: local feedback UI. It may import `core`, but `core` should import it only lazily inside the `serve` command.
- `scholar_alert_reader/enrich.py`: dependency-free public metadata API calls. It should operate on plain paper dictionaries to avoid coupling API code to the dataclass.
- `scholar_alert_reader/weekly.py`: pure renderer for weekly synthesis from retained paper records.
- `scholar_alert_reader/export.py`: pure export renderers for BibTeX/RIS/Markdown/JSONL.
- `scholar_alert_reader/fulltext.py`: local PDF/text extraction and full-text brief rendering. It should gracefully degrade when optional PDF tooling is missing.
- `scholar_alert_reader/copilot.py`: deterministic literature-copilot renderers, including deep-read, Q&A, comparison, map, Obsidian pages, and LLM-ready review context packs.
- `scholar_alert_reader/tuning.py`: deterministic profile-tuning suggestions from retained papers and explicit feedback. It should not mutate profiles directly; keep writes in `core.py` command handlers.
- `scholar_alert_reader/diagnostics.py`: local setup checks for profile, Gmail token/dependencies, outputs, and knowledge-base files.

## Extension Rules

- Preserve existing commands: `foundation`, `daily`, `run`, `feedback`, and `auth-gmail`.
- Preserve `init-project` generated script names because users may automate them.
- New capabilities should usually be subcommands, not hidden flags on `daily`.
- Keep `self-test` private-data-free. It should use bundled sample files and should not read Gmail, Mail.app, Zotero, Obsidian, or user-provided source files unless explicitly configured.
- Keep scoring explainable: exact profile terms and local `semantic_queries` should produce visible matched terms and reasons.
- Keep `profile-tune` conservative. Default to report-only; require `--apply` before writing suggested terms into a user profile.
- Keep `doctor` dependency-light and safe: it should report paths and counts, not secret token contents.
- Keep raw mailbox contents, OAuth credentials, Gmail tokens, `seen_papers.json`, `feedback.json`, and generated knowledge-base files out of shared repos.
- Treat Zotero/Better BibTeX read-back files as private because they can contain local PDF paths and citation-library identifiers.
- Treat fetched PDFs, extracted full-text caches, and review context packs as private generated knowledge-base content.
- Fetch only explicit/open PDF URLs supplied by the user or structured metadata. Do not add publisher-page crawling or access-control bypasses.
- Enrich only selected retained papers by default. Do not call external APIs for every archived alert item.
- Keep deterministic local outputs as the source of truth: `papers.json`, `library.json`, `feedback.json`, and Markdown pages.

## Release Checks

- Run `python -m py_compile scripts/scholar_reader.py scholar_alert_reader/*.py`.
- Run `python -m unittest discover -s tests`.
- Run a temporary `init-project` and `doctor`.
- Scan for personal paths, tokens, raw OAuth secrets, and mailbox data before pushing.

## Feature Roadmap

- Source adapters: Gmail, Mail.app, mbox, BibTeX/RIS, structured webpage metadata, RSS/Atom, and arXiv now; add Semantic Scholar alerts or other provider-specific saved searches as separate source modules.
- Ranking adapters: current term scoring now; future versions can add embeddings or an LLM reranker after local dedupe.
- Feedback adapters: CLI and local UI now; future versions can add browser extension buttons or email reply parsing.
- Exports: Markdown now; future versions can add Zotero collections, Obsidian vault sync, BibTeX, and Notion/Readwise exports.
