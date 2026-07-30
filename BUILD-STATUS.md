# Build status

The Relic Auditor 0.8.2 Windows installer source and release automation are complete.

## Verified locally

- Frozen v0.8.2 archive SHA-256 matches `de4b55657b60074cdf70fc0c01a116c75425324bcdda93f1ec777ae7e3582ff1`.
- Installer source safeguards pass.
- Python entry points compile.
- Icon and Inno Setup wizard assets render correctly.
- No Relic analysis-engine file was modified.

## Remaining external build step

The final `.exe` must be compiled on 64-bit Windows because PyInstaller is not a cross-compiler. The included GitHub Actions workflow performs that build, runs the full 247-test Relic suite, exercises the bundled and installed GUI/CLI, validates uninstall and configuration preservation, and emits the installer plus SHA-256 and release manifest.

The approved release target is the public `installer/v0.8.2` branch. Publishing
the branch triggers the canonical Windows build automatically.
