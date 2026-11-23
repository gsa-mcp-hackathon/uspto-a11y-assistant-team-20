"""Functional tests for check_link_text, check_heading_structure,
check_form_labels, and scan_site.

Network calls are mocked (via fetch_text_safely) so these run
deterministically without depending on live external pages.
"""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from alt_text_mcp.tools import check_form_labels as check_form_labels_module
from alt_text_mcp.tools import check_heading_structure as check_heading_module
from alt_text_mcp.tools import check_link_text as check_link_text_module
from alt_text_mcp.tools import scan_site as scan_site_module
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError

_LINKS_HTML = """
<html><body>
  <a href="/about">About the agency</a>
  <a href="/report.pdf">click here</a>
  <a href="https://example.gov/raw">https://example.gov/raw</a>
  <a href="/icon" aria-label="Open settings"><span class="gear-icon"></span></a>
  <a href="/empty"></a>
</body></html>
"""

_HEADINGS_HTML = """
<html><body>
  <h1>Agency Home</h1>
  <h2>Section One</h2>
  <h4>Skips to h4</h4>
  <h2></h2>
</body></html>
"""

_NO_H1_HTML = "<html><body><h2>Only an h2</h2></body></html>"
_MULTI_H1_HTML = "<html><body><h1>First</h1><h1>Second</h1></body></html>"

_FORM_HTML = """
<html><body>
  <form>
    <label for="name">Name</label>
    <input id="name" type="text">

    <label>Email <input id="email" type="email"></label>

    <input id="phone" type="tel" placeholder="Phone number">

    <input type="text" aria-label="Search" placeholder="Search">

    <input type="hidden" name="token" value="abc">

    <button type="submit">Submit</button>
  </form>
</body></html>
"""

_SITE_START_HTML = """
<html><body>
  <img src="logo.png">
  <a href="/page2">Page two</a>
  <a href="https://other.gov/page">External</a>
  <a href="/page2">Page two again</a>
</body></html>
"""

_SITE_PAGE2_HTML = """
<html><body>
  <img src="banner.png" alt="image of a banner">
</body></html>
"""


@pytest.fixture
def link_tool():
    mcp = FastMCP(name="test")
    check_link_text_module.register(mcp)
    return mcp


@pytest.fixture
def heading_tool():
    mcp = FastMCP(name="test")
    check_heading_module.register(mcp)
    return mcp


@pytest.fixture
def form_tool():
    mcp = FastMCP(name="test")
    check_form_labels_module.register(mcp)
    return mcp


@pytest.fixture
def site_tool():
    mcp = FastMCP(name="test")
    scan_site_module.register(mcp)
    return mcp


# --- check_link_text ---------------------------------------------------


@pytest.mark.asyncio
async def test_check_link_text_classifies_each_link(monkeypatch, link_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _LINKS_HTML

    monkeypatch.setattr(
        check_link_text_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await link_tool.get_tool("check_link_text")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    by_text = {link["text"]: link for link in data["links"]}

    assert by_text["About the agency"]["status"] == "present"
    assert by_text["About the agency"]["issues"] == []

    assert by_text["click here"]["status"] == "present"
    assert any("generic" in i for i in by_text["click here"]["issues"])

    assert by_text["https://example.gov/raw"]["status"] == "present"
    assert any("raw URL" in i for i in by_text["https://example.gov/raw"]["issues"])

    empty_with_label = next(
        link for link in data["links"] if link["href"].endswith("/icon")
    )
    assert empty_with_label["status"] == "empty-text-with-label"

    empty = next(link for link in data["links"] if link["href"].endswith("/empty"))
    assert empty["status"] == "empty"
    assert empty["issues"]

    assert data["summary"]["empty"] == 1
    assert data["summary"]["emptyWithLabel"] == 1


@pytest.mark.asyncio
async def test_check_link_text_reports_blocked_url(monkeypatch, link_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise BlockedUrlError("URL resolves to a disallowed address range.")

    monkeypatch.setattr(
        check_link_text_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await link_tool.get_tool("check_link_text")
    result = await tool.run({"params": {"url": "http://169.254.169.254/"}})

    assert "error" in result.structured_content


@pytest.mark.asyncio
async def test_check_link_text_reports_upstream_error(monkeypatch, link_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise UpstreamServiceError("Upstream returned status 500.")

    monkeypatch.setattr(
        check_link_text_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await link_tool.get_tool("check_link_text")
    result = await tool.run({"params": {"url": "https://example.gov/down"}})

    assert result.structured_content["error"] == "Upstream returned status 500."


# --- check_heading_structure --------------------------------------------


@pytest.mark.asyncio
async def test_check_heading_structure_flags_skipped_level(monkeypatch, heading_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _HEADINGS_HTML

    monkeypatch.setattr(
        check_heading_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await heading_tool.get_tool("check_heading_structure")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["summary"]["totalHeadings"] == 4
    assert data["summary"]["h1Count"] == 1
    assert data["summary"]["skippedLevels"] == 1
    assert data["summary"]["emptyHeadings"] == 1
    assert any("skipped level" in i for i in data["issues"])
    assert any("empty heading" in i for i in data["issues"])
    assert not any("no-h1" in i or "multiple-h1" in i for i in data["issues"])


@pytest.mark.asyncio
async def test_check_heading_structure_flags_no_h1(monkeypatch, heading_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _NO_H1_HTML

    monkeypatch.setattr(
        check_heading_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await heading_tool.get_tool("check_heading_structure")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["summary"]["h1Count"] == 0
    assert any("no-h1" in i for i in data["issues"])


@pytest.mark.asyncio
async def test_check_heading_structure_flags_multiple_h1(monkeypatch, heading_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _MULTI_H1_HTML

    monkeypatch.setattr(
        check_heading_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await heading_tool.get_tool("check_heading_structure")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["summary"]["h1Count"] == 2
    assert any("multiple-h1" in i for i in data["issues"])


@pytest.mark.asyncio
async def test_check_heading_structure_reports_blocked_url(monkeypatch, heading_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise BlockedUrlError("URL resolves to a disallowed address range.")

    monkeypatch.setattr(
        check_heading_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await heading_tool.get_tool("check_heading_structure")
    result = await tool.run({"params": {"url": "http://127.0.0.1/"}})

    assert "error" in result.structured_content


# --- check_form_labels ---------------------------------------------------


@pytest.mark.asyncio
async def test_check_form_labels_classifies_each_field(monkeypatch, form_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _FORM_HTML

    monkeypatch.setattr(
        check_form_labels_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await form_tool.get_tool("check_form_labels")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    # hidden input and submit button excluded entirely.
    assert data["totalFieldsOnPage"] == 4

    by_field = {f["field"]: f for f in data["fields"]}
    assert by_field["input[name]"]["status"] == "labeled"
    assert by_field["input[email]"]["status"] == "labeled"
    assert by_field["input[phone]"]["status"] == "unlabeled"
    assert any("placeholder" in i for i in by_field["input[phone]"]["issues"])

    assert data["summary"]["labeled"] == 3
    assert data["summary"]["unlabeled"] == 1


@pytest.mark.asyncio
async def test_check_form_labels_reports_upstream_error(monkeypatch, form_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise UpstreamServiceError("Upstream returned status 500.")

    monkeypatch.setattr(
        check_form_labels_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await form_tool.get_tool("check_form_labels")
    result = await tool.run({"params": {"url": "https://example.gov/down"}})

    assert result.structured_content["error"] == "Upstream returned status 500."


# --- scan_site ------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_site_crawls_same_origin_links_and_dedupes(monkeypatch, site_tool):
    pages_served = {
        "https://example.gov/": _SITE_START_HTML,
        "https://example.gov/page2": _SITE_PAGE2_HTML,
    }

    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return pages_served[url]

    monkeypatch.setattr(scan_site_module, "fetch_text_safely", fake_fetch_text_safely)

    tool = await site_tool.get_tool("scan_site")
    result = await tool.run({"params": {"url": "https://example.gov/"}})
    data = result.structured_content

    scanned_urls = [p["url"] for p in data["pages"]]
    assert scanned_urls == ["https://example.gov/", "https://example.gov/page2"]
    assert "https://other.gov/page" not in scanned_urls

    page2 = next(p for p in data["pages"] if p["url"] == "https://example.gov/page2")
    assert page2["summary"]["presentWithIssues"] == 1

    assert data["summary"]["pagesScanned"] == 2
    assert data["summary"]["totalMissing"] == 1


@pytest.mark.asyncio
async def test_scan_site_respects_max_pages(monkeypatch, site_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _SITE_START_HTML

    monkeypatch.setattr(scan_site_module, "fetch_text_safely", fake_fetch_text_safely)

    tool = await site_tool.get_tool("scan_site")
    result = await tool.run({"params": {"url": "https://example.gov/", "max_pages": 1}})
    data = result.structured_content

    assert len(data["pages"]) == 1
    assert data["pagesSkipped"] == ["https://example.gov/page2"]


@pytest.mark.asyncio
async def test_scan_site_reports_blocked_start_url(monkeypatch, site_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise BlockedUrlError("URL resolves to a disallowed address range.")

    monkeypatch.setattr(scan_site_module, "fetch_text_safely", fake_fetch_text_safely)

    tool = await site_tool.get_tool("scan_site")
    result = await tool.run({"params": {"url": "http://127.0.0.1/"}})

    assert "error" in result.structured_content
