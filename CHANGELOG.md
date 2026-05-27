# Changelog

## Unreleased

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
