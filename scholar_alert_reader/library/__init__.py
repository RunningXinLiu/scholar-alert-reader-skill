"""Library-layer helpers for retained paper storage and curation."""

from .store import (
    kb_settings,
    load_paper_library,
    merge_papers,
    paper_directions,
    paper_from_dict,
    save_paper_library,
)
from .render import (
    write_kb_paper_pages,
    write_kb_search_index,
    metadata_lines,
)

__all__ = [
    "metadata_lines",
    "kb_settings",
    "paper_directions",
    "paper_from_dict",
    "load_paper_library",
    "merge_papers",
    "save_paper_library",
    "write_kb_paper_pages",
    "write_kb_search_index",
]
