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

## Windows workflow

GitHub Actions run `31870696979` passed on commit
`9d6c23059e6b3adc06a615f93022bea32af757fc`. The hash-pinned Windows workflow
completed all of these release gates:

- source tests with no exclusions;
- bundled CLI and GUI smoke tests;
- clean installation;
- repeat installation into the same application directory;
- stale PyInstaller runtime cleanup;
- installed CLI and GUI smoke tests;
- uninstall with user configuration preserved; and
- CLI PATH cleanup.

Verified Windows installer:

- file: `Relic-Auditor-Setup-0.10.2-x64.exe`
- size: `69,593,574` bytes
- SHA-256: `745c720c1a15af3aa5c7920a642b1716eee9ef2fe4e67bcaeb765a95335cd328`
- Authenticode: `NotSigned`
- workflow artifact: `9243382828`
- artifact ZIP SHA-256:
  `726f67b628f5b45961fb16bfd51cbaafeb2517a2cc1479f9504c7172d8211719`

The unsigned installer is verified for manual testing, but the in-application
updater correctly refuses to run it.

## Still required before automatic updates can be activated

- Sign the installer with a trusted Authenticode certificate whose certificate
  simple name is exactly `Dracanus AI`.
- Publish the signed installer and a matching stable manifest at permanent,
  unauthenticated HTTPS URLs.
- Publish `stable.json` only after the signed installer is durably available.

No tag or GitHub Release has been created.
