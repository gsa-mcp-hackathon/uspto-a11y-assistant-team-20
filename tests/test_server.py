"""Smoke tests for the Alt-Text Accessibility MCP server.

These verify the server imports and every submodule registers without error.
"""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from alt_text_mcp.app import mcp
from alt_text_mcp.config import settings


def test_server_is_importable():
    assert mcp is not None


def test_server_has_name():
    assert mcp.name == "Alt-Text Accessibility MCP Server"


def test_default_transport_is_stdio():
    """Guard against accidentally shipping with a non-stdio default."""
    assert settings.mcp_transport == "stdio"


def test_tools_register_without_error():
    from alt_text_mcp.tools import register_tools

    register_tools(FastMCP("test"))  # must not raise


def test_prompts_register_without_error():
    from alt_text_mcp.prompts import register_prompts

    register_prompts(FastMCP("test"))  # must not raise


def test_resources_register_without_error():
    from alt_text_mcp.resources import register_resources

    register_resources(FastMCP("test"))  # must not raise


def test_routes_register_without_error():
    from alt_text_mcp.routes import register_routes

    register_routes(FastMCP("test"))  # must not raise


@pytest.mark.asyncio
async def test_real_tools_are_discoverable():
    """Both real tools should be registered and discoverable via the MCP API."""
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "scan_page_alt_text" in tool_names
    assert "fetch_image" in tool_names
