"""Server-side paging, for the list endpoints whose row count is a function of customer data.

Two conventions already existed in this codebase and neither was shared: `/semantic/objects/…/instances`
returns `pagination: {limit, offset, total, hasMore}`, and `/data-sources/{id}/tables/{name}/rows`
returns the same block under the name `page`. Everything else returned the whole list, which is
fine for a list whose length is bounded by *platform configuration* -- the six built-in roles,
the quota resource kinds, the axiom kinds -- and not fine for one bounded by the customer's
schema: `/ontologies/{id}/mappings` writes a row per mapped column, and a legacy system with
five hundred tables produces tens of thousands of them for the review queue that gates
publication.

## Additive, because a default cap is the dangerous half

Supplying `limit` pages the response. Not supplying it returns everything, exactly as before,
plus a `pagination` block nobody was asking for. That ordering matters: several screens print
`decisions.length` as a tab count and several more key their empty state off `array.length`, so
quietly capping every list at fifty would have made those numbers wrong without making anything
fail -- the same class of defect as the blank columns.

The block is always present, and `limit: null` means "no limit was applied". A caller can
therefore tell "these are all the rows" from "these are the first fifty of nine hundred"
without having to know whether it passed a limit.

`total` is a real count, not `offset + len(rows)`: a pager that shows "51 of 51" when there are
nine hundred rows is worse than no pager, because it looks like an answer.
"""

from __future__ import annotations

from typing import Any

__all__ = ["PAGE_KEYS", "page_block", "resolve_page"]

# The key every paginated list carries this block under. One name rather than two: the two
# spellings that existed (`pagination` and `page`) were the same object, and a client reading
# both is a client that will get one of them wrong.
PAGE_KEYS = ("limit", "offset", "total", "hasMore")


def resolve_page(limit: int | None, offset: int | None = None) -> tuple[int | None, int]:
    """The page to return: `(limit, offset)`, with the limit clamped and the offset floored.

    `limit=None` means *the whole list*, which is what every one of these endpoints did before
    it took a `limit` parameter and is what a caller that does not pass one still gets.

    A supplied limit is clamped rather than trusted, for the reason `tests/test_query_limit_clamping.py`
    exists: `LIMIT -1` is "no limit" in SQLite, so an unclamped limit is not a large page, it is
    an unbounded response. Zero becomes one rather than none, matching `clamp_page_size` -- a
    request for no rows is not a request anybody means to make.
    """
    if limit is None:
        return None, max(0, int(offset or 0))
    from .config import clamp_page_size

    return clamp_page_size(limit), max(0, int(offset or 0))


def page_block(*, limit: int | None, offset: int, total: int, returned: int) -> dict[str, Any]:
    """The block beside a list, saying how much of it this response is.

    `returned` is passed rather than derived from `len(rows)` by the caller because the callers
    are the ones holding the rows, and one of them slices in memory rather than in SQL.
    """
    return {
        "limit": limit,
        "offset": offset,
        "total": total,
        # False when there is no limit at all, which is the honest answer: a response that
        # contains everything has nothing more to fetch, and a pager that offered a "next page"
        # for it would send the reader to an empty screen.
        "hasMore": limit is not None and offset + returned < total,
    }
