# Relic Auditor 1.0.2 RC — Windows installer

`Relic-Auditor-Setup-1.0.2-x64.exe` installs the focused-flow Relic Auditor 1.0.2 release candidate for the current Windows user.

This candidate preserves the validated v1.0.1 engines and security boundaries while simplifying the desktop journey to Scan → Answer → Prepare → Build. It remains an internal release candidate until the exact frozen-source and Windows lifecycle gates complete successfully.

## What it installs

- Evidence Console desktop application and Start menu shortcut
- `relic` command-line application, including `relic resurrect`, with an optional user-PATH entry enabled by default
- Product Builder Bridge / Build Pack support
- approval-gated Assisted Build Supervisor/runtime
- licensing, LLM health, and fail-closed updater/trust-root support
- Python 3.12, PySide6, keyring, and all required runtime files inside the application directory
- A normal Windows uninstaller

## Safety and persistence

- Installation is per-user by default and does not require administrator rights.
- Installing over v0.10.x, v0.11.x, or v0.12.x upgrades the same application in place; the stable AppId, install directory, shortcuts, and uninstall entry are reused.
- Managed PyInstaller runtime directories are refreshed during upgrade so stale dependencies do not accumulate.
- Scanned targets remain read-only and are never executed by the audit path.
- Assisted builds operate only inside Relic-managed workspaces and remain approval-gated.
- Uninstall removes the application and its exact CLI PATH entry.
- Uninstall preserves Relic profiles and configuration under `%APPDATA%\Relic Auditor` and never removes reports created elsewhere.

## Supported systems

- 64-bit Windows 10 version 1809 or newer
- 64-bit Windows 11

## Build prerequisite

Building the installer from source requires PowerShell 7.2 or later. The
installed application does not require PowerShell 7.

## Verify the installer artifact

Use PowerShell to calculate the installer SHA-256 and compare it with `SHA256SUMS.txt` from the same verified artifact set.

## Code signing

The release manifest records the Authenticode status. Unsigned artifacts are internal test builds. Relic's updater remains fail-closed and does not enable automatic installation unless the installer and update metadata satisfy the configured trust policy.
