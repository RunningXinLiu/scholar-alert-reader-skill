# Privacy

Scholar Alert Reader is designed to run locally.

## Local Data

The tool may read:

- Google Scholar Alert emails through Gmail API, Mail.app, or exported mbox/eml files.
- Local BibTeX/RIS bibliography exports from Zotero, EndNote, Google Scholar, publishers, or databases, including optional Better BibTeX read-back files that may contain local PDF paths.
- Local RSS/Atom feed lists and arXiv queries.
- Local profile files.
- Local generated state such as `reader.env`, `seen_papers.json`, `feedback.json`, and `knowledge_base/`, including profile-tuning reports, optional full-text extraction caches, and review context packs.

Do not commit or publish raw mailbox exports, personal bibliography imports, personal Zotero/Better BibTeX read-back files, personal feed lists, `reader.env`, OAuth credentials, Gmail tokens, `seen_papers.json`, `feedback.json`, profile-tuning reports, extracted full-text caches, review context packs, or generated knowledge-base outputs unless you have intentionally reviewed and sanitized them.

## External Requests

The core triage pipeline runs locally. External requests happen only when you choose a connector or enrichment feature:

- Gmail API reads email metadata/content after OAuth authorization.
- RSS/Atom and arXiv sources fetch structured feed entries from the configured URLs or the public arXiv API.
- OpenAlex/Crossref enrichment sends selected paper titles to public metadata APIs.
- Favicons in HTML digests may be loaded by the browser from Google favicon endpoints.

By default, enrichment should be used only on retained/high-value papers, not every archived alert item.

## OAuth Files

Keep OAuth client secrets and Gmail tokens outside the repository. The default private location is:

```text
~/.codex/scholar-alert-reader/
```
