# Scholar Alert Reader Skill

A Codex skill for turning Google Scholar Alert emails into personalized literature digests and a cumulative reading knowledge base.

## What It Does

- Reads Google Scholar Alert emails from Gmail API, Mail.app, or exported `.mbox`.
- Extracts paper title, author/source line, snippet, alert source, and link.
- Deduplicates papers across alerts.
- Scores papers against a JSON research profile.
- Writes daily digests, HTML reports, CSV/JSON output, and a cumulative knowledge base.

## Install As A Codex Skill

Copy this folder into your Codex skills directory:

```bash
cp -R scholar-alert-reader-skill ~/.codex/skills/scholar-alert-reader
```

Then restart Codex or reload skills.

## Gmail API Setup

Install dependencies in your preferred Python environment:

```bash
python3 -m pip install -r requirements-gmail.txt
```

Create a Google Cloud OAuth client with application type `Desktop app`, download the JSON, and save it as:

```text
~/.codex/scholar-alert-reader/gmail_credentials.json
```

Authorize Gmail:

```bash
python3 scripts/scholar_reader.py auth-gmail \
  --gmail-credentials ~/.codex/scholar-alert-reader/gmail_credentials.json \
  --gmail-token ~/.codex/scholar-alert-reader/gmail_token.json
```

## Quick Start

Create your profile from the example:

```bash
mkdir -p profiles
cp examples/research_profile.example.json profiles/research_profile.json
```

Build the first baseline:

```bash
python3 scripts/scholar_reader.py foundation \
  --source-gmail \
  --profile profiles/research_profile.json \
  --out-dir out/foundation \
  --kb-dir knowledge_base
```

Run daily new-paper triage:

```bash
python3 scripts/scholar_reader.py daily \
  --source-gmail \
  --profile profiles/research_profile.json \
  --out-dir out/daily \
  --kb-dir knowledge_base
```

## Do Not Commit

Do not commit:

- Gmail OAuth credentials or token files
- raw mailbox exports
- `seen_papers.json`
- generated `out/`
- generated `knowledge_base/`

