"""Can I trust the values? Table rows, read as text and tested in DuckDB SQL.

Every value arrives as text, with the schema's missing values already null, so each rule
tests casts with `TRY_CAST` and the like: a value that doesn't fit is a finding, never a
failed read. Each value rule applies one check per column it looks at.
"""

from collections.abc import Iterator
from datetime import date
from typing import Any

import duckdb

from archive_contract.fields import Field, TableSchema
from archive_contract.manifest import SpatialCoverage, TemporalCoverage
from archive_contract.resources import Resource
from cruise.rules.registry import EVIDENCE_LIMIT, Context, Outcome, Problem, rule
from cruise.tables import ROW, quote_identifier, quote_literal, select

PLACEHOLDERS = (-9999, -999, -99, 9999, 99999)
"""Numbers that stand for "no value" in legacy data."""

TRUE_VALUES = ("true", "True", "TRUE", "1")
FALSE_VALUES = ("false", "False", "FALSE", "0")

DATE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("YYYY-MM-DD", ("%Y-%m-%d",)),
    ("YYYY-MM-DD hh:mm", ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M")),
    ("YYYY/MM/DD", ("%Y/%m/%d",)),
    ("MM/DD/YYYY or DD/MM/YYYY", ("%m/%d/%Y", "%d/%m/%Y")),
    ("DD.MM.YYYY", ("%d.%m.%Y",)),
    ("D Mon YYYY", ("%d %b %Y", "%d %B %Y", "%d-%b-%Y")),
    ("Mon D, YYYY", ("%b %d, %Y", "%B %d, %Y")),
)
"""The date patterns a string column is sorted into; the first that parses a value wins."""

LATITUDE_NAMES = frozenset({"lat", "latitude"})
LONGITUDE_NAMES = frozenset({"lon", "long", "longitude"})
DATE_TYPES = frozenset({"date", "datetime", "year"})
ROW_SQL = quote_identifier(ROW)

_ISO_DATETIME = r"\s*\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?(Z|[+-]\d{2}:?\d{2})?\s*"
_ZONE = r"(Z|[+-]\d{2}:?\d{2})\s*$"


def _strptime(value: str, pattern: str) -> str:
    return f"TRY_STRPTIME({value}, {quote_literal(pattern)})"


def _when(value: str, pattern: str, then: str) -> str:
    """SQL for `then` when the whole value matches the regular expression, else null."""
    return f"CASE WHEN regexp_full_match({value}, {quote_literal(pattern)}) THEN {then} END"


def _typed(column: Field, value: str) -> str | None:
    """SQL reading `value` as the column's declared type: null when it doesn't fit, and
    None when the type is one these rules don't check."""
    fmt = column.format or "default"
    match column.type:
        case "integer":
            return _when(value, r"\s*[+-]?[0-9]+\s*", f"TRY_CAST({value} AS HUGEINT)")
        case "number":
            return f"TRY_CAST({value} AS DOUBLE)"
        case "boolean":
            extra = column.model_extra or {}
            trues = ", ".join(quote_literal(str(v)) for v in extra.get("trueValues", TRUE_VALUES))
            falses = ", ".join(
                quote_literal(str(v)) for v in extra.get("falseValues", FALSE_VALUES)
            )
            return (
                f"CASE WHEN {value} IN ({trues}) THEN true "
                f"WHEN {value} IN ({falses}) THEN false END"
            )
        case "date":
            if fmt == "default":
                return f"CAST({_strptime(value, '%Y-%m-%d')} AS DATE)"
            if fmt == "any":
                return f"TRY_CAST({value} AS DATE)"
            return f"CAST({_strptime(value, fmt)} AS DATE)"
        case "datetime":
            if fmt in ("default", "any"):
                bare = f"regexp_replace({value}, '{_ZONE}', '')"
                return _when(value, _ISO_DATETIME, f"TRY_CAST({bare} AS TIMESTAMP)")
            return _strptime(value, fmt)
        case "time":
            return f"TRY_CAST({value} AS TIME)"
        case "year":
            return _when(value, r"\s*-?[0-9]{4}\s*", f"TRY_CAST({value} AS INTEGER)")
        case "yearmonth":
            return _when(value, r"\s*[0-9]{4}-[0-9]{2}\s*", _strptime(f"trim({value})", "%Y-%m"))
        case _:
            return None


def _year(column: Field, value: str) -> str:
    """SQL for the year of a date, datetime or year column's value."""
    typed = _typed(column, value)
    if typed is None:
        raise ValueError(f"{column.name} is not a date, datetime or year column")
    return typed if column.type == "year" else f"year({typed})"


def _evidence(
    relation: duckdb.DuckDBPyRelation, value: str, where: str
) -> tuple[list[int], list[Any], int]:
    """The first rows where `where` holds, the value of `value` at each, and how many there are."""
    found = select(
        relation,
        f"SELECT {ROW_SQL}, {value} FROM t WHERE coalesce({where}, false) "
        f"ORDER BY {ROW_SQL} LIMIT {EVIDENCE_LIMIT}",
    )
    count = select(relation, f"SELECT count(*) FROM t WHERE coalesce({where}, false)")[0][0]
    return [r[0] for r in found], [r[1] for r in found], int(count)


def _columns(
    ctx: Context,
) -> Iterator[tuple[Resource, TableSchema, duckdb.DuckDBPyRelation, Field, str]]:
    """Every column of every readable table, with its value as SQL."""
    for resource, schema, relation in ctx.tables():
        for column in schema.fields:
            yield resource, schema, relation, column, quote_identifier(column.name)


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _agree(count: int, one: str, many: str) -> str:
    return one if count == 1 else many


@rule("values.not-declared-type", question="trust", scope="table", severity="warning")
def not_declared_type(ctx: Context) -> Outcome:
    problems: list[Problem] = []
    checks = 0
    for resource, _, relation, column, value in _columns(ctx):
        typed = _typed(column, value)
        if typed is None:
            continue
        checks += 1
        rows, values, count = _evidence(
            relation, value, f"{value} IS NOT NULL AND ({typed}) IS NULL"
        )
        if count:
            problems.append(
                Problem(
                    f"Column {column.name} has {_plural(count, 'value')} that "
                    f"{_agree(count, 'reads', 'read')} as {column.type} and "
                    f"{_agree(count, 'is', 'are')} not declared missing.",
                    resource=resource.name,
                    field=column.name,
                    rows=rows,
                    values=values,
                    count=count,
                    fix="Correct the values, or declare them in the schema's missingValues.",
                )
            )
    return Outcome(problems, checks)


@rule("values.placeholder", question="trust", scope="table", severity="warning")
def placeholder(ctx: Context) -> Outcome:
    problems: list[Problem] = []
    checks = 0
    for resource, _, relation, column, value in _columns(ctx):
        if column.type not in ("number", "integer"):
            continue
        checks += 1
        number = f"TRY_CAST(({_typed(column, value)}) AS DOUBLE)"
        suspects = [float(p) for p in PLACEHOLDERS]
        negatives = select(
            relation,
            f"SELECT {number} AS n, count(*) FROM t WHERE {number} < 0 GROUP BY n",
        )
        others = select(relation, f"SELECT count(*) FROM t WHERE {number} >= 0")[0][0]
        if len(negatives) == 1 and negatives[0][1] > 1 and others:
            suspects.append(float(negatives[0][0]))
        listed = ", ".join(repr(s) for s in suspects)
        rows, values, count = _evidence(relation, value, f"{number} IN ({listed})")
        if count:
            problems.append(
                Problem(
                    f"Column {column.name} has {_plural(count, 'value')} that "
                    f"{_agree(count, 'looks', 'look')} like a placeholder for no value.",
                    resource=resource.name,
                    field=column.name,
                    rows=rows,
                    values=values,
                    count=count,
                    fix="Declare the placeholder in the schema's missingValues, or replace it.",
                )
            )
    return Outcome(problems, checks)


@rule("values.constant", question="trust", scope="table", severity="warning")
def constant(ctx: Context) -> Outcome:
    problems: list[Problem] = []
    checks = 0
    for resource, _, relation, column, value in _columns(ctx):
        total, present, distinct, only = select(
            relation,
            f"SELECT count(*), count({value}), count(DISTINCT {value}), min({value}) FROM t",
        )[0]
        if total < 2:
            continue
        checks += 1
        if present == total and distinct == 1:
            rows, _, _ = _evidence(relation, value, "true")
            problems.append(
                Problem(
                    f"Column {column.name} holds the same value in every row.",
                    resource=resource.name,
                    field=column.name,
                    rows=rows,
                    values=[only],
                    count=int(total),
                    fix=f"Move {column.name} into the description, or drop it.",
                )
            )
    return Outcome(problems, checks)


def _pattern(value: str) -> str:
    cases = " ".join(
        f"WHEN {' OR '.join(f'{_strptime(value, p)} IS NOT NULL' for p in patterns)} "
        f"THEN {quote_literal(label)}"
        for label, patterns in DATE_PATTERNS
    )
    return f"CASE {cases} END"


@rule("values.mixed-date-formats", question="trust", scope="table", severity="warning")
def mixed_date_formats(ctx: Context) -> Outcome:
    problems: list[Problem] = []
    checks = 0
    order = [label for label, _ in DATE_PATTERNS]
    for resource, _, relation, column, value in _columns(ctx):
        if column.type not in (None, "string"):
            continue
        checks += 1
        pattern = _pattern(value)
        counts = select(
            relation,
            f"SELECT p, count(*) FROM (SELECT {pattern} AS p FROM t) "
            "WHERE p IS NOT NULL GROUP BY p",
        )
        if len(counts) < 2:
            continue
        counts.sort(key=lambda c: (-c[1], order.index(c[0])))
        main = counts[0][0]
        rows, values, count = _evidence(relation, value, f"({pattern}) <> {quote_literal(main)}")
        summary = ", ".join(f"{label} ({_plural(n, 'row')})" for label, n in counts)
        problems.append(
            Problem(
                f"Column {column.name} holds dates in more than one format: {summary}.",
                resource=resource.name,
                field=column.name,
                rows=rows,
                values=values,
                count=count,
                fix=f"Write every date in {column.name} as YYYY-MM-DD and type it as a date.",
            )
        )
    return Outcome(problems, checks)


def _dated_columns(
    ctx: Context,
) -> Iterator[tuple[Resource, duckdb.DuckDBPyRelation, Field, str, TemporalCoverage]]:
    coverage = ctx.manifest.temporal_coverage
    if coverage is None:
        return
    for resource, _, relation, column, value in _columns(ctx):
        if column.type in DATE_TYPES:
            yield resource, relation, column, value, coverage


@rule("values.dates-outside-coverage", question="trust", scope="table", severity="warning")
def dates_outside_coverage(ctx: Context) -> Outcome:
    problems: list[Problem] = []
    checks = 0
    for resource, relation, column, value, coverage in _dated_columns(ctx):
        checks += 1
        end = coverage.end if isinstance(coverage.end, date) else None
        if column.type == "year":
            year = _year(column, value)
            outside = f"{year} < {coverage.start.year}"
            if end is not None:
                outside += f" OR {year} > {end.year}"
        else:
            day = f"CAST(({_typed(column, value)}) AS DATE)"
            outside = f"{day} < DATE '{coverage.start.isoformat()}'"
            if end is not None:
                outside += f" OR {day} > DATE '{end.isoformat()}'"
        rows, values, count = _evidence(relation, value, outside)
        if count:
            span = f"{coverage.start.isoformat()} to {end.isoformat() if end else 'now'}"
            problems.append(
                Problem(
                    f"Column {column.name} has {_plural(count, 'date')} outside the package's "
                    f"temporal coverage ({span}).",
                    resource=resource.name,
                    field=column.name,
                    rows=rows,
                    values=values,
                    count=count,
                    fix="Correct the dates, or widen archive:temporalCoverage.",
                )
            )
    return Outcome(problems, checks)


@rule("values.coverage-gap", question="trust", scope="table", severity="note")
def coverage_gap(ctx: Context) -> Outcome:
    problems: list[Problem] = []
    checks = 0
    for resource, relation, column, value, coverage in _dated_columns(ctx):
        checks += 1
        present = {
            int(r[0])
            for r in select(relation, f"SELECT DISTINCT {_year(column, value)} AS y FROM t")
            if r[0] is not None
        }
        start = coverage.start
        first = start.year if (start.month, start.day) == (1, 1) else start.year + 1
        if isinstance(coverage.end, date):
            end = coverage.end
            last = end.year if (end.month, end.day) == (12, 31) else end.year - 1
        elif present:
            last = max(present)
        else:
            continue
        missing = [y for y in range(first, last + 1) if y not in present]
        if missing:
            years = ", ".join(str(y) for y in missing)
            problems.append(
                Problem(
                    f"Column {column.name} has no rows in {years}, inside the temporal coverage.",
                    resource=resource.name,
                    field=column.name,
                    values=missing,
                    fix="Say in the description or methods why those years have no data.",
                )
            )
    return Outcome(problems, checks)


def _in_lon_box(x: str, box: tuple[float, float, float, float]) -> str:
    west, _, east, _ = box
    if west <= east:
        return f"({x} BETWEEN {west} AND {east})"
    return f"({x} >= {west} OR {x} <= {east})"  # the box crosses the antimeridian


def _coordinate_sql(lat: str, lon: str, coverage: SpatialCoverage | None) -> tuple[str, str, str]:
    """SQL for a bad latitude, a bad longitude and a row that looks swapped."""
    lat_bad = f"abs({lat}) > 90"
    lon_bad = f"abs({lon}) > 180"
    fits_swapped = f"abs({lon}) <= 90 AND abs({lat}) <= 180"
    if coverage is None:
        swapped_into = f"abs({lat}) > 90"
    else:
        box = coverage.bbox
        _, south, _, north = box
        lat_bad += f" OR NOT ({lat} BETWEEN {south} AND {north})"
        lon_bad += f" OR NOT {_in_lon_box(lon, box)}"
        swapped_into = f"({lon} BETWEEN {south} AND {north}) AND {_in_lon_box(lat, box)}"
    swapped = f"coalesce(({lat_bad} OR {lon_bad}) AND {fits_swapped} AND {swapped_into}, false)"
    return f"coalesce({lat_bad}, false)", f"coalesce({lon_bad}, false)", swapped


def _coordinate_columns(schema: TableSchema) -> Iterator[tuple[Field, str, str, Field | None]]:
    """Each coordinate target: its column, its latitude and longitude as SQL, and the
    longitude column paired with a latitude column."""
    by_name = {f.name.lower(): f for f in schema.fields}
    lat = next((by_name[n] for n in by_name if n in LATITUDE_NAMES), None)
    lon = next((by_name[n] for n in by_name if n in LONGITUDE_NAMES), None)
    if lat is not None:
        lon_sql = f"TRY_CAST({quote_identifier(lon.name)} AS DOUBLE)" if lon else "NULL"
        yield lat, f"TRY_CAST({quote_identifier(lat.name)} AS DOUBLE)", lon_sql, lon
    if lon is not None:
        lat_sql = f"TRY_CAST({quote_identifier(lat.name)} AS DOUBLE)" if lat else "NULL"
        yield lon, lat_sql, f"TRY_CAST({quote_identifier(lon.name)} AS DOUBLE)", None
    for column in schema.fields:
        if column.type == "geopoint" and (column.format or "default") in ("default", "array"):
            bare = f"regexp_replace({quote_identifier(column.name)}, '[\\[\\]\\s]', '', 'g')"
            lon_sql = f"TRY_CAST(split_part({bare}, ',', 1) AS DOUBLE)"
            lat_sql = f"TRY_CAST(split_part({bare}, ',', 2) AS DOUBLE)"
            yield column, lat_sql, lon_sql, None


@rule("values.coordinates-out-of-range", question="trust", scope="table", severity="warning")
def coordinates_out_of_range(ctx: Context) -> Outcome:
    """Swapped rows are reported once, on the latitude column, and left out of the longitude's."""
    problems: list[Problem] = []
    checks = 0
    coverage = ctx.manifest.spatial_coverage
    for resource, schema, relation in ctx.tables():
        for column, lat, lon, paired in _coordinate_columns(schema):
            checks += 1
            lat_bad, lon_bad, swapped = _coordinate_sql(lat, lon, coverage)
            name = column.name.lower()
            if name in LATITUDE_NAMES:
                where = f"{lat_bad} OR {swapped}"
            elif name in LONGITUDE_NAMES:
                where = f"{lon_bad} AND NOT {swapped}"
            else:
                where = f"{lat_bad} OR {lon_bad}"
            value = quote_identifier(column.name)
            rows, values, count = _evidence(relation, value, where)
            if not count:
                continue
            bounds = "the coverage box" if coverage else "range"
            message = f"Column {column.name} has {_plural(count, 'coordinate')} out of {bounds}"
            if name not in LONGITUDE_NAMES:
                flipped, _, _ = _evidence(relation, value, swapped)
                if flipped:
                    listed = ", ".join(str(r) for r in flipped)
                    other = f" with {paired.name}" if paired else ""
                    verb = "row" if len(flipped) == 1 else "rows"
                    message += (
                        f"; {verb} {listed} look{'s' if len(flipped) == 1 else ''} swapped{other}"
                    )
            problems.append(
                Problem(
                    message + ".",
                    resource=resource.name,
                    field=column.name,
                    rows=rows,
                    values=values,
                    count=count,
                    fix="Correct the coordinates; swap latitude and longitude where they look "
                    "swapped.",
                )
            )
    return Outcome(problems, checks)


@rule("values.duplicate-key", question="trust", scope="table", severity="warning")
def duplicate_key(ctx: Context) -> Outcome:
    problems: list[Problem] = []
    checks = 0
    for resource, schema, relation in ctx.tables():
        key = schema.primary_key
        names = [key] if isinstance(key, str) else list(key or [])
        if not names:
            continue
        checks += 1
        columns = ", ".join(quote_identifier(n) for n in names)
        present = " AND ".join(f"{quote_identifier(n)} IS NOT NULL" for n in names)
        joined = f"concat_ws(', ', {columns})"
        found = select(
            relation,
            f"SELECT {ROW_SQL}, k, count(*) OVER () FROM ("
            f"SELECT {ROW_SQL}, {joined} AS k, count(*) OVER (PARTITION BY {columns}) AS n "
            f"FROM t WHERE {present}) WHERE n > 1 ORDER BY {ROW_SQL} LIMIT {EVIDENCE_LIMIT}",
        )
        if found:
            label = ", ".join(names)
            count = int(found[0][2])
            problems.append(
                Problem(
                    f"{_plural(count, 'row')} repeat the primary key {label}.",
                    resource=resource.name,
                    field=label,
                    rows=[r[0] for r in found],
                    values=[r[1] for r in found],
                    count=count,
                    fix=f"Make {label} unique in every row.",
                )
            )
    return Outcome(problems, checks)
