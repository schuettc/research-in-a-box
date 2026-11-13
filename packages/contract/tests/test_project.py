import pytest
from pydantic import ValidationError

from archive_contract.project import Project


def test_project_reads_its_record() -> None:
    project = Project.model_validate(
        {
            "id": "stream-monitoring",
            "title": "Stream monitoring program",
            "abstract": "Long-term monitoring of invented streams.",
            "people": [{"name": "A. Researcher", "roles": ["lead"]}],
            "links": [{"url": "https://example.org/streams", "title": "Program page"}],
        }
    )

    assert project.id == "stream-monitoring"
    assert project.people[0].name == "A. Researcher"
    assert project.links[0].url == "https://example.org/streams"


@pytest.mark.parametrize("missing", ["id", "title"])
def test_project_needs_an_id_and_a_title(missing: str) -> None:
    raw = {"id": "p", "title": "T"}
    del raw[missing]

    with pytest.raises(ValidationError):
        Project.model_validate(raw)


def test_project_dump_drops_unset_and_keeps_extras() -> None:
    dumped = Project.model_validate({"id": "p", "title": "T", "x-note": "kept"}).dump()

    assert "abstract" not in dumped
    assert dumped["people"] == []
    assert dumped["x-note"] == "kept"
