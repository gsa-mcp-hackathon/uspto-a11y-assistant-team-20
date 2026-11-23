# Quickstart — Your First MCP Server in 5 Minutes

New to MCP? This gets you from clone to a running server connected to a client.

## 1. Install prerequisites

You need [uv](https://docs.astral.sh/uv/) (a fast Python package manager):

```bash
pip install uv     # or: brew install uv
```

## 2. Set up the project

```bash
cp .env.example .env
uv sync
```

## 3. Run the server

```bash
uv run python main.py
```

The server starts in **stdio** mode and waits for a client to connect over
stdin/stdout. That's correct — it doesn't print a URL, because a local MCP
server is launched *by* the client as a subprocess. Press `Ctrl-C` to stop it.

## 4. Connect a client

### Claude Code

This repo already ships a `.mcp.json` at its root, so there's nothing to
write by hand. Just open Claude Code **from inside this directory**
(`cd gsahackathon && claude`) and approve the server when prompted — Claude
Code reads `.mcp.json` on startup and launches the server itself.

If you ever need to wire this server into a *different* repo, don't hand-edit
JSON — generate it with Claude Code's own command, run from that repo's root:

```bash
claude mcp add --scope project alt-text-mcp -- uv run alt-text-mcp
```

This writes a `.mcp.json` with no machine-specific path, because it inherits
whatever directory `claude` was launched from — which only works correctly if
you always launch `claude` from the repo root.

### Claude Desktop

Claude Desktop's config is global, not per-repo, so it needs an **absolute
path** to this clone. Add this block to
`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or
`%APPDATA%\Claude\claude_desktop_config.json` (Windows), then restart Claude
Desktop:

```json
{
  "mcpServers": {
    "alt-text-mcp": {
      "command": "uv",
      "args": ["run", "alt-text-mcp"],
      "cwd": "/absolute/path/to/gsahackathon"
    }
  }
}
```

Once connected, ask the client to call one of this server's real tools, e.g.:

> "Use scan_page_alt_text to check https://www.w3.org/WAI/demos/bad/before/home.html for alt-text issues."

You'll get a real list of flagged images — proof the wiring works.

## 5. Verify everything

```bash
uv sync --group dev
uv run pytest tests/ -v      # tests pass
uv run ruff check .          # lint clean
```

## 6. Test HTTP mode (optional)

Cloud hosts run the server over HTTP. Try it locally:

```bash
MCP_TRANSPORT=streamable-http uv run python main.py
# in another terminal:
curl http://localhost:8000/health      # {"status":"healthy",...}
```

---

## Next steps

- **Add a real tool** — follow "The one-tool-per-file pattern" in the
  [README](README.md#the-one-tool-per-file-pattern).
- **Rename the package** from `alt_text_mcp` to your service — see the
  [README](README.md#rename-the-package).
- **Deploy it** — see [deploy/README.md](deploy/README.md) (Databricks).
- **Evaluate it** — build a local harness with the `mcp-eval` skill (see
  [eval/README.md](eval/README.md)), or use the existing MLflow harness for
  your deployed app (see [eval/databricks/README.md](eval/databricks/README.md)).
