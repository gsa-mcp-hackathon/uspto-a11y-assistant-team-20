"""Functional tests for check_iframe_titles.

Network calls are mocked (via fetch_text_safely) so these run
deterministically without depending on live external pages.
"""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from alt_text_mcp.tools import check_iframe_titles as check_iframe_titles_module
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError

_IFRAMES_HTML = """
<html><body>
  <iframe title="Scheduling widget" src="https://example.gov/schedule"></iframe>
  <iframe src="https://example.gov/untitled"></iframe>
</body></html>
"""

_WHITESPACE_TITLE_HTML = """
<html><body>
  <iframe title="   " src="https://example.gov/whitespace"></iframe>
</body></html>
"""

_TWO_IFRAMES_HTML = """
<html><body>
  <iframe title="First" src="https://example.gov/first"></iframe>
  <iframe title="Second" src="https://example.gov/second"></iframe>
</body></html>
"""


@pytest.fixture
def iframe_tool():
    mcp = FastMCP(name="test")
    check_iframe_titles_module.register(mcp)
    return mcp


@pytest.mark.asyncio
async def test_check_iframe_titles_classifies_each_iframe(monkeypatch, iframe_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _IFRAMES_HTML

    monkeypatch.setattr(
        check_iframe_titles_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await iframe_tool.get_tool("check_iframe_titles")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    by_src = {f["src"]: f for f in data["iframes"]}

    present = by_src["https://example.gov/schedule"]
    assert present["status"] == "present"
    assert present["issues"] == []

    missing = by_src["https://example.gov/untitled"]
    assert missing["status"] == "missing"
    assert any("no title attribute" in i for i in missing["issues"])

    assert data["summary"]["present"] == 1
    assert data["summary"]["missing"] == 1


@pytest.mark.asyncio
async def test_check_iframe_titles_treats_whitespace_title_as_missing(
    monkeypatch, iframe_tool
):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _WHITESPACE_TITLE_HTML

    monkeypatch.setattr(
        check_iframe_titles_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await iframe_tool.get_tool("check_iframe_titles")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert len(data["iframes"]) == 1
    assert data["iframes"][0]["status"] == "missing"
    assert any("no title attribute" in i for i in data["iframes"][0]["issues"])
    assert data["summary"]["missing"] == 1
    assert data["summary"]["present"] == 0


@pytest.mark.asyncio
async def test_check_iframe_titles_total_count_unaffected_by_limit(
    monkeypatch, iframe_tool
):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _TWO_IFRAMES_HTML

    monkeypatch.setattr(
        check_iframe_titles_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await iframe_tool.get_tool("check_iframe_titles")
    result = await tool.run({"params": {"url": "https://example.gov/page", "limit": 1}})
    data = result.structured_content

    assert data["totalIframesOnPage"] == 2
    assert data["iframesReturned"] == 1
    assert len(data["iframes"]) == 1


@pytest.mark.asyncio
async def test_check_iframe_titles_reports_blocked_url(monkeypatch, iframe_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise BlockedUrlError("URL resolves to a disallowed address range.")

    monkeypatch.setattr(
        check_iframe_titles_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await iframe_tool.get_tool("check_iframe_titles")
    result = await tool.run({"params": {"url": "http://169.254.169.254/"}})

    assert "error" in result.structured_content


@pytest.mark.asyncio
async def test_check_iframe_titles_reports_upstream_error(monkeypatch, iframe_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise UpstreamServiceError("Upstream returned status 500.")

    monkeypatch.setattr(
        check_iframe_titles_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await iframe_tool.get_tool("check_iframe_titles")
    result = await tool.run({"params": {"url": "https://example.gov/down"}})

    assert result.structured_content["error"] == "Upstream returned status 500."
