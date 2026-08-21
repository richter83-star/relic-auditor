# Focused Flow

Relic Auditor v1.0.2 follows one product rule:

> One screen. One question. One primary action.

The redesign changes information architecture, not the evidence engines. Scanned targets remain read-only evidence. Technical Truth, Product Opportunities, Resurrection, deterministic Build Packs, provenance, entitlements, updater trust checks, Supervisor approvals, and the audit ledger keep their existing authority boundaries.

## Primary journey

| State | Question | Dominant action |
|---|---|---|
| `NO_TARGET` / `TARGET_SELECTED` | What should Relic analyze? | Scan this folder |
| `SCANNING` | What is happening? | None; cancellation remains available |
| `ANSWER_READY` | What do I have, is it valuable, and what should I do? | Prepare this product |
| `PREPARING_PRODUCT` | What exactly are we about to build? | Create Build Pack |
| `BUILD_PACK_READY` | What can I hand to a builder? | Start Assisted Build |
| `BUILD_SESSION_ACTIVE` | What exact approved action happens next? | Current Supervisor action |

Selecting a different target intentionally starts a new workflow. Completed reports remain in History. Opening a secondary surface never changes the active flow state.

## Answer contract

The Answer begins with a plain-English conclusion. It then shows the strongest opportunity, the reusable foundation, the work needing attention, and the recommended next move. Counts support these statements; they do not replace them.

Other opportunities, exports, and Technical Evidence are secondary. Raw evidence and provider diagnostics are not visible by default.

## Secondary surfaces

- **History** lists prior completed scans and opens from the header. It contains no current-workflow banner or global primary action.
- **Settings** contains Scan, Updates, Plan, Storage, and About categories. Update checks and plan information are not permanent header controls.
- **Technical Evidence** is the expert console. Its first tab is **Evidence Summary**, followed by Opportunities, Reusable Assets, Recommended Actions, System Map, Technical Truth, Reasoning, Duplicates, and Files.

Technical Evidence remembers its origin. Returning from evidence restores the originating Answer, Prepare, Build Pack, or Settings surface without discarding the active workflow.

## Evidence disclosure

Normal users receive the decision. Experts deliberately request the proof through contextual links such as View technical evidence and Review reusable assets. Advanced scan controls and provider health remain available in the expert surface and are hidden during normal Scan and Answer use.

## Plan presentation

The signed entitlement engine remains fail-closed. Because paid production activation is not provisioned, the v1.0.2 plan dialog contains no license-key field, Activate button, Deactivate button, or engineering placeholder. It presents Free and marks Pro and Premium as coming soon.

UI simplification never grants a capability. Free, Pro, and Premium enforcement remains in the domain services and cannot be changed by manipulating widgets.

## Update-error presentation

Updater validation remains fail-closed. Ordinary dialogs describe update unavailability without displaying raw HTTP, network, signature, or manifest exceptions. The exact diagnostic is retained under Settings → Updates and appears only after the user chooses Show technical diagnostics.

## Accessibility

Every primary action is keyboard reachable, has accessible text, and receives the existing visible focus treatment. Status meaning never relies on color alone. Secondary surfaces and Technical Evidence remain keyboard accessible, and modal review/approval dialogs retain explicit default focus and approval language.
