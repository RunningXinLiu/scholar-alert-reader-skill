# Changelog

## Unreleased

## v0.2.6 - 2026-05-27

- Add dependency-free `semantic_queries` scoring to rescue papers that match the user's research intent without exact phrase matches.
- Add explainable semantic-match reasons and a `semantic` tag in matched paper outputs.
- Update bundled profile templates with starter semantic queries for AI seismology, seismic imaging, induced seismicity, dense-array monitoring, and general geophysics.

## v0.2.5 - 2026-05-27

- Add `review-pack` / generated `review_paper.sh` for creating LLM-ready selected-paper review context packs.
- Include target metadata, user profile, feedback status, optional local full-text cache, closest foundation papers, and interested/active-reading context in review packs.
- Document the cross-assistant workflow for using Scholar Alert Reader with Codex, Claude, ChatGPT, or any other markdown-capable assistant.

## v0.2.4 - 2026-05-27

- Add `full-text` / generated `full_text_paper.sh` for local PDF/text extraction and full-text reading briefs.
- Cache extracted text under `knowledge_base/full_text/` and write briefs under `knowledge_base/analysis/`.
- Support `pdftotext`, optional Python PDF libraries, and plain text/Markdown exports with graceful errors when tooling is missing.

## v0.2.3 - 2026-05-27

- Add `zotero-sync` / generated `zotero_sync.sh` to read Better BibTeX/BibTeX metadata back into retained papers.
- Store Zotero citation keys, item keys, and local PDF paths under `metadata.zotero`.
- Reuse synced Zotero citation keys and PDF paths in Obsidian paper-note frontmatter.

## v0.2.2 - 2026-05-27

- Add `setup` / generated `setup_reader.sh` to persist local source, profile, schedule, Obsidian, and Zotero defaults in `reader.env`.
- Make generated helper scripts read `reader.env` without overriding explicit one-off environment variables from the caller.
- Show persistent configuration status in generated `START_HERE.md`.

## v0.2.1 - 2026-05-27

- Add bundled research-profile templates for general geophysics, AI seismology, induced seismicity, seismic imaging, and dense-array monitoring.
- Add `list-profile-templates`, `init-profile --template`, `init-project --profile-template`, and generated `copy_profile_template.sh`.
- Clarify that deep-read/Q&A/advice are metadata and retained-library triage aids until a full-text/PDF pipeline is added.

## v0.2.0 - 2026-05-27

- Add a product-oriented `guide` command and generated `START_HERE.md` for local projects.
- Add a sanitized demo mailbox and `demo_reader.sh` so users can test without Gmail, Obsidian, or Zotero.
- Add BibTeX/RIS as first-class input sources for Zotero, publisher, database, and Google Scholar library exports.
- Add RSS/Atom and arXiv as structured web input sources without arbitrary web scraping.
- Add `source-check` / `source_check.sh` for Gmail, Mail.app, mbox, BibTeX/RIS, RSS/arXiv, and auto source diagnostics.
- Add checked-in GitHub/朋友圈 marketing assets: social card, architecture diagram, workflow GIF, and Chinese share copy.
- Add CodeGraph/source-of-truth documentation while keeping `.codegraph/` ignored as generated local state.
- Add literature-copilot commands for deep reads, local-library Q&A, research advice, reading status, comparisons, and research maps.
- Add optional Zotero and Obsidian export flows with structured Obsidian folders and citation-oriented frontmatter.
- Expand diagnostics to check optional Obsidian and Zotero integration outputs.
- Document Codex-only, Obsidian, Zotero, and platform support modes in `README.md` and `PRODUCT.md`.

## v0.1.0 - 2026-05-27

Initial private release.

- Read Google Scholar Alert emails from Gmail API, Mail.app, or exported mbox files.
- Generate Markdown/HTML digests, JSON/CSV outputs, and a retained knowledge base.
- Support personalized ranking through research profiles and paper-level feedback.
- Provide local feedback UI, OpenAlex/Crossref enrichment, weekly synthesis, exports, and diagnostics.
- Add `init-project` for creating a runnable local project scaffold.
- Add unit tests and GitHub Actions CI.
