"""arXiv query adapter."""

from __future__ import annotations

from urllib.parse import urlencode

from typing import Any, Callable

from . import rss


def arxiv_api_url(query: str, limit: int, sort_by: str = "submittedDate", sort_order: str = "descending") -> str:
    params = {
        "search_query": query,
        "start": "0",
        "max_results": str(max(1, int(limit or 50))),
        "sortBy": sort_by,
        "sortOrder": sort_order,
    }
    return "https://export.arxiv.org/api/query?" + urlencode(params)


def parse_arxiv_source(
    query: str,
    limit: int = 50,
    timeout: int = 20,
    paper_factory: Callable[..., Any] | None = None,
) -> tuple[list[Any], dict[str, int]]:
    if paper_factory is None:
        from ..core import Paper

        paper_factory = Paper

    url = arxiv_api_url(query, limit)
    papers, counts = rss.parse_rss_source(url, timeout=timeout, limit=limit, paper_factory=paper_factory)
    counts["arxiv_query"] = query
    counts["arxiv_api_url"] = url
    return papers, counts
