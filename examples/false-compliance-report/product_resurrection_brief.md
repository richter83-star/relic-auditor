# Relic Product Resurrection Brief

> Offline, repository-derived hypothesis. No market validation or source execution was performed.

## Executive summary

Relic found **7** evidenced capabilities and **4** proposals that passed the quality gate.

## What the estate was intended to become

**Complete Compliance Cloud** — # Complete Compliance Cloud

## What it actually contains

finding, report, evaluate

## Most valuable reusable capabilities

- **Structured data ingestion** — Accepts and normalizes data or files for downstream work. (53% completion signal)
- **Traceable reporting** — Turns system results into a reviewable report or dashboard. (85% completion signal)
- **Scoring and evaluation** — Applies repeatable evaluation or scoring to inputs. (53% completion signal)
- **Workflow orchestration** — Coordinates multi-step or asynchronous work. (40% completion signal)
- **Compliance gap analysis** — Compares evidence or policies against defined requirements. (53% completion signal)
- **User access control** — Identifies users and controls access. (40% completion signal)
- **Commercial billing** — Supports payment, subscription, or invoice workflows. (40% completion signal)

## Hidden products discovered

| Rank | Product | Score | Evidence | Effort | Why it may fail |
|---:|---|---:|---:|---|---|
| 1 | Traceable compliance gap assessment | 55 | 71 | moderate | Reject if prospects do not rank the triggering event as urgent or no paid pilot emerges. |
| 2 | Bulk intake and qualification service | 55 | 59 | moderate | Reject if prospects do not rank the triggering event as urgent or no paid pilot emerges. |
| 3 | Workflow reliability diagnostic | 42 | 65 | moderate | Reject if prospects do not rank the triggering event as urgent or no paid pilot emerges. |
| 4 | Reusable paid-workflow launch shell | 42 | 47 | high | Reject if prospects do not rank the triggering event as urgent or no paid pilot emerges. |

## Recommended primary product

**Traceable compliance gap assessment** — The repository contains components that could support traceable compliance gap assessment; a working product was not technically verified.

## Recommended near-term revenue product

**Workflow reliability diagnostic** — The repository contains components that could support workflow reliability diagnostic; a working product was not technically verified.

## Most surprising product opportunity

**Reusable paid-workflow launch shell** — The repository contains components that could support reusable paid-workflow launch shell; a working product was not technically verified.

## Extraction plan

- Reuse: dashboard.tsx, evaluator.py, report.py, schema.py, tests/test_evaluator.py
- Rewrite: Any interface that directly couples the workflow to unrelated product modules
- Relative effort: **moderate**

## GTM plan

For compliance teams experiencing a policy or control set must be reviewed before an audit, Traceable compliance gap assessment provides a bounded traceable compliance gap assessment with a traceable evidence report. Unlike manual code archaeology or generic consulting, it uses the repository-supported compliance gap analysis, traceable reporting capabilities.

## 30-day validation plan

- Experiments: 15 interviews, 3 concierge demos, At least 1 explicitly paid pilot request
- Success: Two paid pilots or one paid pilot plus three concrete follow-ups
- Kill: Zero prospects describe the trigger as urgent and zero paid commitment after 30 qualified contacts
- Pivot: Repeated demand for a different output supported by the same capabilities

## Risks and counterarguments

- Demand has not been externally validated
- Evidence may describe disconnected prototypes

## What should not be built

- Do not complete unrelated flagship scope before a buyer validates the narrow workflow.
- Do not add a marketplace, autonomous agent layer, or broad dashboard without repository and customer evidence.

## Unknowns requiring human confirmation

- Who has paid for this outcome?
- Can the workflow handle representative customer data safely?

## Repository evidence appendix

- `ev_0dcc6dbd8d15` — `billing.py` lines 1-1 (implementation_signal, confidence 0.72)
- `ev_255a5a0ec1d2` — `tests/test_evaluator.py` lines 1-7 (test, confidence 0.9)
- `ev_360f3bfbda66` — `schema.py` lines 4-8 (schema, confidence 0.9)
- `ev_40ba53f1c350` — `README.md` lines 1-3 (stated_intent, confidence 0.72)
- `ev_6738ec3f2cca` — `report.py` lines 1-2 (implementation_signal, confidence 0.72)
- `ev_7f3a1a1a3c48` — `app.py` lines 1-12 (implementation_signal, confidence 0.72)
- `ev_849ff7105ab6` — `evaluator.py` lines 1-6 (implementation_signal, confidence 0.72)
- `ev_99928290d461` — `dashboard.tsx` lines 2-4 (user_interface, confidence 0.72)
- `ev_c6f1b3ec905d` — `service.py` lines 3-4 (implementation_signal, confidence 0.72)
