# Troubleshooting

Start with commands that cannot read private data:

```bash
python3 -m scholar_alert_reader self-test --strict
python3 -m scholar_alert_reader init-project --project-dir ~/scholar_alerts
cd ~/scholar_alerts
./self_test.sh
./demo_sources.sh
./setup_wizard.sh --defaults
```

When running from a source checkout, `python3 scripts/scholar_reader.py ...` is still supported. When installed with `pip`, use `scholar-alert-reader ...`, `scholar-reader ...`, or `python3 -m scholar_alert_reader ...`.

If these fail, the problem is the local Python/project setup. If these pass but your real run fails, the problem is probably the chosen input source, OAuth setup, local file path, or state filtering.

Use `./setup_wizard.sh` for guided configuration. It writes `SOURCE_CHECK.md` after setup; pass `--live-check` to attempt a real read immediately. Use `./setup_reader.sh ...` or `scholar-alert-reader setup ...` when you need a non-interactive scriptable setup path.

## Fast Checks

Inside an initialized project:

```bash
./source_check.sh --source auto
./source_check.sh --source gmail --live
./source_check.sh --source mbox --mbox-path examples/sample_scholar_alerts.mbox --live
./source_check.sh --source bibtex --bibtex-path import.bib --live
./source_check.sh --source ris --ris-path import.ris --live
./source_check.sh --source web --web-source examples/sample_web_article.html --live
./source_check.sh --source rss --rss-source examples/sample_feed.atom --live
./source_check.sh --source arxiv --arxiv-query 'cat:physics.geo-ph AND all:tomography' --live
./doctor_reader.sh
./support_bundle.sh
```

From the repository root:

```bash
python3 -m scholar_alert_reader source-check --project-dir ~/scholar_alerts --source auto
python3 -m scholar_alert_reader doctor --profile ~/scholar_alerts/profiles/research_profile.json --kb-dir ~/scholar_alerts/knowledge_base --out-dir ~/scholar_alerts/reader_out/daily --gmail-deps
python3 -m scholar_alert_reader support-bundle --project-dir ~/scholar_alerts
```

Use `support-bundle` when opening a public GitHub issue. It writes `SUPPORT_BUNDLE.md` with redacted paths, URLs, config values, and report excerpts; still review it before posting.

## Generated Scripts Cannot Find `scholar_alert_reader`

Generated project scripts prefer `PROJECT_DIR/.venv/bin/python`, then the Python that created the project, then `python3`. If you later add or replace a project virtual environment, install the package into that environment or point `PYTHON_BIN` at the Python where it is installed:

```bash
./.venv/bin/python -m pip install "git+https://github.com/RunningXinLiu/scholar-alert-reader-skill.git"
PYTHON_BIN=./.venv/bin/python ./source_check.sh --source auto
```

From a source checkout, you can also point scripts at the compatibility wrapper:

```bash
SKILL_SCRIPT=/path/to/scholar-alert-reader-skill/scripts/scholar_reader.py ./source_check.sh --source auto
```

## `Papers in digest: 0`

Common causes:

- `daily` mode filters out papers already recorded in `seen_papers.json`.
- The selected source has no Scholar Alert messages or no parseable paper metadata.
- Gmail dependencies or OAuth token are missing, so `SOURCE=auto` selected a different source or failed.
- `GMAIL_QUERY`, `SINCE_DAYS`, `RSS_SOURCE`, `WEB_SOURCE`, or file paths point at the wrong data.
- Your profile and feedback archive everything, especially after strong exclude terms or archive feedback.

Useful checks:

```bash
./source_check.sh --source auto --live
MODE=run ONLY_NEW=0 NO_KB_UPDATE=1 ./run_reader.sh
MODE=foundation ./run_reader.sh
```

Look at:

```text
reader_out/daily/summary.json
reader_out/daily/papers.json
profiles/seen_papers.json
knowledge_base/feedback.json
```

## Gmail OAuth Shows `access_denied` Or App Not Verified

For personal/local use, the clean path is bring-your-own OAuth:

1. In Google Cloud Console, enable Gmail API for the project.
2. Configure the OAuth consent screen.
3. Set the app to testing if it is not verified.
4. Add your Gmail account as a test user.
5. Create an OAuth client with application type `Desktop app`.
6. Download the JSON and save it outside the repo:

```text
~/.codex/scholar-alert-reader/gmail_credentials.json
```

Then authorize:

```bash
python3 -m pip install -r requirements-gmail.txt
python3 -m scholar_alert_reader auth-gmail \
  --gmail-credentials ~/.codex/scholar-alert-reader/gmail_credentials.json \
  --gmail-token ~/.codex/scholar-alert-reader/gmail_token.json
```

If Google says the app has not completed verification and blocks access, you are probably signing in with an account that is not listed as a test user, or the OAuth consent screen is not configured for testing. A public shared OAuth client requires Google verification; do not commit or share your private OAuth client JSON.

## Gmail Token Exists But Runs Still Fail

Check the exact Python used by the project:

```bash
which python3
python3 -m pip show google-api-python-client google-auth-oauthlib
./source_check.sh --source gmail --live
```

If the project uses a virtual environment, install dependencies into that environment:

```bash
./.venv/bin/python -m pip install -r requirements-gmail.txt
PYTHON_BIN=./.venv/bin/python ./source_check.sh --source gmail --live
```

Generated scripts prefer `PROJECT_DIR/.venv/bin/python` when it exists, otherwise `python3`.

## Mail.app Source Fails

Mail.app is macOS-only and uses AppleScript. It can fail when the terminal, Codex app, or Python process does not have Automation permission.

Use Gmail API, exported mbox, BibTeX/RIS, webpage metadata, RSS, or arXiv when you need a cross-platform or less permission-sensitive setup. If you still want Mail.app:

```bash
SOURCE=mail-app AUTO_ALLOW_MAIL_APP=1 ./run_reader.sh
./source_check.sh --source mail-app --live
```

Then grant Automation permission in macOS Settings when prompted.

## mbox Import Finds No Scholar Messages

The mbox parser is tuned for Google Scholar Alert HTML messages. Check:

- The export includes actual Google Scholar Alert emails.
- The messages are not plain text only.
- The file path points at an mbox file or Apple Mail `.mbox` package.

Try the sample first:

```bash
./source_check.sh --source mbox --mbox-path examples/sample_scholar_alerts.mbox --live
SOURCE=mbox MBOX_PATH=examples/sample_scholar_alerts.mbox MODE=run NO_KB_UPDATE=1 ./run_reader.sh
```

## BibTeX Or RIS Import Fails

Use the bundled demos to separate parser issues from your file:

```bash
BIBTEX_PATH=examples/sample_import.bib ./bibtex_import.sh
RIS_PATH=examples/sample_import.ris ./ris_import.sh
```

For real files, check that the export contains titles. DOI, abstract, journal, year, and URL improve output quality but are not mandatory.

## Web Metadata Import Finds Nothing

`--source-web` is not a full crawler. It reads configured pages or saved HTML files and extracts common article metadata:

- citation meta tags such as `citation_title`
- JSON-LD `ScholarlyArticle`
- Dublin Core
- OpenGraph
- HTML `<title>` as a fallback

Try:

```bash
WEB_SOURCE=examples/sample_web_article.html ./web_import.sh
WEB_SOURCE=examples/web_sources.example.txt ./web_import.sh
./source_check.sh --source web --web-source examples/sample_web_article.html --live
```

If a publisher page renders metadata only after JavaScript, save/export the final HTML from the browser or use RSS/Atom/arXiv when available.

## RSS Or arXiv Fails

For RSS/Atom, prefer real feed URLs or saved feed XML. For arXiv, use precise category/topic queries:

```bash
RSS_SOURCE=examples/sample_feed.atom ./rss_import.sh
ARXIV_QUERY='cat:physics.geo-ph AND all:tomography' ./arxiv_search.sh
```

If network requests fail, test with local sample files first. If local files pass and remote feeds fail, the issue is network, URL validity, timeout, or remote feed format.

## Obsidian Or Zotero Does Not Update

Obsidian and Zotero are optional. The core workflow is complete without either one.

For Obsidian:

```bash
./obsidian_export.sh
./sync_obsidian_vault.sh
```

Keep generated notes in a dedicated folder, for example:

```text
01_Literatures/10_Scholar_Alert_Reader/
```

For Zotero:

```bash
./zotero_export.sh
ZOTERO_BIBTEX_PATH=~/Downloads/My_Library.bib ./zotero_sync.sh
```

Better BibTeX read-back can expose local PDF paths, so treat exported Zotero files as private.

## Privacy Checklist

Do not commit:

- Gmail OAuth credentials or token files
- raw mailbox exports
- personal `import.bib` / `import.ris`
- personal `web_sources.txt` / `feeds.txt`
- `reader.env`
- `seen_papers.json`
- `feedback.json`
- generated `reader_out/`
- generated `knowledge_base/`
- extracted full-text caches or review packs
