# Claude Max Quickstart (Claude Code subscription provider)

Relic Auditor v0.8 can run its optional advisory reasoning layer through the
**locally installed Claude Code CLI**, reusing your existing **Claude.ai /
Claude Max subscription session**. No Anthropic API key is required, requested,
or used.

## How this is billed — read this first

**Claude Max and the Anthropic API are separate products.**

- An **Anthropic API key** (Console) is metered, pay-per-token billing.
- A **Claude Max (or Pro) subscription** is the Claude.ai plan you sign in to
  with `claude auth login`.

This integration uses Claude Code as the reasoning host and consumes whatever
subscription allowance Anthropic currently assigns to Claude Code / print-mode
usage on your plan. **Relic does not and cannot promise that subscription usage
is unlimited or that overage charges are impossible.** Usage remains subject to
Anthropic's current plan limits, rate limits, and your account settings, which
Anthropic can change at any time.

To keep the billing boundary strict, the `claude-code` provider:

- verifies before every invocation that Claude Code is logged in with a
  Claude.ai/OAuth subscription session (an obvious Console/API-key login is
  rejected),
- removes `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, and
  `ANTHROPIC_BASE_URL` from the Claude Code child process (your own
  PowerShell environment is never modified), and
- fails closed — deterministic reports are always produced and preserved even
  when reasoning is unavailable.

## What Relic never does

- Never reads Claude credential files or extracts, copies, prints, exports, or
  stores OAuth tokens.
- Never calls the Anthropic Messages API directly from this provider.
- Never gives Claude Code filesystem, shell, browser, editing, deployment, or
  MCP tools (`--tools ""` and `--strict-mcp-config` on every invocation).
- Never lets Claude Code inspect the scanned target: Claude receives only the
  same bounded, secret-redacted evidence package used by the other providers,
  passed through stdin, from an empty temporary working directory.
- Never executes, installs, modifies, moves, extracts, or deletes scanned
  files, and never suppresses deterministic results when Claude fails.

## Prerequisites

- Windows with Python 3.11+ and Relic Auditor v0.8 installed.
- [Claude Code](https://claude.com/claude-code) installed and on `PATH`
  (`claude --version` works).
- A Claude.ai subscription (Max or Pro) you can sign in with.

## Setup (PowerShell)

Clear any API-billing variables from your session so nothing can be mistaken
for API mode, then refresh and authenticate Claude Code:

```powershell
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:ANTHROPIC_AUTH_TOKEN -ErrorAction SilentlyContinue

claude update
claude auth logout
claude auth login
claude auth status --text
```

`claude auth login` opens the official Claude.ai browser flow. Relic never
intercepts or parses the OAuth token — the session lives entirely inside
Claude Code.

Create the Relic profile:

```powershell
py -m relic_auditor llm add Claude-Max `
  --protocol claude-code `
  --model sonnet `
  --auth claude-subscription
```

Model aliases: `sonnet`, `opus`, `haiku`. Optional `--effort low|medium|high`
(default `medium`).

Check readiness:

```powershell
py -m relic_auditor llm status Claude-Max
```

The status report contains only safe fields (`ready`, `executable_found`,
`claude_code_version`, `logged_in`, `authentication_type`,
`subscription_detected`, `model`, `effort`, `billing_guard`) — never your
email, organization or account identifiers, tokens, or credential paths.

If `logged_in` is false, launch the official login flow through Relic:

```powershell
py -m relic_auditor llm login Claude-Max
```

## Run an audit with Claude Max reasoning

```powershell
py -m relic_auditor acquire "D:\Powerhouse-platform" `
  --output "D:\Relic-Reports\Powerhouse-Claude-Max" `
  --llm-profile Claude-Max
```

Also supported on `audit` and `monitor`:

```powershell
py -m relic_auditor audit "D:\Powerhouse-platform" `
  --technical-truth `
  --capability-acquisition `
  --llm-profile Claude-Max

py -m relic_auditor monitor "D:\Relic-Inbox" `
  --output "D:\Relic-Monitor-Reports" `
  --llm-profile Claude-Max
```

The reasoning output lands in `llm_reasoning_report.md` and
`llm_reasoning.json` next to the deterministic reports, with safe provider
metadata (`provider_protocol: claude-code`, `authentication:
claude-subscription`, model, effort, truncation flag, evidence record count,
success flag, sanitized error, and `deterministic_reports_preserved: true`).

## Dashboard

`relic dashboard` (with the `gui` extra installed) has first-class support:
enable **Use optional LLM reasoning**, pick **Claude Code / Claude Max
(subscription)**, choose the model alias and effort, then use **Check Claude
Code** and **Open Claude login** before running the audit. The dashboard
clearly separates Claude Max subscription reasoning from API-key billing and
generic OAuth profiles.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `executable_found: false` | Install Claude Code and ensure `claude` is on PATH. |
| `logged_in: false` | Run `py -m relic_auditor llm login Claude-Max`. |
| `authentication_type: api-key` | `claude auth logout`, then `claude auth login` with your Claude.ai account. |
| Reasoning "unavailable" but reports exist | Expected fail-closed behavior; check the sanitized error in `llm_reasoning.json`. |
| Timeouts on large estates | Raise `--llm-timeout-seconds` (default 90). |
