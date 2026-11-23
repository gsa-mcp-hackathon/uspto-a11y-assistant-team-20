"""Hand-rolled app-to-app MCP client for the mcp-alt-text Databricks App.

databricks_mcp's Python client only accepts a WorkspaceClient whose auth
type it recognizes as OAuth (checked via `config.oauth_token()`) when
talking to a *.databricksapps.com host. This app's own auto-injected
service-principal credentials (DATABRICKS_CLIENT_ID/DATABRICKS_CLIENT_SECRET)
are valid for a real tools/call, but don't satisfy that library-side check
in this workspace. The same problem, and the same fix, were already worked
out for the patent-compliance-agent app's server/lib/uspto-mcp-client.ts:
mint an app-to-app OAuth token directly and speak the MCP streamable-HTTP
wire protocol by hand instead of going through that library.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx

MCP_SERVER_URL = os.environ.get(
    "MCP_ALT_TEXT_URL",
    "https://mcp-alt-text-7474654188777746.aws.databricksapps.com/mcp",
)

_token_cache: dict[str, Any] = {"token": None, "expires_at": 0.0}


def _get_app_token() -> str:
    """Mint (and cache) an app-to-app OAuth M2M token from this app's own SP creds."""
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now:
        return _token_cache["token"]

    host = os.environ["DATABRICKS_HOST"].rstrip("/")
    if not host.startswith("http"):
        host = f"https://{host}"
    client_id = os.environ["DATABRICKS_CLIENT_ID"]
    client_secret = os.environ["DATABRICKS_CLIENT_SECRET"]

    resp = httpx.post(
        f"{host}/oidc/v1/token",
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials", "scope": "all-apis"},
        timeout=20.0,
    )
    resp.raise_for_status()
    data = resp.json()
    # Refresh a minute early to avoid races with in-flight calls.
    ttl = data.get("expires_in", 3600) - 60
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + ttl
    return _token_cache["token"]


def _parse_sse_jsonrpc(body: str) -> list[dict[str, Any]]:
    """Parse an SSE response body into its JSON-RPC payload(s)."""
    payloads = []
    for block in body.split("\n\n"):
        lines = [
            line[5:].strip() for line in block.split("\n") if line.startswith("data:")
        ]
        joined = "\n".join(lines)
        if not joined:
            continue
        try:
            payloads.append(json.loads(joined))
        except ValueError:
            continue
    return payloads


def _mcp_request(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """One full MCP handshake + request: initialize -> session id ->
    notifications/initialized -> method.

    A fresh handshake per call, not a cached session — simpler and safer
    than tracking session expiry, at the cost of two extra round trips.
    """
    token = _get_app_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    with httpx.Client(timeout=30.0) as client:
        init_resp = client.post(
            MCP_SERVER_URL,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "team20-alt-text-agent", "version": "1.0"},
                },
            },
        )
        init_resp.raise_for_status()
        session_id = init_resp.headers.get("mcp-session-id")
        if not session_id:
            raise RuntimeError(
                "mcp-alt-text initialize response had no Mcp-Session-Id header."
            )
        session_headers = {**headers, "Mcp-Session-Id": session_id}

        client.post(
            MCP_SERVER_URL,
            headers=session_headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )

        call_resp = client.post(
            MCP_SERVER_URL,
            headers=session_headers,
            json={"jsonrpc": "2.0", "id": 2, "method": method, "params": params or {}},
        )
    call_resp.raise_for_status()

    payloads = _parse_sse_jsonrpc(call_resp.text)
    envelope = next(
        (p for p in payloads if "result" in p or "error" in p),
        None,
    )
    if envelope is None:
        raise RuntimeError(f"mcp-alt-text {method} returned no JSON-RPC payload.")
    if "error" in envelope:
        message = envelope["error"].get("message", "unknown error")
        raise RuntimeError(f"mcp-alt-text error: {message}")
    return envelope["result"]


def list_tools() -> list[dict[str, Any]]:
    """List tools exposed by mcp-alt-text, in raw MCP tool-schema form."""
    result = _mcp_request("tools/list")
    return result.get("tools", [])


def call_tool(name: str, arguments: dict[str, Any]) -> Any:
    """Call one tool; return structured content if present, else parsed text."""
    result = _mcp_request("tools/call", {"name": name, "arguments": arguments})
    if result.get("structuredContent") is not None:
        return result["structuredContent"]
    content = result.get("content") or []
    text = content[0].get("text") if content else None
    if isinstance(text, str):
        try:
            return json.loads(text)
        except ValueError:
            return text
    return result
