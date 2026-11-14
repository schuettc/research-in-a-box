"""The dataset page: `site/datasets/<id>/index.html`, served at `/datasets/<id>`.

One self-contained HTML file per dataset, rewritten at each publish: the title, description,
citation, current version, the file links when the data is open, and the schema.org JSON-LD
from the contract's export in the head. The readable content sits in `<div id="app">`, which the
web app's `/app.js` takes over; without the script the page still reads on its own. Every
manifest value is escaped; the JSON-LD escapes `<`, `>` and `&` so no value can close its
script element.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from html import escape
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from archive_contract.exports._common import creators, person_name
from archive_contract.exports.readme import citation as readme_citation
from archive_contract.exports.schemaorg import to_schemaorg
from archive_contract.manifest import Manifest

if TYPE_CHECKING:
    # Dev-only stubs: the Lambda asset is built without them.
    from mypy_boto3_s3 import S3Client

APP_SCRIPT = '<script type="module" src="/app.js"></script>'

# Scoped to the static <main>, a direct child of #app: once the web app renders over #app, its
# own markup sits a level deeper, so none of these rules reach it.
STYLE = (
    "#app>main{font-family:system-ui,sans-serif;max-width:46rem;margin:2rem auto;padding:0 1rem;"
    "line-height:1.5;color:#1b1b1b}#app>main h1{line-height:1.2}#app>main code{font-size:.95em}"
    "#app>main dl{display:grid;grid-template-columns:max-content 1fr;gap:.25rem 1rem}"
    "#app>main dd{margin:0}"
)


def page_url(domain: str, dataset_id: str) -> str:
    return f"https://{domain}/datasets/{dataset_id}"


def identifier(domain: str, dataset_id: str, version: int) -> str:
    """The version's stable identifier."""
    return f"{page_url(domain, dataset_id)}/v{version}"


def data_url(domain: str, dataset_id: str, version: int) -> str:
    """Where an open version's files are read, with a trailing slash."""
    return f"https://{domain}/data/{dataset_id}/{version}/"


def _jsonld(data: dict[str, Any]) -> str:
    text = json.dumps(data, indent=2, ensure_ascii=False)
    return text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


def schema_org(manifest: Manifest, *, dataset_id: str, version: int, domain: str) -> dict[str, Any]:
    """The contract's schema.org Dataset, with the page as its url and the stable identifier;
    open data's downloads point at its files, and other levels list none."""
    is_open = (manifest.access or "open") == "open"
    data = to_schemaorg(
        manifest,
        url=data_url(domain, dataset_id, version) if is_open else page_url(domain, dataset_id),
    )
    data["url"] = page_url(domain, dataset_id)
    data["identifier"] = identifier(domain, dataset_id, version)
    if not is_open:
        data.pop("distribution", None)
    return data


def render_page(
    manifest: Manifest,
    *,
    dataset_id: str,
    version: int,
    domain: str,
    files: Sequence[str] = (),
) -> str:
    """The dataset page for `version`, linking `files` when the data is open."""
    title = manifest.title or dataset_id
    access = manifest.access or "open"
    data = schema_org(manifest, dataset_id=dataset_id, version=version, domain=domain)
    lines = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape(title)}</title>",
    ]
    if manifest.description:
        summary = " ".join(manifest.description.split())
        lines.append(f'<meta name="description" content="{escape(summary)}">')
    lines += [
        f'<link rel="canonical" href="{escape(page_url(domain, dataset_id))}">',
        f"<style>{STYLE}</style>",
        f'<script type="application/ld+json">\n{_jsonld(data)}\n</script>',
        "</head>",
        "<body>",
        '<div id="app">',
        "<main>",
        f"<h1>{escape(title)}</h1>",
    ]
    if manifest.description:
        lines.append(f"<p>{escape(' '.join(manifest.description.split()))}</p>")
    ident = identifier(domain, dataset_id, version)
    facts = [
        ("Version", f"Version {version}"),
        ("Identifier", f'<a href="{escape(ident)}">{escape(ident)}</a>'),
        ("Access", escape(access)),
    ]
    if manifest.published:
        facts.append(("Published", escape(manifest.published.date().isoformat())))
    names = [n for n in (person_name(c) for c in creators(manifest)) if n]
    if names:
        facts.append(("Creators", escape(", ".join(names))))
    lines.append("<dl>")
    lines += [f"<dt>{label}</dt><dd>{value}</dd>" for label, value in facts]
    lines.append("</dl>")
    citation = readme_citation(manifest)
    if citation:
        lines += ["<h2>Citation</h2>", f"<p>{escape(citation)}</p>"]
    lines.append("<h2>Files</h2>")
    if access == "open" and files:
        base = data_url(domain, dataset_id, version)
        lines.append("<ul>")
        lines += [
            f'<li><a href="{escape(base + quote(path))}"><code>{escape(path)}</code></a></li>'
            for path in sorted(files)
        ]
        lines.append("</ul>")
    else:
        lines.append(f"<p>The files are {escape(access)}: ask the archive for access.</p>")
    lines += ["</main>", "</div>", APP_SCRIPT, "</body>", "</html>"]
    return "\n".join(lines) + "\n"


def page_key(dataset_id: str) -> str:
    return f"site/datasets/{dataset_id}/index.html"


def write_page(s3: S3Client, bucket: str, html: str, dataset_id: str) -> str:
    """Put the dataset page at `site/datasets/<id>/index.html` and return its key."""
    key = page_key(dataset_id)
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=html.encode("utf-8"),
        ContentType="text/html; charset=utf-8",
        # Short, so a later version's page shows within five minutes.
        CacheControl="max-age=300",
    )
    return key
