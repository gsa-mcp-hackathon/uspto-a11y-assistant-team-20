"""Tests for check_color_contrast.

Network calls are mocked (via fetch_text_safely) so these run
deterministically without depending on live external pages.
"""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from alt_text_mcp.tools import check_color_contrast as check_color_contrast_module
from alt_text_mcp.tools.check_color_contrast import _contrast_ratio, _parse_color
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError

_LOW_CONTRAST_HTML = """
<html><body>
  <p style="color: #777777; background-color: #808080;">text</p>
</body></html>
"""

_GOOD_CONTRAST_HTML = """
<html><body>
  <p style="color: black; background-color: white;">text</p>
</body></html>
"""

_RGB_LOW_CONTRAST_HTML = """
<html><body>
  <p style="color: rgb(119,119,119); background-color: rgb(128,128,128);">text</p>
</body></html>
"""

_COLOR_ONLY_HTML = """
<html><body>
  <p style="color: red;">text</p>
</body></html>
"""

_UNSUPPORTED_FORMAT_HTML = """
<html><body>
  <p style="color: hsl(0, 0%, 50%); background-color: white;">text</p>
</body></html>
"""


@pytest.fixture
def contrast_tool():
    mcp = FastMCP(name="test")
    check_color_contrast_module.register(mcp)
    return mcp


# --- check_color_contrast tool -------------------------------------------


@pytest.mark.asyncio
async def test_check_color_contrast_flags_low_contrast_hex(monkeypatch, contrast_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _LOW_CONTRAST_HTML

    monkeypatch.setattr(
        check_color_contrast_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await contrast_tool.get_tool("check_color_contrast")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["elementsChecked"] == 1
    assert data["issuesReturned"] == 1
    assert data["summary"]["lowContrastCount"] == 1
    issue = data["issues"][0]
    assert issue["foreground"] == "#777777"
    assert issue["background"] == "#808080"
    assert issue["ratio"] < 4.5


@pytest.mark.asyncio
async def test_check_color_contrast_passes_good_contrast(monkeypatch, contrast_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _GOOD_CONTRAST_HTML

    monkeypatch.setattr(
        check_color_contrast_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await contrast_tool.get_tool("check_color_contrast")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["elementsChecked"] == 1
    assert data["issuesReturned"] == 0
    assert data["issues"] == []
    assert data["summary"]["lowContrastCount"] == 0


@pytest.mark.asyncio
async def test_check_color_contrast_parses_rgb_syntax(monkeypatch, contrast_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _RGB_LOW_CONTRAST_HTML

    monkeypatch.setattr(
        check_color_contrast_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await contrast_tool.get_tool("check_color_contrast")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["elementsChecked"] == 1
    assert data["issuesReturned"] == 1
    assert data["summary"]["lowContrastCount"] == 1


@pytest.mark.asyncio
async def test_check_color_contrast_skips_missing_background(
    monkeypatch, contrast_tool
):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _COLOR_ONLY_HTML

    monkeypatch.setattr(
        check_color_contrast_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await contrast_tool.get_tool("check_color_contrast")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["elementsChecked"] == 0
    assert data["issuesReturned"] == 0
    assert data["summary"]["lowContrastCount"] == 0


@pytest.mark.asyncio
async def test_check_color_contrast_skips_unsupported_format_silently(
    monkeypatch, contrast_tool
):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _UNSUPPORTED_FORMAT_HTML

    monkeypatch.setattr(
        check_color_contrast_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await contrast_tool.get_tool("check_color_contrast")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["elementsChecked"] == 0
    assert data["issuesReturned"] == 0
    assert data["issues"] == []


@pytest.mark.asyncio
async def test_check_color_contrast_reports_upstream_error(monkeypatch, contrast_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise UpstreamServiceError("Upstream returned status 500.")

    monkeypatch.setattr(
        check_color_contrast_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await contrast_tool.get_tool("check_color_contrast")
    result = await tool.run({"params": {"url": "https://example.gov/down"}})

    assert result.structured_content["error"] == "Upstream returned status 500."


@pytest.mark.asyncio
async def test_check_color_contrast_reports_blocked_url(monkeypatch, contrast_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise BlockedUrlError("URL resolves to a disallowed address range.")

    monkeypatch.setattr(
        check_color_contrast_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await contrast_tool.get_tool("check_color_contrast")
    result = await tool.run({"params": {"url": "http://127.0.0.1/"}})

    assert "error" in result.structured_content


# --- _parse_color unit tests ----------------------------------------------


def test_parse_color_hex3():
    assert _parse_color("#fff") == (255, 255, 255)
    assert _parse_color("#000") == (0, 0, 0)


def test_parse_color_hex6():
    assert _parse_color("#ff0000") == (255, 0, 0)


def test_parse_color_rgb():
    assert _parse_color("rgb(10, 20, 30)") == (10, 20, 30)
    assert _parse_color("rgba(10, 20, 30, 0.5)") == (10, 20, 30)


def test_parse_color_named():
    assert _parse_color("white") == (255, 255, 255)
    assert _parse_color("Black") == (0, 0, 0)


def test_parse_color_invalid_returns_none():
    assert _parse_color("hsl(0, 0%, 50%)") is None
    assert _parse_color("not-a-color") is None


# --- _contrast_ratio unit tests --------------------------------------------


def test_contrast_ratio_black_white_is_21():
    ratio = _contrast_ratio((0, 0, 0), (255, 255, 255))
    assert round(ratio, 1) == 21.0


def test_contrast_ratio_identical_colors_is_1():
    ratio = _contrast_ratio((128, 128, 128), (128, 128, 128))
    assert round(ratio, 2) == 1.0
