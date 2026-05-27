# Claude Code Notes

This repository can be used from Claude Code without Codex. Treat it as a local Python CLI project with optional agent guidance files.

## Source Of Truth

- Core implementation: `scholar_alert_reader/`
- CLI wrapper: `scripts/scholar_reader.py`
- Tests: `tests/`
- Public documentation: `README.md`, `PRODUCT.md`, `PRIVACY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `references/`
- Codex-specific guidance: `SKILL.md`
- Claude-specific guidance: this file

Do not treat generated user data as source code.

## Privacy Rules

Do not commit or print sensitive user data:

- raw `.mbox` or `.eml` mailbox exports
- Gmail OAuth credentials or token files
- `seen_papers.json`
- `feedback.json`
- generated `reader_out/`
- generated `knowledge_base/`
- personal Obsidian vault exports unless explicitly sanitized

The repository intentionally uses sanitized demo data and generated marketing screenshots only.

## Common Commands

Run from the repository root:

```bash
python3 scripts/scholar_reader.py --help
python3 scripts/scholar_reader.py init-project --project-dir ~/scholar_alerts
```

Run the generated demo project:

```bash
cd ~/scholar_alerts
./demo_reader.sh
open reader_out/demo/digest.html
```

Check input sources:

```bash
./source_check.sh --source auto
./source_check.sh --source mbox --mbox-path examples/sample_scholar_alerts.mbox --live
```

Run a daily workflow after setup:

```bash
./run_reader.sh
./serve_reader.sh
```

Use literature-copilot commands:

```bash
./deep_read_paper.sh --paper-id <ID>
./ask_library.sh --question "What papers should I read next?"
./advice_reader.sh
./map_reader.sh
```

## Gmail Setup

Gmail API support is optional. The user must bring their own Desktop OAuth client JSON.

```bash
python3 -m pip install -r requirements-gmail.txt
python3 scripts/scholar_reader.py auth-gmail \
  --gmail-credentials ~/.codex/scholar-alert-reader/gmail_credentials.json \
  --gmail-token ~/.codex/scholar-alert-reader/gmail_token.json
```

Do not add OAuth client JSON or token files to git.

## Optional Integrations

Obsidian and Zotero are optional. The CLI works without either one.

```bash
./obsidian_export.sh
./zotero_export.sh
```

If exporting to a real Obsidian vault, keep generated notes in a dedicated generated folder, such as:

```text
01_Literatures/10_Scholar_Alert_Reader/
```

## Verification

Before committing code changes, run:

```bash
python3 -m py_compile scripts/scholar_reader.py scholar_alert_reader/*.py
python3 -m unittest discover -s tests
```

If `pytest` is available:

```bash
pytest -q
```

For documentation-only changes, a targeted diff and privacy scan are usually enough.

## Marketing Assets

Regenerate checked-in marketing assets with:

```bash
python3 scripts/generate_marketing_assets.py
python3 scripts/generate_marketing_screenshots.py
```

These assets must stay sanitized. Do not use screenshots from a real mailbox or personal knowledge base in public docs.
