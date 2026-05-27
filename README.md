<p align="center">
  <img src="docs/assets/logo.png" alt="Scholar Alert Reader logo" width="104">
</p>

# Scholar Alert Reader Skill

Turn paper alerts, bibliography exports, structured scholarly webpages, and web feeds into a personalized reading queue, daily digest, and cumulative research knowledge base.

Version: `0.2.54`

Created by [Xin Liu](https://github.com/RunningXinLiu).

<p align="center">
  <img src="docs/assets/social-card.en.png" alt="Scholar Alert Reader social card" width="900">
</p>

<p align="center">
  <img src="docs/assets/workflow.en.gif" alt="Animated Scholar Alert Reader workflow" width="760">
</p>

## Start Here

Scholar Alert Reader works as a normal local Python CLI. Codex is the most guided entry point, but it is not required.

If you are a Codex user, install the skill and then talk to Codex in plain language:

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/RunningXinLiu/scholar-alert-reader-skill.git \
  ~/.codex/skills/scholar-alert-reader
```

Restart Codex or reload skills, then ask:

```text
Use the scholar-alert-reader skill to initialize a Scholar Alert project for me.
```

Good next prompts:

- "Explain what this tool can and cannot do before I connect my data."
- "Check whether my Gmail/Mail.app/mbox/BibTeX/RIS/web/RSS/arXiv source is ready."
- "Run the setup wizard and configure my source/profile/schedule."
- "Run the profile wizard and turn my current research questions into a ranking profile."
- "Run the profile doctor and tell me whether my ranking profile is too broad or too sparse."
- "Run semantic rerank and show me papers that exact keywords may have missed."
- "Build my first foundation from existing Scholar Alert emails."
- "Run today's new-paper digest."
- "Import this Zotero or publisher BibTeX/RIS export into the same triage flow."
- "Import papers from this scholarly webpage or saved HTML list."
- "Pull papers from this RSS feed or arXiv query and rank them against my profile."
- "Open the feedback UI so I can mark interested papers."
- "Open my Scholar Alert dashboard so I can see the digest, reading plan, review queue, and setup status."
- "Make a reading plan from my retained and recent papers."
- "Deep-read this paper against my foundation."
- "Fetch the open PDF for this paper and build a full-text brief."
- "Make a workup for this paper and tell me whether it is worth reading or citing."
- "Export my retained library to Obsidian and Zotero."

The skill works without Obsidian or Zotero. Those are optional upgrades for people who want a larger personal knowledge system.

## Use Without Codex

You can run the core tool from any terminal or from any coding agent that can access local files and execute shell commands.

```bash
git clone https://github.com/RunningXinLiu/scholar-alert-reader-skill.git
cd scholar-alert-reader-skill
python3 -m scholar_alert_reader quickstart --project-dir ~/scholar_alerts
cd ~/scholar_alerts
./setup_wizard.sh
./dashboard_reader.sh --open
```

Agent compatibility:

- **Claude Code**: supported through the Python CLI. This repo includes `CLAUDE.md` with Claude-specific operating notes.
- **Cursor, Windsurf, Gemini CLI, and similar local agents**: supported if they can run shell commands and read/write local files.
- **Claude Desktop or web chat**: can help interpret outputs, but needs a local tool/MCP/file bridge to run the workflow on your machine.
- **Plain terminal**: fully supported through `python3 -m scholar_alert_reader`, the installed `scholar-alert-reader` command, the compatibility wrapper at `scripts/scholar_reader.py`, and the generated project scripts.

What is agent-specific:

- `SKILL.md` is for Codex skill loading and guided operation.
- `CLAUDE.md` is for Claude Code orientation.
- The durable source of truth is the Python CLI plus local project files, not any one agent.

## Support And Safe Reporting

Use GitHub issues for bugs, source setup help, and feature requests. The issue forms are privacy-first: do not paste raw emails, OAuth credentials, Gmail tokens, private bibliography/feed lists, `seen_papers.json`, `feedback.json`, or generated knowledge-base content.

For public troubleshooting, run a local privacy check first, then generate a sanitized support bundle and review it before posting:

```bash
./privacy_check.sh --strict
./support_bundle.sh
# or
python3 -m scholar_alert_reader privacy-check --project-dir ~/scholar_alerts --strict
python3 -m scholar_alert_reader support-bundle --project-dir ~/scholar_alerts
```

`privacy-check` reports high-risk paths, review-before-sharing files, and recommended `.gitignore` gaps without including raw file contents.

The bundle summarizes versions, platform, config keys, file presence, counts, and sanitized `SOURCE_CHECK.md` / `DOCTOR.md` excerpts without including token contents, raw mailbox data, feedback contents, or generated knowledge-base text.

For credential leaks, raw mailbox exposure, or other security-sensitive problems, use [SECURITY.md](SECURITY.md) instead of a public issue.

## Screenshots

Sanitized demo screenshots are included for product previews and sharing.

| Daily digest | Feedback triage |
|---|---|
| <img src="docs/screenshots/01-daily-digest.png" alt="Daily digest screenshot" width="420"> | <img src="docs/screenshots/02-feedback-triage.png" alt="Feedback triage screenshot" width="420"> |

| Foundation and interested library | Deep read copilot |
|---|---|
| <img src="docs/screenshots/03-foundation-interested.png" alt="Foundation and interested library screenshot" width="420"> | <img src="docs/screenshots/04-deep-read-copilot.png" alt="Deep read copilot screenshot" width="420"> |

| Research map and advice | Obsidian and Zotero handoff |
|---|---|
| <img src="docs/screenshots/05-research-map-advice.png" alt="Research map and advice screenshot" width="420"> | <img src="docs/screenshots/06-obsidian-zotero.png" alt="Obsidian and Zotero handoff screenshot" width="420"> |

## What It Does

- Connects to Gmail API, Apple Mail, exported `.mbox`, BibTeX/RIS files, structured scholarly webpages, RSS/Atom feeds, and arXiv queries.
- Monitors configured web sources such as publisher article pages, journal feeds, saved-search feeds, and arXiv queries without depending on a hosted service.
- Extracts paper title, author/source line, snippet, source label, and link, then deduplicates repeated papers across sources.
- Scores papers against your research profile: keywords, methods, regions, authors, exclusions, lightweight semantic queries, adaptive feedback similarity, and temporary boost terms.
- Explains why selected papers received their current score and tier, including matched terms, feedback status, thresholds, and tuning suggestions.
- Evaluates ranking quality against your interested/archive feedback, including precision/recall, average precision, false positives, and missed positives.
- Reranks saved papers with a local semantic layer so weak-keyword papers close to your profile or interested seeds can be inspected before you tune broad terms; the default backend is sparse and zero-dependency, and an optional local `sentence-transformers` backend is available for users who install it.
- Checks optional embedding readiness before a real embedding rerank, without loading models unless you pass `--load-model`.
- Produces daily or manual HTML/Markdown digests, CSV/JSON outputs, and a retained knowledge base.
- Writes a local `DASHBOARD.html` home page that links the current digest, reading plan, review queue, profile health, retained library, and setup diagnostics.
- Explains zero-paper runs in `summary.json`, `digest.md/html`, terminal output, and the Dashboard, separating all-seen daily runs from empty sources and parser/source metadata problems.
- Lets you mark papers as `interested`, `archive`, `more-like-this`, or `less-like-this`, and trigger deep-read/full-review/workup/review-pack reports from the browser UI, so future rankings adapt to your taste through reusable terms and local paper-to-paper similarity.
- Includes a bundled-data `self-test` so new users can verify the install without touching private email or note libraries.
- Includes `privacy-check` so users can scan local projects for files that should not be published before sharing issue attachments, screenshots, or zip archives.
- Supports scheduled or manual runs through generated shell scripts, macOS LaunchAgent plists, Codex automations, or your own cron/system scheduler.
- Adds a literature-copilot layer: selected-paper metadata briefs, one-command paper review workflows, human-readable paper workups, local-library Q&A, reading plans, paper comparison, research maps, gap/advice reports, and LLM-ready review packs.
- Fetches explicit/open PDF URLs from user input, arXiv, structured webpage metadata, or OpenAlex metadata into local files before full-text extraction.
- Exports Zotero-ready BibTeX/RIS and Obsidian-ready Markdown notes while keeping both tools optional.

## Capability Boundary

For a concise product-boundary report, run:

```bash
python3 -m scholar_alert_reader capabilities
# or inside an initialized project
./capabilities.sh
```

The core ranking layer is local and explainable: profile terms, methods, regions, watched authors, exclusions, semantic queries, temporary boosts, explicit feedback, adaptive similarity to retained/interested papers, and optional semantic reranking. `semantic-rerank` defaults to sparse TF-IDF with no extra dependencies; `--backend sentence-transformers` uses a user-installed local embedding model. It is not a hosted embedding service or autonomous reviewer.

`deep-read`, `workup`, `ask`, `compare`, `map`, and `advice` use alert metadata, bibliography fields, snippets, profile context, the retained library, and cached local full-text briefs when available. They are triage and research-planning aids. For closer reading, provide local PDF/text paths directly or through Zotero, fetch an explicit/open PDF URL with `fetch-pdf`, run `review-workflow`, or use the lower-level `full-text`, `workup`, `review-pack`, and `review-queue` commands when you want more control.

## Product Modes

Scholar Alert Reader is useful without any external note app:

1. **Codex-only**: read alerts or bibliography exports, rank papers, evaluate ranking from feedback, run semantic rerank, fetch explicit/open PDFs when available, write HTML/Markdown digests, maintain a local knowledge base, and use reading-plan/deep-read/workup/review-workflow/Q&A/review-pack/advice commands.
2. **Codex + Obsidian**: sync generated notes, maps, reading status, answers, comparisons, and deep reads into a generated Obsidian folder.
3. **Codex + Zotero + Obsidian**: use Zotero for citations/PDFs and Obsidian for durable human-written notes and synthesis.

Obsidian and Zotero are optional integrations. The core workflow remains local files plus Codex.

## Architecture

![Scholar Alert Reader architecture](docs/assets/architecture-showcase.en.png)

Chinese sharing assets are also included under `docs/assets/*.zh.*` and paired with Chinese copy in [docs/share-copy.zh.md](docs/share-copy.zh.md).

## Platform Support

- Gmail API source: macOS, Linux, and Windows, as long as Python can open the OAuth browser flow once and store the token.
- Exported `.mbox` source: macOS, Linux, and Windows.
- BibTeX/RIS source: macOS, Linux, and Windows. Useful when the user has Zotero, EndNote, publisher exports, Google Scholar library exports, or no Gmail access.
- Structured webpage metadata, RSS/Atom, and arXiv sources: macOS, Linux, and Windows. Useful for publisher article pages, journal feeds, saved-search feeds, and structured web monitoring without deep crawling.
- Mail.app source: macOS only, because it uses AppleScript and requires Automation permission.
- LaunchAgent scheduling: macOS only. Other platforms can use cron, systemd timers, or Task Scheduler around `run_reader.sh` / the Python CLI.
- Codex skill mode is the intended UX, but the Python CLI can also be run directly from this repository.

## Framework Layout

```text
scholar_alert_reader/
├── core.py        # CLI, source parsing/ranking pipeline, knowledge-base writes
├── copilot.py     # deep-read, workups, Q&A, advice, maps, Obsidian rendering
├── diagnostics.py # setup checks
├── enrich.py      # OpenAlex/Crossref enrichment
├── export.py      # BibTeX/RIS/Markdown/JSONL exporters
├── server.py      # local browser feedback UI
└── weekly.py      # weekly synthesis renderer
```

The package can run as `python3 -m scholar_alert_reader` or as an installed `scholar-alert-reader` command. The original `scripts/scholar_reader.py` path is kept as a compatibility wrapper, so existing automations can continue to call it.

## Install As A CLI

Run directly from a clone:

```bash
git clone https://github.com/RunningXinLiu/scholar-alert-reader-skill.git
cd scholar-alert-reader-skill
python3 -m scholar_alert_reader --version
python3 -m scholar_alert_reader quickstart --project-dir ~/scholar_alerts
```

Install from the checkout into your current Python environment:

```bash
python3 -m pip install .
scholar-alert-reader quickstart --project-dir ~/scholar_alerts
```

Install straight from GitHub:

```bash
python3 -m pip install "git+https://github.com/RunningXinLiu/scholar-alert-reader-skill.git"
scholar-reader quickstart --project-dir ~/scholar_alerts
```

If you plan to use Gmail API from an installed CLI, install the optional Gmail dependencies:

```bash
python3 -m pip install "scholar-alert-reader-skill[gmail] @ git+https://github.com/RunningXinLiu/scholar-alert-reader-skill.git"
```

If you plan to use the optional local embedding reranker, install the embedding extra from a checkout or install `sentence-transformers` in the same environment:

```bash
python3 -m pip install '.[embedding]'
```

Then verify the backend before using it in scheduled runs:

```bash
python3 -m scholar_alert_reader embedding-check \
  --backend sentence-transformers \
  --embedding-model sentence-transformers/all-MiniLM-L6-v2
```

Add `--load-model` only when you want to test actual model loading/cache behavior.

Initialized project scripts remember the Python used at setup time, prefer `PROJECT_DIR/.venv/bin/python` when it exists, and fall back to `python3 -m scholar_alert_reader` when the repository wrapper is not available.

## CodeGraph

CodeGraph is supported as a local structural index, but `.codegraph/` is generated state and is not the source of truth. Source code remains in `scholar_alert_reader/`, `scripts/`, and `tests/`. See [references/codegraph.md](references/codegraph.md).

## Install As A Codex Skill

Copy this folder into your Codex skills directory:

```bash
cp -R scholar-alert-reader-skill ~/.codex/skills/scholar-alert-reader
```

Then restart Codex or reload skills.

You can also install directly from GitHub:

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/RunningXinLiu/scholar-alert-reader-skill.git \
  ~/.codex/skills/scholar-alert-reader
```

After that, Codex can read `SKILL.md` and guide the user through setup, source checks, Gmail OAuth, daily runs, feedback, deep reads, and optional Obsidian/Zotero exports.

## Gmail API Setup

Install dependencies in your preferred Python environment:

```bash
python3 -m pip install -r requirements-gmail.txt
```

Create a Google Cloud OAuth client with application type `Desktop app`, download the JSON, and save it as:

```text
~/.codex/scholar-alert-reader/gmail_credentials.json
```

Authorize Gmail:

```bash
python3 -m scholar_alert_reader auth-gmail \
  --gmail-credentials ~/.codex/scholar-alert-reader/gmail_credentials.json \
  --gmail-token ~/.codex/scholar-alert-reader/gmail_token.json
```

Gmail OAuth distribution model:

- Do not ship your own OAuth client JSON in this repository.
- For private or small-team use, each user should create their own Google Cloud Desktop OAuth client and add themselves as a test user when needed.
- For a public hosted/shared app, the app owner must handle Google OAuth verification before broad distribution.
- The skill requests Gmail read-only access: `https://www.googleapis.com/auth/gmail.readonly`.

## Quick Start

Create a runnable local project:

```bash
python3 -m scholar_alert_reader quickstart --project-dir ~/scholar_alerts
cd ~/scholar_alerts
```

`quickstart` creates the project, runs private-data-free checks and demos, and writes `QUICKSTART_REPORT.md`. To do the steps manually instead:

```bash
python3 -m scholar_alert_reader init-project --project-dir ~/scholar_alerts
cd ~/scholar_alerts
```

Run the bundled-data self-test. It does not read Gmail, Mail.app, Zotero, Obsidian, or any personal files:

```bash
./self_test.sh
```

Read the capability boundary before connecting private data:

```bash
./capabilities.sh
./privacy_check.sh
```

Open the generated onboarding guide:

```bash
cat START_HERE.md
./guide_reader.sh
./dashboard_reader.sh --open
```

Try the built-in demo without Gmail, Obsidian, or Zotero:

```bash
./demo_reader.sh
./demo_sources.sh
./source_check.sh --source auto
open reader_out/demo/digest.html
```

`demo_sources.sh` runs sanitized examples for mbox, BibTeX, RIS, webpage metadata, and RSS into `reader_out/demo_sources/`.

Persist your local defaults:

```bash
./setup_wizard.sh
```

Or configure non-interactively:

```bash
./setup_reader.sh \
  --source auto \
  --profile-template ai-seismology \
  --schedule-time 09:00 \
  --schedule-days weekdays
```

Both setup paths write `reader.env`, which is automatically read by generated helper scripts. Explicit one-off command variables still win, so `SOURCE=mbox ./run_reader.sh`, `WEB_SOURCE=... ./web_import.sh`, or `RSS_SOURCE=... ./rss_import.sh` can override the saved defaults.

The wizard also writes `SOURCE_CHECK.md` after configuration. Add `--live-check` when you want it to attempt a real Gmail, mbox, bibliography, web, RSS, or arXiv read immediately. The report includes source-specific next steps for OAuth, Mail.app permissions, mbox placement, BibTeX/RIS exports, web source lists, RSS feed lists, and arXiv queries.

Render or install the local schedule:

```bash
./schedule_reader.sh --action write
./schedule_reader.sh --action install
./schedule_reader.sh --action status
```

`schedule_reader.sh --action write` creates `SCHEDULE.md` plus a LaunchAgent plist under `LaunchAgents/` without touching macOS scheduling. On macOS, `--action install` writes the plist to `~/Library/LaunchAgents/` and loads it with `launchctl`; `--action uninstall` removes it. Other platforms can use the generated report and `run_reader.sh` with cron, systemd timers, or Task Scheduler.

Choose a starting research profile:

```bash
python3 -m scholar_alert_reader list-profile-templates
python3 -m scholar_alert_reader list-profile-templates --format markdown
./copy_profile_template.sh --template ai-seismology --force
./profile_wizard.sh
./profile_doctor.sh
```

Bundled templates include:

- `general-geophysics`: broad seismology/geophysics triage.
- `ai-seismology`: foundation models, phase picking, association, relocation, continuous waveform learning, and benchmarks.
- `induced-seismicity`: injection-induced seismicity, microseismic monitoring, mechanisms, hazards, and case comparison.
- `seismic-imaging`: surface waves, ambient noise, receiver functions, anisotropy, FWI, and inversion uncertainty.
- `dense-array-monitoring`: dense arrays, DAS, urban monitoring, continuous detection, and array processing.

The template is only the starting point. Use `./profile_wizard.sh` to add your own current questions, regions, authors, methods, exclusions, and semantic queries without editing JSON by hand:

```bash
./profile_wizard.sh \
  --focus "surface wave tomography, ambient noise, seismic foundation model" \
  --method "uncertainty quantification, phase picking" \
  --region "Tibet, Sichuan Basin" \
  --question "Which new papers are worth reading for my current manuscript?"
```

You can still edit `profiles/research_profile.json` directly when you want full control over adaptive ranking settings, tier thresholds, and temporary boost terms.

After editing or after a few days of feedback, run:

```bash
./profile_doctor.sh
```

It writes `profiles/profile_doctor.md` with checks for sparse profiles, overly broad high-weight terms, missing semantic queries, missing exclusions, overlapping thresholds, feedback history, and recent/library ranking behavior.

`semantic_queries` are short natural-language descriptions of things you care about. They use local token-overlap matching, not a hosted embedding service, so they can rescue papers whose wording differs from your exact keywords while keeping the score explainable.

`adaptive_ranking` is the feedback loop. After you mark papers as `interested`, `more-like-this`, `archive`, `less-like-this`, `reading`, `must-cite`, or `method-reference`, later runs compare new papers with those local seeds. Similar papers get a small boost; papers similar to archived seeds get a penalty. This is local and explainable, not an embedding service.

Run daily triage:

```bash
./run_reader.sh
```

Import from BibTeX or RIS without Gmail:

```bash
cp ~/Downloads/my_papers.bib import.bib
./bibtex_import.sh
open reader_out/bibtex/digest.html
```

```bash
cp ~/Downloads/my_papers.ris import.ris
./ris_import.sh
open reader_out/ris/digest.html
```

You can also test the import route with sanitized examples:

```bash
BIBTEX_PATH=examples/sample_import.bib ./bibtex_import.sh
RIS_PATH=examples/sample_import.ris ./ris_import.sh
```

Import from structured scholarly webpages, RSS/Atom, or arXiv:

```bash
WEB_SOURCE=examples/sample_web_article.html ./web_import.sh
open reader_out/web/digest.html
```

```bash
WEB_SOURCE=examples/web_sources.example.txt ./web_import.sh
open reader_out/web/digest.html
```

The webpage importer reads common scholarly metadata from configured URLs or saved HTML files: citation meta tags, JSON-LD, Dublin Core, and OpenGraph. It is meant for article pages and saved search pages with structured metadata, not arbitrary full-site crawling.

```bash
RSS_SOURCE=examples/sample_feed.atom ./rss_import.sh
open reader_out/rss/digest.html
```

```bash
ARXIV_QUERY='cat:physics.geo-ph AND all:tomography' ./arxiv_search.sh
open reader_out/arxiv/digest.html
```

Open the feedback UI:

```bash
./serve_reader.sh
```

The browser UI can mark papers, show current feedback and reading-status badges, filter by tier or reading status, generate `Deep read` / `Full review` / `Workup` / `Review pack` reports, and open generated markdown reports through local `/report?...` links.

Review recent alerts again without modifying the cumulative library:

```bash
./review_recent.sh
./serve_recent.sh
```

You can still run directly from this repository:

```bash
python3 scripts/scholar_reader.py daily --source-gmail --profile profiles/research_profile.json --out-dir out/daily --kb-dir knowledge_base
```

Direct BibTeX/RIS imports use the same ranking and knowledge-base pipeline:

```bash
python3 scripts/scholar_reader.py run --source-bibtex ~/Downloads/export.bib --profile profiles/research_profile.json --out-dir out/bibtex --kb-dir knowledge_base
python3 scripts/scholar_reader.py run --source-ris ~/Downloads/export.ris --profile profiles/research_profile.json --out-dir out/ris --kb-dir knowledge_base
```

Direct webpage/RSS/arXiv imports use the same pipeline:

```bash
python3 scripts/scholar_reader.py run --source-web ~/scholar_alerts/web_sources.txt --profile profiles/research_profile.json --out-dir out/web --kb-dir knowledge_base
python3 scripts/scholar_reader.py run --source-rss ~/scholar_alerts/feeds.txt --profile profiles/research_profile.json --out-dir out/rss --kb-dir knowledge_base
python3 scripts/scholar_reader.py run --source-arxiv-query 'cat:physics.geo-ph AND all:tomography' --profile profiles/research_profile.json --out-dir out/arxiv --kb-dir knowledge_base
```

## Feedback Loop

Each digest includes a short paper `ID`. Mark papers from the latest `papers.json`:

```bash
python3 scripts/scholar_reader.py feedback \
  --profile profiles/research_profile.json \
  --papers-json out/daily/papers.json \
  --paper-id <ID> \
  --mark interested \
  --more-like-this
```

Suppress a paper and similar future papers:

```bash
python3 scripts/scholar_reader.py feedback \
  --profile profiles/research_profile.json \
  --papers-json out/daily/papers.json \
  --paper-id <ID> \
  --mark archive \
  --less-like-this
```

The command writes `knowledge_base/feedback.json` by default and immediately refreshes `foundation.md` / `interested.md` when the selected paper should enter or leave the retained library. Later `daily`, `foundation`, and `run` commands load that file automatically when they use the same `--kb-dir`; they also use retained/interested papers as adaptive ranking seeds. Use `--no-feedback` on a run to ignore saved feedback and adaptive seeds temporarily.

Start the local feedback UI:

```bash
python3 scripts/scholar_reader.py serve \
  --profile profiles/research_profile.json \
  --papers-json out/daily/papers.json \
  --kb-dir knowledge_base \
  --open
```

The UI includes buttons for `Interested`, `Archive`, `Deep read`, `Full review`, `Workup`, `Review pack`, reading status, citation/method labels, `Background only`, and `Not relevant`. Paper cards show the current feedback state, reading status, labels, and more/less-like-this signals. Generated reports appear as links on the paper card after the action completes.

## Literature Copilot

Analyze one selected paper against your retained foundation/interested library:

```bash
python3 scripts/scholar_reader.py deep-read \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --papers-json out/recent/papers.json \
  --paper-id <ID>
```

If `knowledge_base/analysis/<paper-id>_full_text_brief.md` already exists, `deep-read` includes a full-text evidence snapshot with section coverage, missing sections, visual/data/code signals, profile overlap, and an excerpt. Use `--full-text-brief-path` when the brief was written to a custom path.

Capability boundary: `deep-read`, `workup`, `ask`, `compare`, `map`, and `advice` use alert metadata, bibliography fields, snippets, profile terms, adaptive feedback similarity, the retained local library, and cached local full-text briefs when available. They are designed for triage and research planning. `full-text` can extract a local PDF/text file when you provide the path, sync it from Zotero, or fetch an explicit/open PDF URL. The tool does not crawl publisher pages, bypass access controls, or download paywalled PDFs.

Fetch an explicit or open PDF URL into the local project:

```bash
python3 scripts/scholar_reader.py fetch-pdf \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --papers-json reader_out/daily/papers.json \
  --paper-id PAPER_ID \
  --extract
```

`fetch-pdf` looks for `--pdf-url` first, then open PDF candidates in arXiv URLs, structured webpage metadata such as `citation_pdf_url`, and OpenAlex metadata after `enrich`. It writes `knowledge_base/pdfs/<paper-id>.pdf` by default. Use `--update-library` when the paper is already retained and you want future `full-text` / `review-workflow` calls to find the downloaded local path automatically.

If a local PDF path has been synced from Zotero, extract text and write a full-text brief:

```bash
python3 scripts/scholar_reader.py full-text \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --paper-id <ID>
```

`full-text` uses local files only. It tries `pdftotext` first, then optional Python PDF libraries (`pypdf` / `PyPDF2`), and also accepts `.txt` / `.md` text exports through `--pdf-path`. It writes `knowledge_base/full_text/<paper-id>.txt` and `knowledge_base/analysis/<paper-id>_full_text_brief.md`. The brief detects common paper sections, reports section coverage, extracts evidence by section, flags figure/table/supplement/data/code signals, lists missing or weak sections, and adds a citation-readiness checklist before you build a `review-pack`.

Build a human-readable paper workup for one selected paper:

```bash
python3 scripts/scholar_reader.py workup \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --paper-id <ID>
```

`workup` writes `knowledge_base/analysis/<paper-id>_workup.md`. It connects one paper to your profile, feedback state, closest foundation/interested papers, optional full-text brief, possible manuscript role, citation checks, and next commands. Use it when you want to decide whether a paper should become `reading`, `must-cite`, `method-reference`, `background-only`, or `not-relevant`.

Run the one-paper review workflow when you want the simplest path from a selected paper to usable review artifacts:

```bash
python3 scripts/scholar_reader.py review-workflow \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --paper-id <ID>
```

`review-workflow` writes `knowledge_base/analysis/<paper-id>_review_workflow.md`, attempts local PDF/text extraction when a path is provided, synced from Zotero, or fetched from an explicit/open URL, writes/refreshes the full-text brief when possible, then writes both `knowledge_base/analysis/<paper-id>_workup.md` and `knowledge_base/analysis/<paper-id>_review_pack.md`. Use `--pdf-path /path/to/paper.pdf` for an explicit local file, `--fetch-pdf --pdf-url https://.../paper.pdf` for an open PDF URL, `--no-extract` to use existing caches only, and `--strict-full-text` when you want the command to fail if no local text cache is available.

Build an LLM-ready review context pack for Codex, Claude, ChatGPT, or another markdown-capable assistant:

```bash
python3 scripts/scholar_reader.py review-pack \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --paper-id <ID>
```

`review-pack` writes `knowledge_base/analysis/<paper-id>_review_pack.md`. It combines the selected paper, your research profile, feedback status, closest foundation papers, interested/active-reading papers, any cached `knowledge_base/analysis/<paper-id>_full_text_brief.md`, and any cached `knowledge_base/full_text/<paper-id>.txt`. Paste that file into your assistant when you want a more careful discussion of one paper without uploading your whole mailbox or knowledge base. Use `--full-text-brief-path` when your brief was written to a custom path.

Build a batch review queue for the top papers. When Zotero has synced local PDF paths, or when `fetch-pdf --update-library` has stored open PDF paths, the command attempts local full-text extraction first, then writes one review pack per paper plus an index:

```bash
python3 scripts/scholar_reader.py review-queue \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --tiers "Must read" \
  --limit 5
```

`review-queue` writes `knowledge_base/analysis/review_queue.md` and `knowledge_base/analysis/review_queue.html`, `knowledge_base/full_text/<paper-id>.txt` plus `knowledge_base/analysis/<paper-id>_full_text_brief.md` when extraction succeeds, and `knowledge_base/analysis/<paper-id>_review_pack.md` for each selected paper. The queue index summarizes how many papers have briefs, text caches, and visual/data/code signals, then shows each paper's section coverage, missing/weak sections, signals, and next action. Use `--no-extract` to rely only on existing caches, `--no-html` to skip the browser-friendly queue, or `--strict-full-text` when every selected paper must have a local text cache.

Make a reading plan from retained papers plus an optional recent digest:

```bash
python3 scripts/scholar_reader.py reading-plan \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --papers-json out/recent/papers.json \
  --limit 10
```

`reading-plan` writes `knowledge_base/reading_plan.md` and `knowledge_base/reading_plan.html`. It combines tier, score, interested/archive feedback, reading status, labels, latest-run flags, and local full-text cache availability so you can choose which IDs should go into `review-workflow`, `full-text`, `workup`, `review-pack`, or `review-queue` next. Normal runs that update the knowledge base refresh both files automatically; use the command directly when you want to include a specific recent `papers.json`, change the limit, or write to another path.

Explain why one paper or a batch received its current tier and score:

```bash
python3 scripts/scholar_reader.py explain-ranking \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --paper-id <ID>
```

`explain-ranking` writes `knowledge_base/analysis/ranking_explanation.md` by default. It uses saved `papers.json` or `library.json` ranking fields and reports thresholds, matched terms, tags, feedback status, stored ranking reasons, and concrete tuning moves. Use `--tiers "Must read,Skim" --limit 10` to explain a batch, or `--papers-json reader_out/daily/papers.json` to explain a recent digest.

Evaluate whether the saved ranking matches your feedback:

```bash
python3 scripts/scholar_reader.py ranking-eval \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --papers-json reader_out/daily/papers.json
```

`ranking-eval` writes `knowledge_base/analysis/ranking_evaluation.md` by default. It uses explicit `interested`, `archive`, `more-like-this`, `less-like-this`, and reading-status feedback labels to report precision/recall at K, average precision, tier calibration, high-ranked archive false positives, low-ranked interested missed positives, and concrete tuning recommendations. Run it after several labels; unlabeled papers are ignored for metrics.

Rerank saved papers with a local semantic layer:

```bash
python3 scripts/scholar_reader.py semantic-rerank \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --papers-json reader_out/daily/papers.json
```

`semantic-rerank` writes `knowledge_base/analysis/semantic_rerank.md` and `knowledge_base/analysis/semantic_reranked_papers.json` by default. With the default backend, it uses local sparse TF-IDF over titles, snippets, source text, matched terms, tags, profile questions/terms, interested/more-like-this seeds, archive/less-like-this seeds, and optional Must-read tier seeds. Use it to inspect potential semantic rescues before changing broad profile terms.

For optional local embedding reranking, install the extra dependency and choose a sentence-transformers model:

```bash
python3 -m pip install '.[embedding]'
python3 scripts/scholar_reader.py semantic-rerank \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --papers-json reader_out/daily/papers.json \
  --backend sentence-transformers \
  --embedding-model sentence-transformers/all-MiniLM-L6-v2
```

The embedding backend still runs locally and does not upload papers. It may download the chosen model the first time unless you provide a local model path or pre-cache it. Use `--backend sparse` for deterministic zero-dependency reranking.

Preflight the optional embedding backend without loading the model:

```bash
python3 scripts/scholar_reader.py embedding-check \
  --project-dir . \
  --backend sentence-transformers \
  --embedding-model sentence-transformers/all-MiniLM-L6-v2
```

Use `--load-model` when you want the check to actually load the model and encode sample text. Initialized projects provide `./embedding_check.sh`.

Open the project dashboard:

```bash
python3 scripts/scholar_reader.py dashboard \
  --project-dir ~/scholar_alerts \
  --out-dir ~/scholar_alerts/reader_out/daily \
  --open
```

Initialized projects also provide `./dashboard_reader.sh --open`. The dashboard writes `DASHBOARD.md` and `DASHBOARD.html`, then links the current digest, `reading_plan.html`, `review_queue.html`, profile doctor report, foundation/interested files, source check, doctor report, and next commands. Successful `./run_reader.sh` runs refresh both `profiles/profile_doctor.md` and the dashboard automatically unless `REFRESH_PROFILE_DOCTOR=0` or `REFRESH_DASHBOARD=0` is set.

When a run produces zero papers, check the `No-paper diagnosis` section in the digest or Dashboard. The same structured reason appears in `summary.json` as `empty_run_diagnosis`, with one of the common reasons: `all_seen`, `source_no_items`, `parsed_no_papers`, or `empty_unknown`.

Ask a question against the local literature base:

```bash
python3 scripts/scholar_reader.py ask \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --question "receiver function + Tibet 有哪些关键论文？"
```

Generate research-gap and reading-strategy advice:

```bash
python3 scripts/scholar_reader.py advice \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base
```

Project scaffolds also provide `./deep_read_paper.sh`, `./workup_paper.sh`, `./full_text_paper.sh`, `./fetch_pdf.sh`, `./review_paper.sh`, `./review_workflow.sh`, `./review_queue.sh`, `./explain_ranking.sh`, `./ranking_eval.sh`, `./embedding_check.sh`, `./semantic_rerank.sh`, `./reading_plan.sh`, `./tune_profile.sh`, `./ask_library.sh`, and `./advice_reader.sh`.

Tune the profile after you have marked papers as interested/archive or more-like-this/less-like-this:

```bash
python3 scripts/scholar_reader.py profile-tune \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base
```

`profile-tune` writes `knowledge_base/profile_tuning.md` with suggested `focus_terms`, `semantic_queries`, and `exclude_terms`. It does not edit the profile unless you pass `--apply`.

## Reading System And Integrations

Track reading state and labels:

```bash
python3 scripts/scholar_reader.py status \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --papers-json out/recent/papers.json \
  --paper-id <ID> \
  --status reading \
  --label must-cite
```

Compare selected papers:

```bash
python3 scripts/scholar_reader.py compare \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --paper-id <ID1>,<ID2>
```

Generate a topic map from the retained library:

```bash
python3 scripts/scholar_reader.py map \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base
```

Export Zotero-ready BibTeX/RIS files:

```bash
python3 scripts/scholar_reader.py zotero \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base
```

Read Zotero / Better BibTeX metadata back into the retained library:

```bash
python3 scripts/scholar_reader.py zotero-sync \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --bibtex ~/Downloads/My_Library.bib
```

This matches retained papers by DOI or normalized title and stores Zotero citation keys, item keys, and local PDF paths under `metadata.zotero`. Obsidian exports then reuse the Zotero citation key and include linked PDF paths in paper-note frontmatter.

Export an Obsidian-ready Markdown folder:

```bash
python3 scripts/scholar_reader.py obsidian \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --vault-dir "~/Documents/Obsidian Vault/01_Literatures/10_Scholar_Alert_Reader"
```

The Obsidian export is structured as `00_Dashboard/`, `01_Papers/`, `02_Maps/`, `03_Reading/`, `04_Answers/`, `05_Comparisons/`, and `06_Deep_Reads/` inside the target folder. Keep that generated folder separate from user-written reading notes and topic notes.

Project scaffolds also provide `./status_reader.sh`, `./compare_papers.sh`, `./map_reader.sh`, `./zotero_export.sh`, `./zotero_sync.sh`, `./obsidian_export.sh`, and `./sync_obsidian_vault.sh`.

Check input-source readiness without running the full workflow:

```bash
./source_check.sh --source auto
./source_check.sh --source gmail --live
./source_check.sh --source mail-app --live
./source_check.sh --source mbox --mbox-path examples/sample_scholar_alerts.mbox --live
./source_check.sh --source bibtex --bibtex-path import.bib --live
./source_check.sh --source ris --ris-path import.ris --live
./source_check.sh --source web --web-source examples/sample_web_article.html --live
./source_check.sh --source rss --rss-source examples/sample_feed.atom --live
./source_check.sh --source arxiv --arxiv-query 'cat:physics.geo-ph AND all:tomography' --live
```

`mail-app` is intentionally explicit because it can trigger macOS Automation permission prompts.

When `source-check` writes `SOURCE_CHECK.md`, it includes an actionable setup guide for the effective source and common recovery steps for WARN results. Use `--live` only when you want it to attempt an actual read from that source.

## Metadata And Weekly Review

Enrich the retained library with public metadata:

```bash
python3 scripts/scholar_reader.py enrich \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --limit 20 \
  --providers openalex,crossref \
  --update-library
```

Generate or refresh the weekly synthesis:

```bash
python3 scripts/scholar_reader.py weekly \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --days 7
```

The richer knowledge base includes:

- `papers/<paper-id>.md`: one note page per retained paper
- `directions/*.md`: retained papers grouped by topic tags
- `weekly_review.md`: recurring synthesis from the retained library
- `reading_plan.md` / `reading_plan.html`: prioritized next-reading queue from retained/recent papers
- `profile_tuning.md`: suggested profile updates from feedback patterns
- `analysis/ranking_explanation.md`: score/tier explanation and profile tuning moves for selected papers
- Project-root `EMBEDDING_CHECK.md`: optional embedding rerank readiness report
- `analysis/semantic_rerank.md` / `analysis/semantic_reranked_papers.json`: local semantic rerank report and reranked records, including the backend used
- `pdfs/<paper-id>.pdf`: optional PDF fetched from an explicit/open PDF URL
- `full_text/<paper-id>.txt`: optional local text cache extracted from a PDF/text file
- `analysis/<paper-id>_review_workflow.md`: one-paper workflow report linking extraction status, workup, and review pack
- `analysis/<paper-id>_workup.md`: selected-paper decision brief for reading, citation, and manuscript use
- `analysis/<paper-id>_review_pack.md`: selected-paper review context for an assistant
- `analysis/review_queue.md` / `analysis/review_queue.html`: batch index for review packs and full-text extraction status
- Project-root `DASHBOARD.md` / `DASHBOARD.html`: home page for current outputs, setup status, and next actions

## Export And Diagnostics

Export retained papers:

```bash
python3 scripts/scholar_reader.py export \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --format bibtex
```

Supported export formats are `bibtex`, `ris`, `markdown`, and `jsonl`.

Check a local setup:

```bash
python3 -m scholar_alert_reader self-test --strict
python3 -m scholar_alert_reader capabilities \
  --project-dir ~/scholar_alerts \
  --output ~/scholar_alerts/CAPABILITIES.md
python3 -m scholar_alert_reader privacy-check \
  --project-dir ~/scholar_alerts
python3 -m scholar_alert_reader doctor \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --out-dir out/daily \
  --gmail-deps
python3 -m scholar_alert_reader support-bundle \
  --project-dir ~/scholar_alerts
```

Render a product-oriented setup/status guide:

```bash
python3 -m scholar_alert_reader guide \
  --project-dir ~/scholar_alerts \
  --output ~/scholar_alerts/START_HERE.md
```

Pass `--obsidian-dir` and `--zotero-dir` only when those integrations are enabled.

If a source returns no papers, Gmail OAuth is blocked, or generated outputs are missing, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Testing

```bash
python -m py_compile scripts/scholar_reader.py scholar_alert_reader/*.py
python -m scholar_alert_reader --version
python -m unittest discover -s tests
python -m pip install build
python -m build
```

GitHub Actions runs compile and unit tests on Python 3.10, 3.11, and 3.12. It also builds the wheel, installs it into a clean virtual environment, and smoke-tests the installed `scholar-alert-reader` CLI against bundled sample data.

## Privacy

See [PRIVACY.md](PRIVACY.md). The short version: run `./privacy_check.sh --strict` before sharing files, and do not publish raw mailbox exports, OAuth credentials, Gmail tokens, `seen_papers.json`, `feedback.json`, PDFs/full-text caches, or generated knowledge bases unless you have reviewed and sanitized them.

## Do Not Commit

Do not commit:

- Gmail OAuth credentials or token files
- raw mailbox exports
- personal `import.bib` / `import.ris` files
- personal `web_sources.txt` source lists
- personal `zotero.bib` read-back files
- personal `zotero.ris` read-back files
- personal `feeds.txt` source lists
- `reader.env`
- `seen_papers.json`
- `feedback.json`
- `PRIVACY_CHECK.md` if it lists private paths
- `SUPPORT_BUNDLE.md` until reviewed
- local PDFs and extracted full-text caches
- generated `knowledge_base/full_text/` text caches
- generated `out/`
- generated `knowledge_base/`
