# EML 2.2.0 XML Schemas

A test fixture: the EML export is validated against `eml.xsd` with lxml. Nothing at run time
reads it.

- **Files:** `eml.xsd`, the 24 `eml-*.xsd` modules it imports, `stmml.xsd` and `xml.xsd`, all
  unchanged. Every `schemaLocation` in them is a local file name, so validation needs no network.
- **Source:** <https://github.com/NCEAS/eml/tree/RELEASE_EML_2_2_0/xsd>
- **Repository and tag:** `NCEAS/eml` at tag `RELEASE_EML_2_2_0`, commit
  `233427f03610694d2a865e6748bcf8bfb51be900` (fetched 2026-11-13).
- **Licence:** the repository is licensed under the GNU General Public License v2.0. Its
  `LICENSE` file, from the same commit and unchanged, sits next to the schemas here as
  `LICENSE` (sha256 `b8d0e2bcbf36f6af3cdbf94055ad2ea675d5a19fc623eb0ec82febb2b08e719b`). The
  schemas are kept here only as test data and are not part of any built package.
