"""Functional tests for check_table_headers.

Network calls are mocked (via fetch_text_safely) so these run
deterministically without depending on live external pages.
"""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from alt_text_mcp.tools import check_table_headers as check_table_headers_module
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError

_WELL_FORMED_TABLE_HTML = """
<html><body>
  <table>
    <caption>Quarterly Revenue</caption>
    <thead>
      <tr><th scope="col">Quarter</th><th scope="col">Revenue</th></tr>
    </thead>
    <tbody>
      <tr><td>Q1</td><td>$1M</td></tr>
      <tr><td>Q2</td><td>$2M</td></tr>
    </tbody>
  </table>
</body></html>
"""

_NO_TH_TABLE_HTML = """
<html><body>
  <table>
    <caption>Layout-ish table</caption>
    <tr><td>Name</td><td>Value</td></tr>
    <tr><td>Foo</td><td>1</td></tr>
  </table>
</body></html>
"""

_NO_CAPTION_TABLE_HTML = """
<html><body>
  <table>
    <tr><th scope="col">Name</th><th scope="col">Value</th></tr>
    <tr><td>Foo</td><td>1</td></tr>
  </table>
</body></html>
"""

_SCOPE_MISSING_TABLE_HTML = """
<html><body>
  <table>
    <caption>Multi-row data</caption>
    <tr><th>Name</th><th>Value</th></tr>
    <tr><td>Foo</td><td>1</td></tr>
    <tr><td>Bar</td><td>2</td></tr>
  </table>
</body></html>
"""


@pytest.fixture
def table_tool():
    mcp = FastMCP(name="test")
    check_table_headers_module.register(mcp)
    return mcp


@pytest.mark.asyncio
async def test_well_formed_table_has_no_issues(monkeypatch, table_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _WELL_FORMED_TABLE_HTML

    monkeypatch.setattr(
        check_table_headers_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await table_tool.get_tool("check_table_headers")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["totalTablesOnPage"] == 1
    table = data["tables"][0]
    assert table["hasTh"] is True
    assert table["hasCaption"] is True
    assert table["issues"] == []


@pytest.mark.asyncio
async def test_table_with_no_th_is_flagged(monkeypatch, table_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _NO_TH_TABLE_HTML

    monkeypatch.setattr(
        check_table_headers_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await table_tool.get_tool("check_table_headers")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    table = data["tables"][0]
    assert table["hasTh"] is False
    assert "no-th" in table["issues"]
    assert data["summary"]["tablesWithNoTh"] == 1


@pytest.mark.asyncio
async def test_table_with_no_caption_is_flagged(monkeypatch, table_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _NO_CAPTION_TABLE_HTML

    monkeypatch.setattr(
        check_table_headers_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await table_tool.get_tool("check_table_headers")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    table = data["tables"][0]
    assert table["hasCaption"] is False
    assert "missing-caption" in table["issues"]
    assert data["summary"]["tablesMissingCaption"] == 1


@pytest.mark.asyncio
async def test_table_with_missing_scope_is_flagged(monkeypatch, table_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _SCOPE_MISSING_TABLE_HTML

    monkeypatch.setattr(
        check_table_headers_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await table_tool.get_tool("check_table_headers")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    table = data["tables"][0]
    assert table["rows"] == 3
    assert "th-missing-scope" in table["issues"]
    assert data["summary"]["tablesWithScopeIssues"] == 1


@pytest.mark.asyncio
async def test_check_table_headers_reports_upstream_error(monkeypatch, table_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise UpstreamServiceError("Upstream returned status 500.")

    monkeypatch.setattr(
        check_table_headers_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await table_tool.get_tool("check_table_headers")
    result = await tool.run({"params": {"url": "https://example.gov/down"}})

    assert result.structured_content["error"] == "Upstream returned status 500."


@pytest.mark.asyncio
async def test_check_table_headers_reports_blocked_url(monkeypatch, table_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise BlockedUrlError("URL resolves to a disallowed address range.")

    monkeypatch.setattr(
        check_table_headers_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await table_tool.get_tool("check_table_headers")
    result = await tool.run({"params": {"url": "http://127.0.0.1/"}})

    assert "error" in result.structured_content
