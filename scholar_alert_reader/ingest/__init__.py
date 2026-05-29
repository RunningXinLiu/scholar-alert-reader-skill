"""Ingestion adapters for paper sources.

Phase 3 splits parsing by source type so `core.py` keeps only command orchestration.
"""

from . import base  # noqa: F401
from . import mail  # noqa: F401
from . import ris  # noqa: F401
from . import bibtex  # noqa: F401
from . import rss  # noqa: F401
from . import web  # noqa: F401
from . import arxiv  # noqa: F401

__all__ = ["base", "mail", "ris", "bibtex", "rss", "web", "arxiv"]
