# Relic Auditor 0.12.0 — Windows installer

`Relic-Auditor-Setup-0.12.0-x64.exe` installs the frozen Relic Auditor 0.12.0 release candidate for the current Windows user.

## What it installs

- Evidence Console desktop application and Start menu shortcut
- `relic` command-line application, with an optional user-PATH entry enabled by default
- Python 3.12, PySide6, keyring, and all required runtime files inside the application directory
- A normal Windows uninstaller
- A visible stable-channel update checker with verified installer handoff

No separate Python installation and no manual PATH setup are required. The installer does not install or authenticate Claude Code. If Claude Max reasoning is used, the official `claude` command must already be installed and signed in with the intended subscription account.

## Safety and persistence

- Installation is per-user by default and does not require administrator rights.
- Installing over v0.10.x or v0.11.0 upgrades the same application in place;
  the stable AppId, install directory, shortcuts, and uninstall entry are reused.
- Managed PyInstaller runtime directories are refreshed during upgrade so stale
  dependencies do not accumulate.
- Relic retains its read-only/no-execution boundary for scanned targets.
- Uninstall removes the application and its exact CLI PATH entry.
- Uninstall deliberately preserves Relic profiles and configuration under `%APPDATA%\Relic Auditor` and never removes reports created elsewhere.

## Supported systems

- 64-bit Windows 10 version 1809 or newer
- 64-bit Windows 11

## Verify the download

From PowerShell in the download folder:

```powershell
Get-FileHash ".\Relic-Auditor-Setup-0.12.0-x64.exe" -Algorithm SHA256
```

Compare the result with `SHA256SUMS.txt` from the same release.

## Code signing

The release manifest records the Authenticode status. An unsigned build is suitable for internal testing but Windows SmartScreen may warn until the installer is signed with a trusted code-signing certificate and has accumulated reputation.

Relic's built-in updater is stricter than a manual install: it will not enable
**Install update** unless Windows validates a signature from the pinned
Dracanus AI publisher. Automatic checking can therefore ship in an internal
unsigned build, but verified in-app installation remains blocked until the
Windows workflow receives the trusted code-signing certificate.
