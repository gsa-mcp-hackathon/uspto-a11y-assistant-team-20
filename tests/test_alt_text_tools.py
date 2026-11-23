"""Functional tests for scan_page_alt_text and fetch_image.

Network calls are mocked (via fetch_text_safely/fetch_url_safely) so these
run deterministically in CI without depending on live external pages.
"""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from alt_text_mcp.tools import fetch_image as fetch_image_module
from alt_text_mcp.tools import scan_alt_text
from alt_text_mcp.tools.scan_alt_text import _classify_alt
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError

_SAMPLE_HTML = """
<html><body>
  <img src="logo.png">
  <img src="icon.svg" alt="">
  <img src="hero.jpg" alt="DSC_1029_final.jpg">
  <img src="banner.png" alt="image of a sunset over the mountains">
  <img src="team.jpg" alt="Our leadership team posing in front of headquarters">
  <figure>
    <img src="chart.png" alt="Quarterly revenue chart">
    <figcaption>Figure 1: Revenue by quarter</figcaption>
  </figure>
</body></html>
"""


@pytest.fixture
def scan_tool():
    mcp = FastMCP(name="test")
    scan_alt_text.register(mcp)
    return mcp


@pytest.fixture
def fetch_tool():
    mcp = FastMCP(name="test")
    fetch_image_module.register(mcp)
    return mcp


@pytest.mark.asyncio
async def test_scan_page_alt_text_classifies_each_image(monkeypatch, scan_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _SAMPLE_HTML

    monkeypatch.setattr(scan_alt_text, "fetch_text_safely", fake_fetch_text_safely)

    tool = await scan_tool.get_tool("scan_page_alt_text")
    result = await tool.run(
        {"params": {"url": "https://example.gov/page", "limit": 20}}
    )
    data = result.structured_content

    assert data["totalImagesOnPage"] == 6
    by_src = {img["src"].rsplit("/", 1)[-1]: img for img in data["images"]}

    assert by_src["logo.png"]["status"] == "missing"
    assert by_src["icon.svg"]["status"] == "empty-decorative"
    assert by_src["hero.jpg"]["status"] == "present"
    assert "filename" in by_src["hero.jpg"]["issues"][0]
    assert by_src["banner.png"]["status"] == "present"
    assert any("generic phrase" in issue for issue in by_src["banner.png"]["issues"])
    assert by_src["team.jpg"]["issues"] == []
    assert by_src["chart.png"]["nearbyCaption"] == "Figure 1: Revenue by quarter"

    assert data["summary"]["missing"] == 1
    assert data["summary"]["emptyDecorative"] == 1
    assert data["summary"]["presentWithIssues"] == 2
    assert data["summary"]["presentClean"] == 2


def test_classify_alt_does_not_flag_words_that_merely_start_with_image_or_picture():
    # "Picture"/"Image"/"Photo" used as ordinary descriptive words (not the
    # filler phrase "picture of") must not be flagged as generic.
    assert _classify_alt("Picture perfect day at the park", None)["issues"] == []
    assert _classify_alt("Photo finish at the championship race", None)["issues"] == []


def test_classify_alt_flags_generic_of_phrase():
    result = _classify_alt("image of a sunset over the mountains", None)
    assert any("generic phrase" in issue for issue in result["issues"])


@pytest.mark.asyncio
async def test_scan_page_alt_text_respects_limit(monkeypatch, scan_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _SAMPLE_HTML

    monkeypatch.setattr(scan_alt_text, "fetch_text_safely", fake_fetch_text_safely)

    tool = await scan_tool.get_tool("scan_page_alt_text")
    result = await tool.run({"params": {"url": "https://example.gov/page", "limit": 2}})
    data = result.structured_content

    assert data["totalImagesOnPage"] == 6
    assert data["imagesReturned"] == 2


@pytest.mark.asyncio
async def test_scan_page_alt_text_reports_blocked_url(monkeypatch, scan_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise BlockedUrlError("URL resolves to a disallowed address range.")

    monkeypatch.setattr(scan_alt_text, "fetch_text_safely", fake_fetch_text_safely)

    tool = await scan_tool.get_tool("scan_page_alt_text")
    result = await tool.run({"params": {"url": "http://169.254.169.254/", "limit": 20}})

    assert "error" in result.structured_content
    assert "hint" in result.structured_content


@pytest.mark.asyncio
async def test_scan_page_alt_text_reports_upstream_error(monkeypatch, scan_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise UpstreamServiceError("Upstream returned status 500.")

    monkeypatch.setattr(scan_alt_text, "fetch_text_safely", fake_fetch_text_safely)

    tool = await scan_tool.get_tool("scan_page_alt_text")
    result = await tool.run(
        {"params": {"url": "https://example.gov/down", "limit": 20}}
    )

    assert result.structured_content["error"] == "Upstream returned status 500."


@pytest.mark.asyncio
async def test_fetch_image_returns_image_content(monkeypatch, fetch_tool):
    async def fake_fetch_url_safely(url: str, max_bytes: int = 0, timeout: float = 0):
        return b"\x89PNG\r\n\x1a\n fake png bytes", "image/png"

    monkeypatch.setattr(fetch_image_module, "fetch_url_safely", fake_fetch_url_safely)

    tool = await fetch_tool.get_tool("fetch_image")
    result = await tool.run({"params": {"url": "https://example.gov/logo.png"}})

    assert len(result.content) == 1
    assert result.content[0].type == "image"
    assert result.content[0].mime_type == "image/png"


@pytest.mark.asyncio
async def test_fetch_image_rejects_non_image_content_type(monkeypatch, fetch_tool):
    async def fake_fetch_url_safely(url: str, max_bytes: int = 0, timeout: float = 0):
        return b"<html></html>", "text/html"

    monkeypatch.setattr(fetch_image_module, "fetch_url_safely", fake_fetch_url_safely)

    tool = await fetch_tool.get_tool("fetch_image")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})

    assert "error" in result.structured_content
    assert (
        "did not return a recognized image type" in result.structured_content["error"]
    )


@pytest.mark.asyncio
async def test_fetch_image_rejects_svg_despite_being_a_real_image_type(
    monkeypatch, fetch_tool
):
    # SVG is a real image format, but vision-capable models (e.g. Claude)
    # don't accept it — reporting success here would be misleading.
    async def fake_fetch_url_safely(url: str, max_bytes: int = 0, timeout: float = 0):
        return b"<svg></svg>", "image/svg+xml"

    monkeypatch.setattr(fetch_image_module, "fetch_url_safely", fake_fetch_url_safely)

    tool = await fetch_tool.get_tool("fetch_image")
    result = await tool.run({"params": {"url": "https://example.gov/icon.svg"}})

    assert "error" in result.structured_content


@pytest.mark.asyncio
async def test_fetch_image_reports_blocked_url(monkeypatch, fetch_tool):
    async def fake_fetch_url_safely(url: str, max_bytes: int = 0, timeout: float = 0):
        raise BlockedUrlError("URL resolves to a disallowed address range.")

    monkeypatch.setattr(fetch_image_module, "fetch_url_safely", fake_fetch_url_safely)

    tool = await fetch_tool.get_tool("fetch_image")
    result = await tool.run({"params": {"url": "http://127.0.0.1/image.png"}})

    assert "error" in result.structured_content
    assert "hint" in result.structured_content
