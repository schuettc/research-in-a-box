from typing import Any

import pytest
from pydantic import ValidationError

import archive_contract
from archive_contract.review import (
    ReviewPolicy,
    SubmissionFacts,
    match,
    reminder_schedule,
)
from archive_contract.schema import build


def facts(**overrides: Any) -> SubmissionFacts:
    values: dict[str, Any] = {
        "submitter": "user-1",
        "submitter_is_curator": False,
        "kind": "new-dataset",
        "access": "open",
        "themes": ("soils",),
    }
    return SubmissionFacts(**{**values, **overrides})


def policy(*rules: dict[str, Any], **fields: Any) -> ReviewPolicy:
    return ReviewPolicy.model_validate({"rules": list(rules), **fields})


def test_empty_policy_takes_the_defaults() -> None:
    empty = ReviewPolicy.model_validate({})

    assert empty.required is True
    assert empty.rules == []
    assert empty.reviewers == {}
    assert empty.reminders == []
    assert empty.stale_days == 14
    assert match(empty, facts()) == ("one", None)
    assert reminder_schedule(empty) == []


def test_no_match_skips_when_review_is_not_required() -> None:
    assert match(policy(required=False), facts()) == ("skip", None)


def test_no_match_asks_one_curator_when_review_is_required() -> None:
    unmatched = policy({"kind": "new-version", "outcome": "skip"}, required=True)

    assert match(unmatched, facts()) == ("one", None)


@pytest.mark.parametrize(
    ("rule", "matching", "other"),
    [
        ({"submitters": ["user-1"]}, facts(), facts(submitter="user-2")),
        (
            {"submitters": ["curators"]},
            facts(submitter_is_curator=True),
            facts(submitter_is_curator=False),
        ),
        ({"kind": "new-version"}, facts(kind="new-version"), facts(kind="new-dataset")),
        (
            {"access": ["restricted", "by-request"]},
            facts(access="by-request"),
            facts(access="open"),
        ),
        (
            {"themes": ["marine", "soils"]},
            facts(themes=("hydrology", "soils")),
            facts(themes=("hydrology",)),
        ),
    ],
)
def test_each_matcher_alone(
    rule: dict[str, Any], matching: SubmissionFacts, other: SubmissionFacts
) -> None:
    one_rule = policy({**rule, "outcome": "two"})

    assert match(one_rule, matching) == ("two", 0)
    assert match(one_rule, other) == ("one", None)


def test_matchers_combine_so_every_one_must_hold() -> None:
    combined = policy(
        {"submitters": ["curators"], "kind": "new-version", "access": ["open"], "outcome": "skip"}
    )
    curator_version = facts(submitter_is_curator=True, kind="new-version")

    assert match(combined, curator_version) == ("skip", 0)
    assert match(combined, facts(submitter_is_curator=True)) == ("one", None)
    assert match(combined, facts(kind="new-version")) == ("one", None)
    assert match(
        combined, facts(submitter_is_curator=True, kind="new-version", access="restricted")
    ) == (
        "one",
        None,
    )


def test_a_rule_with_no_matchers_matches_everything() -> None:
    assert match(policy({"outcome": "skip"}), facts()) == ("skip", 0)


def test_the_first_matching_rule_wins() -> None:
    ordered = policy(
        {"kind": "new-version", "outcome": "skip"},
        {"access": ["restricted"], "outcome": "two"},
        {"access": ["open"], "outcome": "skip"},
    )

    assert match(ordered, facts(access="restricted")) == ("two", 1)
    assert match(ordered, facts(access="restricted", kind="new-version")) == ("skip", 0)


def test_rules_match_even_when_review_is_not_required() -> None:
    assert match(policy({"themes": ["soils"], "outcome": "two"}, required=False), facts()) == (
        "two",
        0,
    )


def test_reminder_schedule_is_sorted_and_unique() -> None:
    assert reminder_schedule(policy(reminders=[7, 3, 7, 10], staleDays=14)) == [3, 7, 10]


@pytest.mark.parametrize("reminders", [[14], [3, 20]])
def test_reminders_on_or_after_stale_days_are_refused(reminders: list[int]) -> None:
    with pytest.raises(ValidationError):
        policy(reminders=reminders, staleDays=14)


@pytest.mark.parametrize("reminders", [[0], [-2], [1.5]])
def test_reminders_are_positive_whole_days(reminders: list[Any]) -> None:
    with pytest.raises(ValidationError):
        policy(reminders=reminders)


def test_unknown_outcomes_and_kinds_are_refused() -> None:
    with pytest.raises(ValidationError):
        policy({"outcome": "three"})
    with pytest.raises(ValidationError):
        policy({"kind": "new-project", "outcome": "one"})


def test_dump_uses_camel_case_names() -> None:
    dumped = policy({"themes": ["soils"], "outcome": "two"}, reviewers={"soils": ["c-1"]}).dump()

    assert dumped["staleDays"] == 14
    assert dumped["rules"] == [{"themes": ["soils"], "outcome": "two"}]
    assert dumped["reviewers"] == {"soils": ["c-1"]}


def test_the_package_exports_the_policy() -> None:
    assert archive_contract.ReviewPolicy is ReviewPolicy
    assert archive_contract.match is match


def test_json_schema_holds_the_review_policy() -> None:
    defs = build()["$defs"]

    assert "ReviewPolicy" in defs
    assert "staleDays" in defs["ReviewPolicy"]["properties"]
    assert "Rule" in defs
