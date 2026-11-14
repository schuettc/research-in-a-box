"""Search over the catalog file's rows: keywords, facets, dates and a box, in memory.

Pure: no AWS. The API route reads the rows from `site/catalog.json` and hands them here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

Row = dict[str, Any]
Box = tuple[float, float, float, float]

FACETS: dict[str, str] = {
    "access": "access",
    "license": "licenses",
    "format": "formats",
    "project": "project",
}
"""Each facet's query name and the row field it reads."""


@dataclass(frozen=True)
class SearchQuery:
    q: str | None = None
    access: list[str] = field(default_factory=list)
    license: list[str] = field(default_factory=list)
    format: list[str] = field(default_factory=list)
    project: list[str] = field(default_factory=list)
    from_: date | None = None
    to: date | None = None
    bbox: Box | None = None
    page: int = 1
    size: int = 20


@dataclass(frozen=True)
class SearchResult:
    rows: list[Row]
    total: int
    facets: dict[str, dict[str, int]]


def _values(row: Row, name: str) -> list[str]:
    value = row.get(name)
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)] if value is not None else []


def _words(q: str | None) -> list[str]:
    return [w.lower() for w in (q or "").split()]


def _text(row: Row) -> str:
    parts = [str(row.get("title") or ""), str(row.get("description") or "")]
    parts += _values(row, "keywords") + _values(row, "creators")
    return " ".join(parts).lower()


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _in_dates(row: Row, start: date | None, end: date | None) -> bool:
    if start is None and end is None:
        return True
    row_start = _date(row.get("start"))
    if row_start is None:
        return False
    row_end = None if row.get("ongoing") else _date(row.get("end"))
    if end is not None and row_start > end:
        return False
    return start is None or row_end is None or row_end >= start


def _spans(west: float, east: float) -> list[tuple[float, float]]:
    return [(west, east)] if west <= east else [(west, 180.0), (-180.0, east)]


def _in_box(row: Row, box: Box | None) -> bool:
    if box is None:
        return True
    bbox = row.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        return False
    west, south, east, north = (float(v) for v in bbox)
    q_west, q_south, q_east, q_north = box
    if south > q_north or q_south > north:
        return False
    return any(
        a_w <= b_e and b_w <= a_e
        for a_w, a_e in _spans(west, east)
        for b_w, b_e in _spans(q_west, q_east)
    )


def _filters(query: SearchQuery) -> dict[str, Callable[[Row], bool]]:
    words = _words(query.q)
    checks: dict[str, Callable[[Row], bool]] = {
        "q": lambda r: all(w in _text(r) for w in words),
        "dates": lambda r: _in_dates(r, query.from_, query.to),
        "bbox": lambda r: _in_box(r, query.bbox),
    }
    for facet, name in FACETS.items():
        wanted = set(getattr(query, facet))
        if wanted:
            checks[facet] = _any_of(name, wanted)
    return checks


def _any_of(name: str, wanted: set[str]) -> Callable[[Row], bool]:
    return lambda r: bool(wanted & set(_values(r, name)))


def _order(rows: list[Row], words: list[str]) -> list[Row]:
    ordered = sorted(rows, key=lambda r: str(r.get("id")))
    ordered.sort(key=lambda r: str(r.get("published") or ""), reverse=True)
    ordered.sort(key=lambda r: not r.get("published"))
    if words:
        ordered.sort(key=lambda r: not any(w in str(r.get("title") or "").lower() for w in words))
    return ordered


def search(rows: list[Row], query: SearchQuery) -> SearchResult:
    """The page of matching rows, the total, and each facet value's count under the others."""
    checks = _filters(query)
    matched = [r for r in rows if all(check(r) for check in checks.values())]
    facets: dict[str, dict[str, int]] = {}
    for facet, name in FACETS.items():
        others = [check for key, check in checks.items() if key != facet]
        counts: dict[str, int] = {}
        for row in rows:
            if all(check(row) for check in others):
                for value in set(_values(row, name)):
                    counts[value] = counts.get(value, 0) + 1
        facets[facet] = dict(sorted(counts.items()))
    ordered = _order(matched, _words(query.q))
    start = (query.page - 1) * query.size
    return SearchResult(rows=ordered[start : start + query.size], total=len(matched), facets=facets)
