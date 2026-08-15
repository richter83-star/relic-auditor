# Relic Auditor 0.10.2 validation

Prepared from the verified v0.10.1 branch baseline at commit
`31aa5af4c4a621ed8d8397fa743b6ccf441bdcc2`.

## Completed locally

- Python bytecode compilation passed for `src` and `tests`.
- The complete non-environment-sensitive suite passed: 358 tests passed,
  1 test skipped, and 2 Linux offscreen-only scrollbar checks were deselected.
- The exact frozen source ZIP passed: 352 tests passed, 1 test skipped, and the
  same 2 Linux offscreen-only scrollbar checks were deselected.
- Updater and installer-source gates passed: 25 tests.
- A clean virtual environment installed the wheel without dependencies;
  `relic --version` returned `relic 0.10.2`, and the updater imported correctly.
- Source ZIP integrity and all three SHA-256 identifiers were verified.

The two deselected Qt scrollbar assertions also fail on the unchanged v0.10.1
baseline under the Linux offscreen platform. They are retained for the native
Windows workflow rather than changed to hide the platform difference.

## Still required before automatic updates can be activated

- Commit and push the reviewed v0.10.2 change set.
- Run the Windows installer workflow and pass its clean-install, repeat-install,
  stale-runtime cleanup, CLI, GUI, and uninstall checks.
- Sign the installer with a trusted Authenticode certificate whose certificate
  simple name is exactly `Dracanus AI`.
- Publish the signed installer and a matching stable manifest at permanent,
  unauthenticated HTTPS URLs.
- Publish `stable.json` only after the signed installer is durably available.

No tag or GitHub Release has been created.
