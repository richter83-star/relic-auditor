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
| `OPPORTUNITY_CHOOSER` | What other credible product directions did Relic find? | Select this opportunity |
| `OPPORTUNITY_SELECTED` | What does the selected product direction mean? | Prepare this product |
| `PREPARE_PRODUCT` | What exactly are we about to build? | Create Build Pack |
| `BUILD_PACK_GATE` | What does Premium add? | View Premium |
| `BUILD_PACK_READY` | What can I hand to a builder? | Start Assisted Build |
| `BUILD_SESSION_ACTIVE` | What exact approved action happens next? | Current Supervisor action |

Selecting a different target intentionally starts a new workflow. Completed reports remain in History. Opening a secondary surface never changes the active flow state.

## Answer contract

The Answer begins with a plain-English conclusion. It then emphasizes one product opportunity, a compact reusable-assets/attention summary, and the recommended next move.

Other opportunities opens a lightweight ranked chooser. Selecting a direction updates Answer and Prepare as view state over the same scan. A contextual **Why this?** link is the deliberate route from a product direction into its Technical Evidence.

## Secondary surfaces

- **History** lists prior completed scans and opens from the header. It contains no current-workflow banner or global primary action.
- **Settings** contains Scan, Reasoning, Updates, Plan, Storage, and About categories. Scan depth and provider setup apply to future scans.
- **Technical Evidence** is the expert console. Its first tab is **Evidence Summary**, followed by Opportunities, Reusable Assets, Recommended Actions, System Map, Technical Truth, Reasoning, Duplicates, and Files.

Technical Evidence remembers its origin. Returning from evidence restores the originating Answer, Prepare, Build Pack, or Settings surface without discarding the active workflow.

## Evidence disclosure

Normal users receive the decision. Experts deliberately request the proof through contextual links such as Why this?, View technical evidence, and Review reusable assets. Technical Evidence contains completed evidence and reasoning results, never scan configuration or provider setup/login controls.

## Plan presentation

The signed entitlement engine remains fail-closed. Because paid production activation is not provisioned, the v1.0.2 plan dialog contains no license-key field, Activate button, Deactivate button, or engineering placeholder. It presents Free and marks Pro and Premium as coming soon.

Free, Pro, and Premium users can inspect Answer, choose an opportunity, and review the Prepare screen. Premium is checked only when **Create Build Pack** is requested. UI simplification never grants that capability: domain services still independently enforce Build Pack preparation and export, so manipulating widgets cannot authorize it.

## Update-error presentation

Updater validation remains fail-closed. Ordinary dialogs describe update unavailability without displaying raw HTTP, network, signature, or manifest exceptions. The exact diagnostic is retained under Settings → Updates and appears only after the user chooses Show technical diagnostics.

## Accessibility

Every primary action is keyboard reachable, has accessible text, and receives the existing visible focus treatment. Status meaning never relies on color alone. Secondary surfaces and Technical Evidence remain keyboard accessible, and modal review/approval dialogs retain explicit default focus and approval language.
