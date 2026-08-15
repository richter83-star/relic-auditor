# Windows updater contract

Relic's updater is application maintenance, not scan behavior. It never accepts
a scan target and does not weaken the read-only/no-execution boundary applied
to inspected software.

## Stable manifest

Installed builds request this first-party HTTPS resource:

`https://relic-auditor.briandrichter.chatgpt.site/downloads/stable.json`

The response must be UTF-8 JSON no larger than 128 KiB:

```json
{
  "schema_version": 2,
  "key_id": "update-2026-01",
  "channel": "stable",
  "version": "0.12.0",
  "published_at": "2026-08-15T03:00:00Z",
  "release_notes": [
    "Short user-facing change.",
    "Another short user-facing change."
  ],
  "release_notes_url": "https://relic-auditor.briandrichter.chatgpt.site/releases/0.12.0",
  "installer": {
    "filename": "Relic-Auditor-Setup-0.12.0-x64.exe",
    "url": "https://relic-auditor.briandrichter.chatgpt.site/downloads/Relic-Auditor-Setup-0.12.0-x64.exe",
    "sha256": "<64 lowercase hexadecimal characters>",
    "size": 69554266
  },
  "signature": "<base64url Ed25519 signature over every preceding field>"
}
```

Publish the installer first, verify the public bytes, and publish the manifest
last. To withdraw an update, point the manifest back to the last trusted
installer; never reuse a version number for different bytes.

## Client gates

1. Only the stable channel and signed schema version 2 are trusted by the
   production fetch path. Legacy schema 1 can be parsed only by local tooling.
2. The Ed25519 signature must verify under a pinned update key before any
   version or installer claim is trusted.
3. Manifest, release-notes, installer, and redirect URLs must be credential-free
   absolute HTTPS URLs.
4. The filename must be a basename ending in `.exe`.
5. Download size is declared exactly and capped at 750 MiB.
6. Download is written to a `.part` file, flushed, hashed, and atomically
   renamed only after size and SHA-256 match.
7. Superseded Relic installer downloads are removed from the private update
   cache; unrelated files are never selected for cleanup.
8. Windows Authenticode status must be `Valid` and the certificate simple name
   must exactly match the publisher pinned in the application: `Dracanus AI`.
9. Size, digest, and publisher are checked again immediately before launch.
10. The installer is launched without a shell and with fixed Inno Setup
   arguments. The application exits only after launch succeeds.

## Cadence and failure behavior

Packaged builds check at most once every 24 hours. A failed check retries after
six hours. Source checkouts never check automatically. Network, JSON, download,
hash, signature, and launch failures are non-destructive: the installed version
continues to run, and automatic failures do not interrupt the operator.

## Release-order requirement

Do not activate the stable manifest until the Windows build is signed by the
pinned publisher and hosted at a permanent public URL. GitHub Actions artifacts
expire, and clients cannot authenticate to the private source repository.
