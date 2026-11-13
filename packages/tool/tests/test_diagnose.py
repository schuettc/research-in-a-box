import re
import shutil
import socket
from pathlib import Path
from typing import Any

import pytest

from archive_contract.findings import Finding
from archive_contract.manifest import CheckCount, Manifest
from archive_contract.profile import load_profile
from archive_contract.resources import Resource
from cruise.diagnose import diagnose
from cruise.rules import Context, Outcome, Problem, Registry
from cruise.score import completeness
from cruise.tables import UnreadableTable, read_table, select

SAMPLE = Path(__file__).parents[3] / "examples" / "sample-package"


MESSY = Path(__file__).parent / "fixtures" / "messy-package"


def targets(findings: list[Finding]) -> list[tuple[str, str]]:
    """Each finding as its rule id and target, written `resource.field` or `package`."""
    named = []
    for f in findings:
        target = f.target
        where = f"{target.resource}.{target.field}" if target and target.field else "package"
        named.append((f.rule_id, where))
    return sorted(named)


def planted(gaps: Path) -> list[tuple[str, str]]:
    """The rule and target of each row of a GAPS.md table, once each."""
    rows = re.findall(r"^\|[^|]*\| `([^`]+)` +\| `([^`]+)` +\|$", gaps.read_text(), re.M)
    return sorted(set(rows))


def test_sample_package_gives_exactly_its_four_planted_findings() -> None:
    result = diagnose(SAMPLE)

    assert targets(result.findings) == [
        ("field.codes-undocumented", "logger.qc_flag"),
        ("field.description-missing", "logger.battery_v"),
        ("field.description-repeats-name", "logger.depth_cm"),
        ("values.constant", "logger.logger_model"),
    ]
    assert result.quality is not None and result.quality.errors == 0
    assert result.quality.score is not None


def test_messy_package_gives_exactly_the_findings_its_gaps_list_names() -> None:
    result = diagnose(MESSY, [load_profile("ecology")])

    assert result.structure == []
    assert targets(result.findings) == planted(MESSY / "_build" / "GAPS.md")
    assert result.blocking == 2


def test_diagnose_runs_with_the_network_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", refuse)

    assert diagnose(SAMPLE).quality is not None


def test_diagnose_stops_when_the_manifest_cannot_be_read(tmp_path: Path) -> None:
    (tmp_path / "datapackage.json").write_text("{not json", encoding="utf-8")

    result = diagnose(tmp_path)

    assert [f.rule_id for f in result.findings] == ["structure.manifest-invalid"]
    assert result.quality is None


def test_diagnose_reads_no_table_whose_files_failed_the_structure_check(tmp_path: Path) -> None:
    package = tmp_path / "sample"
    shutil.copytree(SAMPLE, package)
    with (package / "data" / "logger.csv").open("a", encoding="utf-8") as stream:
        stream.write("2024-06-02T00:00:00,S1,9.0,0.20,ok,C,TL-100,3.5,30\n")

    result = diagnose(package)

    assert result.structure
    assert result.findings[: len(result.structure)] == result.structure
    codes = next(f for f in result.findings if f.rule_id == "field.codes-undocumented")
    assert codes.evidence is None
    assert not [f for f in result.findings if f.rule_id == "values.unreadable"]


def test_score_is_the_share_of_checks_passed_rounded_down_per_question() -> None:
    registry = Registry()

    @registry.rule("a.find", question="find", scope="package", severity="error")
    def find(ctx: Context) -> Outcome:
        return Outcome([Problem("missing")], 3)

    @registry.rule("a.trust", question="trust", scope="table", severity="warning")
    def trust(ctx: Context) -> Outcome:
        return Outcome([], 0)

    ctx = Context.for_package(Path("."), Manifest())
    score = completeness([rule.run(ctx) for rule in registry.select([])])

    assert score.percent == 66
    assert score.parts == {
        "find": CheckCount(passed=2, applicable=3),
        "understand": CheckCount(passed=0, applicable=0),
        "trust": CheckCount(passed=0, applicable=0),
    }
    assert score.line() == "66% (find 2 of 3, understand 0 of 0, trust 0 of 0)"


def test_messy_package_tables_are_all_readable() -> None:
    manifest = Manifest.model_validate_json((MESSY / "datapackage.json").read_text())

    for resource in manifest.resources:
        read_table(MESSY, resource)


@pytest.mark.parametrize("name", ["t*.csv", "t?.csv", "t[1].csv", "t{1}.csv"])
def test_table_reader_refuses_glob_characters_in_the_path(tmp_path: Path, name: str) -> None:
    (tmp_path / name).write_text("n\n1\n", encoding="utf-8")
    resource = Resource.model_validate(
        {
            "name": "t",
            "path": name,
            "type": "table",
            "format": "csv",
            "schema": {"fields": [{"name": "n"}]},
        }
    )

    with pytest.raises(UnreadableTable, match="glob"):
        read_table(tmp_path, resource)


def test_table_reader_refuses_formats_other_than_csv() -> None:
    resource = Resource.model_validate(
        {"name": "t", "path": "t.xlsx", "type": "table", "format": "xlsx"}
    )

    with pytest.raises(UnreadableTable, match="xlsx"):
        read_table(Path("."), resource)


def test_table_reader_reads_text_with_declared_missing_values_as_null(tmp_path: Path) -> None:
    (tmp_path / "t.csv").write_text("n\n1\nNA\n007\n", encoding="utf-8")
    resource = Resource.model_validate(
        {
            "name": "t",
            "path": "t.csv",
            "type": "table",
            "format": "csv",
            "schema": {"fields": [{"name": "n", "type": "integer"}], "missingValues": ["NA"]},
        }
    )

    relation = read_table(tmp_path, resource)

    assert select(relation, 'SELECT "n" FROM t') == [("1",), (None,), ("007",)]
