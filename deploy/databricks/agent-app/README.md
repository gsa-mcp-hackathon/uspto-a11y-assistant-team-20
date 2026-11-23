# team20-alt-text-agent — a chat agent in front of mcp-alt-text

A small Databricks App that gives team members a chat UI backed by the
`mcp-alt-text` MCP server, so they don't need an MCP client of their own.

## Why a Databricks App, not Model Serving

The first approach tried was deploying the agent as a Model Serving endpoint
with On-Behalf-Of (OBO) user auth, so each caller's own identity would reach
the OAuth-gated `mcp-alt-text` app. That `on_behalf_of_user=True` resource
was correctly declared, but `ModelServingUserCredentials` never activated in
this workspace — it failed identically via the CLI, the Agent Review App,
and AI Playground, with `model_serving_user_credentials auth: Unable to
authenticate using user_credentials in Databricks Model Serving Environment`.
That's a workspace/account-level gap, not something fixable from application
code.

Databricks Apps don't have this problem, and the deploy logs even recommend
them: *"Databricks recommends Databricks Apps for new agent deployments."*
This app runs under its **own** auto-provisioned service principal (no admin
rights needed to create it — same as deploying `mcp-alt-text` itself), with
resources declared at deploy time granting that principal `CAN_QUERY` on the
LLM serving endpoint and `CAN_USE` on `mcp-alt-text`. Every team member sees
the same, shared identity — not per-user OBO — which was an accepted
tradeoff to get something working.

## Why `mcp_client.py` hand-rolls the MCP protocol

`databricks_mcp.DatabricksMCPClient` (used by `databricks_openai.McpServerToolkit`)
refuses to call a `*.databricksapps.com` host unless `WorkspaceClient.config.oauth_token()`
succeeds. This app's auto-injected service-principal credentials
(`DATABRICKS_CLIENT_ID`/`DATABRICKS_CLIENT_SECRET`) are valid for a real
`tools/call`, but don't satisfy that library-side check in this workspace.
`mcp_client.py` mints an app-to-app OAuth M2M token directly from those
credentials and speaks the MCP streamable-HTTP wire protocol by hand
(`initialize` → `Mcp-Session-Id` → `notifications/initialized` → the real
call), parsing the SSE response itself. This mirrors a pattern already
proven in this same workspace by another app
(`patent-compliance-agent`'s `server/lib/uspto-mcp-client.ts`), ported from
TypeScript to Python.

## Deploy

```bash
DATABRICKS_CONFIG_PROFILE=hackathon bash deploy/databricks/agent-app/deploy.sh
```

Idempotent: creates the app on first run (via `--no-compute`), declares/
updates its resources, syncs source, and deploys — `databricks apps deploy`
provisions compute and starts the app itself, no separate `apps start` step
needed.

Grant a group access to the chat UI itself (separate from the app-to-app
resource grants above):

```bash
databricks apps update-permissions team20-alt-text-agent --json '{
  "access_control_list": [{"group_name": "<group>", "permission_level": "CAN_USE"}]
}'
```

## Files

| File | What it is |
|------|------------|
| `server.py` | Starlette app: `/` (chat UI), `/chat` (POST, runs the tool-calling loop), `/health`. |
| `mcp_client.py` | Hand-rolled MCP client — see above. |
| `app.yaml` | Databricks Apps runtime command. |
| `requirements.txt` | Runtime deps Databricks installs server-side. |
| `deploy.sh` | Create-or-reuse, sync, declare resources, deploy. |
