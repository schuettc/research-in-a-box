"""The generated README names every resource and column and never prints a missing value."""

from datetime import date
from pathlib import Path

from archive_contract.exports.readme import render_readme
from archive_contract.manifest import Manifest, TemporalCoverage
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


def test_readme_gives_the_preferred_citation_and_the_purpose() -> None:
    manifest = sample()
    readme = render_readme(manifest)

    assert manifest.citation and manifest.purpose
    assert f"## Citation\n\n{manifest.citation}\n" in readme
    assert f"## Purpose\n\n{manifest.purpose}\n" in readme


def test_readme_column_dictionary_gives_unit_scale_and_related_column() -> None:
    readme = render_readme(sample())

    temp = table_row(readme, "water_temp_c")
    assert "degC" in temp and "interval" in temp
    uncertainty = table_row(readme, "water_temp_unc_c")
    assert "uncertainty of `water_temp_c`" in uncertainty


def test_readme_lists_the_vector_resources_attribute_columns() -> None:
    readme = render_readme(sample())
    sites = readme.split("### `sites`", 1)[1].split("### ", 1)[0]

    assert "| `site`" in sites and "| `name`" in sites


def test_readme_gives_the_project_keywords_and_an_unknown_end() -> None:
    manifest = sample().model_copy(
        update={
            "project": "streams",
            "temporal_coverage": TemporalCoverage(start=date(1991, 1, 1), end="unknown"),
        }
    )
    project = Project(id="streams", title="Streams", keywords=["temperature", "LTER"])
    readme = render_readme(manifest, project)

    assert "- **Project keywords:** temperature, LTER" in readme
    assert "1991-01-01 to an unknown end" in readme
