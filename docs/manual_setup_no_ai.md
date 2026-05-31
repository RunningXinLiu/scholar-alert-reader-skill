# Manual Setup Without Codex Or Another AI Agent

This guide is for users who want to run Scholar Alert Reader from a normal terminal. Codex, Claude, Obsidian, and Zotero are optional. The core workflow is just a local Python CLI plus generated helper scripts.

## What You Get

Standalone mode creates a local paper triage project:

```text
paper source
  -> ingest and parse metadata
  -> deduplicate papers
  -> score against your research profile
  -> write a Review Workspace and static digest
  -> maintain a lightweight local knowledge_base
```

Default outputs:

- `reader_out/foundation/`: first baseline run over existing alerts.
- `reader_out/daily/`: later new-paper runs.
- `knowledge_base/library.json`: retained local library, usually Must read + Skim.
- `knowledge_base/index.html`: static local library index.
- `knowledge_base/papers/*.md`: per-paper notes.
- `DASHBOARD.html`: static project links and diagnostics.
- Review Workspace from `./serve_reader.sh`: interactive browser page for feedback, source links, notes, and reading status.

## 1. Install

Requirements:

- Python 3.10, 3.11, or 3.12.
- Git.
- For Gmail: a Google Cloud Desktop OAuth client and Gmail API enabled.

Clone the repo:

```bash
git clone https://github.com/RunningXinLiu/scholar-alert-reader-skill.git
cd scholar-alert-reader-skill
```

Optional but recommended:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
```

For Gmail support:

```bash
python3 -m pip install -r requirements-gmail.txt
```

You can run from the source checkout without installing a package:

```bash
python3 scripts/scholar_reader.py --version
```

## 2. Create A Local Project

Choose a project directory outside the repo:

```bash
python3 scripts/scholar_reader.py init-project \
  --project-dir ~/scholar_alerts \
  --profile-template ai-seismology

cd ~/scholar_alerts
```

Try the bundled demo before connecting private data:

```bash
RSS_SOURCE=examples/sample_feed.atom ./rss_import.sh
PAPERS_JSON=reader_out/rss/papers.json ./serve_reader.sh
```

If this opens the Review Workspace, the local CLI path works.

## 3. Configure Your Research Profile

Edit:

```text
~/scholar_alerts/profiles/research_profile.json
```

Most users only need these fields:

- `focus_terms`: topics you care about.
- `methods`: methods or model types.
- `regions`: regions, datasets, instruments, or study areas.
- `semantic_queries`: short natural-language research intents.
- `exclude_terms`: recurring noise to penalize.
- `tier_thresholds`: score cutoffs for Must read / Skim / Archive.

You can also use the profile wizard:

```bash
./profile_wizard.sh \
  --focus "seismic foundation model, phase picking, earthquake monitoring" \
  --method "self-supervised learning, uncertainty quantification" \
  --region "Tibet, Sichuan Basin"
```

Check profile quality:

```bash
./profile_doctor.sh
open profiles/profile_doctor.md
```

## 4. Gmail Setup

Gmail is optional, but it is the preferred source for Google Scholar Alerts.

In Google Cloud:

1. Create or choose a project.
2. Enable the Gmail API.
3. Configure the OAuth consent screen.
4. If the app is in testing, add your Gmail account as a test user.
5. Create an OAuth client with application type `Desktop app`.
6. Download the JSON file.

Save it outside the repo, for example:

```text
~/.codex/scholar-alert-reader/gmail_credentials.json
```

Authorize once:

```bash
python3 /path/to/scholar-alert-reader-skill/scripts/scholar_reader.py auth-gmail \
  --gmail-credentials ~/.codex/scholar-alert-reader/gmail_credentials.json \
  --gmail-token ~/.codex/scholar-alert-reader/gmail_token.json
```

Then add these values to `~/scholar_alerts/reader.env`:

```bash
SOURCE=auto
GMAIL_CREDENTIALS=$HOME/.codex/scholar-alert-reader/gmail_credentials.json
GMAIL_TOKEN=$HOME/.codex/scholar-alert-reader/gmail_token.json
```

Check Gmail without importing papers:

```bash
./source_check.sh --source gmail --live
```

Expected result includes:

```text
[OK] Gmail live read
```

## 5. First Real Run: Foundation

The first real run should be a foundation run. It reads existing alert emails, deduplicates papers, scores them, writes the retained library, and records seen papers.

```bash
MODE=foundation SOURCE=gmail ./run_reader.sh
```

Inspect the foundation:

```bash
PAPERS_JSON=reader_out/foundation/papers.json ./serve_reader.sh
open reader_out/foundation/digest.html
open knowledge_base/index.html
```

Use the Review Workspace to edit one or more cards, then click `Save selected changes` once. Notes are saved in the same batch when the note box is not empty.

Common controls:

- `Decision`: `Interested`, `Neutral`, or `Archive`.
- `Priority`: `Auto`, `Must read`, `Skim`, or `Archive`.
- `Learning signal`: `More like this`, `Less like this`, or clear the signal.
- `Reading status`: labels such as `reading`, `read`, `must-cite`, `background-only`, or `not-relevant`.
- `Generate report on save`: optional `Deep read`, `Full review`, `Workup`, or `Review pack`.

## 6. Normal Daily Run

After foundation, daily mode reports only papers that are not already in the seen state.

```bash
SOURCE=gmail ./run_reader.sh
./serve_reader.sh
```

If `Papers in digest: 0`, first check:

```bash
open reader_out/daily/digest.html
python3 -m json.tool reader_out/daily/summary.json | sed -n '1,120p'
```

If the diagnosis says `all_seen`, this is normal after a foundation run. The source produced papers, but all were already recorded in `profiles/seen_papers.json`.

To inspect recent already-seen alerts without changing the foundation:

```bash
./review_recent.sh
./serve_recent.sh
```

## 7. Optional Non-Gmail Sources

Use RSS/Atom:

```bash
RSS_SOURCE=examples/sample_feed.atom ./rss_import.sh
PAPERS_JSON=reader_out/rss/papers.json ./serve_reader.sh
```

Use arXiv:

```bash
ARXIV_QUERY='cat:physics.geo-ph AND all:tomography' ./arxiv_search.sh
PAPERS_JSON=reader_out/arxiv/papers.json ./serve_reader.sh
```

Use BibTeX/RIS:

```bash
cp ~/Downloads/library.bib import.bib
./bibtex_import.sh
PAPERS_JSON=reader_out/bibtex/papers.json ./serve_reader.sh
```

```bash
cp ~/Downloads/library.ris import.ris
./ris_import.sh
PAPERS_JSON=reader_out/ris/papers.json ./serve_reader.sh
```

## 8. Optional Obsidian And Zotero Handoff

Obsidian and Zotero are optional. Keep using the local `knowledge_base/` as the machine working area, then export only selected artifacts downstream.

Recommended Obsidian clean export:

```bash
./sync_obsidian_vault.sh --obsidian-mode clean
```

By default this writes selected paper notes to:

```text
~/Documents/Obsidian Vault/01_Literatures/10_Scholar_Alert_Reader/01_Papers/
```

Clean mode exports only `Must read` papers and papers explicitly marked `Interested`. It does not export dashboards, search indexes, runs, answers, analysis reports, or review packs. Generated notes avoid automatic `[[wikilinks]]`; use tags and normal Markdown links so the Obsidian graph stays under your control.

For a conservative first migration into an existing folder, skip cleanup:

```bash
./sync_obsidian_vault.sh --obsidian-mode clean --no-prune
```

Recommended Zotero export:

```bash
./zotero_export.sh
```

This writes:

```text
knowledge_base/zotero/scholar_alert_reader.bib
knowledge_base/zotero/scholar_alert_reader.ris
```

Import either file into Zotero. After using Better BibTeX in Zotero, you can sync citation keys and local PDF paths back:

```bash
ZOTERO_BIBTEX_PATH=~/Downloads/My_Library.bib ./zotero_sync.sh
```

## 9. What Not To Share

The repo is shareable. A generated project is private by default.

Do not publish:

- Gmail credentials or token files.
- Raw mailbox exports.
- `profiles/seen_papers.json`.
- `knowledge_base/feedback.json`.
- Generated private `knowledge_base/` or `reader_out/` from your real account.

Run before sharing logs or a support bundle:

```bash
./privacy_check.sh
```

## 10. Recommended Daily Habit

```bash
cd ~/scholar_alerts
SOURCE=gmail ./run_reader.sh
./serve_reader.sh
```

Then in the Review Workspace:

1. Open source paper links from titles.
2. Select a few clear `Interested` and `Archive` examples.
3. Write short personal notes only for papers you may read.
4. Click `Save selected changes` once to write the batch.
5. Use `review_recent.sh` only when you want to re-review recent alert traffic.
