# Relic Auditor v0.8.3 — Windows Quick Start

Keep the existing v0.8.2 folder intact while testing v0.8.3.

1. Extract `relic-auditor-0.8.3.zip` to a new folder such as:

   ```text
   D:\relic-auditor-0.8.3
   ```

2. Open PowerShell in that folder.

3. Install Relic, the native GUI, and secure OAuth credential storage:

   ```powershell
   py -m pip install -e ".[all]"
   ```

4. Launch the dashboard:

   ```powershell
   relic dashboard
   ```

5. Or open a specific estate immediately:

   ```powershell
   relic dashboard "D:\Your-Messy-Project"
   ```

Verify the installed version:

```powershell
relic --version
```

Expected:

```text
relic 0.8.3
```

The command-line workflow remains available:

```powershell
relic audit "D:\Your-Messy-Project" --technical-truth --product-discovery
```

Run Capability Acquisition Mode:

```powershell
relic acquire "D:\Your-Messy-Project"
relic acquire "D:\loose-files\agent-loop.py"
relic acquire "D:\archives\powerhouse.zip"
```

Start Relic Monitor:

```powershell
New-Item -ItemType Directory -Force "D:\Relic-Inbox"
relic monitor "D:\Relic-Inbox" --output "D:\Relic-Monitor-Reports"
```

Configure API-key reasoning:

```powershell
$env:OPENAI_API_KEY = "your-key"
relic llm add openai-api `
  --protocol openai-responses `
  --model YOUR_MODEL `
  --auth api-key `
  --api-key-env OPENAI_API_KEY

relic acquire "D:\Your-Messy-Project" --llm-profile openai-api
```

Configure provider-issued OAuth:

```powershell
relic llm add company-oauth `
  --protocol openai-chat `
  --model YOUR_MODEL `
  --base-url "https://llm.example.com/v1" `
  --auth oauth `
  --authorization-url "https://identity.example.com/oauth/authorize" `
  --token-url "https://identity.example.com/oauth/token" `
  --client-id "YOUR_PUBLIC_DESKTOP_CLIENT_ID" `
  --scope openid `
  --scope offline_access

relic llm login company-oauth
relic acquire "D:\Your-Messy-Project" --llm-profile company-oauth
```

OAuth tokens are stored in the Windows credential vault. This generic OAuth
path does not reuse browser cookies; the provider must issue an OAuth client
and authorize the inference endpoint.

Use your Claude Max subscription through the local Claude Code CLI (no API key):

```powershell
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:ANTHROPIC_AUTH_TOKEN -ErrorAction SilentlyContinue

claude update
claude auth logout
claude auth login
claude auth status --text

py -m relic_auditor llm add Claude-Max `
  --protocol claude-code `
  --model sonnet `
  --auth claude-subscription

py -m relic_auditor llm status Claude-Max

py -m relic_auditor acquire "D:\Powerhouse-platform" `
  --output "D:\Relic-Reports\Powerhouse-Claude-Max" `
  --llm-profile Claude-Max
```

Relic never reads Claude credential files or handles the OAuth token — Claude
Code keeps its own session. Claude Max and the Anthropic API are separate
products; this path consumes your Claude Code subscription allowance and
remains subject to Anthropic's current plan limits and account settings. See
[docs/CLAUDE_MAX_QUICKSTART.md](docs/CLAUDE_MAX_QUICKSTART.md).

Relic scans read-only. Dashboard decisions are advisory planning metadata and
cannot execute, install, extract, move, delete, deploy, provision resources, or
expand authority.
