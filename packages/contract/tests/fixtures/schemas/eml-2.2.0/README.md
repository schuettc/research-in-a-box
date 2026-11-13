# EML 2.2.0 XML Schemas

A test fixture: the EML export is validated against `eml.xsd` with lxml. Nothing at run time
reads it.

- **Files:** `eml.xsd`, the 24 `eml-*.xsd` modules it imports, `stmml.xsd` and `xml.xsd`, all
  unchanged. Every `schemaLocation` in them is a local file name, so validation needs no network.
- **Source:** <https://github.com/NCEAS/eml/tree/RELEASE_EML_2_2_0/xsd>
- **Repository and tag:** `NCEAS/eml` at tag `RELEASE_EML_2_2_0`, commit
  `233427f03610694d2a865e6748bcf8bfb51be900` (fetched 2026-11-13).
- **Licence:** the repository is licensed under the GNU General Public License v2.0 (its
  `LICENSE` file). The schemas are kept here only as test data and are not part of any built
  package.
