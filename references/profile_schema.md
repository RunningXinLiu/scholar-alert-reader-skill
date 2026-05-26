# Research Profile Schema

Profile files are JSON so the bundled script works with macOS Python without extra packages.

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

## Feedback Updates

Translate user feedback into profile edits:

- "多推这种": add or increase matching focus/method/region terms.
- "少推这种": add to `exclude_terms` or lower related focus weights.
- "这个作者重点关注": add to `watch_authors`.
- "最近看某个区域/方法": add to `regions` or `methods` with weight 4-6.
- "每天别超过 N 篇": update `limits.must_read` and `limits.deep_read`.

## Knowledge Base Semantics

- `seen_papers.json`: dedupe state only; may include every alert item.
- `library.json`: cumulative retained library for `knowledge_base.foundation_tiers`.
- `foundation.md`: rendered from cumulative `library.json`.
- `interested.md`: cumulative active reading queue for `knowledge_base.interested_tiers`.
- `daily_additions.md`: latest daily new-paper-only retained additions.
- Archive-tier papers are not added to the knowledge base unless `write_archive_index` is true.
