# Obsidian Export Guide (Clean-First)

This guide defines a safe operating model:

- `knowledge_base/` is the machine workspace.
- Obsidian receives selected paper notes by default.
- `clean` is the default mode.
- `full` is explicit and for debugging/archive use.

## Visual Quick Reference

![Mode Decision](assets/obsidian-mode-decision.en.svg)

![Directory Boundary](assets/obsidian-boundary.en.svg)

![Migration Flow](assets/obsidian-migration.en.svg)

## Mode Decision

```mermaid
flowchart TD
  A["Need notes in Obsidian"] --> B{"Do you want only selected papers?"}
  B -->|Yes| C["Use clean (default)"]
  B -->|No, I need all generated reports| D["Use --obsidian-mode full"]
  C --> E{"Same folder had old full outputs?"}
  E -->|Yes, be conservative first| F["Use clean + --no-prune once"]
  E -->|No| G["Use clean"]
  F --> H["Review folder, then run clean without --no-prune if needed"]
  D --> I["Use a separate FULL folder, not your daily inbox"]
```

## Directory Boundary

```mermaid
flowchart LR
  A["Scholar Alert Reader project"] --> B["knowledge_base/ (machine workspace)"]
  A --> C["reader_out/ (digests and run outputs)"]
  D["Obsidian Vault"] --> E["01_Literatures/10_Scholar_Alert_Reader/01_Papers"]
  B -. "Do not sync whole folder" .-> D
  C -. "Do not sync whole folder" .-> D
  A -->|"obsidian export (clean)"| E
```

## Migration Flow (Old Full Folder -> Clean Inbox)

```mermaid
flowchart TD
  A["Old folder has full outputs"] --> B["Run clean with --no-prune"]
  B --> C["Verify paper notes look correct"]
  C --> D{"Need to keep old full outputs?"}
  D -->|Yes| E["Keep using --no-prune"]
  D -->|No| F["Run clean without --no-prune"]
  F --> G["Tool prunes only manifest-marked full artifacts"]
```

## 10-Minute Setup

1. Keep your local project outside Obsidian:
   - Example: `~/scholar_alerts`
2. Pick a dedicated Obsidian inbox folder (not vault root):
   - Example: `~/Documents/Obsidian Vault/01_Literatures/10_Scholar_Alert_Reader`
3. Run daily triage from your project:
   - `./run_reader.sh` or source-specific import scripts
4. Export to Obsidian in clean mode (default):

```bash
python3 scripts/scholar_reader.py obsidian \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --vault-dir "$HOME/Documents/Obsidian Vault/01_Literatures/10_Scholar_Alert_Reader"
```

5. If the target folder previously used `full`, first run:

```bash
python3 scripts/scholar_reader.py obsidian \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --vault-dir "$HOME/Documents/Obsidian Vault/01_Literatures/10_Scholar_Alert_Reader" \
  --obsidian-mode clean \
  --no-prune
```

6. Use full mode only when you intentionally need generated dashboards/reports:

```bash
python3 scripts/scholar_reader.py obsidian \
  --profile profiles/research_profile.json \
  --kb-dir knowledge_base \
  --obsidian-mode full \
  --vault-dir "$HOME/Documents/Obsidian Vault/01_Literatures/10_Scholar_Alert_Reader_FULL"
```

## What Clean Exports

- `01_Papers/*.md` only.
- Only `Must read` papers and papers marked `interested`.
- Notes include generated frontmatter (`source_tool`, `obsidian_import`, `tier`, `score`, `reading_status`, `tags`, `source_types`).
- No automatic `[[wikilinks]]`.

## What Clean Does Not Export

- Dashboard/index/search workspace files.
- `answers/`, `analysis/`, `runs/`, and other machine report folders.

## Do / Do Not

Do:
- Keep Obsidian export in a dedicated inbox folder.
- Use `clean` for daily use.
- Use `full` in a separate folder when needed.

Do not:
- Sync or copy the entire `knowledge_base/` into Obsidian.
- Export to vault root.
- Mix daily clean inbox and full archive outputs in one folder unless intentional.

## Quick Command Reference

```bash
# Recommended daily export
python3 scripts/scholar_reader.py obsidian --profile profiles/research_profile.json --kb-dir knowledge_base --vault-dir "$HOME/Documents/Obsidian Vault/01_Literatures/10_Scholar_Alert_Reader"

# Conservative clean export (skip prune)
python3 scripts/scholar_reader.py obsidian --profile profiles/research_profile.json --kb-dir knowledge_base --vault-dir "$HOME/Documents/Obsidian Vault/01_Literatures/10_Scholar_Alert_Reader" --no-prune

# Full export (explicit)
python3 scripts/scholar_reader.py obsidian --profile profiles/research_profile.json --kb-dir knowledge_base --obsidian-mode full --vault-dir "$HOME/Documents/Obsidian Vault/01_Literatures/10_Scholar_Alert_Reader_FULL"
```
