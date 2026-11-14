import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

import openpyxl  # type: ignore[import-untyped]
import pytest
import shapefile  # type: ignore[import-untyped]

from archive_contract.validate import validate_package
from femc.cli import main
from femc.convert import convert

FIXTURES = Path(__file__).parent / "fixtures" / "datasets"
THIRD_PARTY = "Linked - third party determines data license"

SURVEY_ROWS = [("1", 1204.5, "VT", 12), ("2", 88.25, "NH", 0), ("-1", 310.0, "VT", 7)]


def dataset(tmp_path: Path, name: str, record: str | None = None) -> Path:
    """A copy of the fixture dataset folder, beside a copy of the fixtures' SOURCES.md."""
    femc = tmp_path / "femc"
    femc.mkdir(exist_ok=True)
    shutil.copy(FIXTURES / "SOURCES.md", femc / "SOURCES.md")
    shutil.copytree(FIXTURES / (record or name), femc / name)
    return femc / name


def run(folder: Path, tmp_path: Path) -> tuple[Path, dict[str, Any], list[str]]:
    package = convert(folder, folder.parent / "SOURCES.md", tmp_path / "packages")
    assert package == tmp_path / "packages" / folder.name
    assert validate_package(package) == []
    manifest = json.loads((package / "datapackage.json").read_text(encoding="utf-8"))
    lines = (package / "_build" / "not-imported.txt").read_text(encoding="utf-8").splitlines()
    return package, manifest, lines


def resource(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    found: dict[str, Any] = next(r for r in manifest["resources"] if r["name"] == name)
    return found


def fields(schema: dict[str, Any]) -> list[dict[str, Any]]:
    """The fields with their null `archive:` properties left out, for short assertions."""
    return [{k: v for k, v in f.items() if v is not None} for f in schema["fields"]]


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


COMMON_SKIPS = [
    "dataset/publisher: not read",
    "dataset/project/shortName: not standard EML",
    "dataset/dataTable/physical/distribution: not read",
    "dataset/dataTable/physical/dataFormat/formatName: not standard EML",
]


def test_a_csv_table_with_its_columns_matched_to_the_record(tmp_path: Path) -> None:
    package, manifest, lines = run(dataset(tmp_path, "stream-counts"), tmp_path)

    assert manifest["id"] == manifest["name"] == "stream-counts"
    assert manifest["version"] == "1"
    assert manifest["title"] == "Invented Stream Counts"
    assert manifest["homepage"] == "https://example.org/imc/dataset/stream-counts"
    assert manifest["archive:citation"] == (
        "Placeholder, A. 2001. Invented Stream Counts. Invented Monitoring Cooperative."
    )
    assert manifest["archive:legacyIdentifiers"] == [
        {"scheme": "eml-package-id", "value": "vmc.9101.9102.1"},
        {"scheme": "femc-object", "value": "VMC.9101.9102"},
    ]
    assert manifest["archive:rightsStatus"] == {"status": "third-party", "statement": THIRD_PARTY}
    assert "licenses" not in manifest
    assert manifest["archive:access"] == "open"
    assert manifest["archive:temporalCoverage"] == {
        "start": "2001-06-01",
        "end": "2001-06-30",
        "ongoing": False,
    }
    assert [r["name"] for r in manifest["resources"]] == ["invented-stream-counts", "eml"]
    table = resource(manifest, "invented-stream-counts")
    assert table["path"] == "data/Z9101_counts.csv"
    assert table["archive:kind"] == "table"
    assert table["format"] == "csv"
    assert table["title"] == "Invented Stream Counts"
    assert table["hash"] == sha256(FIXTURES / "stream-counts" / "Z9101_counts.csv")
    assert (package / "data" / "Z9101_counts.csv").read_bytes() == (
        FIXTURES / "stream-counts" / "Z9101_counts.csv"
    ).read_bytes()
    assert fields(table["schema"]) == [
        {"name": "SITE", "type": "string"},
        {
            "name": "COUNT",
            "type": "integer",
            "description": "Insects in the kick net",
            "archive:sourceName": "count",
            "archive:measurementScale": "ratio",
        },
        {
            "name": "VISIT_DATE",
            "type": "date",
            "description": "Date of the visit",
            "archive:measurementScale": "dateTime",
        },
        {"name": "DEPTH_M", "type": "number"},
    ]
    eml = resource(manifest, "eml")
    assert eml["path"] == "original/eml.xml"
    assert eml["archive:kind"] == "file"
    assert (package / "original" / "eml.xml").read_bytes() == (
        FIXTURES / "stream-counts" / "eml.xml"
    ).read_bytes()
    assert (
        (package / "README.md").read_text(encoding="utf-8").startswith("# Invented Stream Counts\n")
    )
    assert lines == [
        "dataset/dataTable/shortName: not standard EML, dropped: Z9101_counts",
        *COMMON_SKIPS,
        "invented-stream-counts: attribute EXTRA has no column in data/Z9101_counts.csv, "
        "so it is not imported",
        "invented-stream-counts: column DEPTH_M has no attribute in the record, "
        "so it has no description",
        "invented-stream-counts: column SITE typed string from its values, "
        "since the record declares no type",
        "invented-stream-counts: column DEPTH_M typed number from its values, "
        "since the record declares no type",
    ]


def test_a_linked_record_points_at_the_url_in_its_citation(tmp_path: Path) -> None:
    _, manifest, lines = run(dataset(tmp_path, "census-linked"), tmp_path)

    assert [r["name"] for r in manifest["resources"]] == ["census-data", "eml"]
    linked = resource(manifest, "census-data")
    assert linked["archive:kind"] == "linked"
    assert linked["path"] == "https://example.org/invented/census_data"
    assert "format" not in linked
    assert linked["title"] == "census_data"
    assert manifest["archive:temporalCoverage"] == {
        "start": "1965-01-01",
        "end": "unknown",
        "ongoing": False,
    }
    assert manifest["contributors"] == [
        {"title": "Invented University", "organization": "Invented University", "roles": ["lead"]}
    ]
    assert manifest["archive:access"] == "open"
    assert manifest["archive:rightsStatus"]["status"] == "third-party"
    assert lines == COMMON_SKIPS


def write_survey_zip(folder: Path) -> None:
    """A three-feature shapefile set, its attribute table as CSV and XLSX, zipped as FEMC
    delivers it."""
    parts = folder / "parts"
    parts.mkdir()
    with shapefile.Writer(str(parts / "InventedSurvey"), shapeType=shapefile.POLYGON) as writer:
        writer.field("DMG_TYPE1", "C", size=4)
        writer.field("Shape_Leng", "N", size=19, decimal=11)
        writer.field("STATE", "C", size=2)
        writer.field("HOST1", "N", size=10, decimal=0)
        for i, row in enumerate(SURVEY_ROWS):
            x = -72.0 - i
            writer.poly([[[x, 44.0], [x, 44.1], [x + 0.1, 44.1], [x, 44.0]]])
            writer.record(*row)
    for suffix, data in [
        (".prj", b'GEOGCS["GCS_WGS_1984"]'),
        (".cpg", b"UTF-8"),
        (".sbn", b"invented index"),
        (".sbx", b"invented index"),
        (".shp.xml", b"<metadata/>"),
    ]:
        (parts / f"InventedSurvey{suffix}").write_bytes(data)
    header = "DMG_TYPE1,Shape_Leng,STATE,HOST1\n"
    (parts / "InventedSurvey.csv").write_text(
        header + "".join(f"{a},{b},{c},{d}\n" for a, b, c, d in SURVEY_ROWS), encoding="utf-8"
    )
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(header.strip().split(","))
    for row in SURVEY_ROWS:
        sheet.append(list(row))
    workbook.save(parts / "InventedSurvey.xlsx")
    with zipfile.ZipFile(folder / "20200101000000_InventedSurvey.zip", "w") as archive:
        for part in sorted(parts.iterdir()):
            archive.write(part, part.name)
    shutil.rmtree(parts)


def test_a_zipped_shapefile_set_with_its_attribute_table(tmp_path: Path) -> None:
    folder = dataset(tmp_path, "aerial-shapefile")
    write_survey_zip(folder)

    package, manifest, lines = run(folder, tmp_path)

    unpacked = "data/20200101000000_InventedSurvey"
    assert not (package / "data" / "20200101000000_InventedSurvey.zip").exists()
    assert [r["name"] for r in manifest["resources"]] == [
        "invented-survey",
        "invented-survey-table",
        "invented-survey-table-xlsx",
        "dmg-type1-codes",
        "eml",
    ]
    vector = resource(manifest, "invented-survey")
    assert vector["archive:kind"] == "vector"
    assert vector["path"] == f"{unpacked}/InventedSurvey.shp"
    assert vector["title"] == "Invented Survey"
    assert [m["path"] for m in vector["archive:files"]] == [
        f"{unpacked}/InventedSurvey.{s}"
        for s in ["cpg", "dbf", "prj", "sbn", "sbx", "shp", "shp.xml", "shx"]
    ]
    assert fields(vector["archive:attributes"]) == [
        {
            "name": "DMG_TYPE1",
            "type": "string",
            "description": "Damage type",
            "archive:measurementScale": "nominal",
        },
        {
            "name": "Shape_Leng",
            "type": "number",
            "description": "Perimeter of the polygon",
            "archive:measurementScale": "ratio",
        },
        {
            "name": "STATE",
            "type": "string",
            "description": "State the polygon lies in",
            "archive:measurementScale": "nominal",
        },
        {"name": "HOST1", "type": "integer"},
    ]
    table = resource(manifest, "invented-survey-table")
    assert table["path"] == f"{unpacked}/InventedSurvey.csv"
    assert fields(table["schema"])[1:3] == [
        {
            "name": "Shape_Leng",
            "type": "number",
            "description": "Perimeter of the polygon",
            "archive:sourceName": "Shape_Length",
            "archive:measurementScale": "ratio",
        },
        {
            "name": "STATE",
            "type": "string",
            "description": "State the polygon lies in",
            "archive:sourceName": "State",
            "archive:measurementScale": "nominal",
        },
    ]
    assert table["schema"]["foreignKeys"] == [
        {"fields": ["DMG_TYPE1"], "reference": {"resource": "dmg-type1-codes", "fields": ["code"]}}
    ]
    alternate = resource(manifest, "invented-survey-table-xlsx")
    assert alternate["archive:alternateOf"] == "invented-survey-table"
    assert alternate["format"] == "xlsx"
    assert "schema" not in alternate
    codes = resource(manifest, "dmg-type1-codes")
    assert codes["path"] == "data/codes/dmg-type1-codes.csv"
    assert (package / codes["path"]).read_text(encoding="utf-8") == (
        "code,label,description\n1,Defoliation,\n2,Mortality,\n"
    )
    assert manifest["archive:rightsStatus"] == {"status": "undetermined"}
    assert lines == [
        "dataset/dataTable/shortName: not standard EML, dropped: 20200101000000_InventedSurvey.zip",
        *COMMON_SKIPS,
        "dataset/dataTable/attributeList/attribute/.../enumeratedDomain: "
        "only codeDefinition is read",
        f"invented-survey: attribute MISSING_A has no column in {unpacked}/InventedSurvey.dbf, "
        "so it is not imported",
        "invented-survey: column HOST1 has no attribute in the record, so it has no description",
        "invented-survey: column HOST1 typed integer from the .dbf header, "
        "since the record declares no type",
        "invented-survey-table: attribute MISSING_A has no column in "
        f"{unpacked}/InventedSurvey.csv, so it is not imported",
        "invented-survey-table: column HOST1 has no attribute in the record, "
        "so it has no description",
        "invented-survey-table: column HOST1 typed integer from its values, "
        "since the record declares no type",
    ]


def test_a_by_request_record_is_metadata_only(tmp_path: Path) -> None:
    _, manifest, lines = run(dataset(tmp_path, "plant-permits"), tmp_path)

    assert [r["name"] for r in manifest["resources"]] == ["eml"]
    assert manifest["archive:access"] == "by-request"
    assert manifest["archive:rightsStatus"] == {"status": "undetermined"}
    assert manifest["archive:citation"] is None
    assert lines == COMMON_SKIPS


def test_an_arcinfo_grid_is_one_raster_resource(tmp_path: Path) -> None:
    folder = dataset(tmp_path, "cover-raster")
    with zipfile.ZipFile(folder / "20180101000000_cover.zip", "w") as archive:
        for name in ["hdr.adf", "prj.adf", "w001001.adf"]:
            archive.writestr(name, f"invented {name}")

    package, manifest, lines = run(folder, tmp_path)

    assert [r["name"] for r in manifest["resources"]] == ["invented-cover-raster", "eml"]
    raster = resource(manifest, "invented-cover-raster")
    assert raster["archive:kind"] == "raster"
    assert raster["path"] == "data/20180101000000_cover/hdr.adf"
    assert [m["path"] for m in raster["archive:files"]] == [
        f"data/20180101000000_cover/{n}" for n in ["hdr.adf", "prj.adf", "w001001.adf"]
    ]
    assert manifest["licenses"] == [
        {
            "name": "CC0-1.0",
            "path": "https://creativecommons.org/publicdomain/zero/1.0/",
            "title": "Creative Commons Zero v1.0 Universal",
        }
    ]
    assert not (package / "data" / "codes").exists()
    assert lines[-1] == (
        "attribute Value: no table in the package to describe, so it is not imported"
    )


def test_each_photograph_is_its_own_media_resource(tmp_path: Path) -> None:
    folder = dataset(tmp_path, "quadrat-photos")
    with zipfile.ZipFile(folder / "photos_1-2.zip", "w") as archive:
        archive.writestr("Q_1a.JPG", b"\xff\xd8 invented photo one")
        archive.writestr("Q_L9a,b.JPG", b"\xff\xd8 invented photo two")

    _, manifest, _ = run(folder, tmp_path)

    assert [r["name"] for r in manifest["resources"]] == ["q-1a", "q-l9a-b", "eml"]
    photo = resource(manifest, "q-l9a-b")
    assert photo["archive:kind"] == "media"
    assert photo["path"] == "data/photos_1-2/Q_L9a,b.JPG"
    assert photo["mediatype"] == "image/jpeg"
    assert manifest["licenses"] == [
        {
            "name": "CC-BY-NC-SA-4.0",
            "path": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
            "title": "Creative Commons Attribution Non Commercial Share Alike 4.0 International",
        }
    ]


def test_a_license_the_corpus_does_not_show_stops_the_conversion(tmp_path: Path) -> None:
    folder = dataset(tmp_path, "unknown-license", record="plant-permits")

    with pytest.raises(ValueError, match="All rights reserved, ask us"):
        convert(folder, folder.parent / "SOURCES.md", tmp_path / "packages")
    assert not (tmp_path / "packages" / "unknown-license").exists()


def test_an_existing_package_folder_is_not_overwritten(tmp_path: Path) -> None:
    folder = dataset(tmp_path, "plant-permits")
    (tmp_path / "packages" / "plant-permits").mkdir(parents=True)

    with pytest.raises(ValueError, match="already exists"):
        convert(folder, folder.parent / "SOURCES.md", tmp_path / "packages")


def test_the_command_reads_the_sources_beside_the_dataset(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = dataset(tmp_path, "plant-permits")

    assert main(["convert", str(folder), str(tmp_path / "packages")]) == 0

    assert validate_package(tmp_path / "packages" / "plant-permits") == []
    assert str(tmp_path / "packages" / "plant-permits") in capsys.readouterr().out


def test_the_command_reports_a_refusal(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = dataset(tmp_path, "unknown-license", record="plant-permits")

    assert main(["convert", str(folder), str(tmp_path / "packages")]) == 1

    assert "All rights reserved, ask us" in capsys.readouterr().err
