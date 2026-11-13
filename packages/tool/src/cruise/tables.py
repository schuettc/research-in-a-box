"""Reading a table resource with DuckDB, the one place a file format appears.

Every value is read as text and the schema's missing values read as null, so a value that
doesn't fit its declared type becomes a finding in a rule's SQL rather than a failed read.
Parquet later is one more branch here.
"""

from pathlib import Path
from typing import Any

import duckdb

from archive_contract.resources import Resource
from archive_contract.validate import readable_member

ROW = "cruise:row"
"""The column holding each row's 1-based number among the data rows."""

DEFAULT_MISSING_VALUES = [""]
"""Table Schema's missing values when a schema states none."""


class UnreadableTable(ValueError):
    """A table resource this reader can't open."""


def connect() -> duckdb.DuckDBPyConnection:
    """An in-memory DuckDB that never installs or loads an extension, so never fetches one."""
    return duckdb.connect(
        ":memory:",
        config={"autoinstall_known_extensions": False, "autoload_known_extensions": False},
    )


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def select(relation: duckdb.DuckDBPyRelation, sql: str) -> list[tuple[Any, ...]]:
    """The rows of `sql` run over the relation, which it names `t`."""
    result = relation.query("t", sql)
    return [] if result is None else result.fetchall()


def _literal_list(values: list[str]) -> str:
    return "[" + ", ".join(quote_literal(v) for v in values) + "]"


def read_table(
    root: Path, resource: Resource, connection: duckdb.DuckDBPyConnection | None = None
) -> duckdb.DuckDBPyRelation:
    """A relation over the resource's file, every column as text, with its row number in `ROW`.

    The columns take the schema's field names in order. Only CSV is read.
    """
    if (resource.format or "").lower() != "csv":
        raise UnreadableTable(f"{resource.name} is {resource.format!r}; only csv tables are read")
    if not isinstance(resource.path, str) or not readable_member(root, resource.path):
        raise UnreadableTable(f"{resource.name} has no single file inside the package to read")
    schema = resource.table_schema
    if schema is None or not schema.fields:
        raise UnreadableTable(f"{resource.name} has no schema to read it by")
    dialect = resource.dialect or {}
    delimiter = str(dialect.get("delimiter", ","))
    quote = str(dialect.get("quoteChar", '"'))
    header = bool(dialect.get("header", True))
    missing = [str(v) for v in (schema.missing_values or DEFAULT_MISSING_VALUES)]
    columns = "{" + ", ".join(f"{quote_literal(f.name)}: 'VARCHAR'" for f in schema.fields) + "}"
    path = (root / resource.path).as_posix()
    sql = (
        f"SELECT row_number() OVER () AS {quote_identifier(ROW)}, * FROM read_csv("
        f"{quote_literal(path)}, auto_detect = false, header = {str(header).lower()}, "
        f"columns = {columns}, delim = {quote_literal(delimiter)}, "
        f"quote = {quote_literal(quote)}, escape = {quote_literal(quote)}, "
        f"nullstr = {_literal_list(missing)}, encoding = 'utf-8')"
    )
    con = connection if connection is not None else connect()
    try:
        relation = con.sql(sql)
        relation.aggregate("count(*)").fetchall()  # read it once, so a bad file fails here
        return relation
    except duckdb.Error as exc:
        raise UnreadableTable(f"{resource.name} can't be read: {exc}") from exc
