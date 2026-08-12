# Entitlements and privacy

Production defaults to Free. Entitlements are injected at the engine boundary;
there is no promotion flag or environment-variable bypass.

| Tier | Capability |
|---|---|
| Free | Offline scan, findings, reusable-asset inventory, risks, actions, reports, exports; may state that Build Packs are an upgrade |
| Pro | Free plus evidence-backed Product Opportunities |
| Premium | Pro plus deterministic Build Pack, approved asset bundle, roadmap/GTM context, and Codex/Claude Code/generic handoffs |

Free and Pro serializers and UI state never receive the canonical Premium pack,
asset approval list, handoffs, roadmap internals, or provider context. Local
entitlement injection is a host integration seam, not a production licensing,
billing, or anti-tamper solution. v0.10 adds no Stripe, license server, or fake
security.

The deterministic path uses no credentials or network. A provider can be
injected only by a consenting host; Relic sends bounded redacted context and
falls back visibly when absent, denied, malformed, timed out, or failed.
