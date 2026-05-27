# Automation Notes

Use the local mbox, BibTeX/RIS, RSS/Atom, or arXiv path for the first reliable version. For a true daily pipeline, choose one source connector:

For a new workspace, initialize the local project first:

```bash
python3 scripts/scholar_reader.py init-project --project-dir ~/scholar_alerts
```

## Gmail API

Best long-term option. Requires user OAuth setup once, then can read messages with label `Google Scholar Alerts` or sender `scholaralerts-noreply@google.com`.

Suggested flow:

1. Create Gmail OAuth desktop credentials.
2. Save the downloaded client JSON to `~/.codex/scholar-alert-reader/gmail_credentials.json`.
3. Run `python3 scripts/scholar_reader.py auth-gmail` once to create `~/.codex/scholar-alert-reader/gmail_token.json`.
3. Fetch messages since last run.
4. Save only extracted paper metadata, not raw emails.

The default `run_reader.sh` uses `SOURCE=auto`: Gmail API is used when the token exists; otherwise it checks `INBOX.mbox`, `import.bib`, `import.ris`, `feeds.txt`, `ARXIV_QUERY`, and then optional Mail.app fallback.

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

## RSS/Atom And arXiv

Best fallback when the user wants structured web monitoring without maintaining Gmail or Zotero. Prefer RSS/Atom feeds and the arXiv public Atom API over arbitrary webpage scraping.

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
