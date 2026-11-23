"""Functional tests for check_aria_conflicts.

Network calls are mocked (via fetch_text_safely) so these run
deterministically without depending on live external pages.
"""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from alt_text_mcp.tools import check_aria_conflicts as check_aria_conflicts_module
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError

_INVALID_ROLE_HTML = """
<html><body>
  <div role="buttonish">Click</div>
</body></html>
"""

_REDUNDANT_ROLE_HTML = """
<html><body>
  <button role="button">OK</button>
</body></html>
"""

_ARIA_HIDDEN_FOCUSABLE_HTML = """
<html><body>
  <a href="/x" aria-hidden="true">Link</a>
</body></html>
"""

_POSITIVE_TABINDEX_HTML = """
<html><body>
  <input type="text" tabindex="5">
</body></html>
"""

_CLEAN_HTML = """
<html><body>
  <h1>Agency Home</h1>
  <p>Some plain content with no ARIA attributes at all.</p>
</body></html>
"""


@pytest.fixture
def aria_tool():
    mcp = FastMCP(name="test")
    check_aria_conflicts_module.register(mcp)
    return mcp


@pytest.mark.asyncio
async def test_check_aria_conflicts_flags_invalid_role(monkeypatch, aria_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _INVALID_ROLE_HTML

    monkeypatch.setattr(
        check_aria_conflicts_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await aria_tool.get_tool("check_aria_conflicts")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["summary"]["invalidRoles"] == 1
    assert any("not a recognized ARIA role" in f["issue"] for f in data["findings"])


@pytest.mark.asyncio
async def test_check_aria_conflicts_flags_redundant_role(monkeypatch, aria_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _REDUNDANT_ROLE_HTML

    monkeypatch.setattr(
        check_aria_conflicts_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await aria_tool.get_tool("check_aria_conflicts")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["summary"]["redundantRoles"] == 1
    assert any("redundant" in f["issue"] for f in data["findings"])


@pytest.mark.asyncio
async def test_check_aria_conflicts_flags_aria_hidden_focusable(monkeypatch, aria_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _ARIA_HIDDEN_FOCUSABLE_HTML

    monkeypatch.setattr(
        check_aria_conflicts_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await aria_tool.get_tool("check_aria_conflicts")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["summary"]["ariaHiddenFocusable"] == 1
    assert any("hidden from assistive tech" in f["issue"] for f in data["findings"])


@pytest.mark.asyncio
async def test_check_aria_conflicts_flags_positive_tabindex(monkeypatch, aria_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _POSITIVE_TABINDEX_HTML

    monkeypatch.setattr(
        check_aria_conflicts_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await aria_tool.get_tool("check_aria_conflicts")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["summary"]["positiveTabindex"] == 1
    assert any("overrides natural tab order" in f["issue"] for f in data["findings"])


@pytest.mark.asyncio
async def test_check_aria_conflicts_clean_page_has_no_findings(monkeypatch, aria_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _CLEAN_HTML

    monkeypatch.setattr(
        check_aria_conflicts_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await aria_tool.get_tool("check_aria_conflicts")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["findings"] == []
    assert data["summary"] == {
        "invalidRoles": 0,
        "redundantRoles": 0,
        "ariaHiddenFocusable": 0,
        "positiveTabindex": 0,
    }


@pytest.mark.asyncio
async def test_check_aria_conflicts_reports_upstream_error(monkeypatch, aria_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise UpstreamServiceError("Upstream returned status 500.")

    monkeypatch.setattr(
        check_aria_conflicts_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await aria_tool.get_tool("check_aria_conflicts")
    result = await tool.run({"params": {"url": "https://example.gov/down"}})

    assert result.structured_content["error"] == "Upstream returned status 500."


@pytest.mark.asyncio
async def test_check_aria_conflicts_reports_blocked_url(monkeypatch, aria_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise BlockedUrlError("URL resolves to a disallowed address range.")

    monkeypatch.setattr(
        check_aria_conflicts_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await aria_tool.get_tool("check_aria_conflicts")
    result = await tool.run({"params": {"url": "http://127.0.0.1/"}})

    assert "error" in result.structured_content
