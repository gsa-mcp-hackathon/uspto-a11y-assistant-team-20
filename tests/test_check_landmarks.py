"""Functional tests for check_landmarks.

Network calls are mocked (via fetch_text_safely) so these run
deterministically without depending on live external pages.
"""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from alt_text_mcp.tools import check_landmarks as check_landmarks_module
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError

_CLEAN_HTML = """
<html><body>
  <a href="#main">Skip to main content</a>
  <header>Agency Header</header>
  <nav>Primary nav</nav>
  <main id="main">Main content</main>
  <footer>Agency Footer</footer>
</body></html>
"""

_NO_MAIN_HTML = """
<html><body>
  <header>Agency Header</header>
  <nav>Primary nav</nav>
  <footer>Agency Footer</footer>
</body></html>
"""

_MULTI_MAIN_HTML = """
<html><body>
  <main>First main</main>
  <main>Second main</main>
</body></html>
"""

_ROLE_NAV_HTML = """
<html><body>
  <div role="navigation">Primary nav</div>
  <main>Main content</main>
</body></html>
"""


@pytest.fixture
def landmarks_tool():
    mcp = FastMCP(name="test")
    check_landmarks_module.register(mcp)
    return mcp


@pytest.mark.asyncio
async def test_check_landmarks_clean_page_has_no_issues(monkeypatch, landmarks_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _CLEAN_HTML

    monkeypatch.setattr(
        check_landmarks_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await landmarks_tool.get_tool("check_landmarks")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["landmarks"] == {"main": 1, "nav": 1, "header": 1, "footer": 1}
    assert data["hasSkipLink"] is True
    assert data["skipLinkText"] == "Skip to main content"
    assert data["issues"] == []


@pytest.mark.asyncio
async def test_check_landmarks_flags_no_main(monkeypatch, landmarks_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _NO_MAIN_HTML

    monkeypatch.setattr(
        check_landmarks_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await landmarks_tool.get_tool("check_landmarks")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["landmarks"]["main"] == 0
    assert any(i.startswith("no-main") for i in data["issues"])


@pytest.mark.asyncio
async def test_check_landmarks_flags_multiple_main(monkeypatch, landmarks_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _MULTI_MAIN_HTML

    monkeypatch.setattr(
        check_landmarks_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await landmarks_tool.get_tool("check_landmarks")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["landmarks"]["main"] == 2
    assert any("multiple-main" in i and "2" in i for i in data["issues"])


@pytest.mark.asyncio
async def test_check_landmarks_counts_role_navigation(monkeypatch, landmarks_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        return _ROLE_NAV_HTML

    monkeypatch.setattr(
        check_landmarks_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await landmarks_tool.get_tool("check_landmarks")
    result = await tool.run({"params": {"url": "https://example.gov/page"}})
    data = result.structured_content

    assert data["landmarks"]["nav"] == 1


@pytest.mark.asyncio
async def test_check_landmarks_reports_blocked_url(monkeypatch, landmarks_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise BlockedUrlError("URL resolves to a disallowed address range.")

    monkeypatch.setattr(
        check_landmarks_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await landmarks_tool.get_tool("check_landmarks")
    result = await tool.run({"params": {"url": "http://127.0.0.1/"}})

    assert "error" in result.structured_content


@pytest.mark.asyncio
async def test_check_landmarks_reports_upstream_error(monkeypatch, landmarks_tool):
    async def fake_fetch_text_safely(url: str, max_bytes: int = 0):
        raise UpstreamServiceError("Upstream returned status 500.")

    monkeypatch.setattr(
        check_landmarks_module, "fetch_text_safely", fake_fetch_text_safely
    )

    tool = await landmarks_tool.get_tool("check_landmarks")
    result = await tool.run({"params": {"url": "https://example.gov/down"}})

    assert result.structured_content["error"] == "Upstream returned status 500."
