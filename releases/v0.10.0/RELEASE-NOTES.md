# Relic Auditor 0.10.0 release candidate

This release candidate adds the Product Builder Bridge: a deterministic,
evidence-linked Build Pack workflow with exact asset approval, atomic managed
export, checksum validation, and render-only Codex, Claude Code, and generic
agent handoffs.

Production defaults to Free. Premium capability is injected at the engine
boundary; there is no CLI flag or environment bypass. The bridge never executes
target code or coding agents, mutates the scanned target or Git, installs
dependencies, deploys, publishes, sends messages, or spends money.

The Python source, wheel, sdist, and representative Build Pack are verified RC
artifacts. The Windows workflow and installer inputs are hash-pinned, but the
installer itself remains unbuilt and unsigned until a separately approved remote
workflow run.
