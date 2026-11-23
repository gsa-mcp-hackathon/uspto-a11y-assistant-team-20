---
description: Diagnose and fix the local dev environment for this project (Windows).
allowed-tools: Bash, Read, Edit, Write, Glob
---

# /setup — Get this project running on Windows

Walk the user through every prerequisite and fix any problems found. Be conversational and specific — tell them exactly what to run and what to expect.

## Steps

### 1. Check Python 3.11+

Run:
```
python --version
```

- If missing or below 3.11: tell the user to download Python 3.11+ from https://www.python.org/downloads/ and **check "Add Python to PATH"** during installation, then restart their terminal.
- If 3.11+: confirm it's good.

### 2. Check uv

Run:
```
uv --version
```

- If missing: tell the user to run `pip install uv`, then restart their terminal.
- If present: confirm it's good.

### 3. Check for .env

Check whether `.env` exists in the project root.

- If missing: tell the user to run `copy .env.example .env`.
- If present: confirm it's good. Remind them the server needs no API keys to run — `.env` is optional for basic use.

### 4. Install dependencies

Run:
```
uv sync
```

- If it fails: show the error, then suggest running as Administrator if it's a permissions error, or check the Python version if it's a requires-python error.
- If it succeeds: confirm all dependencies are installed.

### 5. Smoke-test the server

Run:
```
uv run python main.py
```
Wait 3 seconds, then kill it (Ctrl-C). The server prints nothing on success (it waits for a client over stdio) — that's correct.

- If it errors: show the traceback and diagnose (import error = step 4 failed, port in use = not applicable for stdio mode).
- If it starts cleanly: confirm the server is working.

### 6. Connect Claude Code

Tell the user: this repo ships a `.mcp.json` at its root, so Claude Code wires the server up automatically. They just need to open Claude Code **from inside this directory**:

```
cd path\to\gsahackathon
claude
```

When prompted, approve the `alt-text-mcp` server. Then they can ask Claude to call a tool, e.g.:

> "Use scan_page_alt_text to check https://www.w3.org/WAI/demos/bad/before/home.html"

### 7. Optional: run the tests

If the user wants to verify everything more thoroughly:

```
uv sync --group dev
uv run pytest tests/ -v
uv run ruff check .
```

All should pass on a clean checkout.

---

## Common Windows Issues

- **`python` not found**: Python wasn't added to PATH — reinstall and check the box, or add it manually via System > Environment Variables.
- **`uv` not found after `pip install uv`**: restart the terminal so the PATH update takes effect.
- **Permission denied during `uv sync`**: run Command Prompt or PowerShell as Administrator.
- **`copy` vs `cp`**: use `copy .env.example .env` (not `cp`) in Command Prompt; either works in PowerShell or Git Bash.
