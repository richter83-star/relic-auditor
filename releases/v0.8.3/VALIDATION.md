# Relic Auditor v0.8.3 validation

## Automated suite

- 259 tests passed.
- 1 environment-conditional test skipped because PySide6 was installed; the
  skipped test covers the error message used when the GUI extra is absent.
- Both real offscreen Qt suites ran across their supported window sizes and
  display-scaling rules.
- Source and tests compile successfully with Python 3.12.

## Product-shell regression

- The default shell exposes exactly Scan, Results, and Reports.
- Technical widgets and provider diagnostics are not visible until Technical
  details is opened.
- The complete nine-view evidence console remains populated and usable.
- Results renders all four plain-English answer blocks plus one primary View
  full report action.

## Report persistence

- Automatic output follows
  `Documents/Relic Auditor/Reports/<project> reports/<timestamp>`.
- Windows-invalid project-name characters are sanitized.
- Prior scans are discovered newest first and retain direct links to their
  report and scan folder.
- End-to-end complete appraisal and report export leave the scanned target
  byte-for-byte unchanged.

## Package smoke test

- The wheel and source distribution build successfully.
- A no-dependency clean-target wheel install reports `relic 0.8.3`.
- The v0.8.2 plain-import parser regression tests remain green.
