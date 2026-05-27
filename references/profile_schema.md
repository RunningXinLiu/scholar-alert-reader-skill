# Research Profile Schema

Profile files are JSON so the bundled script works with macOS Python without extra packages.

## Starting Templates

List bundled templates:

```bash
python3 scripts/scholar_reader.py list-profile-templates
```

Copy one into a project profile:

```bash
python3 scripts/scholar_reader.py init-profile \
  --profile ~/scholar_alerts/profiles/research_profile.json \
  --template ai-seismology \
  --force
```

Build or refine a profile without hand-editing JSON:

```bash
python3 scripts/scholar_reader.py profile-wizard \
  --project-dir ~/scholar_alerts \
  --focus "surface wave tomography, ambient noise" \
  --method "uncertainty quantification, phase picking" \
  --region "Tibet, Sichuan Basin" \
  --semantic-query "machine learning for dense array earthquake monitoring"
```

`init-project` also accepts `--profile-template`. Bundled templates live in `assets/profile_templates/` and are copied into each generated project under `profiles/templates/` for local editing.

## Fields

```json
{
  "name": "Seismology literature triage",
  "language": "zh-CN",
  "research_questions": [
    "Which papers improve seismic imaging resolution?"
  ],
  "focus_terms": [
    {"term": "seismic tomography", "weight": 5, "tags": ["method"]},
    {"term": "receiver function", "weight": 5, "tags": ["method"]}
  ],
  "regions": [
    {"term": "Taiwan", "weight": 4}
  ],
  "methods": [
    {"term": "full waveform inversion", "weight": 5}
  ],
  "watch_authors": [
    {"term": "Greg Beroza", "weight": 3}
  ],
  "exclude_terms": [
    {"term": "education", "weight": 4}
  ],
  "tier_thresholds": {
    "must_read": 8,
    "skim": 3
  },
  "adaptive_ranking": {
    "enabled": true,
    "positive_weight": 4,
    "negative_weight": 5,
    "min_overlap": 3,
    "max_seed_papers": 40,
    "seed_tiers": ["Must read"]
  },
  "limits": {
    "must_read": 5,
    "skim": 12,
    "deep_read": 5
  },
  "knowledge_base": {
    "foundation_tiers": ["Must read", "Skim"],
    "interested_tiers": ["Must read"],
    "interested_limit": 50,
    "foundation_limit_per_direction": 40,
    "write_archive_index": false
  },
  "schedule": {
    "timezone": "Asia/Shanghai",
    "default_time": "09:00",
    "default_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
  }
}
```

`term` matching is case-insensitive substring matching over title, author/source, alert name, and snippet. A title hit counts more than a snippet hit. If a list item is a plain string, default weight is `1`.

`semantic_queries` use local token-overlap matching between short natural-language intent statements and the paper title/snippet/source fields. `adaptive_ranking` then uses retained/interested library papers and feedback records as seeds: similar papers receive `positive_weight`, while papers similar to archive / less-like-this seeds receive `negative_weight`. Set `"enabled": false` to disable this feedback-similarity layer.

## Feedback Updates

Use the `feedback` command for paper-level feedback. It writes `knowledge_base/feedback.json` by default, refreshes the retained knowledge base immediately for selected papers, and later runs read that file automatically:

```bash
python3 scripts/scholar_reader.py feedback \
  --profile profiles/research_profile.json \
  --papers-json out/daily/papers.json \
  --paper-id <ID> \
  --mark interested \
  --more-like-this
```

The feedback file has two layers:

- `papers`: exact paper marks such as `interested`, `archive`, `more_like_this`, and `less_like_this`.
- `terms`: reusable positive/negative terms inferred from manual feedback or selected papers.

Later runs also compare new papers with retained/interested papers and feedback records when `adaptive_ranking.enabled` is true. Use `--no-feedback` to temporarily ignore feedback terms and adaptive ranking seeds.

Broad preference changes can still edit the profile:

- "多推这种": add or increase matching focus/method/region terms.
- "少推这种": add to `exclude_terms` or lower related focus weights.
- "这个作者重点关注": add to `watch_authors`.
- "最近看某个区域/方法": add to `regions` or `methods` with weight 4-6.
- "每天别超过 N 篇": update `limits.must_read` and `limits.deep_read`.

## Knowledge Base Semantics

- `seen_papers.json`: dedupe state only; may include every alert item.
- `feedback.json`: explicit user feedback and reusable ranking signals.
- `library.json`: cumulative retained library for `knowledge_base.foundation_tiers`.
- `foundation.md`: rendered from cumulative `library.json`.
- `interested.md`: cumulative active reading queue for `knowledge_base.interested_tiers`.
- `daily_additions.md`: latest daily new-paper-only retained additions.
- `papers/<paper-id>.md`: per-paper note page generated for retained papers.
- `directions/*.md`: topic/direction pages generated from paper tags.
- `weekly_review.md`: weekly synthesis generated from retained papers.
- Archive-tier papers are not added to the knowledge base unless `write_archive_index` is true.
