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
`d0e67e54a7315d5c2dd89746353868d5da10f37275a7f8e109554d99abca34e0`.

Wheel SHA-256:
`a348d873235fa37e7b8e55ce77ed643bd47a8f58d68be7af5504b2a5bebe24a1`.

Sdist SHA-256:
`29a51e2bb2215368a332094ef3bf25edef8bf4ec1b81053ba76eeb55f58717df`.
