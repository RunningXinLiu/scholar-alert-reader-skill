# Agent Notes

## Source Of Truth

- Source code lives in `scholar_alert_reader/`, `scripts/`, and `tests/`.
- Documentation lives in `README.md`, `SKILL.md`, `PRODUCT.md`, `PRIVACY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, and `references/`.
- Generated personal data, OAuth files, mailbox exports, personal BibTeX/RIS imports, `reader_out/`, and `knowledge_base/` must not be committed.
- Marketing assets in `docs/assets/` are checked-in project assets. Regenerate them with `python3 scripts/generate_marketing_assets.py`.
- Marketing screenshots in `docs/screenshots/` are checked-in sanitized demo assets. Regenerate them with `python3 scripts/generate_marketing_screenshots.py`.

## CodeGraph

CodeGraph is a generated local index of the repository, not a replacement for source files.

- Do not edit `.codegraph/` by hand.
- Do not treat `.codegraph/` as source of truth.
- `.codegraph/` is ignored by git and should be regenerated locally.
- To initialize or refresh it after cloning, run:

```bash
codegraph init -i
```

Use CodeGraph for structural questions after the index exists. If the index is missing, build it from the checked-in source files rather than adding generated index data to the repository.
