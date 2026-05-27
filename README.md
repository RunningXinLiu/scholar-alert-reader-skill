<p align="center">
  <img src="https://cdn.jsdelivr.net/gh/RunningXinLiu/scholar-alert-reader-skill@main/docs/assets/logo.png" alt="Scholar Alert Reader logo" width="104">
</p>

# Scholar Alert Reader Skill

A Codex skill for turning Google Scholar Alert emails into personalized literature digests and a cumulative reading knowledge base.

Version: `0.1.0`

Created by [Xin Liu](https://github.com/RunningXinLiu).

<p align="center">
  <img src="https://cdn.jsdelivr.net/gh/RunningXinLiu/scholar-alert-reader-skill@main/docs/assets/social-card.png" alt="Scholar Alert Reader social card" width="900">
</p>

<p align="center">
  <img src="https://cdn.jsdelivr.net/gh/RunningXinLiu/scholar-alert-reader-skill@main/docs/assets/workflow.gif" alt="Animated Scholar Alert Reader workflow" width="760">
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

- "Check whether my Gmail/Mail.app/mbox/BibTeX/RIS/RSS/arXiv source is ready."
- "Build my first foundation from existing Scholar Alert emails."
- "Run today's new-paper digest."
- "Import this Zotero or publisher BibTeX/RIS export into the same triage flow."
- "Pull papers from this RSS feed or arXiv query and rank them against my profile."
- "Open the feedback UI so I can mark interested papers."
- "Deep-read this paper against my foundation."
- "Export my retained library to Obsidian and Zotero."

The skill works without Obsidian or Zotero. Those are optional upgrades for people who want a larger personal knowledge system.

## Use Without Codex

You can run the core tool from any terminal or from any coding agent that can access local files and execute shell commands.

```bash
git clone https://github.com/RunningXinLiu/scholar-alert-reader-skill.git
cd scholar-alert-reader-skill
python3 scripts/scholar_reader.py init-project --project-dir ~/scholar_alerts
cd ~/scholar_alerts
./demo_reader.sh
open reader_out/demo/digest.html
```

Agent compatibility:

- **Claude Code**: supported through the Python CLI. This repo includes `CLAUDE.md` with Claude-specific operating notes.
- **Cursor, Windsurf, Gemini CLI, and similar local agents**: supported if they can run shell commands and read/write local files.
- **Claude Desktop or web chat**: can help interpret outputs, but needs a local tool/MCP/file bridge to run the workflow on your machine.
- **Plain terminal**: fully supported through `scripts/scholar_reader.py` and the generated project scripts.

What is agent-specific:

- `SKILL.md` is for Codex skill loading and guided operation.
- `CLAUDE.md` is for Claude Code orientation.
- The durable source of truth is the Python CLI plus local project files, not any one agent.

## Screenshots

Sanitized demo screenshots are included for product previews and sharing.

| Daily digest | Feedback triage |
|---|---|
| <img src="https://cdn.jsdelivr.net/gh/RunningXinLiu/scholar-alert-reader-skill@main/docs/screenshots/01-daily-digest.png" alt="Daily digest screenshot" width="420"> | <img src="https://cdn.jsdelivr.net/gh/RunningXinLiu/scholar-alert-reader-skill@main/docs/screenshots/02-feedback-triage.png" alt="Feedback triage screenshot" width="420"> |

| Foundation and interested library | Deep read copilot |
|---|---|
| <img src="https://cdn.jsdelivr.net/gh/RunningXinLiu/scholar-alert-reader-skill@main/docs/screenshots/03-foundation-interested.png" alt="Foundation and interested library screenshot" width="420"> | <img src="https://cdn.jsdelivr.net/gh/RunningXinLiu/scholar-alert-reader-skill@main/docs/screenshots/04-deep-read-copilot.png" alt="Deep read copilot screenshot" width="420"> |

| Research map and advice | Obsidian and Zotero handoff |
|---|---|
| <img src="https://cdn.jsdelivr.net/gh/RunningXinLiu/scholar-alert-reader-skill@main/docs/screenshots/05-research-map-advice.png" alt="Research map and advice screenshot" width="420"> | <img src="https://cdn.jsdelivr.net/gh/RunningXinLiu/scholar-alert-reader-skill@main/docs/screenshots/06-obsidian-zotero.png" alt="Obsidian and Zotero handoff screenshot" width="420"> |

## What It Does

- Reads Google Scholar Alert emails from Gmail API, Mail.app, exported `.mbox`, bibliography files (`.bib` / `.ris`), RSS/Atom feeds, or arXiv queries.
- Extracts paper title, author/source line, snippet, alert source, and link.
- Deduplicates papers across alerts.
- Scores papers against a JSON research profile.
- Writes daily digests, HTML reports, CSV/JSON output, and a cumulative knowledge base.
- Records explicit feedback so future runs learn from `interested`, `archive`, `more-like-this`, and `less-like-this` marks.
- Offers a local feedback UI, metadata enrichment through public APIs, per-paper notes, direction pages, and weekly synthesis.
- Adds a personal literature copilot layer: selected-paper deep reads against your foundation, local-library Q&A, and research-gap advice.
- Tracks reading status, compares selected papers, renders a research map, and exports Zotero/Obsidian-ready handoff files.

## Product Modes

Scholar Alert Reader is useful without any external note app:

1. **Codex-only**: read alerts or bibliography exports, rank papers, write HTML/Markdown digests, maintain a local knowledge base, and use deep-read/Q&A/advice commands.
2. **Codex + Obsidian**: sync generated notes, maps, reading status, answers, comparisons, and deep reads into a generated Obsidian folder.
3. **Codex + Zotero + Obsidian**: use Zotero for citations/PDFs and Obsidian for durable human-written notes and synthesis.

Obsidian and Zotero are optional integrations. The core workflow remains local files plus Codex.

## Architecture

![Scholar Alert Reader architecture](https://cdn.jsdelivr.net/gh/RunningXinLiu/scholar-alert-reader-skill@main/docs/assets/architecture-showcase.png)

## Platform Support

- Gmail API source: macOS, Linux, and Windows, as long as Python can open the OAuth browser flow once and store the token.
- Exported `.mbox` source: macOS, Linux, and Windows.
- BibTeX/RIS source: macOS, Linux, and Windows. Useful when the user has Zotero, EndNote, publisher exports, Google Scholar library exports, or no Gmail access.
- RSS/Atom and arXiv sources: macOS, Linux, and Windows. Useful for journal feeds, saved-search feeds, and structured web monitoring without scraping arbitrary pages.
- Mail.app source: macOS only, because it uses AppleScript and requires Automation permission.
- LaunchAgent scheduling: macOS only. Other platforms can use cron, systemd timers, or Task Scheduler around `run_reader.sh` / the Python CLI.
- Codex skill mode is the intended UX, but the Python CLI can also be run directly from this repository.

## Framework Layout

```text
scholar_alert_reader/
├── core.py        # CLI, source parsing/ranking pipeline, knowledge-base writes
├── copilot.py     # deep-read, Q&A, advice, maps, Obsidian rendering
├── diagnostics.py # setup checks
├── enrich.py      # OpenAlex/Crossref enrichment
├── export.py      # BibTeX/RIS/Markdown/JSONL exporters
├── server.py      # local browser feedback UI
└── weekly.py      # weekly synthesis renderer
```

The original `scripts/scholar_reader.py` path is kept as a compatibility wrapper, so existing automations can continue to call it.

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
python3 scripts/scholar_reader.py auth-gmail \
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
python3 scripts/scholar_reader.py init-project --project-dir ~/scholar_alerts
cd ~/scholar_alerts
```

Open the generated onboarding guide:

```bash
cat START_HERE.md
./guide_reader.sh
```

Try the built-in demo without Gmail, Obsidian, or Zotero:

```bash
./demo_reader.sh
./source_check.sh --source auto
open reader_out/demo/digest.html
```

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

Import from RSS/Atom or arXiv:

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

Direct RSS/arXiv imports use the same pipeline:

```bash
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

The command writes `knowledge_base/feedback.json` by default and immediately refreshes `foundation.md` / `interested.md` when the selected paper should enter or leave the retained library. Later `daily`, `foundation`, and `run` commands load that file automatically when they use the same `--kb-dir`. Use `--no-feedback` on a run to ignore saved feedback temporarily.

Start the local feedback UI:

```bash
python3 scripts/scholar_reader.py serve \
  --profile profiles/research_profile.json \
  --papers-json out/daily/papers.json \
  --kb-dir knowledge_base \
  --open
```

## Literature Copilot

Analyze one selected paper against your retained foundation/interested library:

```bash
python3 scripts/scholar_reader.py deep-read \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --papers-json out/recent/papers.json \
  --paper-id <ID>
```

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

Project scaffolds also provide `./deep_read_paper.sh`, `./ask_library.sh`, and `./advice_reader.sh`.

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

Export an Obsidian-ready Markdown folder:

```bash
python3 scripts/scholar_reader.py obsidian \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --vault-dir "~/Documents/Obsidian Vault/01_Literatures/10_Scholar_Alert_Reader"
```

The Obsidian export is structured as `00_Dashboard/`, `01_Papers/`, `02_Maps/`, `03_Reading/`, `04_Answers/`, `05_Comparisons/`, and `06_Deep_Reads/` inside the target folder. Keep that generated folder separate from user-written reading notes and topic notes.

Project scaffolds also provide `./status_reader.sh`, `./compare_papers.sh`, `./map_reader.sh`, `./zotero_export.sh`, `./obsidian_export.sh`, and `./sync_obsidian_vault.sh`.

Check input-source readiness without running the full workflow:

```bash
./source_check.sh --source auto
./source_check.sh --source gmail --live
./source_check.sh --source mail-app --live
./source_check.sh --source mbox --mbox-path examples/sample_scholar_alerts.mbox --live
./source_check.sh --source bibtex --bibtex-path import.bib --live
./source_check.sh --source ris --ris-path import.ris --live
./source_check.sh --source rss --rss-source examples/sample_feed.atom --live
./source_check.sh --source arxiv --arxiv-query 'cat:physics.geo-ph AND all:tomography' --live
```

`mail-app` is intentionally explicit because it can trigger macOS Automation permission prompts.

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
python3 scripts/scholar_reader.py doctor \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --out-dir out/daily \
  --gmail-deps
```

Render a product-oriented setup/status guide:

```bash
python3 scripts/scholar_reader.py guide \
  --project-dir ~/scholar_alerts \
  --output ~/scholar_alerts/START_HERE.md
```

Pass `--obsidian-dir` and `--zotero-dir` only when those integrations are enabled.

## Testing

```bash
python -m py_compile scripts/scholar_reader.py scholar_alert_reader/*.py
python -m unittest discover -s tests
```

GitHub Actions runs the same checks on Python 3.10, 3.11, and 3.12.

## Privacy

See [PRIVACY.md](PRIVACY.md). The short version: do not publish raw mailbox exports, OAuth credentials, Gmail tokens, `seen_papers.json`, `feedback.json`, or generated knowledge bases unless you have reviewed and sanitized them.

## Do Not Commit

Do not commit:

- Gmail OAuth credentials or token files
- raw mailbox exports
- personal `import.bib` / `import.ris` files
- personal `feeds.txt` source lists
- `seen_papers.json`
- `feedback.json`
- generated `out/`
- generated `knowledge_base/`
