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
`e10c5015afc42f324e474c2d1be27c7c6e3c8e65f43d6ab5190b0934e74144f8`.

Wheel SHA-256:
`3d9fdf72a63ebd95f7689aa757371bb7dd9a5a99e7c35f0365c3775681b0efa3`.

Sdist SHA-256:
`f52f766fbc36a9ca07d20515aad6f6c58aea71511bfecc23ac5d6320594e5683`.
