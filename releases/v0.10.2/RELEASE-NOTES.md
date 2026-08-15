# Relic Auditor 0.10.2 release candidate

v0.10.2 adds the first-party Windows updater foundation and makes repeat
installation an explicit in-place upgrade path.

- Installed builds check the stable channel at most once every 24 hours; failed
  checks retry no sooner than six hours and leave Relic usable offline.
- **Check updates** stays visible beside the installed version.
- Updates follow three explicit steps: compare versions, download and verify,
  then install. Relic never silently installs or interrupts an active audit.
- HTTPS, exact size, SHA-256, and a valid Authenticode certificate whose simple
  name exactly matches `Dracanus AI` are required before an installer can run.
- Size, digest, and publisher are checked again immediately before launch.
- Superseded Relic installer downloads are removed from the private update
  cache, so old versions do not accumulate.
- Repeat installation uses the same Inno Setup identity and per-user directory,
  refreshes stale PyInstaller runtime files, and preserves reports and settings.

Automatic installation remains blocked for unsigned builds. Production
activation requires a permanent public stable-manifest endpoint and a trusted
Dracanus AI code-signing certificate.

No Git tag or GitHub Release is created or authorized by this release candidate.
