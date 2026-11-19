"""DEV Community (Forem) integration.

An article is created with a personal API key. DEV requires a title, so one is
derived from the message when the caller does not provide the message alone.
Docs: https://developers.forem.com/api/v1#tag/articles/operation/createArticle
"""

from __future__ import annotations

import httpx

from app.platforms.base import BasePlatform, PlatformError, PublishOutcome
from app.schemas import extract_links

API_VERSION = "application/vnd.forem.api-v1+json"
TITLE_LIMIT = 80


def build_title(message: str) -> str:
    """Turn a short message into a usable article title."""

    text = message
    for link in extract_links(message):
        text = text.replace(link, "")
    text = " ".join(text.split()).strip(" -—:|,.;")

    if not text:
        return "New update"
    if len(text) <= TITLE_LIMIT:
        return text

    truncated = text[: TITLE_LIMIT - 3]
    cut = truncated.rsplit(" ", 1)[0].rstrip(" ,.;:-") or truncated.rstrip()
    return f"{cut}..."


class DevToPlatform(BasePlatform):
    name = "DEV Community"

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        api_key: str,
        api_base: str = "https://dev.to/api",
    ) -> None:
        super().__init__(client)
        self.api_key = api_key
        self.api_base = api_base.rstrip("/")

    async def publish(self, message: str) -> PublishOutcome:
        response = await self.client.post(
            f"{self.api_base}/articles",
            headers={
                "api-key": self.api_key,
                "Accept": API_VERSION,
                "Content-Type": "application/json",
            },
            json={
                "article": {
                    "title": build_title(message),
                    "body_markdown": message,
                    "published": True,
                }
            },
        )
        if response.status_code in {401, 403}:
            raise PlatformError("Authentication failed: check DEVTO_API_KEY")
        self.ensure_success(response, "Publishing the DEV article")
        payload = self.parse_json(response, "Publishing the DEV article")

        return PublishOutcome(posted_url=payload.get("url"), public_access=True)
