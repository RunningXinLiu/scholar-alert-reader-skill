# Scholar Alert Reader Skill

A Codex skill for turning Google Scholar Alert emails into personalized literature digests and a cumulative reading knowledge base.

Version: `0.1.0`

## What It Does

- Reads Google Scholar Alert emails from Gmail API, Mail.app, or exported `.mbox`.
- Extracts paper title, author/source line, snippet, alert source, and link.
- Deduplicates papers across alerts.
- Scores papers against a JSON research profile.
- Writes daily digests, HTML reports, CSV/JSON output, and a cumulative knowledge base.
- Records explicit feedback so future runs learn from `interested`, `archive`, `more-like-this`, and `less-like-this` marks.
- Offers a local feedback UI, metadata enrichment through public APIs, per-paper notes, direction pages, and weekly synthesis.

## Framework Layout

```text
scholar_alert_reader/
├── core.py       # CLI, parsing/ranking pipeline, knowledge-base writes
├── enrich.py     # OpenAlex/Crossref enrichment
├── server.py     # local browser feedback UI
└── weekly.py     # weekly synthesis renderer
```

The original `scripts/scholar_reader.py` path is kept as a compatibility wrapper, so existing automations can continue to call it.

## Install As A Codex Skill

Copy this folder into your Codex skills directory:

```bash
cp -R scholar-alert-reader-skill ~/.codex/skills/scholar-alert-reader
```

Then restart Codex or reload skills.

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

## Quick Start

Create a runnable local project:

```bash
python3 scripts/scholar_reader.py init-project --project-dir ~/scholar_alerts
cd ~/scholar_alerts
```

Run daily triage:

```bash
./run_reader.sh
```

Open the feedback UI:

```bash
./serve_reader.sh
```

You can still run directly from this repository:

```bash
python3 scripts/scholar_reader.py daily --source-gmail --profile profiles/research_profile.json --out-dir out/daily --kb-dir knowledge_base
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
- `seen_papers.json`
- `feedback.json`
- generated `out/`
- generated `knowledge_base/`
