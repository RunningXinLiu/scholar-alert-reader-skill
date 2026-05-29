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
from .status import (
    feedback_note,
    feedback_note_summary,
    feedback_record,
    reading_labels,
    reading_status,
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
    "feedback_record",
    "reading_status",
    "reading_labels",
    "feedback_note",
    "feedback_note_summary",
]
