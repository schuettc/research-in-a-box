import pytest
from pydantic import ValidationError

from archive_contract.usage import ORGANISATIONS, PURPOSES, UsageAnswers


def test_every_answer_is_optional() -> None:
    assert UsageAnswers.model_validate({}).model_dump(exclude_none=True) == {}


def test_the_six_values_of_each_question() -> None:
    assert ORGANISATIONS == (
        "university",
        "government",
        "nonprofit",
        "company",
        "individual",
        "other",
    )
    assert PURPOSES == (
        "research",
        "teaching",
        "policy-or-management",
        "commercial",
        "personal",
        "other",
    )
    answers = UsageAnswers.model_validate(
        {"organisation": "nonprofit", "purpose": "policy-or-management", "note": "Trends"}
    )
    assert answers.organisation == "nonprofit"
    assert answers.purpose == "policy-or-management"


@pytest.mark.parametrize(
    "raw",
    [
        {"organisation": "school"},
        {"purpose": "fun"},
        {"note": "x" * 501},
        {"email": "a@example.org"},
    ],
)
def test_other_answers_are_refused(raw: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        UsageAnswers.model_validate(raw)


def test_a_note_of_500_characters_is_kept() -> None:
    assert UsageAnswers.model_validate({"note": "x" * 500}).note == "x" * 500
