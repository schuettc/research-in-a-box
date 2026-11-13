"""Build the sample package from fixed, invented data.

Every byte is fixed: no timestamps, no randomness, and compressed formats are written with
stored (uncompressed) blocks so the output does not depend on the zlib build. Rerunning this
script leaves `git diff` empty.

Usage: uv run python examples/sample-package/_build/make.py

README.md is written by hand and left alone; everything else under the package is rebuilt.
"""

import hashlib
import io
import json
import math
import re
import shutil
import struct
import zipfile
import zlib
from pathlib import Path
from typing import Any

import openpyxl
import shapefile

from archive_contract.changes import Change, write_changes
from archive_contract.manifest import Manifest
from archive_contract.validate import CHECKSUMS, MANIFEST, package_files

ROOT = Path(__file__).resolve().parents[1]
FIXED_DATE = (2024, 6, 1)
WGS84_WKT = (
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)

SITES = [
    ("S1", "Invented Brook, upper riffle", -72.7310, 44.3120, 11.2),
    ("S2", "Invented Brook, mill pool", -72.7020, 44.2870, 12.6),
    ("S3", "Imaginary Creek, culvert", -72.6650, 44.2410, 14.1),
]
HOURS = 20

CONDITION_CODES = [
    ("ok", "OK", "The logger was submerged and reading normally."),
    ("drift", "Drift", "The reading drifted from the field check by more than 0.5 C."),
    ("buried", "Buried", "The logger was found buried in sediment."),
    ("dry", "Out of water", "The logger was above the water line."),
]

METHODS = """\
# Methods

Each of three invented sites holds one temperature logger, fixed to a stake about 20 cm
above the stream bed. Loggers record water temperature every hour.

At each visit a field technician checks the logger against a hand thermometer and records the
logger's condition with one of the codes in `data/codes/condition-codes.csv`.

Discharge is measured by a partner program and is linked, not copied.

All sites, readings and people in this package are invented.
"""


# --- JSON, written the way prettier formats it -------------------------------------------


def _scalar(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def to_json(value: Any, indent: int = 0, prefix_width: int = 0, trailing: int = 0) -> str:
    """JSON with objects always expanded and scalar arrays on one line when they fit in 80
    columns, which is what prettier leaves unchanged."""
    pad = " " * indent
    inner = " " * (indent + 2)
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = list(value.items())
        lines = []
        for i, (key, item) in enumerate(items):
            last = i == len(items) - 1
            head = f"{_scalar(key)}: "
            body = to_json(item, indent + 2, indent + 2 + len(head), 0 if last else 1)
            lines.append(f"{inner}{head}{body}{'' if last else ','}")
        return "{\n" + "\n".join(lines) + f"\n{pad}}}"
    if isinstance(value, list):
        if not value:
            return "[]"
        if all(not isinstance(v, dict | list) for v in value):
            flat = "[" + ", ".join(_scalar(v) for v in value) + "]"
            if prefix_width + len(flat) + trailing <= 80:
                return flat
        lines = []
        for i, item in enumerate(value):
            last = i == len(value) - 1
            body = to_json(item, indent + 2, indent + 2, 0 if last else 1)
            lines.append(f"{inner}{body}{'' if last else ','}")
        return "[\n" + "\n".join(lines) + f"\n{pad}]"
    return _scalar(value)


# --- Files ----------------------------------------------------------------------------------


def write(relative: str, data: bytes | str) -> None:
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)


def file_meta(relative: str) -> dict[str, Any]:
    data = (ROOT / relative).read_bytes()
    return {"bytes": len(data), "hash": "sha256:" + hashlib.sha256(data).hexdigest()}


def logger_rows() -> list[dict[str, Any]]:
    rows = []
    for index, (site, _, _, _, base) in enumerate(SITES):
        for hour in range(HOURS):
            temp = base + 1.5 * math.sin(2 * math.pi * (hour - 9) / 24) + 0.1 * index
            if site == "S2" and hour in (14, 15):
                condition = "drift"
            elif site == "S3" and hour == 19:
                condition = "buried"
            else:
                condition = "ok"
            rows.append(
                {
                    "timestamp": f"2024-06-01T{hour:02d}:00:00",
                    "site": site,
                    "water_temp_c": f"{temp:.2f}",
                    "condition": condition,
                    "qc_flag": "B" if hour % 7 == 3 else "A",
                    "logger_model": "TL-100",
                    "battery_v": f"{3.60 - 0.005 * hour:.3f}",
                    "depth_cm": str(30 + 4 * index + hour % 3),
                }
            )
    return rows


def csv_text(header: list[str], rows: list[list[str]]) -> str:
    return "".join(",".join(cells) + "\n" for cells in [header, *rows])


def write_tables(rows: list[dict[str, Any]]) -> list[str]:
    header = list(rows[0])
    write("data/logger.csv", csv_text(header, [[r[h] for h in header] for r in rows]))
    raw_header = ["Timestamp", "Site", "WTemp", "Cond", "QC", "Model", "Batt", "Depth"]
    write("original/logger-raw.csv", csv_text(raw_header, [[r[h] for h in header] for r in rows]))
    write(
        "data/codes/condition-codes.csv",
        csv_text(["code", "label", "description"], [list(c) for c in CONDITION_CODES]),
    )
    return header


def zip_fixed(data: bytes) -> bytes:
    """Rewrite a zip with stored entries and a fixed date, keeping the entry order."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w") as target:
        for entry in source.infolist():
            content = source.read(entry.filename)
            if entry.filename == "docProps/core.xml":
                content = re.sub(
                    rb"(<dcterms:(created|modified)[^>]*>)[^<]*(</dcterms:)",
                    rb"\g<1>2024-06-01T00:00:00Z\g<3>",
                    content,
                )
            info = zipfile.ZipInfo(entry.filename, date_time=(*FIXED_DATE, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            target.writestr(info, content)
    return out.getvalue()


def write_xlsx(header: list[str], rows: list[dict[str, Any]]) -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "logger"
    sheet.append(header)
    for row in rows:
        sheet.append(
            [
                row["timestamp"],
                row["site"],
                float(row["water_temp_c"]),
                row["condition"],
                row["qc_flag"],
                row["logger_model"],
                float(row["battery_v"]),
                int(row["depth_cm"]),
            ]
        )
    buffer = io.BytesIO()
    workbook.save(buffer)
    write("data/logger.xlsx", zip_fixed(buffer.getvalue()))


def write_shapefile() -> list[str]:
    folder = ROOT / "data" / "sites"
    folder.mkdir(parents=True, exist_ok=True)
    with shapefile.Writer(str(folder / "sites"), shapeType=shapefile.POINT) as writer:
        writer.field("site", "C", size=8)
        writer.field("name", "C", size=40)
        for site, name, lon, lat, _ in SITES:
            writer.point(lon, lat)
            writer.record(site, name)
    dbf = bytearray((folder / "sites.dbf").read_bytes())
    year, month, day = FIXED_DATE
    dbf[1:4] = bytes([year - 1900, month, day])  # the dbf header's last-update date
    (folder / "sites.dbf").write_bytes(bytes(dbf))
    (folder / "sites.prj").write_text(WGS84_WKT, encoding="utf-8")
    members = ["sites.shp", "sites.shx", "sites.dbf", "sites.prj"]
    written = sorted(p.name for p in folder.iterdir())
    assert written == sorted(members), written
    return [f"data/sites/{m}" for m in members]


def write_raster() -> None:
    grid = [[42, 38, 35, 31], [47, 44, 40, 36], [51, 49, 45, 41]]
    lines = [
        "ncols 4",
        "nrows 3",
        "xllcorner -72.7400",
        "yllcorner 44.2300",
        "cellsize 0.0200",
        "NODATA_value -9999",
        *(" ".join(str(v) for v in row) for row in grid),
    ]
    write("data/depth.asc", "\n".join(lines) + "\n")
    write("data/depth.prj", WGS84_WKT)


def png(width: int, height: int) -> bytes:
    """A small sky-over-water picture, as an RGB PNG with stored zlib blocks."""

    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(kind + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            if y < height // 2:
                raw += bytes([120 + 4 * y, 170 + 2 * y, 230])
            else:
                raw += bytes([30 + 3 * x, 90 + 2 * y, 110])
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 0))
        + chunk(b"IEND", b"")
    )


# --- The manifest ---------------------------------------------------------------------------


def logger_schema() -> dict[str, Any]:
    return {
        "fields": [
            {
                "name": "timestamp",
                "type": "datetime",
                "title": "Reading time",
                "description": "Local standard time of the reading, on the hour.",
            },
            {
                "name": "site",
                "type": "string",
                "title": "Site",
                "description": "Site code; the sites resource holds each site's location.",
            },
            {
                "name": "water_temp_c",
                "type": "number",
                "title": "Water temperature (C)",
                "description": "Water temperature in degrees Celsius.",
                "archive:sourceName": "WTemp",
            },
            {
                "name": "condition",
                "type": "string",
                "title": "Logger condition",
                "description": "The logger's condition at the reading, from the code list.",
            },
            {
                "name": "qc_flag",
                "type": "string",
                "title": "QC flag",
                "description": "Quality flag set by the logger's software.",
                "archive:codeList": "undocumented",
            },
            {
                "name": "logger_model",
                "type": "string",
                "title": "Logger model",
                "description": "Model of the temperature logger.",
            },
            {"name": "battery_v", "type": "number"},
            {"name": "depth_cm", "type": "integer", "description": "depth_cm"},
        ],
        "foreignKeys": [
            {
                "fields": ["condition"],
                "reference": {"resource": "condition-codes", "fields": ["code"]},
            }
        ],
    }


def resources(site_members: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "name": "logger",
            "path": "data/logger.csv",
            "type": "table",
            "title": "Logger readings",
            "description": "Hourly water temperature at three sites on 1 June 2024.",
            "format": "csv",
            "mediatype": "text/csv",
            "encoding": "utf-8",
            **file_meta("data/logger.csv"),
            "schema": logger_schema(),
            "archive:kind": "table",
        },
        {
            "name": "condition-codes",
            "path": "data/codes/condition-codes.csv",
            "type": "table",
            "title": "Logger condition codes",
            "description": "The codes used in the logger table's condition column.",
            "format": "csv",
            "mediatype": "text/csv",
            "encoding": "utf-8",
            **file_meta("data/codes/condition-codes.csv"),
            "schema": {
                "fields": [
                    {"name": "code", "type": "string", "description": "The code."},
                    {"name": "label", "type": "string", "description": "A short label."},
                    {
                        "name": "description",
                        "type": "string",
                        "description": "What the code means.",
                    },
                ],
                "primaryKey": ["code"],
            },
            "archive:kind": "table",
        },
        {
            "name": "sites",
            "path": "data/sites/sites.shp",
            "title": "Sites",
            "description": "The three logger sites as points, in WGS 84.",
            "format": "shp",
            "archive:kind": "vector",
            "archive:files": [{"path": p, **file_meta(p)} for p in site_members],
        },
        {
            "name": "depth",
            "path": "data/depth.asc",
            "title": "Stream depth",
            "description": "Stream depth in centimetres on a coarse grid, as an ESRI ASCII grid.",
            "format": "asc",
            "archive:kind": "raster",
            "archive:files": [
                {"path": p, **file_meta(p)} for p in ["data/depth.asc", "data/depth.prj"]
            ],
        },
        {
            "name": "logger-xlsx",
            "path": "data/logger.xlsx",
            "type": "table",
            "title": "Logger readings (Excel)",
            "description": "The logger table as an Excel workbook.",
            "format": "xlsx",
            "mediatype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            **file_meta("data/logger.xlsx"),
            "archive:kind": "table",
            "archive:alternateOf": "logger",
        },
        {
            "name": "logger-original",
            "path": "original/logger-raw.csv",
            "title": "Logger export, untouched",
            "description": "The logger software's export before cleaning.",
            "format": "csv",
            "mediatype": "text/csv",
            **file_meta("original/logger-raw.csv"),
            "archive:kind": "file",
        },
        {
            "name": "methods",
            "path": "docs/methods.md",
            "title": "Methods",
            "description": "How the loggers were placed, read and checked.",
            "format": "md",
            "mediatype": "text/markdown",
            **file_meta("docs/methods.md"),
            "archive:kind": "document",
        },
        {
            "name": "site-photo",
            "path": "docs/site-photo.png",
            "title": "Site photo",
            "description": "A stand-in picture of site S1.",
            "format": "png",
            "mediatype": "image/png",
            **file_meta("docs/site-photo.png"),
            "archive:kind": "media",
        },
        {
            "name": "discharge",
            "path": "https://example.org/stream-temperature/discharge.csv",
            "title": "Discharge",
            "description": "Stream discharge at the same sites, held by a partner program.",
            "format": "csv",
            "archive:kind": "linked",
        },
    ]


def manifest(site_members: list[str]) -> dict[str, Any]:
    raw = {
        "$schema": "https://datapackage.org/profiles/2.0/datapackage.json",
        "id": "stream-temperature-sample",
        "name": "stream-temperature-sample",
        "version": "1",
        "title": "Stream temperature at three invented sites",
        "description": (
            "Hourly water temperature from loggers at three invented stream sites, with each "
            "logger's condition, the site locations, a depth grid and the methods. A sample "
            "package for the research archive; every site and reading is invented."
        ),
        "keywords": ["stream temperature", "water quality", "loggers"],
        "contributors": [
            {"title": "Ada Invented", "roles": ["creator"], "organization": "Example Lab"},
            {"title": "Ben Placeholder", "roles": ["data-curator"]},
        ],
        "licenses": [
            {
                "name": "CC-BY-4.0",
                "path": "https://creativecommons.org/licenses/by/4.0/",
                "title": "Creative Commons Attribution 4.0 International",
            }
        ],
        "resources": resources(site_members),
        "archive:access": "open",
        "archive:temporalCoverage": {"start": "2024-06-01", "ongoing": True},
        "archive:spatialCoverage": {
            "bbox": [-72.74, 44.23, -72.66, 44.32],
            "description": "Three invented sites along two streams.",
        },
        "archive:methods": "Hourly loggers with field checks at each visit; see docs/methods.md.",
    }
    return Manifest.model_validate(raw).dump()


def rename() -> Change:
    return Change.model_validate(
        {
            "id": "c1",
            "when": "2024-06-02T09:00:00Z",
            "madeBy": {"kind": "tool", "name": "cruise"},
            "acceptedBy": {"kind": "person", "name": "Ada Invented"},
            "kind": "rename",
            "target": {"resource": "logger", "field": "water_temp_c"},
            "before": "WTemp",
            "after": "water_temp_c",
            "reason": "Spell out what the column holds and its unit.",
            "evidence": {"values": ["WTemp"]},
        }
    )


def write_checksums() -> None:
    paths, _ = package_files(ROOT)
    lines = [
        f"{hashlib.sha256((ROOT / p).read_bytes()).hexdigest()}  {p}\n"
        for p in paths
        if p != CHECKSUMS
    ]
    write(CHECKSUMS, "".join(lines))


def main() -> None:
    for folder in ["data", "original", "docs"]:
        shutil.rmtree(ROOT / folder, ignore_errors=True)
    rows = logger_rows()
    header = write_tables(rows)
    write_xlsx(header, rows)
    site_members = write_shapefile()
    write_raster()
    write("docs/methods.md", METHODS)
    write("docs/site-photo.png", png(16, 12))
    write(MANIFEST, to_json(manifest(site_members)) + "\n")
    write_changes(ROOT / "changes.jsonl", [rename()])
    write_checksums()


if __name__ == "__main__":
    main()
