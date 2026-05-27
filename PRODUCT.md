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

Current releases are strongest as a triage and research-memory layer. Ranking, ranking explanation, ranking evaluation, local semantic reranking, selected-paper deep-read briefs, selected-paper workups, Q&A, comparisons, maps, advice, and profile tuning use metadata, snippets, bibliography fields, exact profile terms, lightweight local semantic queries, adaptive feedback similarity, feedback, retained-library context, and cached local full-text briefs when available. The default semantic reranker is sparse and zero-dependency; advanced users can opt into a user-installed local `sentence-transformers` embedding model. Local PDF/text extraction can create a full-text cache and section-aware brief with figure, table, data, and code signals when the user provides a local file path, Zotero supplies a local path, or `fetch-pdf` saves an explicit/open PDF URL locally. `review-workflow` gives users a simpler one-paper path from optional local full-text extraction to `workup` and `review-pack`. `deep-read` now surfaces a concise full-text evidence snapshot when that brief already exists; `workup` turns one selected paper into a human-readable reading/citation/manuscript decision brief; and `review-pack` turns the selected paper, user profile, foundation, interested papers, optional full-text brief, and optional full-text cache into an LLM-ready markdown context pack. Public copy should still describe this as assisted reading rather than autonomous expert full-paper review.

## User Tiers

### Codex-only

For users who do not use Obsidian or Zotero.

- Input: Gmail API, Mail.app, exported `.mbox`, BibTeX/RIS, structured scholarly webpages, RSS/Atom feeds, or arXiv queries.
- Output: `DASHBOARD.html`, `digest.html`, `digest.md`, `papers.json`, `reading_plan.html`, `review_queue.html`, `profiles/profile_doctor.md`, `knowledge_base/`.
- Main actions: self-test, profile-based ranking, ranking explanation, ranking evaluation, embedding check, semantic rerank, dashboard, feedback UI, scheduled/manual digest, profile-tune, reading-plan, deep-read, workup, fetch-pdf, full-text, review-workflow, review-pack, review-queue, feedback-aware ask-library, advice, compare, map.

## Platform Boundaries

- Gmail API, exported mbox, BibTeX/RIS, structured scholarly webpage metadata, RSS/Atom, and arXiv are the portable sources.
- Mail.app integration is macOS-only.
- macOS LaunchAgent scheduling is currently the packaged scheduler; other platforms should use their native scheduler around the same CLI commands.
- Codex is the intended skill interface, but the repository also exposes a plain Python CLI for users who want to run it outside Codex.
- The CLI should work from a source checkout (`python3 -m scholar_alert_reader`), an installed console script (`scholar-alert-reader` / `scholar-reader`), and the legacy wrapper (`scripts/scholar_reader.py`).
- Gmail OAuth credentials are bring-your-own for public distribution. A shared OAuth client requires Google verification before broad use.

### Obsidian optional

For users who want notes in a local vault.

- Generated area: `10_Scholar_Alert_Reader/`.
- User-owned areas: reading notes, topic notes, writing drafts.
- Rule: generated export folders can be refreshed; user-written notes should live outside them.
- Generated dashboard links answer, comparison, and analysis indexes so exported folders are navigable inside Obsidian.

### Zotero optional

For users who want citation/PDF management.

- Export: BibTeX and RIS from retained papers.
- Read-back: Better BibTeX/BibTeX exports can add citation keys, Zotero item keys, and local PDF paths back into retained papers.
- Full-text scaffold: local PDF/text paths and explicit/open fetched PDF URLs can be extracted into text caches, section-aware brief reports with visual/data/code signals, and review packs/batch review queues that carry both the brief and text cache forward with per-paper next actions.
- Obsidian paper notes include citation-oriented frontmatter such as `citation_key`, `doi`, `year`, and `journal`.
- Future direction: add stronger figure-caption/table-body extraction and optional LLM review over extracted local text.

## Product Requirements

- A new user can run `init-project`, read `START_HERE.md`, and complete a first run without knowing the internals.
- A new user can run one `quickstart` command that creates the local project, runs private-data-free checks/demos, and writes a next-step report.
- A new user can open `DASHBOARD.html` as the project home page for the current digest, reading plan, review queue, profile health, retained library, and setup diagnostics.
- A user who gets zero papers can tell whether the run found no source items, parsed source items but no paper records, or filtered all papers as already seen.
- A terminal-only user can install the project with `pip`, run `scholar-alert-reader`, and use generated helper scripts without depending on Codex.
- A new user can run `capabilities` / `capabilities.sh` to understand the product boundary before connecting private data or expecting full-paper review.
- A new user can run a guided `setup-wizard` / `setup_wizard.sh` to choose source, profile template, schedule, and optional Obsidian/Zotero paths without memorizing setup flags, then get a `SOURCE_CHECK.md` readiness report with source-specific setup guidance and next steps.
- A user can turn saved schedule settings into a concrete `SCHEDULE.md` and macOS LaunchAgent plist, then install/status/uninstall it with generated helper scripts.
- CI must verify both source-checkout execution and installed-wheel execution, including packaged resources used by `quickstart` and `setup-wizard`.
- A new user can run `demo_reader.sh` before connecting Gmail, Obsidian, or Zotero.
- A new user can pick a bundled starting profile: `general-geophysics`, `ai-seismology`, `induced-seismicity`, `seismic-imaging`, or `dense-array-monitoring`.
- A new user can run `profile-wizard` / `profile_wizard.sh` to turn current research questions, focus terms, methods, regions, authors, exclusions, semantic intents, limits, and schedule defaults into a usable profile without hand-editing JSON.
- A new user can run `profile-doctor` / `profile_doctor.sh` to diagnose sparse or overbroad profiles, missing semantic/exclusion signals, overlapping thresholds, feedback history, and recent/library ranking behavior.
- A new user can run `list-profile-templates --format markdown` to compare bundled templates by audience, starter sources, and first edits before choosing one.
- A new user can run a bundled-data `self-test` before connecting private email, Zotero, Obsidian, or external feeds.
- A new user can resolve common Gmail, Mail.app, mbox, BibTeX/RIS, web metadata, RSS/arXiv, Obsidian, and Zotero setup failures from a public troubleshooting guide.
- A new user can persist local defaults with `setup` / `setup_reader.sh` instead of repeatedly typing source, schedule, Obsidian, or Zotero path environment variables.
- A user without Gmail can import `import.bib` or `import.ris` from Zotero, Google Scholar library, publishers, or databases and use the same triage/foundation pipeline.
- A user without Gmail or Zotero can import structured scholarly webpage metadata through `web_sources.txt`, monitor feeds through `feeds.txt`, or run targeted arXiv queries.
- A user can tune ranking with focus terms, methods, regions, authors, exclusions, semantic queries, adaptive feedback similarity, temporary boosts, explicit paper feedback, and generated profile-tuning reports.
- A user can generate a browser-friendly next-reading plan that uses tier, score, interested/archive feedback, reading status, labels, latest-run flags, and full-text cache availability; normal knowledge-base-updating runs refresh it automatically.
- A user can generate a ranking explanation report for one paper or a tier-filtered batch, including thresholds, matched terms, feedback status, stored reasons, and tuning moves.
- A user can evaluate ranking quality after several feedback labels, with precision/recall at K, average precision, tier calibration, high-ranked archive false positives, and low-ranked interested missed positives.
- A user can run local semantic reranking to inspect weak-keyword rescues and archive-like downranks, with a markdown report and reranked JSON. The default sparse backend requires no extra dependencies; an optional local `sentence-transformers` backend supports embedding reranking when the user installs it explicitly.
- A user can run `embedding-check` before optional embedding rerank to verify dependency readiness, and only load the model when they explicitly pass `--load-model`.
- A user can fetch explicit/open PDF URLs from user input, arXiv, structured webpage metadata, or OpenAlex metadata into `knowledge_base/pdfs/` without crawling paywalled publisher pages.
- A user can generate a section-aware full-text brief from a local PDF/text file, including section coverage, evidence excerpts, figure/table/data/code signals, missing-section notes, and citation-readiness checks.
- A user can run `deep-read` on a selected paper and automatically see cached full-text section coverage, missing sections, profile overlap, and visual/data/code signals when a full-text brief exists.
- A user can generate a selected-paper workup that connects one paper to the local foundation, interested papers, feedback, optional full-text brief, possible manuscript role, and citation-readiness checks.
- A user can run one selected-paper review workflow that attempts local full-text extraction when possible, writes a workup, writes a review pack, and records next actions in one report.
- A user can trigger selected-paper deep-read/full-review/workup/review-pack reports from the local feedback UI, see and filter current feedback/reading-status badges, save personal reading notes that carry into deep-read/workup/reading-status reports, knowledge-base paper pages, and Obsidian paper notes, mark papers as background-only or not-relevant after reading, and open generated markdown reports from local browser links.
- A browser UI user can ask a question against the retained library and current digest, generate an answer report under `knowledge_base/answers/`, and open it through a safe local route.
- A browser UI user can open a one-paper workspace from a digest card and ask a selected-paper question that compares that paper against the retained foundation, interested papers, reading labels, and saved personal notes.
- A browser UI user can reopen a paper card or workspace and see existing selected-paper answer links for that paper.
- A browser UI user can open a generated answer index that separates selected-paper answers from library-wide answers.
- An Obsidian export user can open dashboard-linked generated indexes for answers, comparisons, and analysis reports instead of browsing copied markdown files manually.
- A user can see saved feedback status, reading labels, and personal note excerpts in `foundation.md`, `interested.md`, and direction-specific indexes, so the main knowledge-base entry points reflect the user's own reading memory.
- A user can mark feedback or reading status from CLI or browser UI and immediately get refreshed `reading_plan.md/html`; when the project root can be inferred, `DASHBOARD.md/html` is refreshed too.
- A browser UI user can open refreshed reading plan, dashboard, foundation, interested queue, reading status, weekly review, and generated reports from local allowlisted links without browsing the file tree.
- A user can ask the retained library a question and retrieve papers through alert metadata, profile terms, reading status, labels, and saved personal notes.
- A user can see saved personal notes in research advice, paper comparisons, and topic maps, so synthesis reports reflect the user's own reading memory rather than only alert metadata.
- A user can generate a weekly review that includes retained-library signals, reading status, labels, and saved personal notes.
- A user can build a review pack that automatically includes the section-aware full-text brief and raw text cache when they exist, so downstream assistants get structured evidence before raw text.
- A user can open `review_queue.md` or `review_queue.html` as a batch-reading panel showing which papers have briefs, text caches, visual/data/code signals, section coverage, and immediate next actions.
- Successful generated `run_reader.sh` runs should refresh `profiles/profile_doctor.md` and `DASHBOARD.md` / `DASHBOARD.html` automatically, with escape hatches for scripted users who set `REFRESH_PROFILE_DOCTOR=0` or `REFRESH_DASHBOARD=0`.
- Zero-paper explanations should appear in terminal output, `summary.json`, `digest.md/html`, and the Dashboard, not only in logs.
- A user can run `privacy-check` / `privacy_check.sh` before sharing a project folder, screenshots, support bundle, issue attachment, or zip archive; it should list risky paths and `.gitignore` gaps without exposing file contents.
- A user can generate a sanitized support bundle for public bug reports without exposing raw mail, tokens, private source lists, feedback contents, or generated knowledge-base text.
- A user can run manually, through generated shell scripts, through Codex automations, or through their operating system scheduler.
- LaunchAgent install/uninstall must be explicit; default schedule generation should be a safe write/preview step.
- Obsidian and Zotero must remain optional.
- Raw mailbox contents, OAuth secrets, Gmail tokens, personal bibliography/feed lists, feedback, and generated personal knowledge bases must not be committed.
- Public issue and PR templates must actively steer users away from uploading raw mail, credentials, private bibliography/feed lists, or generated knowledge bases.
- The default workflow should prefer local files and local browser UI over hosted services.
- Every product-facing command should have a shell helper when a project is initialized.

## Roadmap

- Optional LLM review over extracted local full-text caches.
- Stronger model-cache guidance and local model-path examples for optional embedding rerank backends.
- More demo scenarios with sanitized sample alerts, feedback, retained-library files, capability reports, and support-bundle outputs.
- Optional PyPI release packaging after the GitHub install path is stable.
