"""One FEMC dataset folder, written as an archive package.

The folder holds FEMC's `eml.xml` and the download, if there is one; its row of `SOURCES.md`
gives the license and access FEMC's page shows and the page itself. The record is read
through `standardize` and the unchanged `from_eml`. The files are the truth about their
columns: each real column becomes a field, and the record's attributes are matched to them.
Whatever is not imported is listed, one line each with its reason, in
`_build/not-imported.txt`.
"""

import csv
import hashlib
import json
import re
import shutil
import struct
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

from archive_contract.exports.readme import render_readme
from archive_contract.fields import Field
from archive_contract.imports.eml import EmlImport, from_eml, slug
from archive_contract.manifest import Manifest
from archive_contract.validate import BUILD, CHECKSUMS, MANIFEST, package_files
from femc.eml import Standardized, standardize

RECORD = "eml.xml"
NOT_IMPORTED = "not-imported.txt"
PROJECT = "project.json"
"""The project record from the EML, kept until the archive decides where project records live."""
PROFILE = "https://datapackage.org/profiles/2.0/datapackage.json"
CODE_COLUMNS = ["code", "label", "description"]
DBF_NAME_LENGTH = 10
"""A shapefile's `.dbf` cuts column names to ten characters."""

LICENSES: dict[str, dict[str, str]] = {
    "CC0 - Public domain": {
        "name": "CC0-1.0",
        "path": "https://creativecommons.org/publicdomain/zero/1.0/",
        "title": "Creative Commons Zero v1.0 Universal",
    },
    "CC BY-NC-SA 4.0": {
        "name": "CC-BY-NC-SA-4.0",
        "path": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
        "title": "Creative Commons Attribution Non Commercial Share Alike 4.0 International",
    },
}
THIRD_PARTY = "Linked - third party determines data license"
NO_LICENSE = "None shown on the overview page"

ACCESS: dict[str, str] = {
    "none (By request)": "by-request",
    "none (Description only)": "description-only",
}

SHAPEFILE_SIDECARS = frozenset({".csv", ".xlsx", ".xls", ".txt"})
"""Files that share a shapefile's stem but are not parts of the set."""
MEDIA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif"}
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
LINKED_URL = re.compile(r"Available online at:\s*(https?://\S+)")

INTEGER = re.compile(r"[+-]?\d+")
NUMBER = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass
class Source:
    """A dataset's row of `SOURCES.md`."""

    folder: str
    data_file: str
    license: str
    page: str


@dataclass
class Record:
    """What the record says about its one table: its fields and their code lists."""

    imported: EmlImport
    table: dict[str, Any] = field(default_factory=dict)
    """The record's table as `from_eml` reads it, or empty when it has none."""
    fields: list[Field] = field(default_factory=list)
    code_lists: dict[str, str] = field(default_factory=dict)
    """The code-list resource of each attribute that has one, by attribute name."""


def read_sources(path: Path, folder: str) -> Source:
    """The row of `SOURCES.md` for a dataset folder. Raises ValueError when there is none."""
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.lstrip().startswith("|") and len(cells) == 6 and cells[0] == folder:
            return Source(folder=cells[0], data_file=cells[2], license=cells[4], page=cells[5])
    raise ValueError(f"{path} has no row for {folder}")


def rights(license_text: str) -> dict[str, Any]:
    """The manifest's rights from the license FEMC's page shows. Raises ValueError on a
    license the corpus doesn't show, rather than guessing at it."""
    if license_text in LICENSES:
        return {"licenses": [LICENSES[license_text]]}
    if license_text == THIRD_PARTY:
        return {"archive:rightsStatus": {"status": "third-party", "statement": license_text}}
    if license_text == NO_LICENSE:
        return {"archive:rightsStatus": {"status": "undetermined"}}
    raise ValueError(f"no rule for the license {license_text!r}; add one to femc.convert")


def access(data_file: str) -> str:
    return next((v for k, v in ACCESS.items() if data_file.startswith(k)), "open")


def file_meta(root: Path, relative: str) -> dict[str, Any]:
    digest = hashlib.sha256()
    with (root / relative).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return {"bytes": (root / relative).stat().st_size, "hash": "sha256:" + digest.hexdigest()}


# --- Columns --------------------------------------------------------------------------------


def csv_columns(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return next(csv.reader(stream), [])


def infer_types(path: Path, columns: list[str]) -> dict[str, str]:
    """Each named column's type from its values, read once from top to bottom: integer,
    number or date when every non-empty value is one, otherwise string."""
    possible = {c: {"integer", "number", "date"} for c in columns}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader, [])
        indexes = [(header.index(c), c) for c in columns]
        for row in reader:
            for index, column in indexes:
                kinds = possible[column]
                value = row[index] if index < len(row) else ""
                if not kinds or not value:
                    continue
                if "integer" in kinds and not INTEGER.fullmatch(value):
                    kinds.discard("integer")
                if "number" in kinds and not NUMBER.fullmatch(value):
                    kinds.discard("number")
                if "date" in kinds and not _iso_date(value):
                    kinds.discard("date")
    return {c: next((k for k in ("integer", "number", "date") if k in possible[c]), "string")
            for c in columns}  # fmt: skip


def _iso_date(value: str) -> bool:
    if not ISO_DATE.fullmatch(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def dbf_columns(path: Path) -> list[tuple[str, str]]:
    """Each column of a dBASE file's header with its type, read from the header alone.

    The header is 32 bytes, its total length at bytes 8-9, then one 32-byte descriptor per
    column (the name null-padded in the first 11 bytes, the type at byte 11, the decimal count
    at byte 17) and a 0x0D terminator.
    """
    with path.open("rb") as stream:
        head = stream.read(32)
        (length,) = struct.unpack_from("<H", head, 8)
        descriptors = stream.read(max(length - 32, 0))
    columns = []
    for offset in range(0, len(descriptors) - 31, 32):
        if descriptors[offset] == 0x0D:
            break
        descriptor = descriptors[offset : offset + 32]
        name = descriptor[:11].split(b"\x00", 1)[0].decode("latin-1")
        kind = chr(descriptor[11])
        if kind == "N":
            columns.append((name, "number" if descriptor[17] else "integer"))
        else:
            columns.append((name, {"F": "number", "D": "date", "L": "boolean"}.get(kind, "string")))
    return columns


def match(
    attributes: list[Field], columns: list[str], truncated: bool
) -> tuple[dict[str, Field], list[Field]]:
    """Each column's attribute, matched by exact name, then case-insensitively, then (for a
    shapefile's columns) by the `.dbf`'s ten-character cut; and the attributes left over."""
    matched: dict[str, Field] = {}
    left = list(attributes)

    def take(same: Any) -> None:
        for column in columns:
            if column in matched:
                continue
            found = next((a for a in left if same(a.name, column)), None)
            if found is not None:
                matched[column] = found
                left.remove(found)

    take(lambda a, c: a == c)
    take(lambda a, c: a.lower() == c.lower())
    if truncated:
        take(lambda a, c: a[:DBF_NAME_LENGTH].lower() == c.lower())
    return matched, left


# --- The package ----------------------------------------------------------------------------


@dataclass
class Builder:
    """The package being written: its folder, resources, code lists in use and the lines of
    what was not imported."""

    root: Path
    record: Record
    resources: list[dict[str, Any]] = field(default_factory=list)
    codes_used: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    described: bool = False

    def name(self, wanted: str) -> str:
        taken = {r["name"] for r in self.resources}
        name, n = wanted, 1
        while name in taken:
            n += 1
            name = f"{wanted}-{n}"
        return name

    def entity(self) -> dict[str, Any]:
        """The record's title and description, for the first resource that is its data."""
        if self.described:
            return {}
        self.described = True
        table = self.table()
        out = {"title": table.get("title"), "description": table.get("description")}
        return {k: v for k, v in out.items() if v}

    def table(self) -> dict[str, Any]:
        return self.record.table

    def base(self) -> str:
        return self.table().get("name") or self.root.name

    def schema(
        self,
        resource: str,
        path: str,
        columns: list[str],
        types: dict[str, str] | None,
        truncated: bool,
        source_names: bool,
    ) -> dict[str, Any]:
        """A Table Schema for the file's columns, with the record's attributes matched to
        them. `types` holds a type per column read from the file header (a `.dbf`), or None
        to infer the types from the values of the CSV at `path`."""
        matched, left = match(self.record.fields, columns, truncated)
        for unmatched in left:
            self.lines.append(
                f"{resource}: attribute {unmatched.name} has no column in {path}, "
                "so it is not imported"
            )
        for column in columns:
            if column not in matched:
                self.lines.append(
                    f"{resource}: column {column} has no attribute in the record, "
                    "so it has no description"
                )
        untyped = [c for c in columns if c not in matched or matched[c].type is None]
        if types is None:
            found = infer_types(self.root / path, untyped)
            how = "from its values"
        else:
            found = {c: types[c] for c in untyped}
            how = "from the .dbf header"
        for column in untyped:
            self.lines.append(
                f"{resource}: column {column} typed {found[column]} {how}, "
                "since the record declares no type"
            )
        out: list[dict[str, Any]] = []
        keys: list[dict[str, Any]] = []
        for column in columns:
            attribute = matched.get(column)
            entry: dict[str, Any] = {"name": column}
            if attribute is not None:
                described = attribute.dump()
                entry |= {k: v for k, v in described.items() if k != "name" and v is not None}
                if source_names and attribute.name != column:
                    entry["archive:sourceName"] = attribute.name
                code_list = self.record.code_lists.get(attribute.name)
                if code_list is not None:
                    keys.append(
                        {
                            "fields": [column],
                            "reference": {"resource": code_list, "fields": ["code"]},
                        }
                    )
                    if code_list not in self.codes_used:
                        self.codes_used.append(code_list)
            if column in found:
                entry["type"] = found[column]
            out.append(entry)
        schema: dict[str, Any] = {"fields": out}
        if keys:
            schema["foreignKeys"] = keys
        return schema

    def add_table(self, path: str, name: str, truncated: bool) -> str:
        name = self.name(name)
        columns = csv_columns(self.root / path)
        resource = {
            "name": name,
            "path": path,
            "type": "table",
            **(self.entity() or {"title": PurePosixPath(path).name}),
            "format": "csv",
            "mediatype": "text/csv",
            "encoding": "utf-8",
            **file_meta(self.root, path),
            "schema": self.schema(name, path, columns, None, truncated, source_names=True),
            "archive:kind": "table",
        }
        self.resources.append(resource)
        return name

    def add_alternate(self, path: str, primary: str) -> None:
        self.resources.append(
            {
                "name": self.name(f"{primary}-xlsx"),
                "path": path,
                "type": "table",
                "title": PurePosixPath(path).name,
                "format": "xlsx",
                "mediatype": XLSX_TYPE,
                **file_meta(self.root, path),
                "archive:kind": "table",
                "archive:alternateOf": primary,
            }
        )

    def add_vector(self, members: list[str]) -> None:
        name = self.name(self.base())
        main = next(m for m in members if m.lower().endswith(".shp"))
        dbf = next((m for m in members if m.lower().endswith(".dbf")), None)
        resource: dict[str, Any] = {
            "name": name,
            "path": main,
            **(self.entity() or {"title": PurePosixPath(main).name}),
            "format": "shp",
            "archive:kind": "vector",
            "archive:files": [{"path": m, **file_meta(self.root, m)} for m in members],
        }
        if dbf is not None:
            columns = dbf_columns(self.root / dbf)
            types = dict(columns)
            resource["archive:attributes"] = self.schema(
                name, dbf, [c for c, _ in columns], types, truncated=True, source_names=False
            )
        self.resources.append(resource)

    def add_raster(self, members: list[str]) -> None:
        main = next(m for m in members if PurePosixPath(m).name.lower() == "hdr.adf")
        self.resources.append(
            {
                "name": self.name(self.base()),
                "path": main,
                **(self.entity() or {"title": PurePosixPath(main).name}),
                "format": "adf",
                "archive:kind": "raster",
                "archive:files": [{"path": m, **file_meta(self.root, m)} for m in members],
            }
        )

    def add_file(self, path: str, kind: str) -> None:
        pure = PurePosixPath(path)
        resource: dict[str, Any] = {
            "name": self.name(slug(pure.stem)),
            "path": path,
            "title": pure.name,
            "format": pure.suffix.lstrip(".").lower(),
        }
        if pure.suffix.lower() in MEDIA:
            resource["mediatype"] = MEDIA[pure.suffix.lower()]
        resource |= {**file_meta(self.root, path), "archive:kind": kind}
        self.resources.append(resource)

    def add_linked(self, url: str) -> None:
        self.resources.append(
            {
                "name": self.name(self.base()),
                "path": url,
                **self.entity(),
                "archive:kind": "linked",
            }
        )

    def add_group(self, files: list[str]) -> None:
        """The files of one download, as resources: a grid, shapefile sets with the tables
        beside them, photographs, and anything else as a file."""
        if any(PurePosixPath(f).name.lower() == "hdr.adf" for f in files):
            self.add_raster(files)
            return
        left = list(files)
        shapefile_stems: set[str] = set()
        for shp in [f for f in files if f.lower().endswith(".shp")]:
            stem = shp[: -len(".shp")]
            members = [
                f
                for f in left
                if f.lower().startswith(stem.lower() + ".")
                and PurePosixPath(f).suffix.lower() not in SHAPEFILE_SIDECARS
            ]
            self.add_vector(sorted(members))
            left = [f for f in left if f not in members]
            shapefile_stems.add(stem.lower())
        csvs = [f for f in left if f.lower().endswith(".csv")]
        for path in csvs:
            stem = path[: -len(".csv")]
            beside_shapefile = stem.lower() in shapefile_stems
            wanted = f"{self.base()}-table" if beside_shapefile else self.base()
            primary = self.add_table(path, wanted, truncated=beside_shapefile)
            left.remove(path)
            for xlsx in [f for f in left if f.lower() == stem.lower() + ".xlsx"]:
                self.add_alternate(xlsx, primary)
                left.remove(xlsx)
        for path in left:
            kind = "media" if PurePosixPath(path).suffix.lower() in MEDIA else "file"
            self.add_file(path, kind)

    def unattached(self) -> None:
        """With nothing in the package to describe, the record's attributes are listed."""
        if any(r.get("schema") or r.get("archive:attributes") for r in self.resources):
            return
        for attribute in self.record.fields:
            self.lines.append(
                f"attribute {attribute.name}: no table in the package to describe, "
                "so it is not imported"
            )

    def write_code_lists(self) -> None:
        planned = {r.name: r for r in self.record.imported.manifest.resources}
        for name in self.codes_used:
            raw = planned[name].dump()
            path = raw["path"]
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream, lineterminator="\n")
                writer.writerow(CODE_COLUMNS)
                for row in self.record.imported.code_lists[name]:
                    writer.writerow([row[c] for c in CODE_COLUMNS])
            self.resources.append(raw | file_meta(self.root, path))


def _unzip(archive: Path, target: Path) -> list[Path]:
    """Unpack a zip into `target`, refusing a member that would land outside it."""
    written: list[Path] = []
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            pure = PurePosixPath(entry.filename)
            if pure.is_absolute() or ".." in pure.parts or "\\" in entry.filename:
                raise ValueError(f"{archive.name} holds {entry.filename!r}, outside the zip")
            if entry.is_dir():
                continue
            out = target.joinpath(*pure.parts)
            out.parent.mkdir(parents=True, exist_ok=True)
            with source.open(entry) as stream, out.open("wb") as sink:
                shutil.copyfileobj(stream, sink, 1 << 20)
            written.append(out)
    return written


def _record(xml: str) -> tuple[Record, Standardized]:
    standardized = standardize(xml)
    imported = from_eml(standardized.xml)
    record = Record(imported=imported)
    tables = [
        r
        for r in imported.manifest.resources
        if r.kind == "table" and r.name not in imported.code_lists
    ]
    if tables:
        record.table = tables[0].dump()
    if tables and tables[0].table_schema is not None:
        schema = tables[0].table_schema
        record.fields = list(schema.fields)
        for key in schema.foreign_keys or []:
            if key.reference.resource:
                record.code_lists[key.field_names()[0]] = key.reference.resource
    return record, standardized


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def convert(dataset: Path, sources: Path, out: Path) -> Path:
    """Write the dataset folder as a package at `out/<folder name>`, and return its path.

    Raises ValueError when SOURCES.md has no row for the folder, its license has no rule,
    the record can't be read, or the package folder already exists.
    """
    source = read_sources(sources, dataset.name)
    manifest_rights = rights(source.license)
    xml = (dataset / RECORD).read_text(encoding="utf-8")
    record, standardized = _record(xml)
    root = out / dataset.name
    if root.exists():
        raise ValueError(f"{root} already exists; remove it to convert again")
    root.mkdir(parents=True)
    try:
        _build(dataset, source, manifest_rights, record, standardized, root)
    except BaseException:
        shutil.rmtree(root)  # only the folder this call just made
        raise
    return root


def _build(
    dataset: Path,
    source: Source,
    manifest_rights: dict[str, Any],
    record: Record,
    standardized: Standardized,
    root: Path,
) -> None:
    builder = Builder(root=root, record=record)
    builder.lines += standardized.dropped + record.imported.skipped

    downloads = sorted(
        p
        for p in dataset.iterdir()
        if p.is_file() and p.name != RECORD and not p.name.startswith(".")
    )
    for download in downloads:
        if download.suffix.lower() == ".zip":
            folder = root / "data" / download.stem
            unpacked = _unzip(download, folder)
            builder.add_group(sorted(p.relative_to(root).as_posix() for p in unpacked))
        else:
            target = root / "data" / download.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(download, target)
            builder.add_group([target.relative_to(root).as_posix()])
    if not downloads and standardized.citation:
        found = LINKED_URL.search(standardized.citation)
        if found:
            builder.add_linked(found.group(1).rstrip(".,;)"))
    builder.unattached()
    builder.write_code_lists()

    (root / "original").mkdir()
    shutil.copyfile(dataset / RECORD, root / "original" / RECORD)
    builder.resources.append(
        {
            "name": builder.name("eml"),
            "path": f"original/{RECORD}",
            "title": "FEMC's EML record",
            "description": "The dataset's EML record as FEMC's archive serves it, unchanged.",
            "format": "xml",
            "mediatype": "application/xml",
            **file_meta(root, f"original/{RECORD}"),
            "archive:kind": "file",
        }
    )

    imported = record.imported.manifest.dump()
    legacy = list(imported.get("archive:legacyIdentifiers") or [])
    if standardized.object_name:
        legacy.append({"scheme": "femc-object", "value": standardized.object_name})
    raw: dict[str, Any] = {
        "$schema": PROFILE,
        "id": dataset.name,
        "name": dataset.name,
        "version": "1",
        "homepage": source.page,
    }
    raw |= {k: v for k, v in imported.items() if k not in ("name", "resources") and v is not None}
    raw |= manifest_rights
    raw["archive:access"] = access(source.data_file)
    if standardized.citation:
        raw["archive:citation"] = standardized.citation
    if legacy:
        raw["archive:legacyIdentifiers"] = legacy
    raw["resources"] = builder.resources
    manifest = Manifest.model_validate(raw)

    (root / MANIFEST).write_text(_json(manifest.dump()), encoding="utf-8")
    (root / "README.md").write_text(render_readme(manifest, record.imported.project), "utf-8")
    (root / BUILD).mkdir()
    if record.imported.project is not None:
        (root / BUILD / PROJECT).write_text(_json(record.imported.project.dump()), encoding="utf-8")
    (root / BUILD / NOT_IMPORTED).write_text(
        "".join(f"{line}\n" for line in builder.lines), encoding="utf-8"
    )
    _write_checksums(root)


def _write_checksums(root: Path) -> None:
    paths, _ = package_files(root)
    lines = (
        f"{file_meta(root, p)['hash'].removeprefix('sha256:')}  {p}\n"
        for p in paths
        if p != CHECKSUMS
    )
    (root / CHECKSUMS).write_text("".join(lines), encoding="utf-8")
