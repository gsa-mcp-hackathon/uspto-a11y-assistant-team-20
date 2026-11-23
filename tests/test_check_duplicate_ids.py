"""Functional tests for check_duplicate_ids.

Network calls are mocked (via fetch_text_safely) so these run
deterministically without depending on live external pages.
"""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from alt_text_mcp.tools import check_duplicate_ids as check_duplicate_ids_module
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError

_DUPLICATE_IDS_HTML = """
<html><body>
  <div id="main">Main content</div>
  <span id="main">Duplicate main</span>
  <p id="intro">Intro</p>
  <input id="email">
  <label id="email">Email</label>
  <label id="email">Email again</label>
  <h1 id="  ">Whitespace id ignored</h1>
  <h2 id="">Empty id ignored</h2>
</body></html>
"""

_NO_DUPLICATE_IDS_HTML = """
<html><body>
  <div id="main">Main content</div>
  <p id="intro">Intro</p>
  <span id="footer">Footer</span>
</body></html>
"""


@pytest.fixture
def duplicate_ids_tool():
    mcp = FastMCP(name="test")
    check_duplicate_ids_module.register(mcp)
    return mcp


@pytest.mark.asyncio
async def test_check_duplicate_ids_groups_and_counts(monkeypatch, duplicate_ids_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _DUPLICATE_IDS_HTML

    monkeypatch.setattr(
        check_duplicate_ids_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await duplicate_ids_tool.get_tool("check_duplicate_ids")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    # main(2) + intro(1) + email(3) == 6; whitespace/empty ids excluded.
    assert data["totalIdsOnPage"] == 6
    assert data["uniqueIds"] == 3

    by_id = {group["id"]: group for group in data["duplicateIds"]}
    assert by_id["main"]["count"] == 2
    assert by_id["main"]["elements"] == ["div", "span"]
    assert by_id["email"]["count"] == 3
    assert by_id["email"]["elements"] == ["input", "label", "label"]
    assert "intro" not in by_id

    assert data["summary"]["duplicateGroups"] == 2
    assert data["summary"]["duplicateElements"] == 5


@pytest.mark.asyncio
async def test_check_duplicate_ids_reports_no_duplicates(
    monkeypatch, duplicate_ids_tool
):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _NO_DUPLICATE_IDS_HTML

    monkeypatch.setattr(
        check_duplicate_ids_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await duplicate_ids_tool.get_tool("check_duplicate_ids")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["totalIdsOnPage"] == 3
    assert data["uniqueIds"] == 3
    assert data["duplicateIds"] == []
    assert data["summary"]["duplicateGroups"] == 0
    assert data["summary"]["duplicateElements"] == 0


@pytest.mark.asyncio
async def test_check_duplicate_ids_reports_blocked_url(monkeypatch, duplicate_ids_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise BlockedUrlError("URL resolves to a disallowed address range.")

    monkeypatch.setattr(
        check_duplicate_ids_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await duplicate_ids_tool.get_tool("check_duplicate_ids")
    result = await tool.run({"params": {"url": "http://127.0.0.1/"}})

    assert "error" in result.structured_content


@pytest.mark.asyncio
async def test_check_duplicate_ids_reports_upstream_error(
    monkeypatch, duplicate_ids_tool
):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise UpstreamServiceError("Upstream returned status 500.")

    monkeypatch.setattr(
        check_duplicate_ids_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await duplicate_ids_tool.get_tool("check_duplicate_ids")
    result = await tool.run({"params": {"url": "https://example.gov/down"}})

    assert result.structured_content["error"] == "Upstream returned status 500."
