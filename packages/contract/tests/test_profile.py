import pytest
from pydantic import ValidationError

from archive_contract.manifest import CORE_FIELDS
from archive_contract.profile import Profile, available_profiles, load_profile


def test_core_and_ecology_profiles_ship_with_the_contract() -> None:
    assert available_profiles() == ["core", "ecology"]


def test_core_profile_holds_only_the_core_fields() -> None:
    core = load_profile("core")

    assert core.name == "core"
    assert core.required == list(CORE_FIELDS)


def test_ecology_profile_promotes_coverage_and_methods_and_switches_on_no_rules() -> None:
    ecology = load_profile("ecology")

    assert ecology.required == [
        "archive:temporalCoverage",
        "archive:spatialCoverage",
        "archive:methods",
    ]
    assert ecology.rules == []


def test_unknown_profile_is_refused() -> None:
    with pytest.raises(ValueError, match="no profile named"):
        load_profile("astronomy")


def test_profile_cannot_require_a_field_the_manifest_lacks() -> None:
    with pytest.raises(ValidationError, match="unknown field"):
        Profile.model_validate({"name": "x", "required": ["colour"]})
