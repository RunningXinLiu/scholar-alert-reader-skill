# Automation Notes

Use the local mbox path for the first reliable version. For a true daily pipeline, choose one source connector:

## Gmail API

Best long-term option. Requires user OAuth setup once, then can read messages with label `Google Scholar Alerts` or sender `scholaralerts-noreply@google.com`.

Suggested flow:

1. Create Gmail OAuth desktop credentials.
2. Save the downloaded client JSON to `~/.codex/scholar-alert-reader/gmail_credentials.json`.
3. Run `python3 scripts/scholar_reader.py auth-gmail` once to create `~/.codex/scholar-alert-reader/gmail_token.json`.
3. Fetch messages since last run.
4. Save only extracted paper metadata, not raw emails.

The default `run_reader.sh` uses `SOURCE=auto`: Gmail API is used when the token exists; otherwise it falls back to Mail.app.

## Apple Mail

Possible but more brittle. AppleScript can ask Mail.app for messages from Scholar Alerts, but macOS may require Automation permission and Mail.app search behavior can vary.

Use only if the user prefers Mail.app over Gmail API.

## Codex Automation

For daily pushes in the Codex app, create a cron automation that runs the triage command in the workspace and reports the digest path plus top papers. Ask the user for preferred wall-clock time before creating the automation.

Prompt should be self-contained:

```text
Run the Scholar Alert Reader triage for the configured mailbox/profile. Report new Must read papers, the digest path, and any errors. Do not upload raw mailbox contents.
```
