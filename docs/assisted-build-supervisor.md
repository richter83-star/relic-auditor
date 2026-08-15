# Assisted Build Supervisor

Relic Auditor v0.12.0 turns a checksum-verified Build Pack into a
reviewable implementation candidate. It does not build inside the original
scan target and it does not publish, deploy, create accounts, send messages, or
make payments.

## The five-step desktop path

1. Verify the exported Build Pack and every checksum.
2. Create a managed workspace outside both the scan target and Build Pack.
3. Choose an installed local builder.
4. Review the immutable action ID and approve every requested capability.
5. Run one approved action, inspect the complete diff, and optionally mark the
   workspace as a review-required candidate.

Nothing is pre-approved. Closing any wizard before the run leaves the original
source unchanged and launches no builder.

The export manifest carries a one-way fingerprint of the original source
root. The supervisor compares it with every parent of the requested sessions
folder and rejects any workspace placed inside that source. Older exported
older packs must be re-exported so this boundary can be enforced; source
paths themselves are not written to the pack.

## Capability model

| Capability | Meaning |
|---|---|
| `file_write` | Authorize workspace changes. Relic's own writes are path-confined; process containment also depends on the selected provider sandbox. |
| `process` | Launch an exact argument list without a shell. |
| `dependency_install` | Install third-party packages; separate from ordinary process execution. |
| `network` | Allow network use. Without it, Relic supplies deny-proxy settings to compliant tools. |
| `credentials` | Let an installed CLI use an explicitly disclosed signed-in session or allow-listed environment variable. |
| `git` | Run a local Git command. Network Git still requires `network`. |
| `external_action` | Change an external system. The default session budget is zero. |

Approvals are content-addressed and bound to the exact action, parameters, and
capability set. Editing an action or approval invalidates its identity. Action
records and session events are written to an append-only SHA-256 hash chain.

## Builder profiles

The Codex profile runs `codex exec` ephemerally with the documented
`workspace-write` sandbox, ignores user-supplied configuration and rules, and
does not request danger-full-access. See the official
[Codex non-interactive documentation](https://developers.openai.com/codex/noninteractive).

The Claude Code profile removes Bash and MCP tools and requests safe mode,
no session persistence, and file tools only. v0.12 displays it as a blocked
developer preview because those controls are not an operating-system isolation
boundary and it is not a commercially cleared subscription integration. Anthropic's official
[Agent SDK overview](https://platform.claude.com/docs/en/agent-sdk/overview)
states that third-party developers may not offer Claude.ai login or rate limits
without prior approval. Dracanus AI must obtain that approval or replace this
profile with an approved API-based integration before commercial activation.

Both profiles request process, file-write, network, and credentials because the
local CLIs may use a saved login and network service. Those four boxes must be
checked individually. Neither profile requests dependency installation, Git,
or external actions.

## CLI lifecycle

```bash
relic build start /path/to/bp_ID --sessions /path/to/Relic-Build-Sessions --json
relic build plan /path/to/session_ID --file reviewed-actions.json --json
relic build approve /path/to/session_ID --action action_ID \
  --capability file_write --actor "reviewer" --json
relic build run /path/to/session_ID --action action_ID --json
relic build diff /path/to/session_ID --json
relic build finalize /path/to/session_ID --json
```

The reviewed plan format contains an `actions` array. A supplied `action_id`
must match the canonical action content or Relic rejects the plan as stale or
tampered.

## Recovery and limits

Relic checkpoints the workspace before every action. If a process modifies
files without `file_write`, or exceeds a file/byte budget, the checkpoint is
restored. Process time, total actions, network actions, and external actions
have independent limits. Process output is bounded and secret-redacted before
it enters the action log.

Pause and resume apply between actions. Cancel also terminates an active child
process tree, records the cancellation, and restores the pre-action checkpoint.
A process still has a hard timeout, and a failed or cancelled action never
becomes a candidate automatically.

## Operating-system boundary

The v0.12 production policy allows Relic's path-confined direct writes and the
exact Codex ephemeral `workspace-write` profile. It refuses altered Codex
arguments, generic native processes, dependency/Git process actions, and the
Claude preview before they start. Code-level injected runners remain available
only to tests. This is still not a new Windows user account, VM, container, or
firewall.

A malicious provider binary could still exploit its own sandbox implementation.
Use a disposable VM or separately configured OS sandbox when the provider
executable is not trusted. Capability approval records consent; it does not
replace operating-system containment.
