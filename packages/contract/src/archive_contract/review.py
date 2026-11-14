"""The review policy: whether a submission is reviewed, by how many curators, and when."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Self

from pydantic import Field as PydanticField
from pydantic import PositiveInt, model_validator

from archive_contract._base import ArchiveModel
from archive_contract.manifest import AccessLevel

Outcome = Literal["skip", "one", "two"]
"""How many curators must approve: none, one, or two different curators."""

SubmissionKind = Literal["new-dataset", "new-version"]

CURATORS = "curators"
"""Written in a rule's `submitters`, it matches any submitter in the curator group."""


@dataclass(frozen=True)
class SubmissionFacts:
    """What a rule can match about a submission when its round enters review."""

    submitter: str
    submitter_is_curator: bool
    kind: SubmissionKind
    access: AccessLevel
    themes: Sequence[str] = ()


class Rule(ArchiveModel):
    """One policy rule. Every matcher it sets must hold; a rule that sets none matches all.

    `submitters` lists user ids, or `curators` for the curator group; `themes` matches when
    the submission has any of them.
    """

    submitters: list[str] | None = None
    kind: SubmissionKind | None = None
    access: list[AccessLevel] | None = None
    themes: list[str] | None = None
    outcome: Outcome

    def matches(self, facts: SubmissionFacts) -> bool:
        if self.submitters is not None and not (
            facts.submitter in self.submitters
            or (CURATORS in self.submitters and facts.submitter_is_curator)
        ):
            return False
        if self.kind is not None and facts.kind != self.kind:
            return False
        if self.access is not None and facts.access not in self.access:
            return False
        return self.themes is None or bool(set(self.themes) & set(facts.themes))


class ReviewPolicy(ArchiveModel):
    """The admin's review policy, the Settings item `review-policy`.

    `rules` are tried in order and the first match wins; with no match the outcome is `one`
    when `required` is true and `skip` when it is false. `reviewers` maps a theme to the
    curators asked first. `reminders` are the days after entering review on which to remind,
    each before `staleDays`, when a waiting review is marked stale.
    """

    required: bool = True
    rules: list[Rule] = PydanticField(default_factory=list)
    reviewers: dict[str, list[str]] = PydanticField(default_factory=dict)
    reminders: list[PositiveInt] = PydanticField(default_factory=list)
    stale_days: PositiveInt = PydanticField(default=14, alias="staleDays")

    @model_validator(mode="after")
    def _reminders_before_stale(self) -> Self:
        late = [day for day in self.reminders if day >= self.stale_days]
        if late:
            raise ValueError(f"reminders must come before staleDays ({self.stale_days}): {late}")
        return self


def match(policy: ReviewPolicy, facts: SubmissionFacts) -> tuple[Outcome, int | None]:
    """The outcome for a submission, and the index of the rule that gave it (None for the
    default)."""
    for index, rule in enumerate(policy.rules):
        if rule.matches(facts):
            return rule.outcome, index
    return ("one" if policy.required else "skip"), None


def reminder_schedule(policy: ReviewPolicy) -> list[int]:
    """The days after entering review on which to remind, sorted, each once."""
    return sorted(set(policy.reminders))
