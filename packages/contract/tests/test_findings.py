import pytest
from pydantic import ValidationError

from archive_contract.findings import Finding


def test_finding_reads_its_parts() -> None:
    finding = Finding.model_validate(
        {
            "ruleId": "columns.description-missing",
            "severity": "warning",
            "message": "Column depth_cm has no description.",
            "target": {"resource": "logger", "field": "depth_cm"},
            "evidence": {"values": ["depth_cm"]},
            "suggestedFix": "Describe what depth_cm measures.",
        }
    )

    assert finding.rule_id == "columns.description-missing"
    assert finding.target is not None and finding.target.field == "depth_cm"
    assert finding.suggested_fix == "Describe what depth_cm measures."


@pytest.mark.parametrize("severity", ["error", "warning", "note"])
def test_severity_takes_three_levels(severity: str) -> None:
    raw = {"ruleId": "r", "severity": severity, "message": "m"}

    assert Finding.model_validate(raw).severity == severity


def test_other_severities_are_refused() -> None:
    with pytest.raises(ValidationError):
        Finding.model_validate({"ruleId": "r", "severity": "info", "message": "m"})


def test_suggested_fix_is_optional_and_left_out_when_unset() -> None:
    dumped = Finding(rule_id="r", severity="note", message="m").dump()

    assert dumped == {"ruleId": "r", "severity": "note", "message": "m"}
