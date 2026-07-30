# Build status

The Relic Auditor 0.8.1 Windows installer source and release automation are complete.

## Verified locally

- Frozen v0.8.1 archive SHA-256 matches `a6959b5747287785196f7319cb097f10621fa06df457727546c62edee8bb819a`.
- Installer source safeguards pass.
- Python entry points compile.
- Icon and Inno Setup wizard assets render correctly.
- No Relic analysis-engine file was modified.

## Remaining external build step

The final `.exe` must be compiled on 64-bit Windows because PyInstaller is not a cross-compiler. The included GitHub Actions workflow performs that build, runs the full 247-test Relic suite, exercises the bundled and installed GUI/CLI, validates uninstall and configuration preservation, and emits the installer plus SHA-256 and release manifest.

Publishing the workflow and frozen source transport to the public `richter83-star/relic-auditor` repository requires the repository owner's explicit approval. No branch or commit was created before that approval gate.
