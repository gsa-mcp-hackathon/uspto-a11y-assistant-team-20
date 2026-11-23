"""check_media_captions — audit a web page's video/audio elements for caption tracks."""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup
from fastmcp import FastMCP

from alt_text_mcp.models import CheckMediaCaptionsInput
from alt_text_mcp.utils import BlockedUrlError, UpstreamServiceError, fetch_text_safely

_CAPTION_KINDS = {"captions", "subtitles"}


def register(mcp: FastMCP) -> None:
    """Register the check_media_captions tool with the MCP server."""

    @mcp.tool(
        name="check_media_captions",
        annotations={
            "title": "Check a Page's Video/Audio Caption Tracks",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def check_media_captions(params: CheckMediaCaptionsInput) -> dict[str, Any]:
        """Scan one page's <video> and <audio> elements for caption tracks.

        Fetches the page as static HTML — no JavaScript execution. Deaf and
        hard-of-hearing users rely on captions (a <track kind="captions"> or
        <track kind="subtitles"> child) to follow video dialogue and sound
        effects. Audio-only content needs a text transcript nearby, but
        whether one exists elsewhere on the page can't be verified from
        markup alone, so audio elements are always flagged for a manual
        check rather than silently assumed accessible.

        For each <video>, checks for a child <track> whose kind is
        "captions" or "subtitles"; flags "missing-captions" if none is
        found. For each <audio>, always flags "needs-manual-check" since a
        transcript's existence can't be confirmed from the HTML.

        Args:
            params: The page URL to scan and a max-elements limit.

        Returns:
            {"url", "totalMediaOnPage", "mediaReturned", "media": [...],
            "summary": {...}, "disclaimer"}. Or an error dict with a hint.
        """
        try:
            html = await fetch_text_safely(params.url)
        except BlockedUrlError as exc:
            return {
                "error": str(exc),
                "hint": "Only public http(s) URLs outside private ranges are allowed.",
            }
        except UpstreamServiceError as exc:
            return {
                "error": str(exc),
                "hint": "Check the URL is reachable and returns HTML.",
            }

        soup = BeautifulSoup(html, "html.parser")
        all_media = soup.find_all(["video", "audio"])

        media = []
        for element in all_media[: params.limit]:
            media_type = element.name
            src = element.get("src")
            if src is None:
                source = element.find("source")
                src = source.get("src") if source else None

            tracks = element.find_all("track")
            caption_tracks = [
                t for t in tracks if (t.get("kind") or "").lower() in _CAPTION_KINDS
            ]

            if media_type == "video":
                if caption_tracks:
                    status = "has-captions"
                    issues = []
                else:
                    status = "missing-captions"
                    issues = [
                        'no <track kind="captions"> or <track kind="subtitles"> child'
                    ]
            else:
                status = "needs-manual-check"
                issues = [
                    "audio content needs an accessible transcript — not "
                    "something this scan can verify from markup alone"
                ]

            media.append(
                {
                    "type": media_type,
                    "src": src,
                    "status": status,
                    "issues": issues,
                }
            )

        summary = {
            "missingCaptions": sum(
                1 for m in media if m["status"] == "missing-captions"
            ),
            "hasCaptions": sum(1 for m in media if m["status"] == "has-captions"),
            "needsManualCheck": sum(
                1 for m in media if m["status"] == "needs-manual-check"
            ),
        }

        return {
            "url": params.url,
            "totalMediaOnPage": len(all_media),
            "mediaReturned": len(media),
            "media": media,
            "summary": summary,
            "disclaimer": (
                "Heuristic checks only, based on static HTML (no JavaScript "
                "execution) — not a substitute for a manual accessibility "
                "audit. Cannot verify whether an audio transcript exists "
                "elsewhere on the page, or whether a caption track's "
                "content is accurate. Media injected by client-side JS is "
                "not seen."
            ),
        }
