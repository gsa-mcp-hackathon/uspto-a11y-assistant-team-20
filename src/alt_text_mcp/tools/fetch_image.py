"""fetch_image — retrieve one image's bytes for visual inspection."""

from __future__ import annotations

from fastmcp import FastMCP
from fastmcp.utilities.types import Image

from alt_text_mcp.models import FetchImageInput
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError, fetch_url_safely

# Limited to formats vision-capable models can actually view. SVG/BMP/TIFF
# are valid image types but aren't accepted by Claude's vision API, so
# returning them here would report a successful fetch the model still can't
# see — accepting fewer formats honestly beats claiming support we don't have.
_FORMAT_FROM_CONTENT_TYPE = {
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
}


def register(mcp: FastMCP) -> None:
    """Register the fetch_image tool with the MCP server."""

    @mcp.tool(
        name="fetch_image",
        annotations={
            "title": "Fetch an Image for Visual Inspection",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def fetch_image(params: FetchImageInput) -> Image | dict:
        """Fetch one image's bytes so you can see it and judge its content.

        Use this on an image scan_page_alt_text flagged as missing, empty,
        or low-quality alt text, before suggesting a replacement — a
        suggestion grounded in what the image actually shows is far more
        useful than one guessed from surrounding page text alone.

        Args:
            params: The image URL to fetch.

        Returns:
            The image, or an error dict with a hint if it can't be fetched
            or isn't recognized as an image.
        """
        try:
            content, content_type = await fetch_url_safely(params.url)
        except BlockedUrlError as exc:
            return {
                "error": str(exc),
                "hint": "Only public http(s) URLs outside private ranges are allowed.",
            }
        except UpstreamServiceError as exc:
            return {
                "error": str(exc),
                "hint": "Check the URL is reachable and points at an image file.",
            }

        image_format = _FORMAT_FROM_CONTENT_TYPE.get(content_type.lower())
        if image_format is None:
            got = content_type or "unknown"
            return {
                "error": f"URL did not return a recognized image type (got '{got}').",
                "hint": "Pass the direct image URL (the <img> src), not the page URL.",
            }

        return Image(data=content, format=image_format)
