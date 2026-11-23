# Databricks Apps Deployment

Deploy your MCP server as a [Databricks App](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/).
Databricks builds a container from your synced source and `app.yaml`, runs it,
and exposes it behind your workspace's authentication.

- **Transport:** MCP over streamable-HTTP at `/mcp` (stateless); health at `/health`
- **Port:** Databricks injects `DATABRICKS_APP_PORT` (defaults to `8000`); this
  template's `app.py` detects it and serves HTTP automatically — no code changes.

> **How the template already supports this:** `src/alt_text_mcp/app.py` checks
> for `DATABRICKS_APP_PORT` (and generic `PORT`) and switches to streamable-HTTP
> on that port. That's the only wiring Databricks Apps needs.

## What Databricks injects at runtime

| Variable | Purpose |
|---|---|
| `DATABRICKS_APP_PORT` | Port your server must listen on (default 8000) |
| `DATABRICKS_HOST` | Workspace URL |
| `DATABRICKS_CLIENT_ID` | Service principal client ID |
| `DATABRICKS_CLIENT_SECRET` | OAuth secret |

The last three are available if your tools need to call back into Databricks
(e.g. query a table). `scan_page_alt_text` and `fetch_image` don't use them —
they fetch caller-supplied URLs directly, not Databricks resources.

---

## Part 1 — Prerequisites

### 1.1 Install the Databricks CLI (v0.205+)

```bash
# macOS
brew tap databricks/tap && brew install databricks
# or see: https://docs.databricks.com/dev-tools/cli/install.html
databricks --version
```

### 1.2 Authenticate

```bash
databricks auth login --host https://<your-workspace>.cloud.databricks.com
databricks current-user me      # confirm you're logged in
```

> **Profile name gotcha:** `databricks auth login` prompts for a profile name and
> defaults it to your workspace host (e.g. `dbc-xxxx`) — **not** `DEFAULT`. Note
> the name you choose; you must set `DATABRICKS_CONFIG_PROFILE` in `.env` (below)
> to that exact name, or the deploy script's auth check will fail with
> "not authenticated". List your profiles with `databricks auth profiles`.

> Databricks **Apps** must be enabled on your workspace. If `apps` commands fail
> with a feature error, ask your workspace admin to enable Databricks Apps.

### 1.3 Configure the deploy env file

```bash
cp deploy/databricks/.env.example deploy/databricks/.env
# edit:
#   - APP_NAME:          your server's name, MUST start with "mcp-" (lowercase, hyphens) —
#                        that prefix is what lets AI Playground discover it as an MCP server
#   - SOURCE_CODE_PATH:  absolute /Workspace path (replace <you> with your user)
#   - DATABRICKS_HOST / DATABRICKS_CONFIG_PROFILE: optional, if not using DEFAULT
set -a; source deploy/databricks/.env; set +a
```

`.env` holds **no secrets** — auth lives in your CLI login. It is git-ignored.

---

## Part 2 — Deploy

```bash
set -a; source deploy/databricks/.env; set +a
bash deploy/databricks/deploy-databricks-app.sh
```

The script is idempotent and:

1. Confirms the CLI is installed and authenticated.
2. Stages `app.yaml` at the repo root (where Databricks expects it) for the sync.
3. Ensures the App exists (create-or-reuse).
4. Syncs the repo to `SOURCE_CODE_PATH` in your workspace.
5. Runs `databricks apps deploy` from that path.
6. Prints the app URL (`/mcp` + `/health`).

The first deploy builds the container and can take a few minutes.

### Smoke-test

```bash
# Private apps are auth-gated — an unauthenticated curl returns 302/401 (expected).
bash deploy/databricks/smoke-test.sh https://<app-url>

# Authenticated check:
DATABRICKS_TOKEN="$(databricks auth token --output json | jq -r .access_token)" \
  bash deploy/databricks/smoke-test.sh https://<app-url>

# If you saved a named profile (not DEFAULT), pass it and the host explicitly:
#   DATABRICKS_TOKEN="$(databricks --profile <your-profile> auth token \
#     --host https://<your-workspace>.cloud.databricks.com --output json | jq -r .access_token)" \
#     bash deploy/databricks/smoke-test.sh https://<app-url>
```

---

## Part 3 — Connect a client

Databricks Apps are gated by workspace auth, so an MCP client must present a
bearer token. For any remote-HTTP-capable MCP client, register the endpoint
and supply the token as an `Authorization: Bearer <token>` header via the
client's connection/credential mechanism.

For a quick local test with an MCP client that supports HTTP + headers:

```json
{
  "mcpServers": {
    "mcp-alt-text": {
      "type": "http",
      "url": "https://<app-url>/mcp",
      "headers": { "Authorization": "Bearer <DATABRICKS_TOKEN>" }
    }
  }
}
```

> Token from `databricks auth token`. Tokens are short-lived; for a durable
> integration use a service principal with access to the app.

### Or skip the client entirely — use AI Playground

Because the app name starts with `mcp-`, AI Playground's own tool picker finds
it automatically — no Unity Catalog connection or MCP service registration
needed (registering a Databricks App as an *external* MCP via Unity Gateway
is explicitly unsupported; the `mcp-` prefix is the actual mechanism for
Apps). In the workspace: open **AI Playground** → pick a model with **Tools**
enabled → **+ Add tool** → **MCP Servers** → **Databricks Apps** → select this
app. The caller needs **CAN USE** on the app.

---

## Continuous deployment via GitLab CI (not currently enabled)

`.gitlab-ci.yml` in this repo deliberately has **no deploy stage** — this
shared hackathon workspace has no dedicated service principal to deploy as,
so live deploys are run manually
(`bash deploy/databricks/deploy-databricks-app.sh`). The steps below are for
setting up CI-driven deploys if this project moves to a workspace where a
service principal can be provisioned — they describe a `deploy` stage you
would add to `.gitlab-ci.yml`, gated to `master`
(`rules: - if: '$CI_COMMIT_BRANCH == "master"'`), so that merging to `master`
deploys automatically — nobody would need personal Databricks CLI access, and
every change would go through an MR review first.

### One-time setup

1. **Create a dedicated service principal** in the Databricks workspace
   (Admin Settings → Identity and access → Service principals → Add). Don't
   reuse a human's identity or an existing app's service principal — this one
   exists only to deploy this app from CI.
2. **Grant it permission** to create/manage Databricks Apps (and, if
   `APP_NAME` already exists, `CAN_MANAGE` on that specific app).
3. **Mint an OAuth client secret** for the service principal (its page →
   "Generate secret"). Note the client ID and secret — the secret is shown
   once.
4. **Add GitLab CI/CD variables** (Project → Settings → CI/CD → Variables),
   each **masked** and **protected** (protected restricts them to protected
   branches — pair with step 5):
   | Variable | Value |
   |---|---|
   | `DATABRICKS_HOST` | Your workspace URL, e.g. `https://<workspace>.cloud.databricks.com` |
   | `DATABRICKS_CLIENT_ID` | The service principal's client ID |
   | `DATABRICKS_CLIENT_SECRET` | The service principal's OAuth secret |
   | `DATABRICKS_SOURCE_CODE_PATH` | Absolute `/Workspace` path to sync source to, e.g. `/Workspace/Shared/mcp-alt-text` |

   The Databricks CLI picks up `DATABRICKS_HOST`/`DATABRICKS_CLIENT_ID`/
   `DATABRICKS_CLIENT_SECRET` automatically and authenticates via OAuth
   machine-to-machine (client credentials) — no `databricks auth login` or
   CI-stored personal token needed.
5. **Protect `master`** (Project → Settings → Repository → Protected
   branches): require merge requests, disallow direct push, and require at
   least one approval. Do this *after* the initial scaffold lands on
   `master` — there's no history to protect before that.

### What would run, once added

- Every branch/MR: the `test` stage (`ruff check`, `ruff format --check`,
  `pytest`) — this part already exists in `.gitlab-ci.yml` today.
- `master` only: the `test` stage, then a `deploy` stage you add, running
  `deploy/databricks/deploy-databricks-app.sh` — the same script you'd run by
  hand, pointed at the service principal's credentials instead of yours.

---

## Teardown

```bash
set -a; source deploy/databricks/.env; set +a
databricks apps delete "${APP_NAME}"
# Optionally remove the synced source:
#   databricks workspace delete "${SOURCE_CODE_PATH}" --recursive
```

---

## Files in this directory

| File | Purpose |
|---|---|
| `app.yaml` | Databricks Apps runtime config (the `command` that starts the server) |
| `.env.example` | Deploy coordinates template (copy to `.env`, no secrets) |
| `deploy-databricks-app.sh` | Idempotent create → sync → deploy |
| `smoke-test.sh` | Live `/health` + `/mcp` reachability check (auth-aware) |
| `README.md` | This runbook |

## Known gaps / notes

- **Auth-gated by default:** Databricks Apps sit behind workspace SSO/OAuth, so
  unauthenticated probes return 302/401 — that's expected, not a failure. Use a
  bearer token to reach the app programmatically.
- **Renamed package:** if you renamed `alt_text_mcp`, update the module path in
  `app.yaml` (`python -m <your_pkg>.app`).
- **`app.yaml` location:** Databricks reads `app.yaml` from the deployed source
  root. The deploy script stages this kit's copy at the repo root for the sync
  and removes it afterward; if you prefer, commit a copy at the repo root instead.
- **Stateless HTTP:** the server runs stateless streamable-HTTP, which scales
  cleanly on Apps (no sticky sessions required).
