# Privacy

Scholar Alert Reader is designed to run locally.

## Local Data

The tool may read:

- Google Scholar Alert emails through Gmail API, Mail.app, or exported mbox/eml files.
- Local BibTeX/RIS bibliography exports from Zotero, EndNote, Google Scholar, publishers, or databases.
- Local profile files.
- Local generated state such as `seen_papers.json`, `feedback.json`, and `knowledge_base/`.

Do not commit or publish raw mailbox exports, personal bibliography imports, OAuth credentials, Gmail tokens, `seen_papers.json`, `feedback.json`, or generated knowledge-base outputs unless you have intentionally reviewed and sanitized them.

## External Requests

The core triage pipeline runs locally. External requests happen only when you choose a connector or enrichment feature:

- Gmail API reads email metadata/content after OAuth authorization.
- OpenAlex/Crossref enrichment sends selected paper titles to public metadata APIs.
- Favicons in HTML digests may be loaded by the browser from Google favicon endpoints.

By default, enrichment should be used only on retained/high-value papers, not every archived alert item.

## OAuth Files

Keep OAuth client secrets and Gmail tokens outside the repository. The default private location is:

```text
~/.codex/scholar-alert-reader/
```
