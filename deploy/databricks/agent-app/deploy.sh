#!/usr/bin/env bash
# Deploy the team20-alt-text-agent Databricks App.
#
# Flow:
#   1. Ensure the app exists (create-or-reuse).
#   2. Sync this folder to a workspace path.
#   3. Declare resources (LLM serving endpoint + mcp-alt-text) so Databricks
#      grants this app's own service principal CAN_QUERY / CAN_USE on them.
#   4. Deploy.
#
# Usage:
#   DATABRICKS_CONFIG_PROFILE=hackathon bash deploy/databricks/agent-app/deploy.sh
set -euo pipefail

APP_NAME="${APP_NAME:-team20-alt-text-agent}"
SOURCE_CODE_PATH="${SOURCE_CODE_PATH:-/Workspace/Users/jonathan.yi@uspto.gov/apps/${APP_NAME}}"
LLM_ENDPOINT_NAME="${LLM_ENDPOINT_NAME:-databricks-gpt-5-1}"
MCP_APP_NAME="${MCP_APP_NAME:-mcp-alt-text}"

PROFILE_ARGS=()
if [[ -n "${DATABRICKS_CONFIG_PROFILE:-}" ]]; then
  PROFILE_ARGS=(--profile "${DATABRICKS_CONFIG_PROFILE}")
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Target ==="
echo "  app name:          ${APP_NAME}"
echo "  source code path:  ${SOURCE_CODE_PATH}"
echo "  llm endpoint:      ${LLM_ENDPOINT_NAME}"
echo "  mcp app:           ${MCP_APP_NAME}"
echo ""

echo "=== Ensuring app '${APP_NAME}' ==="
if databricks "${PROFILE_ARGS[@]}" apps get "${APP_NAME}" >/dev/null 2>&1; then
  echo "  app exists — reusing."
else
  echo "  creating app '${APP_NAME}'..."
  databricks "${PROFILE_ARGS[@]}" apps create "${APP_NAME}" --no-compute
fi

echo "=== Syncing source to ${SOURCE_CODE_PATH} ==="
# `sync` with an absolute SRC path silently no-ops on this CLI/workspace combo
# (reports "Initial Sync Complete" with zero changes even when files genuinely
# differ from the remote copy) — cd in and use a relative "." SRC instead,
# which reliably triggers real uploads.
(cd "${SCRIPT_DIR}" && MSYS_NO_PATHCONV=1 databricks "${PROFILE_ARGS[@]}" sync --full . "${SOURCE_CODE_PATH}")

echo "=== Declaring resources ==="
# apps update (PATCH /api/2.0/apps/{name}) sets only the fields supplied.
# apps create-update silently drops the "resources" field on CLI v1.22.1.
databricks "${PROFILE_ARGS[@]}" apps update "${APP_NAME}" --json "{
  \"name\": \"${APP_NAME}\",
  \"resources\": [
    {
      \"name\": \"agents-serving-endpoint\",
      \"serving_endpoint\": {\"name\": \"${LLM_ENDPOINT_NAME}\", \"permission\": \"CAN_QUERY\"}
    },
    {
      \"name\": \"${MCP_APP_NAME}\",
      \"app\": {\"name\": \"${MCP_APP_NAME}\", \"permission\": \"CAN_USE\"}
    }
  ]
}"

echo "=== Deploying app '${APP_NAME}' from ${SOURCE_CODE_PATH} ==="
MSYS_NO_PATHCONV=1 databricks "${PROFILE_ARGS[@]}" apps deploy "${APP_NAME}" \
  --source-code-path "${SOURCE_CODE_PATH}"

APP_URL=""
APP_URL="$(databricks "${PROFILE_ARGS[@]}" apps get "${APP_NAME}" \
  --output json 2>/dev/null | grep -o '"url"[^,]*' | head -1 | cut -d'"' -f4)" || true
echo ""
echo "=== Deployed ==="
[[ -n "${APP_URL}" ]] && echo "  App URL: ${APP_URL}"
