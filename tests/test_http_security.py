"""Regression tests for the arbitrary-URL-fetching SSRF defenses in utils.py.

Unlike a fixed-origin API wrapper, this server's tools fetch URLs supplied by
the caller, so the defense is resolve-and-check-every-IP rather than
reject-path-escape. These tests cover: the IP blocklist itself, DNS
resolution enforcement, redirect-hop re-validation, size capping, and error
sanitization.
"""

from __future__ import annotations

import socket

import httpx
import pytest

from alt_text_mcp import utils


async def _ok_resolve(hostname: str) -> None:
    return None


class _FakeStream:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    async def __aenter__(self) -> httpx.Response:
        return self.response

    async def __aexit__(self, *args: object) -> None:
        return None


class _FakeClient:
    """Minimal httpx.AsyncClient stand-in that returns queued responses."""

    def __init__(self, responses: list[httpx.Response], **kwargs: object) -> None:
        self._responses = list(responses)

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def stream(self, method: str, url: str, **kwargs: object) -> _FakeStream:
        return _FakeStream(self._responses.pop(0))


def _client_factory(responses: list[httpx.Response]):
    def factory(**kwargs: object) -> _FakeClient:
        return _FakeClient(responses, **kwargs)

    return factory


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",  # cloud metadata endpoint
        "224.0.0.1",  # multicast
        "0.0.0.0",  # unspecified
        "100.64.0.1",  # CGNAT
        "::1",  # loopback v6
        "fe80::1",  # link-local v6
        "fc00::1",  # unique-local v6
        "::ffff:100.64.0.1",  # CGNAT, IPv4-mapped IPv6 form
        "::ffff:127.0.0.1",  # loopback, IPv4-mapped IPv6 form
    ],
)
def test_is_blocked_ip_rejects_internal_ranges(ip: str) -> None:
    assert utils._is_blocked_ip(ip) is True


@pytest.mark.parametrize(
    "ip",
    [
        "8.8.8.8",
        "93.184.216.34",
        "2606:4700:4700::1111",
    ],
)
def test_is_blocked_ip_allows_public_addresses(ip: str) -> None:
    assert utils._is_blocked_ip(ip) is False


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "file:///etc/passwd",
        "http://",
        "not-a-url",
    ],
)
def test_validate_url_rejects_bad_schemes_and_missing_host(url: str) -> None:
    with pytest.raises(utils.BlockedUrlError):
        utils._validate_url(url)


def test_validate_url_accepts_well_formed_http_url() -> None:
    url = "https://www.agency.gov/page"
    assert utils._validate_url(url) == url


class _FakeLoop:
    def __init__(self, infos: list[tuple] | Exception) -> None:
        self._infos = infos

    async def getaddrinfo(self, hostname: str, port: object) -> list[tuple]:
        if isinstance(self._infos, Exception):
            raise self._infos
        return self._infos


@pytest.mark.asyncio
async def test_assert_host_resolves_safely_blocks_private_ip(monkeypatch) -> None:
    infos = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.5", 0))]
    monkeypatch.setattr(utils.asyncio, "get_running_loop", lambda: _FakeLoop(infos))

    with pytest.raises(utils.BlockedUrlError):
        await utils._assert_host_resolves_safely("internal.example")


@pytest.mark.asyncio
async def test_assert_host_resolves_safely_allows_public_ip(monkeypatch) -> None:
    infos = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(utils.asyncio, "get_running_loop", lambda: _FakeLoop(infos))

    await utils._assert_host_resolves_safely("example.com")  # must not raise


@pytest.mark.asyncio
async def test_assert_host_resolves_safely_rejects_unresolvable_host(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        utils.asyncio,
        "get_running_loop",
        lambda: _FakeLoop(socket.gaierror("Name or service not known")),
    )

    with pytest.raises(utils.BlockedUrlError, match="Could not resolve host"):
        await utils._assert_host_resolves_safely("nonexistent.invalid")


@pytest.mark.asyncio
async def test_fetch_url_safely_follows_and_revalidates_redirects(monkeypatch) -> None:
    hosts_checked: list[str] = []

    async def tracking_resolve(hostname: str) -> None:
        hosts_checked.append(hostname)

    monkeypatch.setattr(utils, "_assert_host_resolves_safely", tracking_resolve)

    redirect_response = httpx.Response(
        302,
        headers={"location": "https://example.com/final"},
        request=httpx.Request("GET", "https://example.com/start"),
    )
    final_response = httpx.Response(
        200,
        content=b"hello world",
        headers={"content-type": "text/plain; charset=utf-8"},
        request=httpx.Request("GET", "https://example.com/final"),
    )
    monkeypatch.setattr(
        utils.httpx, "AsyncClient", _client_factory([redirect_response, final_response])
    )

    content, content_type = await utils.fetch_url_safely("https://example.com/start")

    assert content == b"hello world"
    assert content_type == "text/plain"
    assert hosts_checked == ["example.com", "example.com"]


@pytest.mark.asyncio
async def test_fetch_url_safely_rejects_redirect_to_blocked_host(monkeypatch) -> None:
    async def resolve(hostname: str) -> None:
        if hostname == "internal.example":
            raise utils.BlockedUrlError("URL resolves to a disallowed address range.")

    monkeypatch.setattr(utils, "_assert_host_resolves_safely", resolve)

    redirect_response = httpx.Response(
        302,
        headers={"location": "http://internal.example/admin"},
        request=httpx.Request("GET", "https://example.com/start"),
    )
    monkeypatch.setattr(
        utils.httpx, "AsyncClient", _client_factory([redirect_response])
    )

    with pytest.raises(utils.BlockedUrlError):
        await utils.fetch_url_safely("https://example.com/start")


@pytest.mark.asyncio
async def test_fetch_url_safely_enforces_size_cap(monkeypatch) -> None:
    monkeypatch.setattr(utils, "_assert_host_resolves_safely", _ok_resolve)

    big_response = httpx.Response(
        200,
        content=b"x" * 1000,
        headers={"content-type": "application/octet-stream"},
        request=httpx.Request("GET", "https://example.com/big"),
    )
    monkeypatch.setattr(utils.httpx, "AsyncClient", _client_factory([big_response]))

    with pytest.raises(utils.UpstreamServiceError, match="size limit"):
        await utils.fetch_url_safely("https://example.com/big", max_bytes=10)


@pytest.mark.asyncio
async def test_fetch_url_safely_sanitizes_upstream_error(monkeypatch) -> None:
    monkeypatch.setattr(utils, "_assert_host_resolves_safely", _ok_resolve)

    sensitive = "secret-token-abc123"
    error_response = httpx.Response(
        500,
        text=sensitive,
        request=httpx.Request("GET", "https://example.com/fail"),
    )
    monkeypatch.setattr(utils.httpx, "AsyncClient", _client_factory([error_response]))

    with pytest.raises(utils.UpstreamServiceError) as captured:
        await utils.fetch_url_safely("https://example.com/fail")

    message = str(captured.value)
    assert message == "Upstream returned status 500."
    assert sensitive not in message


@pytest.mark.asyncio
async def test_fetch_text_safely_decodes_with_replacement(monkeypatch) -> None:
    async def fake_fetch_url_safely(
        url: str, max_bytes: int = utils.MAX_RESPONSE_BYTES
    ):
        return b"\xff\xfe invalid utf8", "text/html"

    monkeypatch.setattr(utils, "fetch_url_safely", fake_fetch_url_safely)

    text = await utils.fetch_text_safely("https://example.com")
    assert "invalid utf8" in text


def test_paginate_returns_standard_envelope() -> None:
    result = utils.paginate(list(range(25)), limit=10, offset=20)
    assert result == {
        "total": 25,
        "count": 5,
        "offset": 20,
        "items": [20, 21, 22, 23, 24],
        "has_more": False,
        "next_offset": None,
    }
