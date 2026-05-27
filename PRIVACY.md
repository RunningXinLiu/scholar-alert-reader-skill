# Privacy

Scholar Alert Reader is designed to run locally.

## Local Data

The tool may read:

- Google Scholar Alert emails through Gmail API, Mail.app, or exported mbox/eml files.
- Local BibTeX/RIS bibliography exports from Zotero, EndNote, Google Scholar, publishers, or databases, including optional Better BibTeX read-back files that may contain local PDF paths.
- Local scholarly webpage source lists, saved HTML files, RSS/Atom feed lists, and arXiv queries.
- Local profile files.
- Local generated state such as `reader.env`, `seen_papers.json`, `feedback.json`, and `knowledge_base/`, including fetched PDFs, profile-tuning reports, optional full-text extraction caches, and review context packs.

`self-test` uses bundled sample data only by default. If a user passes `--project-dir`, the generated self-test project may still contain local generated outputs and should be treated as disposable/private.

Do not commit or publish raw mailbox exports, personal bibliography imports, personal Zotero/Better BibTeX read-back files, personal webpage/feed source lists, `reader.env`, OAuth credentials, Gmail tokens, `seen_papers.json`, `feedback.json`, fetched PDFs, profile-tuning reports, extracted full-text caches, review context packs, or generated knowledge-base outputs unless you have intentionally reviewed and sanitized them.

Before sharing a project folder, screenshots, support bundle, issue attachment, or zip archive, run:

```bash
./privacy_check.sh --strict
# or
python3 -m scholar_alert_reader privacy-check --project-dir ~/scholar_alerts --strict
```

The privacy check writes `PRIVACY_CHECK.md` by default. It reports risky paths, review-before-sharing files, and recommended `.gitignore` gaps without including raw file contents.

The GitHub issue templates are designed for sanitized diagnostics only. If a report needs credentials, raw mailbox content, or private generated data to explain the problem, use the private security reporting path described in [SECURITY.md](SECURITY.md) instead of a public issue.

## External Requests

The core triage pipeline runs locally. External requests happen only when you choose a connector or enrichment feature:

- Gmail API reads email metadata/content after OAuth authorization.
- Web metadata, RSS/Atom, and arXiv sources fetch configured URLs or public API/feed entries when those sources are selected.
- OpenAlex/Crossref enrichment sends selected paper titles to public metadata APIs.
- Favicons in HTML digests may be loaded by the browser from Google favicon endpoints.

By default, enrichment should be used only on retained/high-value papers, not every archived alert item.

## OAuth Files

Keep OAuth client secrets and Gmail tokens outside the repository. The default private location is:

```text
~/.codex/scholar-alert-reader/
```
