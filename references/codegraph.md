# CodeGraph Notes

This repository is compatible with CodeGraph, but the index is local generated state.

## Source Boundary

- Canonical source: tracked files under `scholar_alert_reader/`, `scripts/`, `tests/`, and documentation files.
- Generated index: `.codegraph/`.
- Commit policy: commit source and docs; do not commit `.codegraph/`.

## Local Setup

```bash
codegraph init -i
```

After initialization, use CodeGraph for symbol-level questions such as:

- where a command is defined
- what calls a function
- what changes might affect a symbol
- source snippets for related functions

If the index is stale, rebuild it from the repository source. Do not patch generated CodeGraph files as if they were code.
