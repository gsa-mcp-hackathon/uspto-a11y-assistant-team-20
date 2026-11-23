"""Pydantic models and enums for tool parameters and responses.

Typed parameters give MCP clients a precise schema, which helps the LLM call
your tools correctly. Prefer enums for closed sets of values and Pydantic
models for structured inputs/outputs.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, Field


class ResponseFormat(str, Enum):
    """How a tool should shape its return value.

    - JSON     → machine-readable dict/list (best for chaining tool calls)
    - MARKDOWN → human-readable text (best for direct display)
    """

    JSON = "json"
    MARKDOWN = "markdown"


class PaginationParams(BaseModel):
    """Reusable pagination inputs for list-style tools.

    Federal APIs almost always paginate. Expose these to the caller (or handle
    paging internally) and return `has_more` / `next_offset` in your response.
    """

    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of items to return (1–100).",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Number of items to skip from the start of the result set.",
    )


def _validate_http_url(value: str) -> str:
    """Shape check only — a schema-level fail-fast, not the security boundary.

    The real SSRF defense (DNS resolution + blocked-range check on every
    redirect hop) lives in `utils.fetch_url_safely`, which runs regardless
    of this check; this just gives the LLM a clear, immediate error for an
    obviously-malformed URL instead of a sanitized upstream failure later.
    """
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("url must start with http:// or https://")
    if not parsed.hostname:
        raise ValueError("url must include a host, e.g. https://www.agency.gov/page")
    return value


# Shared across every tool's `url` field below: same shape check, reused via
# Annotated instead of a `@field_validator("url")` copy-pasted onto each
# model. Each field still sets its own Field(description=...).
HttpUrlStr = Annotated[str, AfterValidator(_validate_http_url)]


class ScanPageInput(BaseModel):
    """Input for scanning one page's images for alt-text issues."""

    url: HttpUrlStr = Field(
        ...,
        description="The page URL to scan, e.g. 'https://www.agency.gov/page'.",
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of images to return (1–100).",
    )


class FetchImageInput(BaseModel):
    """Input for fetching one image's bytes."""

    url: HttpUrlStr = Field(..., description="The image URL to fetch.")


class CheckLinkTextInput(BaseModel):
    """Input for checking a page's links for non-descriptive text."""

    url: HttpUrlStr = Field(
        ...,
        description="The page URL to scan, e.g. 'https://www.agency.gov/page'.",
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of links to return (1–200).",
    )


class CheckHeadingStructureInput(BaseModel):
    """Input for checking a page's heading (h1–h6) structure."""

    url: HttpUrlStr = Field(
        ...,
        description="The page URL to scan, e.g. 'https://www.agency.gov/page'.",
    )


class CheckFormLabelsInput(BaseModel):
    """Input for checking a page's form fields for accessible labels."""

    url: HttpUrlStr = Field(
        ...,
        description="The page URL to scan, e.g. 'https://www.agency.gov/page'.",
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of form fields to return (1–200).",
    )


class CheckDuplicateIdsInput(BaseModel):
    """Input for checking a page for duplicate id attributes."""

    url: HttpUrlStr = Field(
        ...,
        description="The page URL to scan, e.g. 'https://www.agency.gov/page'.",
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of duplicate id groups to return (1–200).",
    )


class CheckLandmarksInput(BaseModel):
    """Input for checking a page's ARIA landmarks and skip-navigation link."""

    url: HttpUrlStr = Field(
        ...,
        description="The page URL to scan, e.g. 'https://www.agency.gov/page'.",
    )


class CheckTableHeadersInput(BaseModel):
    """Input for checking a page's data tables for header cells."""

    url: HttpUrlStr = Field(
        ...,
        description="The page URL to scan, e.g. 'https://www.agency.gov/page'.",
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of tables to return (1–200).",
    )


class CheckLangAttributeInput(BaseModel):
    """Input for checking a page's root lang attribute."""

    url: HttpUrlStr = Field(
        ...,
        description="The page URL to scan, e.g. 'https://www.agency.gov/page'.",
    )


class CheckPageTitleInput(BaseModel):
    """Input for checking a page's <title> element."""

    url: HttpUrlStr = Field(
        ...,
        description="The page URL to scan, e.g. 'https://www.agency.gov/page'.",
    )


class CheckIframeTitlesInput(BaseModel):
    """Input for checking a page's iframes for a title attribute."""

    url: HttpUrlStr = Field(
        ...,
        description="The page URL to scan, e.g. 'https://www.agency.gov/page'.",
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of iframes to return (1–200).",
    )


class CheckMediaCaptionsInput(BaseModel):
    """Input for checking a page's video/audio elements for caption tracks."""

    url: HttpUrlStr = Field(
        ...,
        description="The page URL to scan, e.g. 'https://www.agency.gov/page'.",
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of media elements to return (1–200).",
    )


class CheckAriaConflictsInput(BaseModel):
    """Input for checking a page for conflicting or invalid ARIA usage."""

    url: HttpUrlStr = Field(
        ...,
        description="The page URL to scan, e.g. 'https://www.agency.gov/page'.",
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=300,
        description="Maximum number of findings to return (1–300).",
    )


class CheckColorContrastInput(BaseModel):
    """Input for checking a page's inline-styled text for low color contrast."""

    url: HttpUrlStr = Field(
        ...,
        description="The page URL to scan, e.g. 'https://www.agency.gov/page'.",
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of elements to return (1–200).",
    )


class ScanSiteInput(BaseModel):
    """Input for crawling a page's same-origin links and scanning each for issues."""

    url: HttpUrlStr = Field(
        ...,
        description="The starting page URL, e.g. 'https://www.agency.gov/'.",
    )
    max_pages: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of pages to scan, including the start page (1–20).",
    )
    limit_per_page: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of images to return per page (1–100).",
    )
