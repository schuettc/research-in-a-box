"""The generated README names every resource and column and never prints a missing value."""

from pathlib import Path

from archive_contract.exports.readme import render_readme
from archive_contract.manifest import Manifest
from archive_contract.project import Project

SAMPLE = Path(__file__).parents[3] / "examples" / "sample-package"


def sample() -> Manifest:
    return Manifest.model_validate_json((SAMPLE / "datapackage.json").read_text(encoding="utf-8"))


def table_row(readme: str, column: str) -> str:
    return next(line for line in readme.splitlines() if line.startswith(f"| `{column}`"))


def test_readme_names_every_resource_and_every_column() -> None:
    manifest = sample()
    readme = render_readme(manifest)

    for resource in manifest.resources:
        assert f"`{resource.name}`" in readme
        if resource.table_schema is not None:
            for field in resource.table_schema.fields:
                assert table_row(readme, field.name)


def test_readme_gives_the_title_citation_rights_access_and_coverage() -> None:
    readme = render_readme(sample())

    assert readme.startswith("# Stream temperature at three invented sites\n")
    assert "Ada Invented" in readme
    assert "Version 1" in readme
    assert "CC-BY-4.0" in readme
    assert "open" in readme
    assert "2024-06-01 to ongoing" in readme


def test_readme_shows_an_undocumented_code_list_as_undocumented() -> None:
    readme = render_readme(sample())

    assert "undocumented" in table_row(readme, "qc_flag")
    assert "`condition-codes`" in table_row(readme, "condition")


def test_readme_names_the_project_by_its_title() -> None:
    manifest = sample().model_copy(update={"project": "streams"})
    project = Project(id="streams", title="Invented stream monitoring program")

    assert "Invented stream monitoring program" in render_readme(manifest, project)


def test_readme_prints_nothing_for_a_missing_property() -> None:
    manifest = Manifest.model_validate(
        {"title": "Bare", "resources": [{"name": "notes", "path": "docs/notes.txt"}]}
    )
    readme = render_readme(manifest)

    assert "None" not in readme
    assert "null" not in readme
    assert "`notes`" in readme
