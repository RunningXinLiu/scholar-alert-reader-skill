# Automation Notes

Use the local mbox, BibTeX/RIS, webpage metadata, RSS/Atom, or arXiv path for the first reliable version. For a true daily pipeline, choose one source connector:

For a new workspace, initialize the local project first:

```bash
python3 scripts/scholar_reader.py init-project --project-dir ~/scholar_alerts
cd ~/scholar_alerts
./self_test.sh
```

`self_test.sh` uses bundled sample data only. It verifies the Python CLI, project scaffold, sample mbox parsing, sample web metadata/RSS checks, digest generation, and doctor report before connecting Gmail or personal files.

Then persist local defaults so scheduled runs do not depend on a long command line:

```bash
./setup_reader.sh --source auto --profile-template ai-seismology --schedule-time 09:00 --schedule-days weekdays
```

`reader.env` is read by generated shell scripts only for variables that are not already set by the caller. This keeps daily automation simple while still allowing one-off overrides such as `SOURCE=web WEB_SOURCE=... ./run_reader.sh` or `SOURCE=rss RSS_SOURCE=... ./run_reader.sh`.

Render the schedule before installing it:

```bash
./schedule_reader.sh --action write
```

This writes `SCHEDULE.md` and a project-local `LaunchAgents/*.plist` preview. On macOS, install it only after source checks pass:

```bash
./source_check.sh --source auto --live
./schedule_reader.sh --action install
./schedule_reader.sh --action status
```

`./schedule_reader.sh --action uninstall` removes the installed LaunchAgent. Non-macOS users should use `run_reader.sh` with cron, systemd timers, Task Scheduler, or their agent scheduler.

## Gmail API

Best long-term option. Requires user OAuth setup once, then can read messages with label `Google Scholar Alerts` or sender `scholaralerts-noreply@google.com`.

Suggested flow:

1. Create Gmail OAuth desktop credentials.
2. Save the downloaded client JSON to `~/.codex/scholar-alert-reader/gmail_credentials.json`.
3. Run `python3 scripts/scholar_reader.py auth-gmail` once to create `~/.codex/scholar-alert-reader/gmail_token.json`.
3. Fetch messages since last run.
4. Save only extracted paper metadata, not raw emails.

The default `run_reader.sh` uses `SOURCE=auto`: Gmail API is used when the token exists; otherwise it checks `INBOX.mbox`, `import.bib`, `import.ris`, `web_sources.txt`, `feeds.txt`, `ARXIV_QUERY`, and then optional Mail.app fallback.

If the workflow uses `--kb-dir knowledge_base`, saved paper feedback is read from `knowledge_base/feedback.json` automatically. Pass `--no-feedback` only for a diagnostic run that should ignore personal ranking signals.

After a digest is generated, the user can run `serve` against the latest `papers.json` for browser-based feedback. Keep this as a manual/local action unless the user explicitly asks to expose a persistent server.

Metadata enrichment should run after triage and only against retained papers, for example:

```bash
python3 scripts/scholar_reader.py enrich --profile profiles/research_profile.json --kb-dir knowledge_base --limit 20 --update-library
```

Weekly synthesis can be scheduled separately from daily triage:

```bash
python3 scripts/scholar_reader.py weekly --profile profiles/research_profile.json --kb-dir knowledge_base --days 7
```

Use `doctor` as the first debugging command when an automation returns no papers or fails to read Gmail:

```bash
python3 scripts/scholar_reader.py doctor --profile profiles/research_profile.json --kb-dir knowledge_base --out-dir out/daily --gmail-deps
```

## Apple Mail

Possible but more brittle. AppleScript can ask Mail.app for messages from Scholar Alerts, but macOS may require Automation permission and Mail.app search behavior can vary.

Use only if the user prefers Mail.app over Gmail API.

## BibTeX/RIS Imports

Best fallback when the user has no Gmail access or wants to triage a Zotero, EndNote, Google Scholar library, publisher, or database export.

```bash
SOURCE=bibtex BIBTEX_PATH=~/Downloads/export.bib MODE=run ./run_reader.sh
SOURCE=ris RIS_PATH=~/Downloads/export.ris MODE=run ./run_reader.sh
```

Project scaffolds also include `./bibtex_import.sh` and `./ris_import.sh`, which default to `import.bib` and `import.ris` inside the project directory.

## Zotero Read-back

Use Zotero/Better BibTeX read-back after papers have entered `knowledge_base/library.json`. This is separate from importing a bibliography as a paper source: it enriches already-retained papers with Zotero citation keys, item keys, and local PDF paths.

```bash
ZOTERO_BIBTEX_PATH=~/Downloads/My_Library.bib ./zotero_sync.sh
```

The sync matches retained papers by DOI first and normalized title second. Keep the exported `zotero.bib` private because it may expose local file paths.

## Local Full-text Briefs

After Zotero read-back has added local PDF paths, generate a local full-text cache and brief for one retained paper:

```bash
./full_text_paper.sh --paper-id <ID>
```

The command uses local files only. It tries `pdftotext`, then optional Python PDF libraries, and can also accept a text export through `--pdf-path`. Treat the generated text cache as private research material.

## Selected-paper Review Pack

After `deep-read` or `full-text`, create a context pack that can be pasted into Codex, Claude, ChatGPT, or another assistant:

```bash
./review_paper.sh --paper-id <ID>
```

The pack includes the selected paper, research profile, feedback status, closest foundation papers, active interested papers, and any cached local full text. Treat the generated review pack as private because it can contain extracted full text and personal research notes.

For a batch of top papers, build a review queue:

```bash
./review_queue.sh --tiers "Must read" --limit 5
```

The queue attempts local full-text extraction for each selected paper when Zotero PDF/text paths are present, then writes `knowledge_base/analysis/review_queue.md` and one review pack per paper. Use `--no-extract` when caches already exist, or `--strict-full-text` when missing local text should fail the run.

## Profile Tuning

After the user has marked several papers as interested/archive or more-like-this/less-like-this, generate a tuning report:

```bash
./tune_profile.sh
```

This writes `knowledge_base/profile_tuning.md` and is safe by default. It only edits the active profile when the user passes `--apply`.

## Web Metadata, RSS/Atom, And arXiv

Best fallback when the user wants structured web monitoring without maintaining Gmail or Zotero. Prefer structured webpage metadata, RSS/Atom feeds, and the arXiv public Atom API over arbitrary deep crawling.

```bash
SOURCE=web WEB_SOURCE=~/scholar_alerts/web_sources.txt MODE=run ./run_reader.sh
./web_import.sh
```

`WEB_SOURCE` accepts a URL, saved `.html`/`.htm` file, directory of saved HTML pages, or `.txt`/`.list` file with one source per line. It reads citation meta tags, JSON-LD, Dublin Core, and OpenGraph.

```bash
SOURCE=rss RSS_SOURCE=~/scholar_alerts/feeds.txt MODE=run ./run_reader.sh
SOURCE=arxiv ARXIV_QUERY='cat:physics.geo-ph AND all:tomography' MODE=run ./run_reader.sh
```

Project scaffolds include `./rss_import.sh` and `./arxiv_search.sh`.

## Codex Automation

For daily pushes in the Codex app, create a cron automation that runs the triage command in the workspace and reports the digest path plus top papers. Ask the user for preferred wall-clock time before creating the automation.

Prompt should be self-contained:

```text
Run the Scholar Alert Reader triage for the configured mailbox/profile. Report new Must read papers, the digest path, and any errors. Do not upload raw mailbox contents.
```
