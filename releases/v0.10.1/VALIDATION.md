# Relic Auditor 0.10.1 RC validation

## Completed locally

- Source, scripts, and tests compile successfully with Python 3.12.
- CLI reports `relic 0.10.1`.
- Source-tree and clean-wheel offline audit smoke tests completed and wrote the
  expected report set outside the scanned target.
- Wheel and sdist built successfully from version 0.10.1.
- Two frozen-source builds were byte-identical.
- Frozen source contains no build, dist, release, or generated-artifact output.
- Staged changes pass `git diff --check`.

## Pending Windows gate

The current execution environment cannot download PySide6 or pytest, so the
complete repository suite, offscreen Qt regressions, PyInstaller build, clean
install, installed CLI/GUI smoke, uninstall, and Authenticode inspection must
pass in the hash-pinned `windows-latest` workflow before this installer is
called verified.

Frozen source SHA-256:
`46be88a88accea81885b40fc0618fd186b1b6be08640e1d8944a195874e6003a`.

Wheel SHA-256:
`8b7652242cc6b89b5ad0c586e74ffd4bc36bd32038018b4bf184b6ac90a794fe`.

Sdist SHA-256:
`c83a9da4e5e5b94077bc6444f1b2c9ab9578c845a5e57ad19a69157320b3a64c`.
