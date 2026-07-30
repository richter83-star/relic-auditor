# Relic Auditor 0.8.2 Windows installer build kit

This build kit treats `releases/relic-auditor-0.8.2.zip` as an immutable release input. The build fails unless its SHA-256 is:

`de4b55657b60074cdf70fc0c01a116c75425324bcdda93f1ec777ae7e3582ff1`

It does not patch or regenerate the Relic analysis engine. On a Windows x64 build host it:

1. extracts and verifies the frozen source;
2. creates an isolated Python 3.12 build environment;
3. runs the full Relic test suite;
4. builds separate windowed Evidence Console and console CLI bundles;
5. smoke-tests audit, acquire, and a real Qt widget tree;
6. compiles a per-user Inno Setup installer;
7. installs to a clean location and repeats the CLI/GUI smoke tests;
8. uninstalls and verifies that user configuration survives and PATH is cleaned;
9. writes the installer, release manifest, and SHA-256 file.

## Automated build

The GitHub workflow is the canonical build path. Push this kit to the `installer/v0.8.2` branch or dispatch `Build Relic Auditor Windows Installer` manually.

The source ZIP, wheel, source distribution, release notes, validation record,
and checksums are under `releases/`.

## Local Windows build

Install Python 3.12 x64 and Inno Setup 6, then run from the kit root:

```powershell
.\installer\windows\build-installer.ps1
```

The installed application is self-contained; end users do not need Python.

## Optional Authenticode signing

For GitHub Actions, configure:

- `WINDOWS_SIGNING_PFX_BASE64`
- `WINDOWS_SIGNING_PFX_PASSWORD`

If those secrets are absent, the workflow intentionally produces an unsigned internal-test build and records `NotSigned` in `release-manifest.json`.
