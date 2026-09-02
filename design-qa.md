# Relic Auditor v1.0.3 Design QA

## Comparison target

- Source visual truth: the two v1.0.2 desktop captures supplied during the
  focused-flow review.
- Rendered implementation: native Qt offscreen captures at 1920 × 1080 and
  the supported 960 × 600 minimum.
- Renderer: native PySide6/Qt offscreen platform. A browser-rendered screenshot is not applicable to this Windows desktop application.
- State:
  - Opportunity chooser with the highest-ranked opportunity selected.
  - Contextual Technical Evidence opened for `Reusable paid-workflow launch shell`, with the scoped row selected and its complete record visible.

## Viewports and normalization

| Artifact | Pixels | Logical/CSS size | Density handling |
|---|---:|---:|---|
| v1.0.2 opportunity source | 2048 × 1386 | Native desktop capture; CSS not applicable | Source density metadata unavailable; aspect ratio preserved |
| v1.0.2 evidence source | 2048 × 1360 | Native desktop capture; CSS not applicable | Source density metadata unavailable; aspect ratio preserved |
| v1.0.3 desktop implementation | 1920 × 1080 | 1920 × 1080 Qt logical viewport | Qt offscreen capture at environment density; no resampling in the implementation evidence |
| v1.0.3 minimum implementation | 960 × 600 | 960 × 600 Qt logical viewport | Qt offscreen capture at environment density; no resampling in the implementation evidence |

The source and implementation have different native frame dimensions. The comparison sheets fit each full capture into an equal 960 × 720 bounding box while preserving aspect ratio. Findings therefore use relative hierarchy, density, wrapping, control visibility, and state—not false pixel-perfect alignment. The focused chooser comparison crops the equivalent decision region from each native capture before equal-box scaling.

## Durable comparison evidence

The review captures were session evidence and are intentionally not represented
as repository files. Durable regression coverage lives in
`tests/test_focused_flow_v102.py`, which verifies hierarchy, focus, selection,
responsive behavior, contextual evidence state, and control visibility.

## Findings

No actionable P0, P1, or P2 findings remain.

- Fonts and typography: the existing Bahnschrift/Segoe UI fallback hierarchy is preserved. Row titles, decision context, and action labels remain readable at 1920 × 1080 and 960 × 600 without horizontal truncation of controls.
- Spacing and layout rhythm: six repeated cards are replaced by a compact ranked list, a single selected-opportunity preview, and one primary action. The decision controls remain above the fold at the 960 × 600 supported minimum.
- Colors and visual tokens: selected list and table rows use the existing yellow selection tokens; secondary rows retain muted text and panel/border tokens. Focus and selection no longer fall back to the system-blue Qt style.
- Image quality and asset fidelity: these screens contain no product imagery, illustrations, or custom icons requiring raster/vector substitution. The existing Relic wordmark treatment remains unchanged.
- Copy and content: the chooser explicitly says to choose a row and then use the single primary action. Technical Evidence says `Scoped to opportunity`, and the tab count says `1 scoped`.
- Behavior and accessibility: the chooser is keyboard focusable, has accessible naming and description, disables horizontal scrolling, supports double-click selection, and exposes one primary action. Contextual evidence filters to the originating opportunity, selects it, and immediately populates the full-record pane. Closing Technical Evidence restores the complete opportunity table.
- Responsive resilience: the 960 × 600 render keeps the ranked chooser, selected preview, primary action, secondary evidence action, and return navigation visible without overlap. The list scrolls vertically when all six rows cannot fit.

## Comparison history

### Iteration 1

- Earlier finding: **P2 — chooser selection used the host system-blue highlight and unstyled white list rows**, which broke Relic's yellow selection semantics and made the new chooser look like an unfinished Qt default.
- Fix: added token-driven `QListWidget` surface, row, hover, selected, and focus rules in `src/relic_auditor/dashboard/theme.py`.
- Result: selected rows now use Relic yellow, secondary rows use the dark panel system, and keyboard focus remains visible.

## Primary interactions tested

- Open opportunity chooser.
- Move selection between ranked rows and update the preview.
- Select the highlighted opportunity with the single primary action.
- Open contextual Technical Evidence from the highlighted opportunity.
- Confirm one scoped row is selected and the detail pane is populated.
- Return to the chooser and confirm the complete evidence table is restored.
- Exercise the chooser at the 960 × 600 supported minimum.

Qt render emitted no application warnings or errors. The exact candidate test
count is recorded by the pull-request source and Windows jobs rather than being
copied into this design record.

## Implementation checklist

- [x] Compact ranked opportunity comparison.
- [x] One primary decision action.
- [x] Opportunity-scoped Technical Evidence.
- [x] Default selected evidence row and populated detail pane.
- [x] Keyboard focus, accessible labels, and minimum-viewport checks.
- [x] Token-consistent list selection and focus styling.

final result: passed
