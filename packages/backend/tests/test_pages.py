import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from archive_backend.pages import PageBrand, page_brand, render_page, write_page
from archive_contract.config import ArchiveConfig
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
        self.app_text: list[str] = []
        self.apps = 0
        self._in: str | None = None
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "div":
            if self._depth:
                self._depth += 1
            elif attributes.get("id") == "app":
                self.apps += 1
                self._depth = 1
        if tag == "a" and attributes.get("href"):
            self.links.append(str(attributes["href"]))
        if tag == "script":
            self.scripts.append(attributes)
            self._in = attributes.get("type")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in = None
        if tag == "div" and self._depth:
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in == "application/ld+json":
            self.jsonld.append(data)
        else:
            self.text.append(data)
            if self._depth:
                self.app_text.append(data)


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
    assert [s.get("type") for s in page.scripts] == ["application/ld+json", "module"]
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


def test_the_page_holds_the_app_root_and_loads_the_app() -> None:
    html = render_page(
        _manifest(id="stream", version="1"),
        dataset_id="stream",
        version=1,
        domain=DOMAIN,
        files=FILES,
    )
    page = _parse(html)

    assert page.apps == 1
    assert {"type": "module", "src": "/app.js"} in page.scripts
    assert [s.get("type") for s in page.scripts] == ["application/ld+json", "module"]


def test_a_script_in_the_title_is_still_escaped_inside_the_app_root() -> None:
    title = 'Rain </script><script>alert("x")</script> & more'
    html = render_page(
        _manifest(title=title, id="rain", version="1"),
        dataset_id="rain",
        version=1,
        domain=DOMAIN,
        files=FILES,
    )
    page = _parse(html)

    assert "<script>alert" not in html
    assert title in "".join(page.app_text)
    assert "Version 1" in "".join(page.app_text)


class _S3:
    def __init__(self) -> None:
        self.puts: list[dict[str, Any]] = []

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.puts.append(kwargs)
        return {}


def test_write_page_puts_the_html_at_the_dataset_page_key() -> None:
    s3 = _S3()

    key = write_page(s3, "derived", "<p>hi</p>", "stream")  # type: ignore[arg-type]

    assert key == "site/datasets/stream/index.html"
    assert s3.puts == [
        {
            "Bucket": "derived",
            "Key": "site/datasets/stream/index.html",
            "Body": b"<p>hi</p>",
            "ContentType": "text/html; charset=utf-8",
            "CacheControl": "max-age=300",
        }
    ]


def test_the_static_style_applies_only_to_the_static_content() -> None:
    html = render_page(
        _manifest(id="stream", version="1"),
        dataset_id="stream",
        version=1,
        domain=DOMAIN,
        files=FILES,
    )
    style = html.split("<style>", 1)[1].split("</style>", 1)[0]

    # Once the app renders over #app, its own header and main sit in a div inside #app, so the
    # static page's rules must reach only #app's direct static children, never body or a bare dl.
    rules = [rule.split("{", 1)[0] for rule in style.split("}") if "{" in rule]
    assert rules
    assert all(selector.startswith("#app>") for rule in rules for selector in rule.split(","))


def test_a_versioned_page_names_its_version_and_links_the_current_one() -> None:
    html = render_page(
        _manifest(id="stream", version="2"),
        dataset_id="stream",
        version=2,
        domain=DOMAIN,
        files=FILES,
        versioned=True,
    )
    page = _parse(html)

    assert f'<link rel="canonical" href="https://{DOMAIN}/datasets/stream/v2">' in html
    assert "/datasets/stream" in page.links
    assert f"https://{DOMAIN}/data/stream/2/data/logger.csv" in page.links
    assert "Version 2" in "".join(page.app_text)
    assert "latest version" in "".join(page.app_text)


def test_a_versioned_page_escapes_manifest_text_as_the_current_one_does() -> None:
    title = "<script>alert(1)</script> & co"
    for versioned in (False, True):
        html = render_page(
            _manifest(id="stream", version="1", title=title, description="<b>bold</b>"),
            dataset_id="stream",
            version=1,
            domain=DOMAIN,
            files=FILES,
            versioned=versioned,
        )
        assert "<script>alert" not in html
        assert "<b>bold</b>" not in html
        assert title in "".join(_parse(html).app_text)


def test_the_page_takes_the_brands_name_logo_and_colour() -> None:
    brand = PageBrand(name="Lake <Works>", logo="/brand/logo.svg", color="#0b6e4f")
    html = render_page(
        _manifest(id="stream", version="1"),
        dataset_id="stream",
        version=1,
        domain=DOMAIN,
        files=FILES,
        brand=brand,
    )

    assert "Lake &lt;Works&gt;" in html
    assert '<img src="/brand/logo.svg" alt=""' in html
    assert "#0b6e4f" in html
    assert "/" in _parse(html).links


def test_the_page_brand_comes_from_the_config_with_defaults() -> None:
    plain = page_brand(ArchiveConfig.model_validate({"publisher": "Coop"}))
    assert plain == PageBrand(name="Coop", logo=None, color="#24395f")
    branded = page_brand(
        ArchiveConfig.model_validate(
            {"publisher": "Coop", "brand": {"logo": "brand/Logo.PNG", "primaryColor": "#112233"}}
        )
    )
    assert branded == PageBrand(name="Coop", logo="/brand/logo.png", color="#112233")


def test_write_page_puts_a_versioned_page_under_its_version() -> None:
    s3 = _S3()

    key = write_page(s3, "derived", "<p>hi</p>", "stream", version=3)  # type: ignore[arg-type]

    assert key == "site/datasets/stream/v3/index.html"
    assert s3.puts[0]["Key"] == key
