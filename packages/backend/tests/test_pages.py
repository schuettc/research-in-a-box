import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from archive_backend.pages import render_page
from archive_contract.manifest import Manifest

SAMPLE = Path(__file__).parents[3] / "examples" / "sample-package" / "datapackage.json"
DOMAIN = "d111.cloudfront.net"
FILES = ["README.md", "checksums.sha256", "data/logger.csv", "datapackage.json"]


def _manifest(**changes: Any) -> Manifest:
    raw = json.loads(SAMPLE.read_text(encoding="utf-8"))
    raw.update(changes)
    return Manifest.model_validate(raw)


class _Page(HTMLParser):
    """The page's text, links and JSON-LD blocks, as a browser would read them."""

    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []
        self.links: list[str] = []
        self.jsonld: list[str] = []
        self.scripts: list[dict[str, str | None]] = []
        self._in: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "a" and attributes.get("href"):
            self.links.append(str(attributes["href"]))
        if tag == "script":
            self.scripts.append(attributes)
            self._in = attributes.get("type")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in = None

    def handle_data(self, data: str) -> None:
        if self._in == "application/ld+json":
            self.jsonld.append(data)
        else:
            self.text.append(data)


def _parse(html: str) -> _Page:
    page = _Page()
    page.feed(html)
    return page


def test_the_page_escapes_a_script_in_the_title_and_holds_parsable_json_ld() -> None:
    title = 'Rain </script><script>alert("x")</script> & more'
    manifest = _manifest(title=title, id="rain-abcdef", version="2")

    html = render_page(manifest, dataset_id="rain-abcdef", version=2, domain=DOMAIN, files=FILES)
    page = _parse(html)

    assert "<script>alert" not in html
    assert [s.get("type") for s in page.scripts] == ["application/ld+json"]
    [block] = page.jsonld
    data = json.loads(block)
    assert data["@type"] == "Dataset"
    assert data["name"] == title
    assert data["url"] == f"https://{DOMAIN}/datasets/rain-abcdef"
    assert data["identifier"] == f"https://{DOMAIN}/datasets/rain-abcdef/v2"
    text = "".join(page.text)
    assert title in text
    assert "Version 2" in text


def test_an_open_page_links_every_file_under_its_version() -> None:
    manifest = _manifest(id="stream", version="1", **{"archive:access": "open"})

    html = render_page(manifest, dataset_id="stream", version=1, domain=DOMAIN, files=FILES)
    page = _parse(html)

    base = f"https://{DOMAIN}/data/stream/1/"
    assert f"{base}data/logger.csv" in page.links
    assert f"{base}datapackage.json" in page.links
    [data] = [json.loads(b) for b in page.jsonld]
    urls = [d["contentUrl"] for d in data["distribution"]]
    assert f"{base}data/logger.csv" in urls
    assert manifest.description is not None
    assert " ".join(manifest.description.split()) in "".join(page.text)
    assert re.search(r"Ada Invented", "".join(page.text))


def test_a_restricted_page_has_no_file_links() -> None:
    manifest = _manifest(id="stream", version="1", **{"archive:access": "restricted"})

    html = render_page(manifest, dataset_id="stream", version=1, domain=DOMAIN, files=FILES)
    page = _parse(html)

    assert not [link for link in page.links if "/data/" in link]
    [data] = [json.loads(b) for b in page.jsonld]
    assert "distribution" not in data
