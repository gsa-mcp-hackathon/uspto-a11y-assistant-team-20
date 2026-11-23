"""team20-alt-text-agent — a small Databricks App chatting with mcp-alt-text.

Browser users hit this app through Databricks' own SSO gate (CAN_USE on
this app, granted to the team-20 group). Server-side, this app calls the
LLM serving endpoint and the mcp-alt-text app using its own auto-injected
service-principal credentials (CAN_QUERY / CAN_USE resources declared at
deploy time) — see mcp_client.py for why the MCP leg is hand-rolled.
"""

from __future__ import annotations

import json
import os

import mcp_client
from databricks_openai import DatabricksOpenAI
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

LLM_ENDPOINT_NAME = os.environ.get("LLM_ENDPOINT_NAME", "databricks-gpt-5-1")
MAX_TOOL_CALL_TURNS = 10

SYSTEM_PROMPT = (
    "You are an accessibility assistant for federal web teams. You have tools "
    "from the alt-text-mcp server that scan live, public web pages for "
    "Section 508 / WCAG accessibility issues: missing or low-quality alt "
    "text, non-descriptive link text, broken heading structure, unlabeled "
    "form fields, missing page titles/landmarks/lang attributes, duplicate "
    "IDs, color contrast, and more — plus a multi-page site-wide scan. "
    "Always call the relevant tool against the actual URL the user gives you "
    "rather than guessing about a page's accessibility. Summarize findings "
    "clearly, cite concrete elements (not just counts), and suggest specific "
    "fixes. These tools use static-HTML heuristics (no JavaScript execution) "
    "— say so when it's relevant to a result, don't present it as a full "
    "manual audit."
)

_llm_client = DatabricksOpenAI()

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def _tool_spec(tool: dict) -> dict:
    schema = tool.get("inputSchema") or {"type": "object", "properties": {}}
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": schema,
        },
    }


def run_agent(user_message: str) -> str:
    tools = mcp_client.list_tools()
    tool_specs = [_tool_spec(t) for t in tools]

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    for _ in range(MAX_TOOL_CALL_TURNS):
        response = _llm_client.chat.completions.create(
            model=LLM_ENDPOINT_NAME,
            messages=messages,
            tools=tool_specs or None,
        )
        message = response.choices[0].message

        if not message.tool_calls:
            return message.content or ""

        messages.append(message.model_dump())
        for tool_call in message.tool_calls:
            arguments = json.loads(tool_call.function.arguments or "{}")
            try:
                result = mcp_client.call_tool(tool_call.function.name, arguments)
            except Exception as exc:  # noqa: BLE001 — surface to the LLM, don't crash the turn
                result = f"Tool error: {exc}"
            content = result if isinstance(result, str) else json.dumps(result)
            messages.append(
                {"role": "tool", "tool_call_id": tool_call.id, "content": content}
            )

    return (
        f"Stopped after {MAX_TOOL_CALL_TURNS} tool-call turns without a final answer."
    )


async def chat(request: Request) -> JSONResponse:
    body = await request.json()
    user_message = (body.get("message") or "").strip()
    if not user_message:
        return JSONResponse({"error": "message is required"}, status_code=400)
    try:
        reply = run_agent(user_message)
    except Exception as exc:  # noqa: BLE001 — return the error to the UI instead of a 500 page
        return JSONResponse({"error": str(exc)}, status_code=500)
    return JSONResponse({"reply": reply})


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "healthy"})


_INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
<title>Accessibility Assistant &middot; USPTO Team 20</title>
<link rel="icon" href="/static/favicon/favicon.ico" type="image/vnd.microsoft.icon">
<link rel="stylesheet" href="/static/css/usptostrap.min.css">
<link rel="stylesheet" href="https://fonts.googleapis.com/icon?family=Material+Icons">
<style>
  /* Full-height flex shell */
  html, body { height: 100%; }
  body { display: flex; flex-direction: column; overflow: hidden; }

  /* Let the USPTO banner and header sit at natural height */
  .banner, #global-header { flex-shrink: 0; }

  /* Page sub-header below the USPTO bar */
  #app-subheader { flex-shrink: 0; background: #fff; border-bottom: 1px solid #dee2e6;
                   padding: 0.6rem 1.25rem; }
  #app-subheader h1 { font-size: 1.1rem; font-weight: 600; color: #212529; margin: 0; }
  #app-subheader p  { font-size: 0.8rem; color: #6c757d; margin: 0; }

  /* Scrollable chat column */
  #chat { flex: 1; overflow-y: auto; min-height: 0;
          padding: 1.25rem 1rem; display: flex; flex-direction: column; gap: 1rem;
          background: #f8f9fa; }

  /* Welcome screen */
  #welcome { margin: auto; text-align: center; max-width: 480px; padding: 1rem; }
  #welcome h2 { font-size: 1.1rem; font-weight: 600; color: #333; margin-bottom: 0.4rem; }
  #welcome p  { font-size: 0.875rem; color: #6c757d; margin-bottom: 1.5rem; line-height: 1.5; }
  .chips { display: flex; flex-wrap: wrap; gap: 0.5rem; justify-content: center; }
  .chip { background: #fff; border: 1px solid #dee2e6; border-radius: 20px;
          padding: 0.4rem 0.9rem; font-size: 0.8rem; color: #495057;
          cursor: pointer; transition: background 0.15s, border-color 0.15s; }
  .chip:hover { background: #e8f0fe; border-color: #0054a6; color: #0054a6; }

  /* Chat bubbles */
  .msg { display: flex; align-items: flex-end; gap: 0.5rem; max-width: 85%; }
  .msg-user  { align-self: flex-end; flex-direction: row-reverse; }
  .msg-agent { align-self: flex-start; }

  .avatar { width: 1.75rem; height: 1.75rem; border-radius: 50%; display: flex;
            align-items: center; justify-content: center; font-size: 0.65rem;
            font-weight: 700; flex-shrink: 0; }
  .msg-user  .avatar { background: #0054a6; color: #fff; }
  .msg-agent .avatar { background: #dee2e6; color: #495057; }

  .bubble { padding: 0.65rem 0.95rem; border-radius: 18px; font-size: 0.9rem;
            line-height: 1.55; max-width: 100%; word-break: break-word; }
  .msg-user  .bubble { background: #0054a6; color: #fff; border-bottom-right-radius: 4px; }
  .msg-agent .bubble { background: #fff; color: #212529; border: 1px solid #dee2e6;
                       border-bottom-left-radius: 4px; }

  /* Markdown inside bubbles */
  .bubble p { margin: 0.4rem 0; }
  .bubble p:first-child { margin-top: 0; }
  .bubble p:last-child  { margin-bottom: 0; }
  .bubble h1,.bubble h2,.bubble h3,.bubble h4,.bubble h5,.bubble h6
    { margin: 0.65rem 0 0.25rem; font-size: 0.95rem; }
  .bubble ul,.bubble ol { padding-left: 1.3rem; margin: 0.3rem 0; }
  .bubble li { margin: 0.2rem 0; }
  .bubble code { background: #f1f3f5; border-radius: 4px; padding: 0.1em 0.35em; font-size: 0.85em; }
  .msg-user .bubble code { background: rgba(255,255,255,0.2); }
  .bubble pre { background: #f1f3f5; border-radius: 8px; padding: 0.75rem; overflow-x: auto; margin: 0.5rem 0; }
  .bubble pre code { background: none; padding: 0; }
  .bubble blockquote { margin: 0.4rem 0; padding-left: 0.75rem; border-left: 3px solid #ced4da; color: #6c757d; }
  .bubble table { border-collapse: collapse; width: 100%; margin: 0.5rem 0; font-size: 0.85rem; }
  .bubble th,.bubble td { border: 1px solid #dee2e6; padding: 0.3rem 0.6rem; text-align: left; }
  .bubble th { background: #f8f9fa; font-weight: 600; }
  .bubble a { color: #0054a6; }
  .msg-user .bubble a { color: #bfdbfe; }
  .bubble hr { border: none; border-top: 1px solid #dee2e6; margin: 0.5rem 0; }

  /* Typing indicator */
  .typing { display: flex; align-items: center; gap: 5px; padding: 0.15rem 0.1rem; }
  .typing span { width: 7px; height: 7px; border-radius: 50%; background: #adb5bd;
                 animation: bounce 1.2s ease-in-out infinite; }
  .typing span:nth-child(2) { animation-delay: 0.2s; }
  .typing span:nth-child(3) { animation-delay: 0.4s; }
  @keyframes bounce {
    0%,60%,100% { transform: translateY(0); opacity: 0.6; }
    30% { transform: translateY(-6px); opacity: 1; }
  }

  /* Input bar */
  #app-footer { flex-shrink: 0; background: #fff; border-top: 1px solid #dee2e6; padding: 0.75rem 1rem; }
  #app-footer form { display: flex; gap: 0.5rem; max-width: 760px; margin: 0 auto; align-items: center; }
  #app-footer input[type=text] { flex: 1; padding: 0.6rem 1rem; font-size: 0.9rem;
                                  border: 1px solid #ced4da; border-radius: 24px; outline: none;
                                  background: #f8f9fa; transition: border-color 0.15s, background 0.15s; }
  #app-footer input[type=text]:focus    { border-color: #0054a6; background: #fff; box-shadow: 0 0 0 3px rgba(0,84,166,0.15); }
  #app-footer input[type=text]:disabled { opacity: 0.55; cursor: not-allowed; }
  #app-footer button[type=submit] { width: 2.5rem; height: 2.5rem; background: #0054a6; color: #fff;
                                     border: none; border-radius: 50%; cursor: pointer; font-size: 1rem;
                                     display: flex; align-items: center; justify-content: center;
                                     flex-shrink: 0; transition: background 0.15s, opacity 0.15s; }
  #app-footer button[type=submit]:hover:not(:disabled) { background: #003d7a; }
  #app-footer button[type=submit]:disabled { opacity: 0.45; cursor: not-allowed; }
</style>
</head>
<body>

<!-- USPTO: Global header with logo -->
<header id="global-header">
  <div class="uspto-header-top">
    <nav class="navbar navbar-expand-lg navbar-dark">
      <a href="https://www.uspto.gov" target="_blank" class="uspto-logo"
         title="United States Patent and Trademark Office - An Agency of the Department of Commerce">
        <span class="visually-hidden">United States Patent and Trademark Office</span>
      </a>
    </nav>
  </div>
</header>

<!-- App title bar -->
<div id="app-subheader">
  <h1>Accessibility Assistant</h1>
  <p>Scan public URLs for Section 508 / WCAG issues &middot; Team 20</p>
</div>

<!-- Chat messages -->
<div id="chat">
  <div id="welcome">
    <h2>What would you like to check?</h2>
    <p>Give me a public URL and I&rsquo;ll scan it for accessibility issues &mdash;
       alt text, headings, links, forms, landmarks, ARIA, and more.</p>
    <div class="chips">
      <button class="chip" onclick="useChip(this)">Scan alt text on a page</button>
      <button class="chip" onclick="useChip(this)">Check heading structure</button>
      <button class="chip" onclick="useChip(this)">Audit form labels</button>
      <button class="chip" onclick="useChip(this)">Find broken link text</button>
      <button class="chip" onclick="useChip(this)">Check ARIA issues</button>
      <button class="chip" onclick="useChip(this)">Scan an entire site</button>
    </div>
  </div>
</div>

<!-- Input bar -->
<div id="app-footer">
  <form id="f">
    <input id="msg" type="text" placeholder="Ask me to check a URL&hellip;" autofocus autocomplete="off">
    <button type="submit" aria-label="Send">&#9658;</button>
  </form>
</div>

<!-- Bootstrap JS (for banner collapse) -->
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"
        integrity="sha384-geWF76RCwLtnZ8qwWowPQNguL3RmwHVBC9FhGdlKrxdiJJigb/j/68SIy3Te4Bkz"
        crossorigin="anonymous"></script>

<script>
const chat  = document.getElementById('chat');
const form  = document.getElementById('f');
const input = document.getElementById('msg');
const btn   = form.querySelector('button[type=submit]');

function setLoading(on) {
  input.disabled = on;
  btn.disabled   = on;
}

function hideWelcome() {
  const w = document.getElementById('welcome');
  if (w) w.remove();
}

function useChip(el) {
  input.value = el.textContent;
  input.focus();
}

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function renderInline(s) {
  s = s.replace(/`([^`]+)`/g, (_, code) => '<code>' + code + '</code>');
  s = s.replace(/\\[([^\\]]+)\\]\\((https?:\\/\\/[^\\s)]+)\\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  s = s.replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>');
  s = s.replace(/__([^_]+)__/g, '<strong>$1</strong>');
  s = s.replace(/\\*([^*]+)\\*/g, '<em>$1</em>');
  s = s.replace(/(?<!\\w)_([^_]+)_(?!\\w)/g, '<em>$1</em>');
  return s;
}

function isBlockStart(line) {
  return /^```/.test(line) || /^#{1,6}\\s+/.test(line) ||
         /^(-{3,}|\\*{3,})\\s*$/.test(line.trim()) || /^&gt;\\s?/.test(line) ||
         /^\\s*[-*+]\\s+/.test(line) || /^\\s*\\d+\\.\\s+/.test(line);
}

function splitTableRow(line) {
  let t = line.trim();
  if (t.startsWith('|')) t = t.slice(1);
  if (t.endsWith('|')) t = t.slice(0, -1);
  return t.split('|').map(c => c.trim());
}

function renderBlocks(lines) {
  let html = '';
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === '') { i++; continue; }

    if (/^```/.test(line)) {
      const codeLines = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) { codeLines.push(lines[i]); i++; }
      i++;
      html += '<pre><code>' + codeLines.join('\\n') + '</code></pre>';
      continue;
    }

    const heading = line.match(/^(#{1,6})\\s+(.*)$/);
    if (heading) {
      const level = heading[1].length;
      html += '<h' + level + '>' + renderInline(heading[2]) + '</h' + level + '>';
      i++;
      continue;
    }

    if (/^(-{3,}|\\*{3,})\\s*$/.test(line.trim())) {
      html += '<hr>';
      i++;
      continue;
    }

    if (/^&gt;\\s?/.test(line)) {
      const quoteLines = [];
      while (i < lines.length && /^&gt;\\s?/.test(lines[i])) {
        quoteLines.push(lines[i].replace(/^&gt;\\s?/, ''));
        i++;
      }
      html += '<blockquote>' + renderBlocks(quoteLines) + '</blockquote>';
      continue;
    }

    if (line.includes('|') && i + 1 < lines.length &&
        /^\\s*\\|?\\s*:?-{3,}:?\\s*(\\|\\s*:?-{3,}:?\\s*)*\\|?\\s*$/.test(lines[i + 1])) {
      const headerCells = splitTableRow(line);
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].includes('|') && lines[i].trim() !== '') {
        rows.push(splitTableRow(lines[i]));
        i++;
      }
      html += '<table><thead><tr>' +
        headerCells.map(c => '<th>' + renderInline(c) + '</th>').join('') +
        '</tr></thead><tbody>' +
        rows.map(r => '<tr>' + r.map(c => '<td>' + renderInline(c) + '</td>').join('') + '</tr>').join('') +
        '</tbody></table>';
      continue;
    }

    if (/^\\s*[-*+]\\s+/.test(line) || /^\\s*\\d+\\.\\s+/.test(line)) {
      const ordered = /^\\s*\\d+\\.\\s+/.test(line);
      const re = ordered ? /^\\s*\\d+\\.\\s+/ : /^\\s*[-*+]\\s+/;
      const items = [];
      while (i < lines.length && re.test(lines[i])) {
        items.push(lines[i].replace(re, ''));
        i++;
      }
      const tag = ordered ? 'ol' : 'ul';
      html += '<' + tag + '>' + items.map(it => '<li>' + renderInline(it) + '</li>').join('') + '</' + tag + '>';
      continue;
    }

    const paraLines = [line];
    i++;
    while (i < lines.length && lines[i].trim() !== '' && !isBlockStart(lines[i])) {
      paraLines.push(lines[i]);
      i++;
    }
    html += '<p>' + paraLines.map(renderInline).join('<br>') + '</p>';
  }
  return html;
}

function renderMarkdown(raw) {
  const lines = escapeHtml(raw).replace(/\\r\\n/g, '\\n').split('\\n');
  return renderBlocks(lines);
}

function appendMsg(role, text, asMarkdown) {
  const wrap   = document.createElement('div');
  wrap.className = 'msg msg-' + role;
  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.setAttribute('aria-hidden', 'true');
  avatar.textContent = role === 'user' ? 'You' : 'A11y';
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  if (asMarkdown) {
    bubble.innerHTML = renderMarkdown(text);
  } else {
    bubble.textContent = text;
  }
  wrap.appendChild(avatar);
  wrap.appendChild(bubble);
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  return bubble;
}

function showTyping() {
  const wrap   = document.createElement('div');
  wrap.className = 'msg msg-agent';
  wrap.id = 'typing-indicator';
  const avatar = document.createElement('div');
  avatar.className = 'avatar';
  avatar.setAttribute('aria-hidden', 'true');
  avatar.textContent = 'A11y';
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.innerHTML = '<div class="typing"><span></span><span></span><span></span></div>';
  wrap.appendChild(avatar);
  wrap.appendChild(bubble);
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
}

function removeTyping() {
  const el = document.getElementById('typing-indicator');
  if (el) el.remove();
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const message = input.value.trim();
  if (!message) return;
  hideWelcome();
  appendMsg('user', message, false);
  input.value = '';
  setLoading(true);
  showTyping();
  try {
    const resp = await fetch('/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message}),
    });
    const data = await resp.json();
    removeTyping();
    if (resp.ok && data.reply !== undefined) {
      appendMsg('agent', data.reply, true);
    } else {
      appendMsg('agent', 'Error: ' + data.error, false);
    }
  } catch (err) {
    removeTyping();
    appendMsg('agent', 'Error: ' + err, false);
  } finally {
    setLoading(false);
    input.focus();
  }
});
</script>
</body>
</html>
"""


async def index(request: Request) -> HTMLResponse:
    return HTMLResponse(_INDEX_HTML)


app = Starlette(
    routes=[
        Route("/", index),
        Route("/health", health),
        Route("/chat", chat, methods=["POST"]),
        Mount("/static", app=StaticFiles(directory=_STATIC_DIR), name="static"),
    ]
)

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("DATABRICKS_APP_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
