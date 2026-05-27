# Product Shape

Scholar Alert Reader should feel like a small local literature product, not a pile of scripts.

## Public Assets

- `docs/assets/social-card.en.svg` and `docs/assets/social-card.en.png`: English social sharing card for GitHub and public launch.
- `docs/assets/social-card.zh.svg` and `docs/assets/social-card.zh.png`: Chinese social sharing card for personal/social promotion.
- `docs/assets/logo.svg` and `docs/assets/logo.png`: project logo with a subtle author signature.
- `docs/assets/workflow.en.gif` and `docs/assets/workflow.zh.gif`: bilingual animated workflow overview.
- `docs/assets/architecture.en.svg` / `.png` and `docs/assets/architecture.zh.svg` / `.png`: bilingual architecture diagrams.
- `docs/assets/architecture-showcase.en.svg` / `.png` and `docs/assets/architecture-showcase.zh.svg` / `.png`: bilingual README/social architecture diagrams.
- `docs/assets/social-card.svg`, `docs/assets/social-card.png`, `docs/assets/workflow.gif`, `docs/assets/architecture.svg`, and `docs/assets/architecture.png`: English compatibility aliases.
- `docs/share-copy.zh.md`: short Chinese copy for sharing.
- Regenerate source assets with `python3 scripts/generate_marketing_assets.py`.

## Core Promise

Turn scattered paper alerts, bibliography exports, structured scholarly webpages, and web feeds into a personalized reading queue, daily digest, and cumulative research memory.

## Capability Boundary

Current releases are strongest as a triage and research-memory layer. Ranking, alert-level deep-read briefs, Q&A, comparisons, maps, advice, and profile tuning use metadata, snippets, bibliography fields, exact profile terms, lightweight local semantic queries, feedback, and retained-library context. Local PDF/text extraction can create a full-text cache and brief when the user provides a local file path. `review-pack` turns the selected paper, user profile, foundation, interested papers, and optional full-text cache into an LLM-ready markdown context pack, but public copy should still describe this as assisted reading rather than autonomous expert full-paper review.

## User Tiers

### Codex-only

For users who do not use Obsidian or Zotero.

- Input: Gmail API, Mail.app, exported `.mbox`, BibTeX/RIS, structured scholarly webpages, RSS/Atom feeds, or arXiv queries.
- Output: `digest.html`, `digest.md`, `papers.json`, `knowledge_base/`.
- Main actions: self-test, profile-based ranking, feedback UI, scheduled/manual digest, profile-tune, deep-read, full-text, review-pack, ask-library, advice, compare, map.

## Platform Boundaries

- Gmail API, exported mbox, BibTeX/RIS, structured scholarly webpage metadata, RSS/Atom, and arXiv are the portable sources.
- Mail.app integration is macOS-only.
- macOS LaunchAgent scheduling is currently the packaged scheduler; other platforms should use their native scheduler around the same CLI commands.
- Codex is the intended skill interface, but the repository also exposes a plain Python CLI for users who want to run it outside Codex.
- Gmail OAuth credentials are bring-your-own for public distribution. A shared OAuth client requires Google verification before broad use.

### Obsidian optional

For users who want notes in a local vault.

- Generated area: `10_Scholar_Alert_Reader/`.
- User-owned areas: reading notes, topic notes, writing drafts.
- Rule: generated export folders can be refreshed; user-written notes should live outside them.

### Zotero optional

For users who want citation/PDF management.

- Export: BibTeX and RIS from retained papers.
- Read-back: Better BibTeX/BibTeX exports can add citation keys, Zotero item keys, and local PDF paths back into retained papers.
- Full-text scaffold: local PDF/text paths can be extracted into text caches and brief reports.
- Obsidian paper notes include citation-oriented frontmatter such as `citation_key`, `doi`, `year`, and `journal`.
- Future direction: add stronger section-aware parsing and optional LLM review over extracted local text.

## Product Requirements

- A new user can run `init-project`, read `START_HERE.md`, and complete a first run without knowing the internals.
- A new user can run `demo_reader.sh` before connecting Gmail, Obsidian, or Zotero.
- A new user can pick a bundled starting profile: `general-geophysics`, `ai-seismology`, `induced-seismicity`, `seismic-imaging`, or `dense-array-monitoring`.
- A new user can run a bundled-data `self-test` before connecting private email, Zotero, Obsidian, or external feeds.
- A new user can resolve common Gmail, Mail.app, mbox, BibTeX/RIS, web metadata, RSS/arXiv, Obsidian, and Zotero setup failures from a public troubleshooting guide.
- A new user can persist local defaults with `setup` / `setup_reader.sh` instead of repeatedly typing source, schedule, Obsidian, or Zotero path environment variables.
- A user without Gmail can import `import.bib` or `import.ris` from Zotero, Google Scholar library, publishers, or databases and use the same triage/foundation pipeline.
- A user without Gmail or Zotero can import structured scholarly webpage metadata through `web_sources.txt`, monitor feeds through `feeds.txt`, or run targeted arXiv queries.
- A user can tune ranking with focus terms, methods, regions, authors, exclusions, semantic queries, temporary boosts, explicit paper feedback, and generated profile-tuning reports.
- A user can run manually, through generated shell scripts, through Codex automations, or through their operating system scheduler.
- Obsidian and Zotero must remain optional.
- Raw mailbox contents, OAuth secrets, Gmail tokens, personal bibliography/feed lists, feedback, and generated personal knowledge bases must not be committed.
- The default workflow should prefer local files and local browser UI over hosted services.
- Every product-facing command should have a shell helper when a project is initialized.

## Roadmap

- Interactive setup prompts layered on top of the current non-interactive `setup` command.
- Better section-aware parsing for extracted local PDF text.
- More demo scenarios with sanitized sample alerts, feedback, and retained-library files.
- Release packaging with a versioned changelog and minimal public sample profile.
