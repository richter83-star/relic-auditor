# Relic Auditor 0.10.0 — Windows installer

`Relic-Auditor-Setup-0.10.0-x64.exe` installs the frozen Relic Auditor 0.10.0 release for the current Windows user.

## What it installs

- Evidence Console desktop application and Start menu shortcut
- `relic` command-line application, with an optional user-PATH entry enabled by default
- Python 3.12, PySide6, keyring, and all required runtime files inside the application directory
- A normal Windows uninstaller

No separate Python installation and no manual PATH setup are required. The installer does not install or authenticate Claude Code. If Claude Max reasoning is used, the official `claude` command must already be installed and signed in with the intended subscription account.

## Safety and persistence

- Installation is per-user by default and does not require administrator rights.
- Relic retains its read-only/no-execution boundary for scanned targets.
- Uninstall removes the application and its exact CLI PATH entry.
- Uninstall deliberately preserves Relic profiles and configuration under `%APPDATA%\Relic Auditor` and never removes reports created elsewhere.

## Supported systems

- 64-bit Windows 10 version 1809 or newer
- 64-bit Windows 11

## Verify the download

From PowerShell in the download folder:

```powershell
Get-FileHash ".\Relic-Auditor-Setup-0.10.0-x64.exe" -Algorithm SHA256
```

Compare the result with `SHA256SUMS.txt` from the same release.

## Code signing

The release manifest records the Authenticode status. An unsigned build is suitable for internal testing but Windows SmartScreen may warn until the installer is signed with a trusted code-signing certificate and has accumulated reputation.
