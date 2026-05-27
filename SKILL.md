---
name: scholar-alert-reader
description: Build and run an automatic literature triage workflow from Google Scholar Alert emails, exported mbox files, BibTeX/RIS bibliography files, RSS/Atom feeds, arXiv queries, Gmail API, Mail.app, and research-profile feedback. Use when the user wants daily or manual paper-reading digests, Scholar Alert analysis, bibliography import, structured web literature monitoring, personalized paper ranking, or an automated research reading push system.
---

# Scholar Alert Reader

Turn Google Scholar Alert emails into a small, personalized reading queue and cumulative literature knowledge base.

Core rule: reduce noise before summarizing. Extract, dedupe, score against the user's current research profile, then deep-read only the highest-value papers.

## Workflow

1. For a new local setup, run `init-project` to create profiles, outputs, knowledge-base directories, helper scripts, and `START_HERE.md`.
2. Run `./demo_reader.sh` first when the user wants to test without connecting Gmail, Obsidian, or Zotero.
3. Choose a source:
   - Gmail API: preferred for automation after OAuth setup.
   - Mail.app: works locally on macOS after Automation permission.
   - `.mbox`: works from exported Gmail/Apple Mail archives.
   - BibTeX/RIS: works from Zotero, EndNote, Google Scholar library, publisher, and database exports.
   - RSS/Atom or arXiv: works for structured web monitoring without scraping arbitrary pages.
4. Load or create a JSON research profile. For new users, start from a bundled template such as `general-geophysics`, `ai-seismology`, `induced-seismicity`, `seismic-imaging`, or `dense-array-monitoring`, then edit the terms.
5. First run: use `foundation` to build the seen-paper baseline.
6. Later runs: use `daily` so only papers not already in the state file are reported.
7. Use `feedback` to mark papers as interested/archive or more-like-this/less-like-this. The command refreshes the retained knowledge base immediately, and later runs load `knowledge_base/feedback.json` automatically.
8. For interactive triage, use `serve` to open a local feedback UI. For higher-value retained papers, use `enrich` before weekly synthesis.
9. Use `deep-read`, `ask`, and `advice` to turn the retained library into a personal literature copilot.
10. Use `status`, `compare`, and `map` to track reading state, compare papers, and see the research landscape.
11. Use `zotero`, `obsidian`, or `export` for external-tool handoff, `guide` for product-oriented setup/status guidance, and `doctor` when diagnosing local setup problems.

Platform rule: Gmail API, exported mbox, BibTeX/RIS, RSS/Atom, and arXiv work cross-platform; Mail.app and LaunchAgent automation are macOS-only. Do not imply Obsidian or Zotero are required.

Gmail distribution rule: never ship the developer's OAuth client JSON or token. For shared/public use, each user should bring their own Desktop OAuth client unless the app owner has completed Google OAuth verification for a shared client. The requested scope is Gmail read-only.

Capability boundary: ranking and literature-copilot commands are currently based on alert metadata, bibliography fields, snippets, profile terms, feedback, and retained-library context. Treat `deep-read` as a triage/planning brief unless a future full-text/PDF pipeline is explicitly added.

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
- `knowledge_base/analysis/<paper-id>_deep_read.md`: selected-paper deep-read brief against the foundation.
- `knowledge_base/answers/*.md`: local-library answers to user research questions.
- `knowledge_base/research_advice.md`: gap and reading-strategy advice from retained/interested papers.
- `knowledge_base/reading_status.md`: reading tracker grouped by status.
- `knowledge_base/comparisons/*.md`: side-by-side paper comparisons.
- `knowledge_base/research_map.md`: topic clusters and representative papers.
- `knowledge_base/zotero/`: Zotero-ready BibTeX/RIS files.
- `knowledge_base/obsidian/`: Obsidian-ready Markdown dashboard, paper notes, maps, reading status, library answers, comparisons, and deep reads. In a real vault, sync it into a generated folder such as `01_Literatures/10_Scholar_Alert_Reader/`.

Archive-tier papers should not enter the knowledge base by default; they stay in the run outputs and seen-state file only.

## Commands

Create a local project:

```bash
python3 scripts/scholar_reader.py init-project --project-dir ~/scholar_alerts --profile-template ai-seismology
```

List or copy bundled profile templates:

```bash
python3 scripts/scholar_reader.py list-profile-templates
python3 scripts/scholar_reader.py init-profile \
  --profile ~/scholar_alerts/profiles/research_profile.json \
  --template seismic-imaging \
  --force
```

Render or refresh the local onboarding guide:

```bash
python3 scripts/scholar_reader.py guide \
  --project-dir ~/scholar_alerts \
  --output ~/scholar_alerts/START_HERE.md
```

Check the configured input source without a full run:

```bash
python3 scripts/scholar_reader.py source-check \
  --project-dir ~/scholar_alerts \
  --source auto
```

Use `--live` to attempt an actual Gmail, Mail.app, mbox, BibTeX, RIS, RSS/Atom, or arXiv read.

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

Analyze a selected paper against the local foundation:

```bash
python3 scripts/scholar_reader.py deep-read \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --papers-json out/recent/papers.json \
  --paper-id <ID>
```

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

Treat mailbox exports, personal bibliography imports, feed lists, and Gmail tokens as private data. Do not upload raw mailbox contents, OAuth credentials, Gmail tokens, `seen_papers.json`, or generated knowledge-base outputs unless the user explicitly asks for that.
