import json
from pathlib import Path

import pytest

from archive_contract.findings import Finding
from archive_contract.manifest import QualityVerdict, ValidationVerdict
from cruise.cli import main

SAMPLE = Path(__file__).parents[3] / "examples" / "sample-package"


def test_version_prints_name_and_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out == "cruise 0.1.0\n"


def test_diagnose_prints_findings_by_question_then_score_and_verdict(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main(["diagnose", str(SAMPLE)])

    out = capsys.readouterr().out
    assert code == 0
    assert "Can I understand each column?" in out
    assert "logger.battery_v" in out
    assert "fix: " in out
    lines = out.rstrip().splitlines()
    assert lines[-2].startswith("Score: ") and "(find 5 of 5, understand " in lines[-2]
    assert lines[-1].startswith("Verdict: publishable, with ")


def test_diagnose_json_round_trips_through_the_contract(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["diagnose", str(SAMPLE), "--json"]) == 0

    data = json.loads(capsys.readouterr().out)
    assert ValidationVerdict.model_validate(data["validation"]).valid
    assert QualityVerdict.model_validate(data["quality"]).errors == 0
    findings = [Finding.model_validate(f) for f in data["findings"]]
    assert [f.dump() for f in findings] == data["findings"]
    assert len(findings) >= 3


def test_diagnose_exits_1_when_a_finding_blocks_publishing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["diagnose", str(tmp_path)])

    assert code == 1
    assert "Verdict: blocks publishing (1)" in capsys.readouterr().out


def test_diagnose_profile_requires_its_fields(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "archive.yaml"
    config.write_text("publisher: Example\nprofiles: [core]\nrequired: [keywords]\n")

    assert main(["diagnose", str(SAMPLE), "--profile", "ecology", "--config", str(config)]) == 0
    assert "(find 9 of 9, " in capsys.readouterr().out


def test_diagnose_refuses_an_unknown_profile(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["diagnose", str(SAMPLE), "--profile", "astronomy"]) == 2
    assert "no profile named" in capsys.readouterr().err
