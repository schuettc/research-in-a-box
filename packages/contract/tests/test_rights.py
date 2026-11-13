import pytest
from pydantic import ValidationError

from archive_contract.rights import License, RightsStatus, rights_stated


@pytest.mark.parametrize("status", ["third-party", "all-rights-reserved"])
def test_status_needs_a_statement(status: str) -> None:
    with pytest.raises(ValidationError, match="statement"):
        RightsStatus.model_validate({"status": status})
    with pytest.raises(ValidationError, match="statement"):
        RightsStatus.model_validate({"status": status, "statement": "  "})


@pytest.mark.parametrize("status", ["third-party", "all-rights-reserved"])
def test_status_with_a_statement_is_accepted(status: str) -> None:
    rights = RightsStatus.model_validate({"status": status, "statement": "Terms set by the agency"})

    assert rights.statement == "Terms set by the agency"


@pytest.mark.parametrize("status", ["public-domain", "undetermined"])
def test_status_without_a_statement_is_accepted(status: str) -> None:
    assert RightsStatus.model_validate({"status": status}).status == status


def test_unknown_status_is_refused() -> None:
    with pytest.raises(ValidationError):
        RightsStatus.model_validate({"status": "open"})


def test_license_needs_a_name_or_a_path() -> None:
    assert License.model_validate({"name": "CC-BY-4.0"}).name == "CC-BY-4.0"
    assert License.model_validate({"path": "https://example.org/terms"}).path
    with pytest.raises(ValidationError, match="name or a path"):
        License.model_validate({"title": "Some license"})


def test_license_dump_drops_unset_properties() -> None:
    assert License.model_validate({"name": "CC-BY-4.0"}).dump() == {"name": "CC-BY-4.0"}


def test_rights_are_stated_by_a_license_or_a_settled_status() -> None:
    cc_by = [License(name="CC-BY-4.0")]
    assert rights_stated(cc_by, None)
    assert rights_stated([], RightsStatus(status="public-domain"))
    assert not rights_stated([], None)
    assert not rights_stated([], RightsStatus(status="undetermined"))
