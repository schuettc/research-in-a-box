"""The rule registry: each rule's id, question, scope and severity, and what a rule receives.

A rule is a function given a `Context` that returns an `Outcome`: the problems it found and
how many checks it applied. A check is the rule applied to one target, and a rule reports at
most one problem per check, so the checks passed are the checks applied minus the problems.
The registry turns each problem into a contract `Finding` with the rule's id and severity.
"""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Literal

import duckdb

from archive_contract.fields import Field, TableSchema
from archive_contract.findings import Evidence, Finding, Severity, Target
from archive_contract.manifest import CORE_FIELDS, Manifest
from archive_contract.profile import Profile
from archive_contract.resources import Resource
from cruise.tables import UnreadableTable, connect, read_table

Question = Literal["find", "understand", "trust"]
QUESTIONS: tuple[Question, ...] = ("find", "understand", "trust")
Scope = Literal["package", "field", "table"]

TableReader = Callable[[Resource], duckdb.DuckDBPyRelation]

EVIDENCE_LIMIT = 20
"""The most rows or values a finding lists."""


@dataclass(frozen=True)
class Context:
    """What every rule receives: the package, the fields it must have and a table reader.

    `skip` names the resources whose files failed the structure check: no rule reads them.
    """

    root: Path
    manifest: Manifest
    required: tuple[str, ...]
    reader: TableReader
    skip: frozenset[str] = frozenset()

    @classmethod
    def for_package(
        cls,
        root: Path,
        manifest: Manifest,
        *,
        required: Sequence[str] = (),
        skip: frozenset[str] = frozenset(),
    ) -> "Context":
        reader = partial(read_table, root, connection=connect())
        return cls(root, manifest, tuple(required), reader, skip)

    def columns(self) -> Iterator[tuple[Resource, Field]]:
        """Every column of every table and every attribute of every vector resource."""
        for resource in self.manifest.resources:
            for schema in (resource.table_schema, resource.attributes):
                if schema is not None:
                    for column in schema.fields:
                        yield resource, column

    def read(self, resource: Resource) -> duckdb.DuckDBPyRelation | None:
        """The resource's rows, or None when it is skipped, not a table or can't be read."""
        if resource.name in self.skip or resource.table_schema is None:
            return None
        try:
            return self.reader(resource)
        except UnreadableTable:
            return None

    def tables(self) -> Iterator[tuple[Resource, TableSchema, duckdb.DuckDBPyRelation]]:
        """Every table resource that can be read, with its schema and rows."""
        for resource in self.manifest.resources:
            if resource.kind != "table" or resource.table_schema is None:
                continue
            relation = self.read(resource)
            if relation is not None:
                yield resource, resource.table_schema, relation


@dataclass(frozen=True)
class Problem:
    """One thing a rule found on one target, before it becomes a `Finding`."""

    message: str
    resource: str | None = None
    field: str | None = None
    path: str | None = None
    rows: list[int] | None = None
    values: list[Any] | None = None
    count: int | None = None
    fix: str | None = None


@dataclass(frozen=True)
class Outcome:
    problems: list[Problem]
    checks: int


@dataclass(frozen=True)
class RuleResult:
    rule: "Rule"
    findings: list[Finding]
    checks: int

    @property
    def passed(self) -> int:
        return self.checks - len(self.findings)


RuleFunction = Callable[[Context], Outcome]


def _finding(rule: "Rule", problem: Problem) -> Finding:
    target = None
    if problem.resource or problem.field or problem.path:
        target = Target(resource=problem.resource, field=problem.field, path=problem.path)
    evidence = None
    if problem.rows is not None or problem.values is not None or problem.count is not None:
        evidence = Evidence(rows=problem.rows, values=problem.values, count=problem.count)
    return Finding(
        rule_id=rule.id,
        severity=rule.severity,
        message=problem.message,
        target=target,
        evidence=evidence,
        suggested_fix=problem.fix,
    )


@dataclass(frozen=True)
class Rule:
    id: str
    question: Question
    scope: Scope
    severity: Severity
    core: bool
    check: RuleFunction

    def run(self, ctx: Context) -> RuleResult:
        outcome = self.check(ctx)
        if len(outcome.problems) > outcome.checks:
            raise RuntimeError(f"{self.id} found more problems than it applied checks")
        return RuleResult(self, [_finding(self, p) for p in outcome.problems], outcome.checks)


class Registry:
    """The rules, by question and then in the order they were registered."""

    def __init__(self) -> None:
        self._rules: dict[str, Rule] = {}

    def rule(
        self,
        rule_id: str,
        *,
        question: Question,
        scope: Scope,
        severity: Severity,
        core: bool = True,
    ) -> Callable[[RuleFunction], RuleFunction]:
        def register(check: RuleFunction) -> RuleFunction:
            if rule_id in self._rules:
                raise ValueError(f"rule {rule_id} is registered twice")
            self._rules[rule_id] = Rule(rule_id, question, scope, severity, core, check)
            return check

        return register

    def get(self, rule_id: str) -> Rule:
        return self._rules[rule_id]

    def __iter__(self) -> Iterator[Rule]:
        """The rules by question (find, understand, trust), each in registration order."""
        return iter(sorted(self._rules.values(), key=lambda r: QUESTIONS.index(r.question)))

    def select(self, profiles: Sequence[Profile]) -> list[Rule]:
        """The core rules, and the extra rules the profiles switch on by id."""
        switched = {rule_id for profile in profiles for rule_id in profile.rules}
        unknown = sorted(switched - set(self._rules))
        if unknown:
            raise ValueError(f"profile names unknown rule(s) {unknown}")
        return [r for r in self if r.core or r.id in switched]


REGISTRY = Registry()
rule = REGISTRY.rule


def required_fields(profiles: Sequence[Profile], extra: Sequence[str] = ()) -> tuple[str, ...]:
    """The fields the profiles and the archive config require, less the core fields."""
    wanted = [f for profile in profiles for f in profile.required] + list(extra)
    return tuple(dict.fromkeys(f for f in wanted if f not in CORE_FIELDS))
