# Relic Technical Truth Report

> Static analysis only. Scanned source was not imported, executed, built, tested, migrated, or modified.

## Executive technical conclusion

This repository is not verified as the complete product described by its documentation. The strongest connected evidence is an authenticated document-ingestion prototype. Rule evaluation is implemented but disconnected. The analysis path stops after queue production because no matching production consumer is connected. Reporting is implemented but disconnected. At least one user-visible screen renders mock data. Billing is configured or mentioned but not implemented as a verified production workflow.

> Evidence gate passed. Negative conclusions remain limited to the specific project families and static evidence cited below.

Relic parsed **8** files, detected **10** symbols and **29** relationships, reconstructed **2** workflows, and verified **0** end-to-end workflows.

## What the software claims to do

Documentation/code contradictions detected: **6**.

## Observed capability evidence

- **Rule-based evaluation** — implemented but disconnected (moderate evidence)
- **Persistent data storage** — partially implemented (moderate evidence)
- **Document or file ingestion** — partially implemented (moderate evidence)
- **Subscription billing** — contradicted (weak evidence)
- **Authenticated user access** — partially implemented (moderate evidence)
- **Report generation and delivery** — implemented but disconnected (moderate evidence)

## Project-family map

- `.`: . — independent_project (0.7)

## Language and framework coverage

- Coverage: 100%
- Languages: {"python": 7, "typescript": 1}

## Verified application surfaces

- Framework evidence: FastAPI
- Endpoints: 2
- UI screens: 1
- UI actions: 0
- Schemas: 3
- Async surfaces: 1
- Integrations: 2

## Verified end-to-end workflows

- None.

## Partial or broken workflows

- **POST /api/login** — partially implemented; confidence moderate. Missing: none detected
- **POST /api/documents** — partially implemented; confidence moderate. Missing: Queue producer exists, but no matching production consumer is connected.

## Disconnected implementations

- **Rule-based evaluation** — implemented but disconnected. Rule-based evaluation is classified as implemented but disconnected based on static production-path evidence; scanned code was not executed.
- **Report generation and delivery** — implemented but disconnected. Report generation and delivery is classified as implemented but disconnected based on static production-path evidence; scanned code was not executed.

## Interface-only features

- None.

## Schema-only features

- None.

## Test-only or mock-only behavior

- UI screen `dashboard.tsx::ReportDashboard` uses mock or fixture data.
- `tests/test_evaluator.py` contains mock-based test evidence; tests were not executed.

## Contradictions

- Documentation claims report-related behavior. **Finding:** Report generation and delivery is classified as implemented but disconnected based on static production-path evidence; scanned code was not executed.
- Documentation claims compliance-related behavior. **Finding:** Rule-based evaluation is classified as implemented but disconnected based on static production-path evidence; scanned code was not executed.
- Documentation claims billing-related behavior. **Finding:** Subscription billing is classified as configuration only based on static production-path evidence; scanned code was not executed.
- Documentation claims automat-related behavior. **Finding:** No substantive implementation was found in the same project family.
- Documentation claims monitor-related behavior. **Finding:** No substantive implementation was found in the same project family.
- A user-visible surface presents result data. **Finding:** The surface contains mock or fixture data.

## Dead and unreachable code

- `schema.py::Finding` — unreferenced
- `schema.py::Report` — unreferenced
- `tests/test_evaluator.py::test_evaluator_with_mock_rule` — test_only
- `dashboard.tsx::ReportDashboard` — unreferenced
- `schema.py::Document` — unreferenced
- `evaluator.py::evaluate_policy` — test_only
- `report.py::generate_pdf_report` — unreferenced

## Strongest reusable capabilities

- **Authenticated user access** — partially implemented. Authenticated user access is classified as partially implemented based on static production-path evidence; scanned code was not executed.
- **Document or file ingestion** — partially implemented. Document or file ingestion is classified as partially implemented based on static production-path evidence; scanned code was not executed.
- **Persistent data storage** — partially implemented. Persistent data storage is classified as partially implemented based on static production-path evidence; scanned code was not executed.
- **Report generation and delivery** — implemented but disconnected. Report generation and delivery is classified as implemented but disconnected based on static production-path evidence; scanned code was not executed.
- **Rule-based evaluation** — implemented but disconnected. Rule-based evaluation is classified as implemented but disconnected based on static production-path evidence; scanned code was not executed.

## Technical extraction candidates

- Authenticated user access: moderate readiness; moderate coupling.
- Document or file ingestion: moderate readiness; moderate coupling.
- Persistent data storage: moderate readiness; moderate coupling.
- Report generation and delivery: moderate readiness; moderate coupling.
- Rule-based evaluation: moderate readiness; moderate coupling.

## Major missing components

- No verified connected path from product trigger to meaningful output.

## Security and operational concerns

- No conclusive security finding was established. Static absence of a finding is not a security guarantee.

## Unsupported or uncertain areas

- JavaScript and TypeScript use a deterministic in-process token AST, not a full compiler type checker.
- Dynamic dispatch, reflection, generated code, dependency injection, and cross-language calls can remain unresolved.
- Static reachability is evidence, not proof of runtime behavior.
- Persistent cache accelerates unchanged parsing but does not make dynamic behavior observable.

## Impact on Product Resurrection recommendations

Product opportunities are now gated by technical verification. Unverified or disconnected implementations cannot be described as existing launch-ready products and receive capped readiness scores.

## Evidence appendix

- `edge_2fdbf9d3f521da40` routes_to: `endpoint_4efeb026aff90cc5` → `sym_57af45d080150c7d` (direct, 0.94)
- `edge_cc2250fd27d85b68` routes_to: `endpoint_fde47a4527b7a71d` → `sym_486abb8e5ca7fe57` (direct, 0.94)
- `edge_8e2e0840d79b9084` defines: `file_0739ad88c5b27aea` → `sym_54c69b3ecdde65c0` (direct, 1.0)
- `edge_816d79da573db198` contains: `file_38de450109f1e656` → `schema_9086c623325ced63` (direct, 1.0)
- `edge_19ffb4ee8d6da1e1` contains: `file_38de450109f1e656` → `schema_a803e3fefc36262a` (direct, 1.0)
- `edge_62c144adf4108c6d` contains: `file_38de450109f1e656` → `schema_d5a76eec4331f6d9` (direct, 1.0)
- `edge_f4e09e832adedbf2` defines: `file_38de450109f1e656` → `sym_2d83f3f9e74efda2` (direct, 1.0)
- `edge_248cfe7d77a3df59` defines: `file_38de450109f1e656` → `sym_33d7833ce2033bcf` (direct, 1.0)
- `edge_03342f4b22af90a8` defines: `file_38de450109f1e656` → `sym_c4f80ddfc8c97e85` (direct, 1.0)
- `edge_2b89ecacb0d82a0d` contains: `file_3a47b4c168e35e57` → `producer_24503e537faf2c97` (direct, 1.0)
- `edge_4d6056adaf7453a0` defines: `file_3a47b4c168e35e57` → `sym_51aa127483e62c54` (direct, 1.0)
- `edge_7e920a1c04943cff` contains: `file_4275264ca642c789` → `integration_efb625fc47b2b3a6` (direct, 1.0)
- `edge_93fe9e908f1107d1` contains: `file_568470d013cd12e4` → `endpoint_4efeb026aff90cc5` (direct, 1.0)
- `edge_8c4abc9760055542` contains: `file_568470d013cd12e4` → `endpoint_fde47a4527b7a71d` (direct, 1.0)
- `edge_b69c37c46ec2e7ed` contains: `file_568470d013cd12e4` → `framework_c43af04033494552` (direct, 1.0)
- `edge_cfbac7f43e32c352` defines: `file_568470d013cd12e4` → `sym_486abb8e5ca7fe57` (direct, 1.0)
- `edge_952d4daa76edcd9c` defines: `file_568470d013cd12e4` → `sym_57af45d080150c7d` (direct, 1.0)
- `edge_c3cb10598d7ed9e6` defines: `file_83a9b05d8a20fb6b` → `sym_d3a2512aa9a78711` (direct, 1.0)
- `edge_ad748287ea9954c7` defines: `file_c446ee45576e598a` → `sym_af5214c7eeec1604` (direct, 1.0)
- `edge_b0553cfafb83ffef` contains: `file_c446ee45576e598a` → `ui-screen_8975d4b312fc2e33` (direct, 1.0)
- `edge_38b9ef9612587117` defines: `file_cc6f62d365261a68` → `sym_fbc1662ea0e90335` (direct, 1.0)
- `edge_dd950a86f423db3c` uses: `sym_486abb8e5ca7fe57` → `framework_c43af04033494552` (direct, 0.82)
- `edge_85ebba74dab8af5a` calls: `sym_486abb8e5ca7fe57` → `sym_51aa127483e62c54` (heuristic, 0.58)
- `edge_6e324a7bba7f0cfe` passes_data: `sym_486abb8e5ca7fe57` → `sym_51aa127483e62c54` (heuristic, 0.58)
- `edge_c8bc3ed9bc89389d` produces: `sym_51aa127483e62c54` → `producer_24503e537faf2c97` (direct, 0.82)
- `edge_24364865abc445f1` calls: `sym_54c69b3ecdde65c0` → `sym_d3a2512aa9a78711` (heuristic, 0.58)
- `edge_ac605a5ce641e4ef` passes_data: `sym_54c69b3ecdde65c0` → `sym_d3a2512aa9a78711` (heuristic, 0.58)
- `edge_e327f16d6981d22b` uses: `sym_af5214c7eeec1604` → `ui-screen_8975d4b312fc2e33` (direct, 0.82)
- `edge_7711db3142087ff2` persists: `sym_c4f80ddfc8c97e85` → `schema_9086c623325ced63` (direct, 0.82)
