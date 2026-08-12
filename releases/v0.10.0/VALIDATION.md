# Relic Auditor 0.10.0 RC validation

- Recovered v0.8.3 source baseline: 259 passed, 1 skipped.
- v0.9 Opportunity Engine slice: 26 passed.
- v0.10 Product Builder Bridge slice: 47 passed.
- Complete repository suite: 338 passed, 1 skipped, 0 deselected.
- Extracted frozen-source suite: 332 passed, 1 skipped. The six installer-source
  tests are intentionally outside the frozen archive to avoid a circular hash.
- New and modified v0.9/v0.10 Python surfaces: Ruff format and lint passed.
- Build Pack domain: MyPy passed with no issues.
- Source/tests/scripts: compileall passed.
- Active and clean-wheel environments: dependency consistency passed.
- Wheel and sdist: built successfully from version 0.10.0.
- Clean wheel: CLI version, offline audit, default-Free entitlement, and offscreen
  Qt launch passed outside the repository.
- Frozen source: two builds were byte-identical.
- Representative Build Pack: two builds were byte-identical; canonical/checksum
  validation passed; target before/after tree hashes matched; no local absolute
  paths were serialized.
- Windows installer: hash-pinned inputs and full source-test gates prepared;
  native build, clean install/uninstall, Authenticode, and SmartScreen status are
  pending a separately approved remote workflow run.

Frozen source SHA-256:
`45d06bd992c4acb8b7de4414443c354f1094cf77ec0d9ca80c7082789619c5a4`.

Representative Build Pack SHA-256:
`d566f6cb9c1d13815952eb650406b3b5072b6f3403aa0583305d83711acf115d`.
Its canonical content SHA-256 is
`73996f91f056c8cd8565778371d7756df2ad9d41a5dd7b595feb25d50dba54c6`.
