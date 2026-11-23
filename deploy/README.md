# Deploying Your MCP Server

Local development runs your server over **stdio** (how Claude Desktop / Claude
Code launch it). To share it with an agent platform, deploy it to a host that
serves it over **streamable-HTTP**, then register it.

This project ships one deployment kit, for Databricks.

## The server code doesn't change

The kit runs the server in `src/alt_text_mcp/` unmodified. The entry point
`app.py` auto-selects its transport:

- a platform port (`DATABRICKS_APP_PORT` or `PORT`) → **HTTP** on that port;
- `MCP_TRANSPORT=streamable-http` → HTTP on `MCP_HOST:MCP_PORT`;
- otherwise → **stdio**.

So Databricks Apps "just works" — it injects a port and the server serves
HTTP with `/mcp` + `/health`.

## Databricks

See [`databricks/README.md`](databricks/README.md). Deploy as a Databricks App:
the kit syncs your repo to the workspace and runs `databricks apps deploy`. The
app is gated by workspace auth, so clients present a bearer token.

In this repo, live deploys are run manually
(`bash deploy/databricks/deploy-databricks-app.sh`) rather than through GitLab
CI, since this shared hackathon workspace has no service principal available
for CI to deploy as — see [`databricks/README.md`](databricks/README.md).

## cloud.gov (bonus)

Not a full kit, but the repo root includes a `manifest.yaml` for cloud.gov
(Cloud Foundry). Deploy with `cf push` after `cf login`/`cf target`. See the
comments in `manifest.yaml`.

---

## Security reminder

The Databricks kit is gated by workspace SSO. For anything beyond a
hackathon, review your agency's ATO requirements. Never commit secrets —
the kit's `.env` is git-ignored and holds coordinates only.
