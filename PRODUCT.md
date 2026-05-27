# Product Shape

Scholar Alert Reader should feel like a small local literature product, not a pile of scripts.

## Public Assets

- `docs/assets/social-card.svg` and `docs/assets/social-card.png`: social sharing card.
- `docs/assets/workflow.gif`: animated workflow overview.
- `docs/assets/architecture.svg` and `docs/assets/architecture.png`: architecture diagram.
- `docs/share-copy.zh.md`: short Chinese copy for sharing.
- Regenerate source assets with `python3 scripts/generate_marketing_assets.py`.

## Core Promise

Turn noisy Google Scholar Alert emails into a personalized reading queue and a cumulative research memory.

## User Tiers

### Codex-only

For users who do not use Obsidian or Zotero.

- Input: Gmail API, Mail.app, or exported `.mbox`.
- Output: `digest.html`, `digest.md`, `papers.json`, `knowledge_base/`.
- Main actions: feedback UI, deep-read, ask-library, advice, compare, map.

## Platform Boundaries

- Gmail API and exported mbox are the portable sources.
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
- Obsidian paper notes include citation-oriented frontmatter such as `citation_key`, `doi`, `year`, and `journal`.
- Future direction: read Zotero item keys/PDF paths back into the local knowledge base.

## Product Requirements

- A new user can run `init-project`, read `START_HERE.md`, and complete a first run without knowing the internals.
- A new user can run `demo_reader.sh` before connecting Gmail, Obsidian, or Zotero.
- Obsidian and Zotero must remain optional.
- Raw mailbox contents, OAuth secrets, Gmail tokens, feedback, and generated personal knowledge bases must not be committed.
- The default workflow should prefer local files and local browser UI over hosted services.
- Every product-facing command should have a shell helper when a project is initialized.

## Roadmap

- Setup wizard for source selection, Gmail OAuth path, optional Obsidian path, optional Zotero export path, and schedule.
- Zotero read-back for item keys, PDF paths, and Better BibTeX citation keys.
- PDF full-text deep-read when a local Zotero PDF is available.
- More demo scenarios with sanitized sample alerts, feedback, and retained-library files.
- Release packaging with a versioned changelog and minimal public sample profile.
