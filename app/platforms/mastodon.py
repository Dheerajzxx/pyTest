"""Mastodon integration.

Any Mastodon server exposes the same REST API; post with a user access token
that has the `write:statuses` scope.
Docs: https://docs.joinmastodon.org/methods/statuses/#create
"""

from __future__ import annotations

import httpx

from app.platforms.base import BasePlatform, PlatformError, PublishOutcome


class MastodonPlatform(BasePlatform):
    name = "Mastodon"

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        instance_url: str,
        access_token: str,
        visibility: str = "public",
    ) -> None:
        super().__init__(client)
        self.instance_url = instance_url.rstrip("/")
        self.access_token = access_token
        self.visibility = visibility

    async def publish(self, message: str) -> PublishOutcome:
        response = await self.client.post(
            f"{self.instance_url}/api/v1/statuses",
            headers={"Authorization": f"Bearer {self.access_token}"},
            json={"status": message, "visibility": self.visibility},
        )
        if response.status_code == 401:
            raise PlatformError(
                "Authentication failed: check MASTODON_ACCESS_TOKEN and its scopes"
            )
        self.ensure_success(response, "Publishing the Mastodon status")
        payload = self.parse_json(response, "Publishing the Mastodon status")

        return PublishOutcome(
            posted_url=payload.get("url") or payload.get("uri"),
            public_access=self.visibility in {"public", "unlisted"},
        )
