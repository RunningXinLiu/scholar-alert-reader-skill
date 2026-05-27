# Changelog

## Unreleased

## v0.2.51 - 2026-05-28

- Let `deep-read` automatically include a cached local full-text brief and full-text cache status when available.
- Add `deep-read --full-text-path`, `--full-text-brief-path`, and `--max-full-text-brief-chars` for explicit selected-paper evidence control.
- Surface section coverage, missing sections, visual/data/code signals, full-text profile overlap, and brief excerpts directly in the deep-read report.

## v0.2.50 - 2026-05-28

- Add product-facing `profile_meta` to bundled profile templates so each template describes its audience, starter sources, and recommended first edits.
- Upgrade `list-profile-templates` with text, markdown, and JSON catalog formats instead of a bare slug list.
- Document template metadata in the profile schema and onboarding docs.

## v0.2.49 - 2026-05-28

- Add `embedding-check` / `check-embedding` plus generated `embedding_check.sh` to verify semantic rerank backend readiness before a real run.
- Keep embedding model loading opt-in through `--load-model`, so users can inspect dependencies without accidental model downloads.
- Link the embedding check from generated guides, dashboards, capabilities, README, SKILL guidance, product notes, and tests.

## v0.2.48 - 2026-05-28

- Add an optional `semantic-rerank --backend sentence-transformers` path for local embedding-based reranking while keeping `--backend sparse` as the zero-dependency default.
- Add the `embedding` optional dependency group for users who want to install `sentence-transformers` explicitly.
- Record the active semantic backend in reports and reranked JSON so users can distinguish sparse TF-IDF runs from local embedding runs.

## v0.2.47 - 2026-05-28

- Add `semantic-rerank` / `rerank-semantic` plus generated `semantic_rerank.sh` to produce a dependency-free local sparse semantic reranking report.
- Write `knowledge_base/analysis/semantic_rerank.md` and `semantic_reranked_papers.json` with semantic deltas, profile/interested/archive overlaps, potential rescues, and potential downranks.
- Surface semantic rerank in the Dashboard, generated guide, README, SKILL guidance, product notes, capabilities, and tests while keeping the boundary clear that this is not a neural embedding service.

## v0.2.46 - 2026-05-28

- Add `fetch-pdf` / `pdf-fetch` plus generated `fetch_pdf.sh` to download explicit/open PDF URLs from user input, arXiv URLs, structured webpage metadata, or OpenAlex metadata.
- Allow `review-workflow --fetch-pdf` to fetch an open PDF before local full-text extraction, workup generation, and review-pack creation.
- Store fetched PDF metadata under `metadata.full_text`, surface it in paper notes, include `knowledge_base/pdfs/**` in privacy checks, and document that the tool does not crawl paywalled publisher pages or bypass access controls.

## v0.2.45 - 2026-05-28

- Add `ranking-eval` / `eval-ranking` plus generated `ranking_eval.sh` to evaluate saved ranking quality against explicit interested/archive feedback labels.
- Write `knowledge_base/analysis/ranking_evaluation.md` with precision/recall at K, average precision, tier calibration, potential false positives, missed positives, and tuning recommendations.
- Surface ranking evaluation in generated guides, dashboards, capabilities, README, SKILL guidance, product notes, and tests.

## v0.2.44 - 2026-05-28

- Add `privacy-check` / `privacy-audit` plus generated `privacy_check.sh` to scan local projects for files that should not be published.
- Report high-risk files, review-before-sharing files, recommended `.gitignore` coverage, and strict-mode failures before public sharing or issue attachments.
- Surface privacy checks in quickstart, generated guides, dashboards, capabilities, README, SKILL guidance, product notes, privacy policy, and tests.

## v0.2.43 - 2026-05-28

- Add `explain-ranking` / `rank-explain` plus generated `explain_ranking.sh` to explain selected papers' current score, tier, matched terms, feedback state, thresholds, and tuning moves.
- Write `knowledge_base/analysis/ranking_explanation.md` by default for one paper or a tier-filtered batch.
- Surface ranking explanation in generated dashboards, guides, capabilities, README, SKILL guidance, product notes, and tests.

## v0.2.42 - 2026-05-28

- Add `review-workflow` / `paper-review` plus generated `review_workflow.sh` to run the selected-paper path from optional local full-text extraction to workup and review pack in one command.
- Write `knowledge_base/analysis/<paper-id>_review_workflow.md` with extraction status, generated artifacts, capability boundary, and next actions.
- Cover the one-paper review workflow and generated helper script in regression tests.

## v0.2.41 - 2026-05-28

- Add a `Profile Health` section to `DASHBOARD.md/html` with profile-doctor status, link, and refresh command.
- Refresh `profiles/profile_doctor.md` automatically after successful generated `run_reader.sh` runs unless `REFRESH_PROFILE_DOCTOR=0` is set.
- Ignore generated profile onboarding/doctor reports in new project scaffolds and cover dashboard visibility in tests.

## v0.2.40 - 2026-05-28

- Add `profile-doctor` / generated `profile_doctor.sh` to diagnose ranking-profile quality after onboarding or feedback rounds.
- Report sparse or overbroad profile shape, missing semantic queries/exclusions, duplicate terms, threshold issues, feedback history, and recent/library ranking behavior.
- Include profile-doctor in quickstart checks, generated project guides, README, SKILL, product notes, and profile schema docs.

## v0.2.39 - 2026-05-28

- Add `profile-wizard` / generated `profile_wizard.sh` so users can turn current research questions and interests into profile terms without editing JSON by hand.
- Write `profile_onboarding.md` with added signals, profile counts, backup path, and next steps.
- Document the profile onboarding path in README, SKILL, product notes, profile schema, and generated project guides.

## v0.2.38 - 2026-05-28

- Add a `Review pack` action to the local feedback UI so selected papers can become assistant-ready context packs from the browser.
- Share one report-writing path between the `review-pack` CLI and browser UI action.
- Extend browser-report regression coverage to workup and review-pack generation plus local report rendering.

## v0.2.37 - 2026-05-28

- Add a `Workup` action to the local feedback UI so users can generate selected-paper decision briefs from the browser.
- Serve generated markdown reports through local `/report?name=...` links for deep-read, workup, full-text brief, and review-pack outputs.
- Add regression coverage for browser-triggered workup generation and report rendering.

## v0.2.36 - 2026-05-28

- Add `workup` / generated `workup_paper.sh` for a selected-paper decision brief against the user's foundation, feedback, full-text brief, and possible manuscript role.
- Surface the workup flow in the project dashboard, START_HERE guide, README, SKILL, and capability report.
- Add regression coverage for generated workup scripts and workup report content.

## v0.2.35 - 2026-05-28

- Add `schedule` / generated `schedule_reader.sh` to render, install, inspect, and uninstall macOS LaunchAgent schedules from `reader.env`.
- Write `SCHEDULE.md` plus project-local LaunchAgent plist previews before any explicit install.
- Add regression coverage for generated schedule helpers and LaunchAgent plist contents.

## v0.2.34 - 2026-05-28

- Add structured zero-paper diagnostics to `summary.json`, terminal output, `digest.md/html`, and `DASHBOARD.md/html`.
- Separate all-seen daily runs from empty sources, parser/source metadata misses, and unknown empty-result states.
- Add regression coverage for all-seen daily runs and readable webpage sources with no citation metadata.

## v0.2.33 - 2026-05-27

- Add `dashboard` / generated `dashboard_reader.sh` as a project home page linking the latest digest, reading plan, review queue, knowledge-base files, setup reports, and next actions.
- Refresh `DASHBOARD.md` / `DASHBOARD.html` automatically after successful generated `run_reader.sh` runs unless `REFRESH_DASHBOARD=0` is set.
- Add regression coverage for dashboard generation and project-scaffold integration.

## v0.2.32 - 2026-05-27

- Write `review_queue.html` alongside `review_queue.md` by default for browser-friendly batch paper review.
- Add `--html-output` / `--no-html` to `review-queue`.
- Add regression coverage for review-queue HTML generation.

## v0.2.31 - 2026-05-27

- Turn `review_queue.md` into a more actionable batch-reading panel with queue summary counts.
- Show per-paper section coverage, missing/weak sections, visual/data/code signals, and next action.
- Add regression coverage for review-queue evidence/status summaries.

## v0.2.30 - 2026-05-27

- Include cached full-text briefs automatically in `review-pack` and `review-queue` outputs.
- Add `--full-text-brief-path` and `--max-full-text-brief-chars` to `review-pack` for custom brief paths.
- Update review-pack prompts and docs so downstream assistants can use section coverage, visual/data/code signals, and citation checks before raw full text.

## v0.2.29 - 2026-05-27

- Add figure, table, supplement, data-availability, and code/software signal extraction to `full-text` reports.
- Add visual-evidence checks to the citation-readiness checklist.
- Cover visual/data/code evidence extraction in full-text regression tests.

## v0.2.28 - 2026-05-27

- Add section-aware full-text briefs that detect common paper sections, summarize coverage, and extract evidence by section.
- Add a citation-readiness checklist and missing/weak section list to `full-text` reports.
- Keep the existing full-text command interface while improving reports for downstream `review-pack` / `review-queue` workflows.

## v0.2.27 - 2026-05-27

- Add source-specific setup guidance to `SOURCE_CHECK.md` so Gmail, Mail.app, mbox, BibTeX/RIS, web, RSS/Atom, and arXiv users get immediate next steps.
- Print setup-wizard context about generated config, readiness checks, live checks, and the selected source.
- Cover the new onboarding guidance in tests and product docs.

## v0.2.26 - 2026-05-27

- Write `knowledge_base/reading_plan.html` alongside `reading_plan.md` so daily reading plans are browser-friendly.
- Add `--html-output` / `--no-html` to `reading-plan`.
- Include the HTML reading-plan path in summaries, terminal output, and the knowledge-base index.
- Add tests for automatic and explicit HTML reading-plan generation.

## v0.2.25 - 2026-05-27

- Generate `knowledge_base/reading_plan.md` automatically after runs that update the knowledge base.
- Add the reading-plan path to run summaries, terminal output, and the knowledge-base index.
- Keep demo/no-knowledge-base runs from writing personal reading-plan state.
- Add tests for automatic reading-plan generation from a normal source import.

## v0.2.24 - 2026-05-27

- Add `reading-plan` / generated `reading_plan.sh` to prioritize what to read next from retained and recent papers.
- Combine reading status, interested/archive feedback, tier, score, labels, latest-run flags, and full-text cache availability into a local reading queue.
- Document the daily reading-plan workflow in README, SKILL guidance, and product requirements.
- Add tests for the generated helper and reading-plan report output.

## v0.2.23 - 2026-05-27

- Add `capabilities` / generated `capabilities.sh` to explain product strengths, boundaries, non-promises, and recommended workflows.
- Include a redacted local project snapshot when `--project-dir` is provided.
- Tighten README/SKILL wording around metadata-based triage, local full-text extraction, and LLM-ready review packs.
- Add tests for the capability report and generated helper script.

## v0.2.22 - 2026-05-27

- Add `support-bundle` / generated `support_bundle.sh` for sanitized GitHub issue diagnostics.
- Summarize version, platform, config keys, file presence, counts, latest run metrics, and redacted `SOURCE_CHECK.md` / `DOCTOR.md` excerpts.
- Document privacy-safe support reporting in README, SKILL guidance, issue templates, and product requirements.
- Add tests to ensure support bundles redact private paths, URLs, and token contents.

## v0.2.21 - 2026-05-27

- Add `review-queue` / generated `review_queue.sh` to batch-build review packs for selected papers.
- Let review queues attempt local full-text extraction from Zotero/PDF/text paths before writing each review pack.
- Write `knowledge_base/analysis/review_queue.md` with extraction status, cache paths, brief paths, and review-pack paths.
- Document the batch review workflow in README, SKILL guidance, automation reference, and product requirements.

## v0.2.20 - 2026-05-27

- Add adaptive local feedback-similarity ranking from retained/interested papers and archive / less-like-this feedback seeds.
- Include adaptive-ranking defaults in bundled profile templates and the packaged resources.
- Document `adaptive_ranking` in the README, skill guide, product requirements, and profile schema.
- Add unit tests for positive and negative adaptive-ranking behavior.

## v0.2.19 - 2026-05-27

- Add privacy-first GitHub issue forms for bug reports, source setup help, and feature requests.
- Add a pull request template with local checks and private-data safeguards.
- Add `SECURITY.md` for credential leaks, raw mailbox exposure, and other private reports.
- Document safe public reporting in README, CONTRIBUTING, PRIVACY, and product requirements.

## v0.2.18 - 2026-05-27

- Move CI to `actions/checkout@v6` and `actions/setup-python@v6`, which use the Node 24 action runtime directly.

## v0.2.17 - 2026-05-27

- Opt GitHub Actions into Node 24 execution for JavaScript actions to avoid the Node 20 deprecation warning before GitHub changes the default runner behavior.

## v0.2.16 - 2026-05-27

- Add a GitHub Actions package job that builds the wheel, installs it into a clean virtual environment, and runs the installed `scholar-alert-reader` CLI.
- Smoke-test installed-package resources by running `setup-wizard --live-check` against bundled RSS sample data in CI.
- Restrict GitHub Actions permissions to read-only repository contents.
- Modernize package metadata and resource package discovery so wheel builds stay warning-clean on current setuptools.

## v0.2.15 - 2026-05-27

- Make `setup-wizard` write `SOURCE_CHECK.md` after configuration so first-time users immediately see source readiness.
- Add `--live-check`, `--skip-check`, `--check-output`, and strict/limit/timeout options for post-setup validation.
- Document the wizard readiness report in README, SKILL guidance, troubleshooting, and product requirements.

## v0.2.14 - 2026-05-27

- Add `setup-wizard` / generated `setup_wizard.sh` for guided first-time configuration of source, profile template, schedule, and optional Obsidian/Zotero paths.
- Let `setup-wizard --defaults` initialize a new project and write `reader.env` non-interactively for scripted install checks.
- Refresh project onboarding and README guidance so new users can use the wizard before learning setup flags.

## v0.2.13 - 2026-05-27

- Add standard Python packaging metadata with `python -m scholar_alert_reader` plus `scholar-alert-reader` and `scholar-reader` console scripts.
- Bundle default profiles, profile templates, examples, and troubleshooting docs as package resources so installed quickstarts work outside a source checkout.
- Make generated project scripts remember the Python used at initialization and fall back to `python -m scholar_alert_reader` when the repository wrapper is unavailable.
- Use repository-relative README image paths so GitHub shows the latest checked-in logo, workflow, architecture, and screenshot assets.

## v0.2.12 - 2026-05-27

- Add `quickstart` to create a local project, run private-data-free checks and multi-source demos, refresh onboarding docs, and write `QUICKSTART_REPORT.md`.
- Document the one-command terminal setup path in README and SKILL guidance.
- Copy `TROUBLESHOOTING.md` into initialized projects so users can debug sources from the project folder.

## v0.2.11 - 2026-05-27

- Add `TROUBLESHOOTING.md` with concrete checks for zero-paper runs, Gmail OAuth, Gmail dependency environments, Mail.app permissions, mbox, BibTeX/RIS, webpage metadata, RSS/arXiv, Obsidian, Zotero, and privacy pitfalls.
- Link the troubleshooting guide from README, SKILL guidance, Claude notes, and product requirements.

## v0.2.10 - 2026-05-27

- Add generated `demo_sources.sh` to run sanitized examples for mbox, BibTeX, RIS, webpage metadata, and RSS without reading private data or updating the retained knowledge base.
- Surface the multi-source demo in generated project onboarding and README quickstart instructions.

## v0.2.9 - 2026-05-27

- Add `--source-web` / generated `web_import.sh` for structured scholarly webpage metadata imports from URLs, saved HTML, directories, or URL/path lists.
- Parse citation meta tags, JSON-LD, Dublin Core, and OpenGraph into the same ranking, feedback, digest, and knowledge-base pipeline as email, bibliography, RSS, and arXiv sources.
- Add sample webpage data, source-check/self-test coverage, project scaffolding, privacy notes, and user-facing documentation for webpage metadata sources.

## v0.2.8 - 2026-05-27

- Add `self-test` / generated `self_test.sh` for bundled-data end-to-end install validation.
- Verify project scaffolding, sample mbox parsing, sample RSS source checking, digest artifacts, and doctor output without reading private data.
- Add self-test guidance to README, SKILL, automation notes, privacy notes, and project scaffolds.

## v0.2.7 - 2026-05-27

- Add `profile-tune` / generated `tune_profile.sh` to suggest profile updates from interested/archive and more-like-this/less-like-this feedback.
- Write `knowledge_base/profile_tuning.md` with suggested focus terms, semantic queries, exclude terms, evidence papers, and copyable apply commands.
- Keep profile tuning report-only by default; `--apply` is required before suggested terms are written back to the active profile.

## v0.2.6 - 2026-05-27

- Add dependency-free `semantic_queries` scoring to rescue papers that match the user's research intent without exact phrase matches.
- Add explainable semantic-match reasons and a `semantic` tag in matched paper outputs.
- Update bundled profile templates with starter semantic queries for AI seismology, seismic imaging, induced seismicity, dense-array monitoring, and general geophysics.

## v0.2.5 - 2026-05-27

- Add `review-pack` / generated `review_paper.sh` for creating LLM-ready selected-paper review context packs.
- Include target metadata, user profile, feedback status, optional local full-text cache, closest foundation papers, and interested/active-reading context in review packs.
- Document the cross-assistant workflow for using Scholar Alert Reader with Codex, Claude, ChatGPT, or any other markdown-capable assistant.

## v0.2.4 - 2026-05-27

- Add `full-text` / generated `full_text_paper.sh` for local PDF/text extraction and full-text reading briefs.
- Cache extracted text under `knowledge_base/full_text/` and write briefs under `knowledge_base/analysis/`.
- Support `pdftotext`, optional Python PDF libraries, and plain text/Markdown exports with graceful errors when tooling is missing.

## v0.2.3 - 2026-05-27

- Add `zotero-sync` / generated `zotero_sync.sh` to read Better BibTeX/BibTeX metadata back into retained papers.
- Store Zotero citation keys, item keys, and local PDF paths under `metadata.zotero`.
- Reuse synced Zotero citation keys and PDF paths in Obsidian paper-note frontmatter.

## v0.2.2 - 2026-05-27

- Add `setup` / generated `setup_reader.sh` to persist local source, profile, schedule, Obsidian, and Zotero defaults in `reader.env`.
- Make generated helper scripts read `reader.env` without overriding explicit one-off environment variables from the caller.
- Show persistent configuration status in generated `START_HERE.md`.

## v0.2.1 - 2026-05-27

- Add bundled research-profile templates for general geophysics, AI seismology, induced seismicity, seismic imaging, and dense-array monitoring.
- Add `list-profile-templates`, `init-profile --template`, `init-project --profile-template`, and generated `copy_profile_template.sh`.
- Clarify that deep-read/Q&A/advice are metadata and retained-library triage aids until a full-text/PDF pipeline is added.

## v0.2.0 - 2026-05-27

- Add a product-oriented `guide` command and generated `START_HERE.md` for local projects.
- Add a sanitized demo mailbox and `demo_reader.sh` so users can test without Gmail, Obsidian, or Zotero.
- Add BibTeX/RIS as first-class input sources for Zotero, publisher, database, and Google Scholar library exports.
- Add RSS/Atom and arXiv as structured web input sources without arbitrary web scraping.
- Add `source-check` / `source_check.sh` for Gmail, Mail.app, mbox, BibTeX/RIS, RSS/arXiv, and auto source diagnostics.
- Add checked-in GitHub/朋友圈 marketing assets: social card, architecture diagram, workflow GIF, and Chinese share copy.
- Add CodeGraph/source-of-truth documentation while keeping `.codegraph/` ignored as generated local state.
- Add literature-copilot commands for deep reads, local-library Q&A, research advice, reading status, comparisons, and research maps.
- Add optional Zotero and Obsidian export flows with structured Obsidian folders and citation-oriented frontmatter.
- Expand diagnostics to check optional Obsidian and Zotero integration outputs.
- Document Codex-only, Obsidian, Zotero, and platform support modes in `README.md` and `PRODUCT.md`.

## v0.1.0 - 2026-05-27

Initial private release.

- Read Google Scholar Alert emails from Gmail API, Mail.app, or exported mbox files.
- Generate Markdown/HTML digests, JSON/CSV outputs, and a retained knowledge base.
- Support personalized ranking through research profiles and paper-level feedback.
- Provide local feedback UI, OpenAlex/Crossref enrichment, weekly synthesis, exports, and diagnostics.
- Add `init-project` for creating a runnable local project scaffold.
- Add unit tests and GitHub Actions CI.
