"""Search over the catalog file's rows: keywords, facets, dates and a box, in memory.

Pure: no AWS. The API route reads the rows from `site/catalog.json` and hands them here.
"""

from __future__ import annotations

import re
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

STOP_WORDS = frozenset("a an and the of on in near from for to with by at as or".split())
"""Words of `q` that never count toward a match."""

TITLE_WEIGHT = 0.5
"""What a word found in the title adds on top of being found at all."""

FUSION_K = 60
"""Reciprocal rank fusion's constant: a place p in a list scores 1 / (FUSION_K + p)."""


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


MIN_WORD = 3
"""Shorter reduced words are dropped: "is" or "ga" would match almost every row."""


def _reduce(word: str) -> str:
    """The word without a plural ending, when it is long enough to have one."""
    if len(word) <= MIN_WORD:
        return word
    for suffix in ("ies", "es", "s"):
        if word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _words(q: str | None) -> list[str]:
    """The reduced words of `q`, once each, in order, without stop words."""
    words: list[str] = []
    for run in re.findall(r"[a-z0-9]+", (q or "").lower()):
        word = _reduce(run) if run not in STOP_WORDS else ""
        if len(word) >= MIN_WORD and word not in words:
            words.append(word)
    return words


def _text(row: Row) -> str:
    parts = [str(row.get("title") or ""), str(row.get("description") or "")]
    parts += _values(row, "keywords") + _values(row, "creators")
    return " ".join(parts).lower()


def _score(row: Row, words: list[str]) -> float:
    """How many words the row matches, a word in the title counting half again."""
    text = _text(row)
    title = str(row.get("title") or "").lower()
    return sum(1 + (TITLE_WEIGHT if w in title else 0) for w in words if w in text)


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


def _filters(
    query: SearchQuery, scores: dict[int, float] | None
) -> dict[str, Callable[[Row], bool]]:
    checks: dict[str, Callable[[Row], bool]] = {
        "q": lambda r: scores is None or scores[id(r)] > 0,
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


def _order(rows: list[Row], scores: dict[int, float] | None) -> list[Row]:
    ordered = sorted(rows, key=lambda r: str(r.get("id")))
    ordered.sort(key=lambda r: str(r.get("published") or ""), reverse=True)
    ordered.sort(key=lambda r: not r.get("published"))
    if scores is not None:
        ordered.sort(key=lambda r: scores[id(r)], reverse=True)
    return ordered


def _scores(rows: list[Row], q: str | None) -> dict[int, float] | None:
    """Each row's score keyed by the row object, or None when no `q` is given."""
    if not (q or "").strip():
        return None
    words = _words(q)
    return {id(r): _score(r, words) for r in rows}


def keyword_ranking(rows: list[Row], q: str | None) -> list[str]:
    """The ids of the rows `q` matches, best first."""
    scores = _scores(rows, q)
    matched = [r for r in rows if scores is not None and scores[id(r)] > 0]
    return [str(r.get("id")) for r in _order(matched, scores)]


def fuse(keyword_ids: list[str], semantic_ids: list[str]) -> list[str]:
    """Reciprocal rank fusion: each id scores the sum of 1 / (60 + place) over the lists it is
    in, places counting from 1; ties go by id."""
    fused: dict[str, float] = {}
    for ids in (keyword_ids, semantic_ids):
        for place, row_id in enumerate(ids, start=1):
            fused[row_id] = fused.get(row_id, 0.0) + 1 / (FUSION_K + place)
    return sorted(fused, key=lambda row_id: (-fused[row_id], row_id))


def _fused_scores(rows: list[Row], q: str | None, semantic: list[str]) -> dict[int, float]:
    """Scores keyed by the row object that order the fused list: above 0 only for its members."""
    order = fuse(keyword_ranking(rows, q), semantic)
    place = {row_id: n for n, row_id in enumerate(order)}
    return {id(r): float(len(order) - place.get(str(r.get("id")), len(order))) for r in rows}


def search(rows: list[Row], query: SearchQuery, semantic: list[str] | None = None) -> SearchResult:
    """The page of matching rows, the total, and each facet value's count under the others.

    With `semantic`, the ids of the nearest datasets, `q` keeps the keyword matches and those ids,
    ordered by `fuse`.
    """
    if semantic is None:
        scores = _scores(rows, query.q)
    else:
        scores = _fused_scores(rows, query.q, semantic)
    checks = _filters(query, scores)
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
    ordered = _order(matched, scores)
    start = (query.page - 1) * query.size
    return SearchResult(rows=ordered[start : start + query.size], total=len(matched), facets=facets)
