"""Shared helpers: SSRF-hardened HTTP client for arbitrary URLs, pagination.

Import these from your tool modules instead of re-implementing them. Keeping
I/O and formatting here keeps each tool file focused on its own logic.

Unlike a typical federal-API wrapper (one fixed, operator-controlled origin —
see the `example_tool.py` pattern in other hackathon-template servers), this
server's whole job is fetching pages and images at URLs *supplied by the
caller*. That's a materially different threat model: the destination host
isn't known in advance, so the usual "reject any path that tries to escape a
fixed origin" defense doesn't apply — instead every resolved IP address has
to be checked against private/internal ranges before we connect, per
SECURITY.md's guidance for exactly this case.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

# Public, user-facing pages can be slow — give them more room than a typical
# internal API call, but still bounded.
DEFAULT_TIMEOUT = 20.0
MAX_RESPONSE_BYTES = 10_000_000
MAX_REDIRECTS = 5

_CGNAT_RANGE = ipaddress.ip_network("100.64.0.0/10")


class UpstreamServiceError(RuntimeError):
    """Sanitized external-service failure safe to return to an MCP client."""


class BlockedUrlError(ValueError):
    """The URL (or a redirect target) resolves to a disallowed destination."""


def _is_blocked_ip(ip_str: str) -> bool:
    """Reject loopback/private/link-local/multicast/reserved/CGNAT addresses.

    Covers cloud metadata endpoints too: 169.254.169.254 falls under
    `is_link_local` (169.254.0.0/16).
    """
    addr = ipaddress.ip_address(ip_str)
    if addr.is_loopback or addr.is_private or addr.is_link_local:
        return True
    if addr.is_multicast or addr.is_reserved or addr.is_unspecified:
        return True
    # is_private etc. above already see through IPv4-mapped IPv6 (e.g.
    # ::ffff:127.0.0.1), but the CGNAT check below is IPv4Address-only, so
    # unwrap the mapped address first or an IPv4-mapped CGNAT literal
    # (::ffff:100.64.0.1) would slip through.
    v4 = getattr(addr, "ipv4_mapped", None) or (
        addr if isinstance(addr, ipaddress.IPv4Address) else None
    )
    if v4 is not None and v4 in _CGNAT_RANGE:
        return True
    return False


async def _assert_host_resolves_safely(hostname: str) -> None:
    """Resolve `hostname` and reject it if any address is in a blocked range.

    This is a pre-connect check, not a connect-time guarantee: the DNS
    answer could change between this check and httpx's own connection
    (DNS rebinding). A full fix needs a connect-time socket hook pinning
    the validated IP; out of scope for this pass — named here rather than
    silently assumed away.

    Raises:
        BlockedUrlError: if the hostname is unresolvable or resolves to any
            disallowed address.
    """
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise BlockedUrlError(f"Could not resolve host: {exc}") from None
    if not infos:
        raise BlockedUrlError("Host resolved to no addresses.")
    for info in infos:
        ip_str = info[4][0]
        if _is_blocked_ip(ip_str):
            raise BlockedUrlError("URL resolves to a disallowed address range.")


def _validate_url(url: str) -> str:
    """Reject anything that isn't a well-formed, resolvable-looking http(s) URL."""
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https"):
        raise BlockedUrlError("Only http:// and https:// URLs are allowed.")
    if not parsed.hostname:
        raise BlockedUrlError("URL has no host.")
    return url


async def fetch_url_safely(
    url: str,
    max_bytes: int = MAX_RESPONSE_BYTES,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[bytes, str]:
    """GET an arbitrary, caller-supplied URL with SSRF defenses applied.

    Validates scheme + resolves and checks every redirect hop's host before
    connecting (`follow_redirects` is off; redirects are followed manually
    so each hop gets the same validation as the original URL). Streams the
    body with a size cap. Errors are sanitized — never includes the
    resolved IP, response body, or headers.

    Returns:
        (content_bytes, content_type) — content_type is the response's
        Content-Type header (without parameters), or "" if absent.

    Raises:
        BlockedUrlError: if the URL or a redirect target is disallowed.
        UpstreamServiceError: sanitized message for external failures.
    """
    current_url = _validate_url(url)
    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=timeout,
        trust_env=False,
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            hostname = urlsplit(current_url).hostname
            assert hostname is not None  # guaranteed by _validate_url
            await _assert_host_resolves_safely(hostname)
            try:
                async with client.stream("GET", current_url) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise UpstreamServiceError(
                                "Upstream returned a redirect with no Location."
                            )
                        current_url = _validate_url(urljoin(current_url, location))
                        continue
                    response.raise_for_status()
                    content_type = (
                        response.headers.get("content-type", "").split(";")[0].strip()
                    )
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > max_bytes:
                            raise UpstreamServiceError(
                                "Upstream response exceeded the size limit."
                            )
                    return bytes(content), content_type
            except UpstreamServiceError:
                raise
            except httpx.HTTPStatusError as exc:
                raise UpstreamServiceError(
                    f"Upstream returned status {exc.response.status_code}."
                ) from None
            except httpx.RequestError:
                raise UpstreamServiceError("Upstream request failed.") from None
        raise UpstreamServiceError("Too many redirects.")


async def fetch_text_safely(url: str, max_bytes: int = MAX_RESPONSE_BYTES) -> str:
    """Like `fetch_url_safely`, decoded as text (best-effort UTF-8)."""
    content, _ = await fetch_url_safely(url, max_bytes=max_bytes)
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("utf-8", errors="replace")


def paginate(items: list[Any], limit: int, offset: int) -> dict[str, Any]:
    """Slice a list and return a standard pagination envelope.

    Returns a dict with `total`, `count`, `offset`, `items`, `has_more`, and
    `next_offset` — the shape recommended in the MCP best-practices guide.
    """
    total = len(items)
    window = items[offset : offset + limit]
    next_offset = offset + len(window)
    return {
        "total": total,
        "count": len(window),
        "offset": offset,
        "items": window,
        "has_more": next_offset < total,
        "next_offset": next_offset if next_offset < total else None,
    }
