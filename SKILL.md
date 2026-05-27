---
name: scholar-alert-reader
description: Build and run an automatic literature triage workflow from Google Scholar Alert emails, exported mbox files, BibTeX/RIS bibliography files, scholarly webpage metadata, RSS/Atom feeds, arXiv queries, Gmail API, Mail.app, and research-profile feedback. Use when the user wants daily or manual paper-reading digests, Scholar Alert analysis, bibliography import, structured web literature monitoring, personalized paper ranking, or an automated research reading push system.
---

# Scholar Alert Reader

Turn Google Scholar Alert emails into a small, personalized reading queue and cumulative literature knowledge base.

Core rule: reduce noise before summarizing. Extract, dedupe, score against the user's current research profile, then deep-read only the highest-value papers.

## Workflow

1. For a new local setup, prefer `quickstart` to create a project, run private-data-free checks/demos, and write `QUICKSTART_REPORT.md`. Use `init-project` when the user wants only the scaffold. The CLI can be invoked as `python3 -m scholar_alert_reader`, an installed `scholar-alert-reader` / `scholar-reader` command, or the compatibility wrapper `python3 scripts/scholar_reader.py`.
2. Run `self-test` or `./self_test.sh` first when the user wants to verify the install without connecting Gmail, Obsidian, Zotero, or private files.
3. Run `./demo_reader.sh` when the user wants to inspect the sample mbox digest output. Run `./demo_sources.sh` when the user wants to verify all bundled non-private source paths.
4. Run `./setup_wizard.sh` / `setup-wizard` for guided first-time configuration, source-specific setup explanations, and an immediate `SOURCE_CHECK.md`, or `./setup_reader.sh` / `setup` to persist local defaults non-interactively in `reader.env`.
5. Choose a source:
   - Gmail API: preferred for automation after OAuth setup.
   - Mail.app: works locally on macOS after Automation permission.
   - `.mbox`: works from exported Gmail/Apple Mail archives.
   - BibTeX/RIS: works from Zotero, EndNote, Google Scholar library, publisher, and database exports.
   - Structured webpage metadata: works from publisher/article URLs, saved HTML files, or URL/path lists with citation meta tags, JSON-LD, Dublin Core, or OpenGraph.
   - RSS/Atom or arXiv: works for structured web monitoring without deep crawling arbitrary pages.
6. Load or create a JSON research profile. For new users, start from a bundled template such as `general-geophysics`, `ai-seismology`, `induced-seismicity`, `seismic-imaging`, or `dense-array-monitoring`, then run `profile-wizard` / `./profile_wizard.sh` to add current questions, focus terms, methods, regions, authors, exclusions, and semantic intents before editing advanced JSON settings by hand. Use `profile-doctor` / `./profile_doctor.sh` after edits or feedback rounds to check whether the profile is too broad, too sparse, missing semantic queries/exclusions, or producing noisy ranking behavior.
7. First run: use `foundation` to build the seen-paper baseline.
8. Later runs: use `daily` so only papers not already in the state file are reported.
   - If the digest has zero papers, inspect `empty_run_diagnosis` in `summary.json` or the `No-paper diagnosis` section in `digest.md/html` / `DASHBOARD.html` before assuming Gmail/Mail parsing failed.
9. Use `feedback` to mark papers as interested/archive or more-like-this/less-like-this. The command refreshes the retained knowledge base immediately, and later runs load `knowledge_base/feedback.json` plus retained papers for adaptive similarity ranking automatically.
10. Use `profile-tune` after several feedback rounds to suggest profile changes from interested/archive patterns. Apply suggestions only when the user asks for it or passes `--apply`.
11. For interactive triage, use `serve` to open a local feedback UI. For higher-value retained papers, use `enrich` before weekly synthesis.
12. Use `dashboard` / `dashboard_reader.sh` as the project home page after setup or any successful run; it links the current digest, reading plan, review queue, profile health, knowledge base, and diagnostics.
13. Use `schedule` / `schedule_reader.sh` when the user wants local automation from saved `SCHEDULE_TIME` / `SCHEDULE_DAYS`: write first, install only on macOS after source-check passes.
14. Use `reading-plan`, `explain-ranking`, `deep-read`, `workup`, `full-text`, `review-workflow`, `review-pack`, `review-queue`, `ask`, and `advice` to turn the retained library into a personal literature copilot.
15. Use `status`, `compare`, and `map` to track reading state, compare papers, and see the research landscape.
16. Use `capabilities` when the user asks what the tool can/cannot do, `zotero`, `obsidian`, or `export` for external-tool handoff, `guide` for product-oriented setup/status guidance, and `source-check`, `doctor`, `support-bundle`, plus `TROUBLESHOOTING.md` when diagnosing local setup problems.

Platform rule: Gmail API, exported mbox, BibTeX/RIS, structured webpage metadata, RSS/Atom, and arXiv work cross-platform; Mail.app and LaunchAgent automation are macOS-only. Do not imply Obsidian or Zotero are required.

Gmail distribution rule: never ship the developer's OAuth client JSON or token. For shared/public use, each user should bring their own Desktop OAuth client unless the app owner has completed Google OAuth verification for a shared client. The requested scope is Gmail read-only.

Capability boundary: ranking and literature-copilot commands start from alert metadata, bibliography fields, snippets, profile terms, local token-overlap semantic queries, adaptive feedback similarity, and retained-library context. `workup` is a human-readable selected-paper decision brief; `full-text` can extract local PDF/text files when the user provides them or when Zotero sync supplies a local path. `review-pack` creates a markdown context pack for Codex, Claude, ChatGPT, or another assistant; it does not upload files or claim autonomous expert review.

## Outputs

- `digest.md` and `digest.html`: human-readable triage reports.
- `papers.json` and `papers.csv`: structured run output.
- `summary.json`: run metadata, source counts, seen-state filtering counts, and `empty_run_diagnosis` when no papers are written.
- `deep_read_queue.md`: top papers for actual reading.
- `seen_papers.json`: dedupe state; can include every alert item.
- `DASHBOARD.md` and `DASHBOARD.html`: local project home page linking the latest digest, reading plan, review queue, profile health, library files, setup reports, and next actions.
- `SCHEDULE.md` and `LaunchAgents/*.plist`: local schedule report and macOS LaunchAgent plist generated from `reader.env`.
- `knowledge_base/feedback.json`: explicit user feedback and ranking signals.
- `knowledge_base/profile_tuning.md`: suggested profile updates from interested/archive feedback patterns.
- `knowledge_base/library.json`: cumulative retained papers, usually Must read + Skim.
- `knowledge_base/foundation.md`: cumulative retained library grouped by direction.
- `knowledge_base/interested.md`: cumulative high-priority reading queue, usually Must read.
- `knowledge_base/daily_additions.md`: retained additions from the latest daily run.
- `knowledge_base/papers/<paper-id>.md`: per-paper note pages.
- `knowledge_base/directions/*.md`: direction-specific retained-paper indexes.
- `knowledge_base/weekly_review.md`: recurring synthesis from the retained library.
- `knowledge_base/reading_plan.md` and `knowledge_base/reading_plan.html`: prioritized next-reading queue from retained/recent papers and feedback, refreshed automatically by runs that update the knowledge base.
- `knowledge_base/analysis/<paper-id>_deep_read.md`: selected-paper deep-read brief against the foundation.
- `knowledge_base/full_text/<paper-id>.txt`: local text cache extracted from a linked PDF/text file.
- `knowledge_base/analysis/<paper-id>_full_text_brief.md`: local full-text extraction brief with section coverage, evidence excerpts, figure/table/data/code signals, missing-section notes, and citation-readiness checks for a selected paper.
- `knowledge_base/analysis/<paper-id>_review_workflow.md`: selected-paper workflow report linking full-text extraction status, workup, review pack, and next actions.
- `knowledge_base/analysis/<paper-id>_workup.md`: human-readable selected-paper decision brief for reading priority, foundation fit, manuscript role, and citation checks.
- `knowledge_base/analysis/<paper-id>_review_pack.md`: LLM-ready context pack for selected-paper review against the user's profile, foundation, interested papers, optional full-text brief, and optional full-text cache.
- `knowledge_base/analysis/review_queue.md` and `knowledge_base/analysis/review_queue.html`: batch reading panel with selected review packs, full-text extraction status, section coverage, visual/data/code signals, and next actions.
- `knowledge_base/analysis/ranking_explanation.md`: score/tier explanation and profile tuning moves for selected papers.
- `knowledge_base/answers/*.md`: local-library answers to user research questions.
- `knowledge_base/research_advice.md`: gap and reading-strategy advice from retained/interested papers.
- `knowledge_base/reading_status.md`: reading tracker grouped by status.
- `knowledge_base/comparisons/*.md`: side-by-side paper comparisons.
- `knowledge_base/research_map.md`: topic clusters and representative papers.
- `knowledge_base/zotero/`: Zotero-ready BibTeX/RIS files.
- `knowledge_base/obsidian/`: Obsidian-ready Markdown dashboard, paper notes, maps, reading status, library answers, comparisons, and deep reads. In a real vault, sync it into a generated folder such as `01_Literatures/10_Scholar_Alert_Reader/`.

`zotero-sync` can read a Better BibTeX/BibTeX export back into `knowledge_base/library.json` so retained papers keep Zotero citation keys, item keys, and local PDF paths under `metadata.zotero`.

Archive-tier papers should not enter the knowledge base by default; they stay in the run outputs and seen-state file only.

## Commands

Create a local project:

```bash
python3 -m scholar_alert_reader quickstart --project-dir ~/scholar_alerts --profile-template ai-seismology
```

Guided first-time setup:

```bash
cd ~/scholar_alerts
./setup_wizard.sh
```

Terminal-only users can also run:

```bash
python3 -m scholar_alert_reader setup-wizard --project-dir ~/scholar_alerts
```

Use `--live-check` when the user wants the wizard to attempt a real source read immediately. Use `--skip-check` only when generating config without validation. `SOURCE_CHECK.md` includes the effective source, readiness checks, and next steps for OAuth, source files, feed lists, arXiv queries, or Mail.app permissions.

Create only the scaffold:

```bash
python3 -m scholar_alert_reader init-project --project-dir ~/scholar_alerts --profile-template ai-seismology
```

Run the bundled-data self-test:

```bash
python3 -m scholar_alert_reader self-test --strict
```

Explain product capabilities and boundaries:

```bash
python3 -m scholar_alert_reader capabilities
python3 -m scholar_alert_reader capabilities \
  --project-dir ~/scholar_alerts \
  --output ~/scholar_alerts/CAPABILITIES.md
```

After `python3 -m pip install .` or a GitHub install, `scholar-alert-reader quickstart ...` and `scholar-reader quickstart ...` are equivalent. When running from a source checkout, `python3 scripts/scholar_reader.py ...` remains supported for backward compatibility.

List or copy bundled profile templates:

```bash
python3 scripts/scholar_reader.py list-profile-templates
python3 scripts/scholar_reader.py init-profile \
  --profile ~/scholar_alerts/profiles/research_profile.json \
  --template seismic-imaging \
  --force
```

Refine a project profile without manual JSON editing:

```bash
python3 scripts/scholar_reader.py profile-wizard \
  --project-dir ~/scholar_alerts \
  --focus "surface wave tomography, ambient noise" \
  --method "uncertainty quantification" \
  --region "Tibet, Sichuan Basin" \
  --question "Which new papers are worth reading for my current manuscript?"
```

Diagnose profile quality:

```bash
python3 scripts/scholar_reader.py profile-doctor \
  --project-dir ~/scholar_alerts \
  --papers-json ~/scholar_alerts/reader_out/daily/papers.json
```

Render or refresh the local onboarding guide:

```bash
python3 scripts/scholar_reader.py guide \
  --project-dir ~/scholar_alerts \
  --output ~/scholar_alerts/START_HERE.md
```

Render or open the local project dashboard:

```bash
python3 scripts/scholar_reader.py dashboard \
  --project-dir ~/scholar_alerts \
  --out-dir ~/scholar_alerts/reader_out/daily \
  --open
```

Initialized projects provide `./dashboard_reader.sh --open`. Successful `./run_reader.sh` runs refresh `profiles/profile_doctor.md`, `DASHBOARD.md`, and `DASHBOARD.html` automatically unless `REFRESH_PROFILE_DOCTOR=0` or `REFRESH_DASHBOARD=0` is set.

Render or install the local schedule:

```bash
python3 scripts/scholar_reader.py schedule \
  --project-dir ~/scholar_alerts \
  --action write
```

Initialized projects provide `./schedule_reader.sh --action write`, `./schedule_reader.sh --action install`, `./schedule_reader.sh --action status`, and `./schedule_reader.sh --action uninstall`. LaunchAgent install/uninstall is macOS-only; other platforms should use the same `run_reader.sh` with their native scheduler.

Persist local source/integration/schedule defaults:

```bash
python3 scripts/scholar_reader.py setup \
  --project-dir ~/scholar_alerts \
  --source auto \
  --profile-template ai-seismology \
  --schedule-time 09:00 \
  --schedule-days weekdays
```

Generated project scripts read `reader.env` only for variables the caller has not already set, so explicit one-off overrides such as `SOURCE=mbox ./run_reader.sh` still win.

Check the configured input source without a full run:

```bash
python3 scripts/scholar_reader.py source-check \
  --project-dir ~/scholar_alerts \
  --source auto
```

Use `--live` to attempt an actual Gmail, Mail.app, mbox, BibTeX, RIS, webpage metadata, RSS/Atom, or arXiv read.

Install Gmail dependencies when using Gmail API:

```bash
python3 -m pip install -r requirements-gmail.txt
```

Authorize Gmail once:

```bash
python3 scripts/scholar_reader.py auth-gmail \
  --gmail-credentials ~/.codex/scholar-alert-reader/gmail_credentials.json \
  --gmail-token ~/.codex/scholar-alert-reader/gmail_token.json
```

Build a foundation from Gmail:

```bash
python3 scripts/scholar_reader.py foundation \
  --source-gmail \
  --profile profiles/research_profile.json \
  --out-dir out/foundation \
  --kb-dir knowledge_base
```

Run daily new-paper triage:

```bash
python3 scripts/scholar_reader.py daily \
  --source-gmail \
  --profile profiles/research_profile.json \
  --out-dir out/daily \
  --kb-dir knowledge_base
```

Run from an exported mbox:

```bash
python3 scripts/scholar_reader.py run \
  --source-mbox ~/Downloads/INBOX.mbox \
  --profile profiles/research_profile.json \
  --out-dir out/manual \
  --kb-dir knowledge_base
```

Run from a BibTeX export:

```bash
python3 scripts/scholar_reader.py run \
  --source-bibtex ~/Downloads/export.bib \
  --profile profiles/research_profile.json \
  --out-dir out/bibtex \
  --kb-dir knowledge_base
```

Run from an RIS export:

```bash
python3 scripts/scholar_reader.py run \
  --source-ris ~/Downloads/export.ris \
  --profile profiles/research_profile.json \
  --out-dir out/ris \
  --kb-dir knowledge_base
```

Run from scholarly webpage metadata:

```bash
python3 scripts/scholar_reader.py run \
  --source-web web_sources.txt \
  --profile profiles/research_profile.json \
  --out-dir out/web \
  --kb-dir knowledge_base
```

`--source-web` accepts a URL, saved `.html`/`.htm` file, directory of saved HTML files, or `.txt`/`.list` file with one URL/path per line. It reads citation meta tags, JSON-LD, Dublin Core, and OpenGraph; it is not a full-site crawler.

Run from an RSS/Atom feed or feed list:

```bash
python3 scripts/scholar_reader.py run \
  --source-rss feeds.txt \
  --profile profiles/research_profile.json \
  --out-dir out/rss \
  --kb-dir knowledge_base
```

Run from an arXiv query:

```bash
python3 scripts/scholar_reader.py run \
  --source-arxiv-query 'cat:physics.geo-ph AND all:tomography' \
  --profile profiles/research_profile.json \
  --out-dir out/arxiv \
  --kb-dir knowledge_base
```

Record feedback from a digest:

```bash
python3 scripts/scholar_reader.py feedback \
  --profile profiles/research_profile.json \
  --papers-json out/daily/papers.json \
  --paper-id <ID> \
  --mark interested \
  --more-like-this
```

```bash
python3 scripts/scholar_reader.py feedback \
  --profile profiles/research_profile.json \
  --papers-json out/daily/papers.json \
  --paper-id <ID> \
  --mark archive \
  --less-like-this
```

Open the local feedback UI:

```bash
python3 scripts/scholar_reader.py serve \
  --profile profiles/research_profile.json \
  --papers-json out/daily/papers.json \
  --kb-dir knowledge_base \
  --open
```

The browser UI can mark papers, generate `Deep read` / `Workup` / `Review pack` reports, update reading labels, and open generated markdown reports through local `/report?name=...` links.

Suggest profile updates from accumulated feedback:

```bash
python3 scripts/scholar_reader.py profile-tune \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base
```

Use `--apply` only when the user wants to write suggested focus/exclude/semantic terms back into the profile.

Analyze a selected paper against the local foundation:

```bash
python3 scripts/scholar_reader.py deep-read \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --papers-json out/recent/papers.json \
  --paper-id <ID>
```

Extract local PDF/text content and write a section-aware full-text brief:

```bash
python3 scripts/scholar_reader.py full-text \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --paper-id <ID>
```

Build a selected-paper workup for reading/citation decisions:

```bash
python3 scripts/scholar_reader.py workup \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --paper-id <ID>
```

Run the one-paper review workflow from optional local full-text extraction to workup and review pack:

```bash
python3 scripts/scholar_reader.py review-workflow \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --paper-id <ID>
```

Use `--pdf-path /path/to/paper.pdf` for an explicit local file, `--no-extract` for existing caches only, and `--strict-full-text` when missing local text should fail the command.

Build a selected-paper review context pack for Codex, Claude, ChatGPT, or another assistant:

```bash
python3 scripts/scholar_reader.py review-pack \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --paper-id <ID>
```

Build review packs for the top reading queue:

```bash
python3 scripts/scholar_reader.py review-queue \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --tiers "Must read" \
  --limit 5
```

Make a reading plan before choosing workup/review-pack IDs:

```bash
python3 scripts/scholar_reader.py reading-plan \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --papers-json out/recent/papers.json \
  --limit 10
```

Normal runs that update the knowledge base refresh `knowledge_base/reading_plan.md` and `knowledge_base/reading_plan.html` automatically; run `reading-plan` directly when the user wants to include a specific recent `papers.json`, change the limit, or set `--html-output`.

Explain why selected papers received their current tier and score:

```bash
python3 scripts/scholar_reader.py explain-ranking \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --paper-id <ID>
```

Use `--tiers "Must read,Skim" --limit 10` to explain a batch, or `--papers-json reader_out/daily/papers.json` to explain a recent digest.

Ask the retained literature base a question:

```bash
python3 scripts/scholar_reader.py ask \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --question "receiver function + Tibet 有哪些关键论文？"
```

Generate research advice:

```bash
python3 scripts/scholar_reader.py advice \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base
```

Track reading status and labels:

```bash
python3 scripts/scholar_reader.py status \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --papers-json out/recent/papers.json \
  --paper-id <ID> \
  --status reading \
  --label must-cite
```

Compare papers:

```bash
python3 scripts/scholar_reader.py compare \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --paper-id <ID1>,<ID2>
```

Render a research map:

```bash
python3 scripts/scholar_reader.py map \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base
```

Export to Zotero or Obsidian:

```bash
python3 scripts/scholar_reader.py zotero \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base
```

```bash
python3 scripts/scholar_reader.py zotero-sync \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --bibtex ~/Downloads/My_Library.bib
```

```bash
python3 scripts/scholar_reader.py obsidian \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --vault-dir "~/Documents/Obsidian Vault/01_Literatures/10_Scholar_Alert_Reader"
```

The Obsidian export is generated content. Prefer syncing it into a dedicated folder such as `01_Literatures/10_Scholar_Alert_Reader/`; keep user-authored reading notes, topic synthesis, and writing drafts in sibling folders so reruns never overwrite personal notes.

Enrich retained papers and write a weekly review:

```bash
python3 scripts/scholar_reader.py enrich \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --limit 20 \
  --providers openalex,crossref \
  --update-library
```

```bash
python3 scripts/scholar_reader.py weekly \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --days 7
```

Export retained papers or diagnose setup:

```bash
python3 scripts/scholar_reader.py export \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --format bibtex
```

```bash
python3 scripts/scholar_reader.py doctor \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --out-dir out/daily \
  --gmail-deps
```

Generate a sanitized public-support bundle:

```bash
python3 scripts/scholar_reader.py support-bundle \
  --project-dir ~/scholar_alerts
```

For extension points and module boundaries, see `references/framework.md`.

## Ranking Guidance

Prioritize papers that match:

- The user's current research questions.
- High-weight focus terms, methods, regions, authors, semantic queries, and adaptive-ranking seeds in the profile/feedback/library.
- Recent papers and papers appearing in multiple alerts.

Down-rank:

- Educational outreach, conference logistics, generic news, non-research items.
- Papers outside the current question even if they are in the broad field.
- Repeated citation alerts unless the cited paper itself is important.
- Papers or terms the user marked with `archive` or `less-like-this`.

## Privacy

Treat mailbox exports, personal bibliography imports, feed lists, and Gmail tokens as private data. Do not upload raw mailbox contents, OAuth credentials, Gmail tokens, `seen_papers.json`, or generated knowledge-base outputs unless the user explicitly asks for that.
