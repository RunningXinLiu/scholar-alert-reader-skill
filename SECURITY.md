# Security Policy

## Private Reports

Please do not open public GitHub issues for credential leaks, raw mailbox exposure, OAuth problems involving secrets, or private knowledge-base data.

Use GitHub private vulnerability reporting for this repository when available:

```text
https://github.com/RunningXinLiu/scholar-alert-reader-skill/security/advisories/new
```

If private reporting is unavailable, open a minimal public issue that says a private security contact is needed, without including secrets or private data.

## Do Not Share

Do not include:

- Gmail OAuth client JSON files
- Gmail token files
- raw `.mbox` / `.eml` exports
- raw Scholar Alert email bodies
- personal BibTeX/RIS exports unless sanitized
- private webpage/feed source lists
- `reader.env`
- `seen_papers.json`
- `feedback.json`
- generated `knowledge_base/`
- extracted full-text caches or review packs

## Scope

This is a local-first CLI and Codex skill. The most important security boundary is keeping private research data, mailbox content, and OAuth material on the user's machine.

Supported reports include:

- accidental secret exposure paths
- unsafe default file locations
- commands that may upload or publish private data unexpectedly
- HTML/report rendering issues that could expose private data
- dependency or packaging vulnerabilities in installed CLI paths
