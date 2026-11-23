"""Functional tests for check_media_captions.

Network calls are mocked (via fetch_text_safely) so these run
deterministically without depending on live external pages.
"""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from alt_text_mcp.tools import check_media_captions as check_media_captions_module
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError

_VIDEO_WITH_CAPTIONS_HTML = """
<html><body>
  <video src="clip.mp4"><track kind="captions" src="captions.vtt"></video>
</body></html>
"""

_VIDEO_WITHOUT_CAPTIONS_HTML = """
<html><body>
  <video><source src="clip2.mp4"></video>
</body></html>
"""

_AUDIO_HTML = """
<html><body>
  <audio src="podcast.mp3"></audio>
</body></html>
"""

_MIXED_HTML = """
<html><body>
  <video src="clip.mp4"><track kind="captions" src="captions.vtt"></video>
  <video><source src="clip2.mp4"></video>
  <audio src="podcast.mp3"></audio>
</body></html>
"""


@pytest.fixture
def media_tool():
    mcp = FastMCP(name="test")
    check_media_captions_module.register(mcp)
    return mcp


@pytest.mark.asyncio
async def test_video_with_caption_track_has_captions(monkeypatch, media_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _VIDEO_WITH_CAPTIONS_HTML

    monkeypatch.setattr(
        check_media_captions_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await media_tool.get_tool("check_media_captions")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["totalMediaOnPage"] == 1
    item = data["media"][0]
    assert item["type"] == "video"
    assert item["src"] == "clip.mp4"
    assert item["status"] == "has-captions"
    assert item["issues"] == []


@pytest.mark.asyncio
async def test_video_without_track_missing_captions_src_from_source(
    monkeypatch, media_tool
):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _VIDEO_WITHOUT_CAPTIONS_HTML

    monkeypatch.setattr(
        check_media_captions_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await media_tool.get_tool("check_media_captions")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    item = data["media"][0]
    assert item["type"] == "video"
    assert item["src"] == "clip2.mp4"
    assert item["status"] == "missing-captions"
    assert item["issues"]


@pytest.mark.asyncio
async def test_audio_always_needs_manual_check(monkeypatch, media_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _AUDIO_HTML

    monkeypatch.setattr(
        check_media_captions_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await media_tool.get_tool("check_media_captions")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    item = data["media"][0]
    assert item["type"] == "audio"
    assert item["src"] == "podcast.mp3"
    assert item["status"] == "needs-manual-check"
    assert any("transcript" in i for i in item["issues"])


@pytest.mark.asyncio
async def test_summary_counts_across_mixed_page(monkeypatch, media_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _MIXED_HTML

    monkeypatch.setattr(
        check_media_captions_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await media_tool.get_tool("check_media_captions")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["totalMediaOnPage"] == 3
    assert data["mediaReturned"] == 3
    assert data["summary"]["missingCaptions"] == 1
    assert data["summary"]["hasCaptions"] == 1
    assert data["summary"]["needsManualCheck"] == 1


@pytest.mark.asyncio
async def test_check_media_captions_reports_upstream_error(monkeypatch, media_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise UpstreamServiceError("Upstream returned status 500.")

    monkeypatch.setattr(
        check_media_captions_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await media_tool.get_tool("check_media_captions")
    result = await tool.run({"params": {"url": "https://example.gov/down"}})

    assert result.structured_content["error"] == "Upstream returned status 500."


@pytest.mark.asyncio
async def test_check_media_captions_reports_blocked_url(monkeypatch, media_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise BlockedUrlError("URL resolves to a disallowed address range.")

    monkeypatch.setattr(
        check_media_captions_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await media_tool.get_tool("check_media_captions")
    result = await tool.run({"params": {"url": "http://127.0.0.1/"}})

    assert "error" in result.structured_content
