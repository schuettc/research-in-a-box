import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from archive_contract.manifest import CORE_FIELDS, Manifest
from archive_contract.profile import Profile, load_profile
from cruise.rules import REGISTRY, Context, Outcome, Problem, Registry, required_fields

LONG_DESCRIPTION = "Hourly water temperature at three invented stream sites, 2024 onward."


def complete() -> dict[str, Any]:
    return {
        "title": "Stream temperature",
        "description": LONG_DESCRIPTION,
        "contributors": [{"title": "A. Researcher", "roles": ["creator"]}],
        "licenses": [{"name": "CC-BY-4.0"}],
        "resources": [{"name": "notes", "path": "notes.md", "description": "Notes"}],
    }


def context(raw: dict[str, Any], required: tuple[str, ...] = ()) -> Context:
    return Context.for_package(Path("."), Manifest.model_validate(raw), required=required)


def test_core_missing_gives_one_finding_per_missing_core_field() -> None:
    result = REGISTRY.get("package.core-missing").run(context({}))

    assert [f.evidence.values for f in result.findings if f.evidence] == [
        [field] for field in CORE_FIELDS
    ]
    assert {f.severity for f in result.findings} == {"error"}
    assert result.checks == 5


def test_complete_package_passes_all_five_core_checks() -> None:
    result = REGISTRY.get("package.core-missing").run(context(complete()))

    assert result.findings == []
    assert result.checks == 5


def test_profile_field_missing_gives_one_finding_per_required_field_absent() -> None:
    raw = complete() | {"archive:temporalCoverage": {"start": "2024-06-01", "ongoing": True}}
    required = ("archive:temporalCoverage", "archive:methods")

    result = REGISTRY.get("package.profile-field-missing").run(context(raw, required))

    assert [f.evidence.values for f in result.findings if f.evidence] == [["archive:methods"]]
    assert result.findings[0].severity == "error"
    assert result.checks == 2


def test_required_fields_join_profiles_and_config_without_the_core_fields() -> None:
    profiles = [load_profile("core"), load_profile("ecology")]

    assert required_fields(profiles, ["keywords", "archive:methods"]) == (
        "archive:temporalCoverage",
        "archive:spatialCoverage",
        "archive:methods",
        "keywords",
    )


def test_core_rules_always_run_and_a_profile_switches_on_extra_rules() -> None:
    registry = Registry()

    @registry.rule("core.one", question="find", scope="package", severity="note")
    def core_one(ctx: Context) -> Outcome:
        return Outcome([], 1)

    @registry.rule("extra.two", question="find", scope="package", severity="note", core=False)
    def extra_two(ctx: Context) -> Outcome:
        return Outcome([Problem("x")], 1)

    assert [r.id for r in registry.select([])] == ["core.one"]
    switched = Profile(name="p", rules=["extra.two"])
    assert [r.id for r in registry.select([switched])] == ["core.one", "extra.two"]


def test_a_profile_naming_an_unknown_rule_is_an_error() -> None:
    with pytest.raises(ValueError, match="unknown rule"):
        REGISTRY.select([Profile(name="p", rules=["nope.never"])])


def test_rules_import_without_the_command_line() -> None:
    code = "import sys, cruise.rules; print('cruise.cli' in sys.modules, 'argparse' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)

    assert out.stdout.split() == ["False", "False"]
