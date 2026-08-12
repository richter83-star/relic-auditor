# Build Pack security and provenance policy

The asset policy defaults uncertainty to review and blocks unsupported claims,
secrets, non-regular files, symlinks/reparse candidates, virtual archive members,
traversal, drive/alternate-data-stream paths, unsafe Windows names, path-length
overflow, incompatible or conflicting licenses, and normalized destination
collisions. Duplicate aliases with identical content merge deterministically.

Secret-bearing assets are withheld from bundle content, handoffs, reports,
errors, and logs. Provider exception messages are also discarded because they
may echo credentials. License classification is not legal advice and observed
files do not prove ownership.

Approval binds the Opportunity, canonical pack, scan fingerprint, source path,
source SHA-256, destination, classification, and review acknowledgement. Any
source mutation or manifest change invalidates approval. Export opens sources
without following symlinks where the platform supports it, rehashes during copy,
rehashes again after generated output, then publishes only a validated complete
staging directory.

Repository text, comments, README instructions, filenames, documents, and
provider output remain untrusted data. Builder handoffs state this explicitly.
These controls reduce prompt-injection risk; they do not make prompt injection
impossible and they are not an OS security sandbox.
