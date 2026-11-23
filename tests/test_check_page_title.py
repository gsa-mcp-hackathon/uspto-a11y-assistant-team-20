"""Functional tests for check_page_title.

Network calls are mocked (via fetch_text_safely) so these run
deterministically without depending on live external pages.
"""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from alt_text_mcp.tools import check_page_title as check_page_title_module
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError

_PRESENT_HTML = (
    "<html><head><title>Agency Benefits Overview</title></head><body></body></html>"
)
_MISSING_HTML = "<html><head></head><body><p>No title here</p></body></html>"
_EMPTY_HTML = "<html><head><title></title></head><body></body></html>"
_GENERIC_HTML = (
    "<html><head><title>Untitled Document</title></head><body></body></html>"
)
_WHITESPACE_GENERIC_HTML = (
    "<html><head><title>  Home  </title></head><body></body></html>"
)


@pytest.fixture
def title_tool():
    mcp = FastMCP(name="test")
    check_page_title_module.register(mcp)
    return mcp


@pytest.mark.asyncio
async def test_check_page_title_present_with_no_issues(monkeypatch, title_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _PRESENT_HTML

    monkeypatch.setattr(
        check_page_title_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await title_tool.get_tool("check_page_title")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["status"] == "present"
    assert data["title"] == "Agency Benefits Overview"
    assert data["issues"] == []


@pytest.mark.asyncio
async def test_check_page_title_missing(monkeypatch, title_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _MISSING_HTML

    monkeypatch.setattr(
        check_page_title_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await title_tool.get_tool("check_page_title")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["status"] == "missing"
    assert data["title"] is None
    assert any("no <title> element" in i for i in data["issues"])


@pytest.mark.asyncio
async def test_check_page_title_empty(monkeypatch, title_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _EMPTY_HTML

    monkeypatch.setattr(
        check_page_title_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await title_tool.get_tool("check_page_title")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["status"] == "empty"
    assert data["title"] is None
    assert any("present but empty" in i for i in data["issues"])


@pytest.mark.asyncio
async def test_check_page_title_flags_generic_title(monkeypatch, title_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _GENERIC_HTML

    monkeypatch.setattr(
        check_page_title_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await title_tool.get_tool("check_page_title")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["status"] == "present"
    assert data["title"] == "Untitled Document"
    assert any("generic" in i for i in data["issues"])


@pytest.mark.asyncio
async def test_check_page_title_flags_generic_title_with_whitespace(
    monkeypatch, title_tool
):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _WHITESPACE_GENERIC_HTML

    monkeypatch.setattr(
        check_page_title_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await title_tool.get_tool("check_page_title")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["status"] == "present"
    assert data["title"] == "Home"
    assert any("generic" in i for i in data["issues"])


@pytest.mark.asyncio
async def test_check_page_title_reports_blocked_url(monkeypatch, title_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise BlockedUrlError("URL resolves to a disallowed address range.")

    monkeypatch.setattr(
        check_page_title_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await title_tool.get_tool("check_page_title")
    result = await tool.run({"params": {"url": "http://127.0.0.1/"}})

    assert "error" in result.structured_content


@pytest.mark.asyncio
async def test_check_page_title_reports_upstream_error(monkeypatch, title_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise UpstreamServiceError("Upstream returned status 500.")

    monkeypatch.setattr(
        check_page_title_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await title_tool.get_tool("check_page_title")
    result = await tool.run({"params": {"url": "https://example.gov/down"}})

    assert result.structured_content["error"] == "Upstream returned status 500."
