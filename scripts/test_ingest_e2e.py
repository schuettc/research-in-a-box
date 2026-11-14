import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest
import yaml

from archive_contract import ReviewPolicy, SubmissionFacts, match
from archive_contract.config import ArchiveConfig
from cruise.diagnose import diagnose


def _load() -> ModuleType:
    path = Path(__file__).with_name("ingest_e2e.py")
    spec = importlib.util.spec_from_file_location("ingest_e2e", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["ingest_e2e"] = module
    spec.loader.exec_module(module)
    return module


e2e = _load()
TEST_CONFIG = e2e.ROOT / "examples" / "ingest-test-stage" / "archive.yaml"


def _errors(folder: Path) -> list[str]:
    config = ArchiveConfig.model_validate(yaml.safe_load(TEST_CONFIG.read_text()))
    result = diagnose(folder, config.load_profiles(), config.required)
    return [f.rule_id for f in result.findings if f.severity == "error"]


def test_a_package_copy_leaves_out_the_build_folder_and_lists_every_other_file(
    tmp_path: Path,
) -> None:
    folder = e2e.package_copy(tmp_path, e2e.themed("e2e-two"))

    manifest = json.loads((folder / "datapackage.json").read_text())
    assert manifest["archive:themes"] == ["e2e-two"]
    assert not (folder / "_build").exists()
    listed = {}
    for line in (folder / "checksums.sha256").read_text().splitlines():
        digest, path = line.split("  ", 1)
        listed[path] = digest
    files = {p.relative_to(folder).as_posix(): p for p in folder.rglob("*") if p.is_file()}
    assert set(listed) == set(files) - {"checksums.sha256"}
    for path, digest in listed.items():
        assert hashlib.sha256(files[path].read_bytes()).hexdigest() == digest


def test_the_sample_passes_the_checks_and_a_copy_without_its_description_is_blocked(
    tmp_path: Path,
) -> None:
    assert _errors(e2e.package_copy(tmp_path / "a", e2e.themed("e2e-skip"))) == []
    assert "package.core-missing" in _errors(
        e2e.package_copy(tmp_path / "b", e2e.without("description"))
    )


def test_the_file_list_has_each_path_size_and_sha256(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "a.csv").write_bytes(b"x,y\n")
    (tmp_path / "README.md").write_bytes(b"")

    assert e2e.file_list(tmp_path) == [
        {"path": "README.md", "size": 0, "sha256": hashlib.sha256(b"").hexdigest()},
        {"path": "data/a.csv", "size": 4, "sha256": hashlib.sha256(b"x,y\n").hexdigest()},
    ]


@pytest.mark.parametrize(
    ("themes", "outcome", "rule"),
    [(["e2e-skip"], "skip", 0), (["e2e-two"], "two", 1), (["e2e-remind"], "one", None)],
)
def test_the_policy_matches_each_run_by_theme(
    themes: list[str], outcome: str, rule: int | None
) -> None:
    policy = ReviewPolicy.model_validate(e2e.e2e_policy("reviewer-1"))
    facts = SubmissionFacts("u", False, "new-dataset", "open", tuple(themes))

    assert match(policy, facts) == (outcome, rule)
    assert policy.reminders == [1]
    assert policy.reviewers == {"e2e-remind": ["reviewer-1"]}
    assert ReviewPolicy.model_validate(e2e.e2e_policy(None)).reviewers == {}


def test_event_types_are_compared_as_a_multiset() -> None:
    events = [{"type": "submitted"}, {"type": "created"}, {"type": "decided"}]

    assert e2e.event_mismatch(["created", "submitted", "decided"], events) is None
    assert (
        e2e.event_mismatch(["created", "submitted", "decided", "decided"], events)
        == "missing decided"
    )
    assert e2e.event_mismatch(["created", "submitted"], events) == "extra decided"


def test_the_state_file_round_trips_under_the_state_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    path = e2e.state_path("ingest-test")

    assert path == tmp_path / "research-archive" / "ingest-e2e-ingest-test.json"
    assert e2e.load_state(path) is None
    e2e.save_state(path, {"submissionId": "s1", "enteredAt": "2026-11-13T00:00:00Z"})
    assert e2e.load_state(path) == {"submissionId": "s1", "enteredAt": "2026-11-13T00:00:00Z"}
    e2e.save_state(path, None)
    assert not path.exists()


def test_a_day_one_reminder_is_due_a_day_and_an_hour_after_entering_review() -> None:
    entered = "2026-11-13T10:00:00.000000Z"

    assert not e2e.reminder_due(entered, datetime(2026, 11, 14, 10, 59, tzinfo=UTC))
    assert e2e.reminder_due(entered, datetime(2026, 11, 14, 11, 0, tzinfo=UTC))


def test_a_waiting_status_holds_only_once_the_pipeline_waits() -> None:
    assert e2e.holds({"status": "in-review", "waiting": False}, "in-review") is False
    assert e2e.holds({"status": "in-review", "waiting": True}, "in-review") is True
    assert e2e.holds({"status": "needs-changes", "waiting": True}, "needs-changes") is True
    assert e2e.holds({"status": "published", "waiting": False}, "published") is True
    assert e2e.holds({"status": "checking", "waiting": True}, "in-review") is False
