# Build Pack schema and lifecycle

`build-pack.json` uses schema `1.0` and contains a stable `pack_id`, canonical
content SHA-256, selected Opportunity, scan fingerprint, brief, MVP scope,
architecture, ordered tasks, acceptance criteria, candidate assets, provenance,
risks, decisions, provider status, and the exact safety boundary.

Missing components are always `new_work` tasks. They never appear as reusable
assets. Every reusable candidate carries a source hash, destination, evidence
link, classification, policy reasons, license/provenance status, and the explicit
statement that ownership is not proven.

Lifecycle:

1. Load v0.8/v0.9 Opportunity through the compatibility adapter.
2. Refuse weak or documentation-only evidence.
3. Prepare a deterministic preview without copying assets.
4. Review eligible, review-required, and blocked classifications.
5. Create a versioned, content-addressed approval for exact path/hash/destination
   tuples. Review-required assets need an additional acknowledgement.
6. Revalidate source hashes and export atomically.
7. Verify canonical content, manifest, symlink/reparse safety, and checksums.

Old reports without hashes can produce a readable plan preview. Asset export
requires a current rescan; Relic never invents missing provenance.
