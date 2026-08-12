# Product Builder Bridge architecture

Relic Auditor v0.10.0 turns one supported Opportunity into a deterministic,
evidence-linked Build Pack. It is a planning and handoff system, not a builder.

The canonical path is: compatibility loader → entitlement gate → deterministic
composer → asset policy → explicit content-addressed approval → atomic managed
export → render-only handoffs. CLI and Qt call the same service; neither owns
composition or policy logic.

The original target is read-only. Preview writes no assets. Export copies only
approved, hash-verified regular files into a newly created directory outside the
target. The bridge does not execute target code, launch a shell or coding agent,
install dependencies, use credentials, mutate Git, contact a remote, deploy, or
publish.

Optional provider enrichment is bounded to assumptions, questions, and market
hypotheses. It is disabled by default, receives redacted context, cannot add
assets or implementation claims, and degrades to deterministic output without
serializing provider exception text.
