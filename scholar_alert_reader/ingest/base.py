"""Shared ingest helpers.

Kept intentionally small in Phase 3; most parser-specific helpers remain in
source modules.
"""

from __future__ import annotations

import hashlib
import re


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def stable_id(title: str) -> str:
    return hashlib.sha1(normalize_title(title).encode("utf-8")).hexdigest()[:12]


def strip_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]
