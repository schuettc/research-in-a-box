from datetime import date
from typing import Any

from archive_backend.search import SearchQuery, search


def _row(dataset_id: str, **fields: Any) -> dict[str, Any]:
    return {"id": dataset_id, "version": 1, "title": f"Dataset {dataset_id}", "access": "open"} | (
        fields
    )


def _ids(rows: list[dict[str, Any]], **query: Any) -> list[str]:
    return [r["id"] for r in search(rows, SearchQuery(**query)).rows]


def test_every_word_of_q_must_appear_ignoring_case() -> None:
    rows = [
        _row("a", title="Stream temperature", description="Hourly loggers"),
        _row("b", description="stream chemistry", keywords=["Temperature"]),
        _row("c", creators=["Ada Stream"], description="TEMPERATURE"),
        _row("d", title="Lake temperature"),
    ]

    assert sorted(_ids(rows, q="stream TEMPERATURE")) == ["a", "b", "c"]
    assert _ids(rows, q="  ") == ["a", "b", "c", "d"]


def test_title_matches_come_first_then_newest_published_then_id() -> None:
    rows = [
        _row("old", description="lake", published="2024-01-01T00:00:00Z"),
        _row("new", description="lake", published="2026-01-01T00:00:00Z"),
        _row("none-b", description="lake"),
        _row("none-a", description="lake"),
        _row("titled", title="Lake survey", published="2020-01-01T00:00:00Z"),
    ]

    assert _ids(rows, q="lake") == ["titled", "new", "old", "none-a", "none-b"]
    assert _ids(rows) == ["new", "old", "titled", "none-a", "none-b"]


def test_list_filters_keep_a_row_with_any_value() -> None:
    rows = [
        _row("a", access="open", licenses=["CC-BY-4.0"], formats=["csv"], project="p1"),
        _row("b", access="restricted", licenses=["CC0-1.0"], formats=["shp", "csv"]),
        _row("c", access="by-request", formats=["xlsx"], project="p2"),
    ]

    assert _ids(rows, access=["open", "restricted"]) == ["a", "b"]
    assert _ids(rows, license=["CC0-1.0"]) == ["b"]
    assert _ids(rows, format=["csv"]) == ["a", "b"]
    assert _ids(rows, project=["p2", "p3"]) == ["c"]
    assert _ids(rows, access=["open"], format=["xlsx"]) == []


def test_dates_keep_overlapping_coverage() -> None:
    rows = [
        _row("closed", start="2020-01-01", end="2020-12-31", ongoing=False),
        _row("ongoing", start="2022-01-01", ongoing=True),
        _row("unknown", start="2021-06-01", end="unknown", ongoing=False),
        _row("undated"),
    ]

    assert _ids(rows, from_=date(2021, 1, 1)) == ["ongoing", "unknown"]
    assert _ids(rows, to=date(2020, 6, 1)) == ["closed"]
    assert _ids(rows, from_=date(2020, 12, 31), to=date(2021, 6, 1)) == ["closed", "unknown"]
    assert _ids(rows, to=date(2019, 1, 1)) == []


def test_box_keeps_intersecting_rows_and_splits_at_the_antimeridian() -> None:
    rows = [
        _row("vermont", bbox=[-73.4, 42.7, -71.5, 45.0]),
        _row("fiji", bbox=[177.0, -19.0, -179.0, -16.0]),
        _row("samoa", bbox=[-172.8, -14.1, -171.4, -13.4]),
        _row("nowhere"),
    ]

    assert _ids(rows, bbox=(-74.0, 42.0, -72.0, 44.0)) == ["vermont"]
    assert _ids(rows, bbox=(-179.5, -20.0, -178.0, -15.0)) == ["fiji"]
    assert _ids(rows, bbox=(178.0, -20.0, -172.0, -13.0)) == ["fiji", "samoa"]
    assert _ids(rows, bbox=(170.0, 0.0, -170.0, 10.0)) == []


def test_facets_count_each_value_under_the_other_filters() -> None:
    rows = [
        _row("a", access="open", licenses=["CC-BY-4.0"], formats=["csv"], project="p1"),
        _row("b", access="open", licenses=["CC0-1.0"], formats=["csv", "shp"], project="p1"),
        _row("c", access="restricted", licenses=["CC-BY-4.0"], formats=["shp"]),
    ]

    result = search(rows, SearchQuery(access=["open"]))

    assert result.total == 2
    assert result.facets == {
        "access": {"open": 2, "restricted": 1},
        "license": {"CC-BY-4.0": 1, "CC0-1.0": 1},
        "format": {"csv": 2, "shp": 1},
        "project": {"p1": 2},
    }


def test_pages_split_the_ordered_rows() -> None:
    rows = [_row(f"ds-{n:02d}") for n in range(25)]

    first = search(rows, SearchQuery())
    second = search(rows, SearchQuery(page=2, size=10))
    past = search(rows, SearchQuery(page=4, size=10))

    assert first.total == 25 and len(first.rows) == 20
    assert [r["id"] for r in second.rows] == [f"ds-{n:02d}" for n in range(10, 20)]
    assert past.rows == [] and past.total == 25
