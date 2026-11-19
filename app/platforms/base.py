"""Shared building blocks for the platform integrations."""

from __future__ import annotations

import abc
from dataclasses import dataclass

import httpx


class PlatformError(Exception):
    """Raised when a platform rejects a post or cannot be reached."""


@dataclass(frozen=True)
class PublishOutcome:
    """What a platform reports after a successful publish."""

    posted_url: str | None
    public_access: bool


def describe_error(response: httpx.Response, limit: int = 300) -> str:
    """Build a short, credential-free description of a failed response."""

    detail = ""
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        for key in ("error_description", "description", "message", "error", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                detail = value.strip()
                break
        if not detail and payload.get("errors"):
            detail = str(payload["errors"])
    elif isinstance(payload, list) and payload:
        detail = str(payload[0])

    if not detail:
        detail = (response.text or "").strip() or response.reason_phrase

    return f"HTTP {response.status_code}: {detail[:limit]}"


class BasePlatform(abc.ABC):
    """One third-party integration.

    Subclasses only need `publish`; turning failures into response entries is
    handled by the posting service so every platform behaves the same way.
    """

    name: str = "unknown"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    @abc.abstractmethod
    async def publish(self, message: str) -> PublishOutcome:
        """Publish the message and return where it can be found."""

    @staticmethod
    def ensure_success(response: httpx.Response, action: str) -> httpx.Response:
        if response.status_code >= 400:
            raise PlatformError(f"{action} failed ({describe_error(response)})")
        return response

    @staticmethod
    def parse_json(response: httpx.Response, action: str) -> dict:
        try:
            payload = response.json()
        except ValueError as exc:
            raise PlatformError(f"{action} returned a response that is not JSON") from exc
        if not isinstance(payload, dict):
            raise PlatformError(f"{action} returned an unexpected response body")
        return payload
