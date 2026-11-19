"""Request and response models, including the message rules."""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_MESSAGE_LENGTH = 200
MIN_LINK_COUNT = 1
MAX_LINK_COUNT = 1

_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
# A link without a scheme is the most common mistake, so we look for one to
# explain the problem instead of only saying "no link found".
_BARE_DOMAIN_PATTERN = re.compile(
    r"(?<![\w@.])(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,24}(?:/[^\s<>\"']*)?",
    re.IGNORECASE,
)
_TRAILING_PUNCTUATION = ".,;:!?)]}'\""


def extract_links(message: str) -> list[str]:
    """Return the http(s) links found in a message, without trailing punctuation."""

    links = []
    for match in _URL_PATTERN.findall(message):
        cleaned = match.rstrip(_TRAILING_PUNCTUATION)
        if cleaned:
            links.append(cleaned)
    return links


def is_valid_url(candidate: str) -> bool:
    """True when candidate is an absolute http(s) URL with a plausible host."""

    try:
        parsed = urlparse(candidate)
        port = parsed.port
    except ValueError:
        return False

    if parsed.scheme.lower() not in {"http", "https"}:
        return False
    if not parsed.netloc or not parsed.hostname:
        return False
    if any(character.isspace() for character in candidate):
        return False
    if port is not None and not 0 < port < 65536:
        return False

    host = parsed.hostname
    if host in {"localhost"} or host.replace(".", "").isdigit():
        return True
    return "." in host and not host.startswith(".") and not host.endswith(".")


class PostRequest(BaseModel):
    """Body of POST /posting."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(
        ...,
        description=(
            "Message to publish. Maximum 200 characters and exactly one "
            "absolute http(s) call-to-action link."
        ),
        examples=[
            "Check out our latest business platform and grow your online "
            "visibility. https://example.com"
        ],
    )

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if not value:
            raise ValueError("message must not be empty")

        if len(value) > MAX_MESSAGE_LENGTH:
            raise ValueError(
                f"message must be {MAX_MESSAGE_LENGTH} characters or fewer "
                f"(received {len(value)})"
            )

        links = extract_links(value)
        if len(links) > MAX_LINK_COUNT:
            raise ValueError(
                f"message must contain exactly one call-to-action link "
                f"(found {len(links)})"
            )
        if not links:
            lowered = value.lower()
            if "http://" in lowered or "https://" in lowered:
                raise ValueError("the call-to-action link is not a valid URL")
            if _BARE_DOMAIN_PATTERN.search(value):
                raise ValueError(
                    "the call-to-action link must be a full URL starting with "
                    "http:// or https://"
                )
            raise ValueError("message must contain exactly one call-to-action link")

        if not is_valid_url(links[0]):
            raise ValueError(f"the call-to-action link is not a valid URL: {links[0]}")

        return value


class PostResult(BaseModel):
    """Outcome for a single platform."""

    platform: str = Field(..., description="Human readable platform name")
    status: Literal["success", "failed"] = Field(..., description="Publish status")
    posted_url: str | None = Field(None, description="URL of the published content")
    public_access: bool = Field(False, description="Whether the content is public")
    date: str | None = Field(None, description="Posting date (UTC, YYYY-MM-DD)")
    time: str | None = Field(None, description="Posting time (UTC, HH:MM:SS)")
    error: str | None = Field(None, description="Error details when the post failed")


class PostResponse(BaseModel):
    """Body returned by POST /posting."""

    success: bool = Field(
        ..., description="True when at least one platform accepted the message"
    )
    results: list[PostResult] = Field(
        default_factory=list, description="One entry per attempted platform"
    )
