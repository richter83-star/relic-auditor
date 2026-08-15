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
`a80211a87864f131fefb6bf58359c0db65ae8d74414b94cae8cd4560d63a4b3d`.

Wheel SHA-256:
`327434b01357d5847baea579787563e3ec2ba71fc7e9be05b8f20b8f820e38d8`.

Sdist SHA-256:
`b264fbf4c70dfa5b27816a3daefeda0ca568afb8e09591b0d04d6b34634f84fb`.
