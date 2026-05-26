---
name: scholar-alert-reader
description: Build and run an automatic literature triage workflow from Google Scholar Alert emails, exported mbox files, Gmail API, Mail.app, and research-profile feedback. Use when the user wants daily or manual paper-reading digests, Scholar Alert analysis, literature monitoring, personalized paper ranking, or an automated research reading push system.
---

# Scholar Alert Reader

Turn Google Scholar Alert emails into a small, personalized reading queue and cumulative literature knowledge base.

Core rule: reduce noise before summarizing. Extract, dedupe, score against the user's current research profile, then deep-read only the highest-value papers.

## Workflow

1. For a new local setup, run `init-project` to create profiles, outputs, knowledge-base directories, and helper scripts.
2. Choose a source:
   - Gmail API: preferred for automation after OAuth setup.
   - Mail.app: works locally on macOS after Automation permission.
   - `.mbox`: works from exported Gmail/Apple Mail archives.
3. Load or create a JSON research profile.
4. First run: use `foundation` to build the seen-paper baseline.
5. Later runs: use `daily` so only papers not already in the state file are reported.
6. Use `feedback` to mark papers as interested/archive or more-like-this/less-like-this. The command refreshes the retained knowledge base immediately, and later runs load `knowledge_base/feedback.json` automatically.
7. For interactive triage, use `serve` to open a local feedback UI. For higher-value retained papers, use `enrich` before weekly synthesis.
8. Use `export` for BibTeX/RIS/Markdown handoff and `doctor` when diagnosing local setup problems.

## Outputs

- `digest.md` and `digest.html`: human-readable triage reports.
- `papers.json` and `papers.csv`: structured run output.
- `deep_read_queue.md`: top papers for actual reading.
- `seen_papers.json`: dedupe state; can include every alert item.
- `knowledge_base/feedback.json`: explicit user feedback and ranking signals.
- `knowledge_base/library.json`: cumulative retained papers, usually Must read + Skim.
- `knowledge_base/foundation.md`: cumulative retained library grouped by direction.
- `knowledge_base/interested.md`: cumulative high-priority reading queue, usually Must read.
- `knowledge_base/daily_additions.md`: retained additions from the latest daily run.
- `knowledge_base/papers/<paper-id>.md`: per-paper note pages.
- `knowledge_base/directions/*.md`: direction-specific retained-paper indexes.
- `knowledge_base/weekly_review.md`: recurring synthesis from the retained library.

Archive-tier papers should not enter the knowledge base by default; they stay in the run outputs and seen-state file only.

## Commands

Create a local project:

```bash
python3 scripts/scholar_reader.py init-project --project-dir ~/scholar_alerts
```

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

For extension points and module boundaries, see `references/framework.md`.

## Ranking Guidance

Prioritize papers that match:

- The user's current research questions.
- High-weight focus terms, methods, regions, and authors in the profile.
- Recent papers and papers appearing in multiple alerts.

Down-rank:

- Educational outreach, conference logistics, generic news, non-research items.
- Papers outside the current question even if they are in the broad field.
- Repeated citation alerts unless the cited paper itself is important.
- Papers or terms the user marked with `archive` or `less-like-this`.

## Privacy

Treat mailbox exports and Gmail tokens as private data. Do not upload raw mailbox contents, OAuth credentials, Gmail tokens, `seen_papers.json`, or generated knowledge-base outputs unless the user explicitly asks for that.
