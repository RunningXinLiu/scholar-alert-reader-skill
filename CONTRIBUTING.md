# Contributing

This project is a Codex skill plus a dependency-light Python CLI.

## Local Checks

Run:

```bash
python -m py_compile scripts/scholar_reader.py scholar_alert_reader/*.py
python -m unittest discover -s tests
```

## Issues And Support

Use the GitHub issue forms for bug reports, source setup help, and feature requests. Keep reports reproducible with sanitized commands and generated reports such as `SOURCE_CHECK.md`, `DOCTOR.md`, or `QUICKSTART_REPORT.md`.

Do not paste raw emails, OAuth credentials, Gmail tokens, private bibliography/feed lists, `seen_papers.json`, `feedback.json`, generated `knowledge_base/` content, or extracted full-text/review packs into public issues.

Security-sensitive reports should follow [SECURITY.md](SECURITY.md).

## Design Rules

- Keep `scripts/scholar_reader.py` as a stable compatibility wrapper.
- Put implementation code under `scholar_alert_reader/`.
- Keep Gmail and mailbox parsing local by default.
- Do not add dependencies for core triage unless the benefit is clear.
- Do not commit generated user data, raw emails, OAuth files, tokens, or local knowledge bases.
- New features should usually be CLI subcommands and should have tests that do not require network access.

## Release Checklist

- Run local checks.
- Run `python scripts/scholar_reader.py doctor` against a sample project.
- Confirm `rg` does not find personal paths, tokens, raw OAuth secrets, or mailbox content.
- Update `VERSION` and `CHANGELOG.md`.
- Tag the release.
