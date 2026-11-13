import json
from pathlib import Path

from archive_contract.schema import main


def test_writes_json_schema_with_title(tmp_path: Path) -> None:
    out = tmp_path / "schema.json"

    main([str(out)])

    schema = json.loads(out.read_text(encoding="utf-8"))
    assert schema["title"] == "ArchiveContract"
