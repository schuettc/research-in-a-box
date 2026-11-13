"""Can I understand each column? Every table column and every vector attribute."""

import re

from archive_contract.fields import Field
from cruise.rules.registry import EVIDENCE_LIMIT, Context, Outcome, Problem, rule
from cruise.tables import quote_identifier, select

MEASUREMENT_TYPES = frozenset({"number", "integer"})
MEASUREMENT_SCALES = frozenset({"interval", "ratio", None})
"""The scales on which a number needs a unit; no scale stated counts as a measurement."""


def _bare(text: str) -> str:
    """The text lower-cased with everything but letters and digits removed."""
    return re.sub(r"[\W_]+", "", text.lower())


def _described(column: Field) -> bool:
    return bool((column.description or "").strip())


@rule("field.description-missing", question="understand", scope="field", severity="warning")
def description_missing(ctx: Context) -> Outcome:
    problems: list[Problem] = []
    checks = 0
    for resource, column in ctx.columns():
        checks += 1
        if not _described(column):
            problems.append(
                Problem(
                    f"Column {column.name} has no description.",
                    resource=resource.name,
                    field=column.name,
                    fix=f"Describe what {column.name} holds and how it was measured.",
                )
            )
    return Outcome(problems, checks)


@rule("field.description-repeats-name", question="understand", scope="field", severity="warning")
def description_repeats_name(ctx: Context) -> Outcome:
    problems: list[Problem] = []
    checks = 0
    for resource, column in ctx.columns():
        if not _described(column):
            continue
        checks += 1
        names = {_bare(column.name)} | (
            {_bare(column.source_name)} if column.source_name else set()
        )
        if _bare(column.description or "") in names:
            problems.append(
                Problem(
                    f"Column {column.name}'s description only repeats its name.",
                    resource=resource.name,
                    field=column.name,
                    values=[column.description],
                    fix=f"Say what {column.name} holds, not just its name.",
                )
            )
    return Outcome(problems, checks)


@rule("field.unit-missing", question="understand", scope="field", severity="warning")
def unit_missing(ctx: Context) -> Outcome:
    problems: list[Problem] = []
    checks = 0
    for resource, column in ctx.columns():
        if column.type not in MEASUREMENT_TYPES or column.measurement_scale not in (
            MEASUREMENT_SCALES
        ):
            continue
        checks += 1
        if not (column.unit or "").strip():
            problems.append(
                Problem(
                    f"Column {column.name} is a measurement with no unit.",
                    resource=resource.name,
                    field=column.name,
                    fix=f"Set archive:unit on {column.name}, or mark it nominal or ordinal.",
                )
            )
    return Outcome(problems, checks)


@rule("field.codes-undocumented", question="understand", scope="field", severity="warning")
def codes_undocumented(ctx: Context) -> Outcome:
    problems: list[Problem] = []
    checks = 0
    for resource, column in ctx.columns():
        checks += 1
        if column.code_list != "undocumented":
            continue
        values: list[object] | None = None
        relation = ctx.read(resource)
        if relation is not None:
            name = quote_identifier(column.name)
            rows = select(
                relation,
                f"SELECT DISTINCT {name} FROM t WHERE {name} IS NOT NULL "
                f"ORDER BY {name} LIMIT {EVIDENCE_LIMIT}",
            )
            values = [row[0] for row in rows]
        problems.append(
            Problem(
                f"Column {column.name} holds codes with no code list.",
                resource=resource.name,
                field=column.name,
                values=values,
                fix=f"Add a code list for {column.name} and link it with a foreign key.",
            )
        )
    return Outcome(problems, checks)
