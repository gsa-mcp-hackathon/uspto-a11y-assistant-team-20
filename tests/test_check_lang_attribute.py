"""Functional tests for check_lang_attribute.

Network calls are mocked (via fetch_text_safely) so these run
deterministically without depending on live external pages.
"""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from alt_text_mcp.tools import check_lang_attribute as check_lang_attribute_module
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError

_LANG_EN_HTML = '<html lang="en"><body><p>Hello</p></body></html>'
_LANG_EN_US_HTML = '<html lang="en-US"><body><p>Hello</p></body></html>'
_NO_LANG_HTML = "<html><body><p>Hello</p></body></html>"
_EMPTY_LANG_HTML = '<html lang=""><body><p>Hello</p></body></html>'
_MALFORMED_LANG_HTML = '<html lang="not a real tag!!"><body><p>Hello</p></body></html>'


@pytest.fixture
def lang_tool():
    mcp = FastMCP(name="test")
    check_lang_attribute_module.register(mcp)
    return mcp


@pytest.mark.asyncio
async def test_check_lang_attribute_present_en(monkeypatch, lang_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _LANG_EN_HTML

    monkeypatch.setattr(
        check_lang_attribute_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await lang_tool.get_tool("check_lang_attribute")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["status"] == "present"
    assert data["lang"] == "en"
    assert data["issues"] == []


@pytest.mark.asyncio
async def test_check_lang_attribute_present_hyphenated(monkeypatch, lang_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _LANG_EN_US_HTML

    monkeypatch.setattr(
        check_lang_attribute_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await lang_tool.get_tool("check_lang_attribute")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["status"] == "present"
    assert data["lang"] == "en-US"
    assert data["issues"] == []


@pytest.mark.asyncio
async def test_check_lang_attribute_missing(monkeypatch, lang_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _NO_LANG_HTML

    monkeypatch.setattr(
        check_lang_attribute_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await lang_tool.get_tool("check_lang_attribute")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["status"] == "missing"
    assert data["lang"] is None
    assert any("no lang attribute" in i for i in data["issues"])


@pytest.mark.asyncio
async def test_check_lang_attribute_empty(monkeypatch, lang_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _EMPTY_LANG_HTML

    monkeypatch.setattr(
        check_lang_attribute_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await lang_tool.get_tool("check_lang_attribute")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["status"] == "empty"
    assert any("empty" in i for i in data["issues"])


@pytest.mark.asyncio
async def test_check_lang_attribute_malformed(monkeypatch, lang_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _MALFORMED_LANG_HTML

    monkeypatch.setattr(
        check_lang_attribute_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await lang_tool.get_tool("check_lang_attribute")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["status"] == "malformed"
    assert any("BCP-47" in i for i in data["issues"])


@pytest.mark.asyncio
async def test_check_lang_attribute_reports_blocked_url(monkeypatch, lang_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise BlockedUrlError("URL resolves to a disallowed address range.")

    monkeypatch.setattr(
        check_lang_attribute_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await lang_tool.get_tool("check_lang_attribute")
    result = await tool.run({"params": {"url": "http://127.0.0.1/"}})

    assert "error" in result.structured_content


@pytest.mark.asyncio
async def test_check_lang_attribute_reports_upstream_error(monkeypatch, lang_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise UpstreamServiceError("Upstream returned status 500.")

    monkeypatch.setattr(
        check_lang_attribute_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await lang_tool.get_tool("check_lang_attribute")
    result = await tool.run({"params": {"url": "https://example.gov/down"}})

    assert result.structured_content["error"] == "Upstream returned status 500."
