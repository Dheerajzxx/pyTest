"""Bluesky (AT Protocol) integration.

Sign in with an app password to get a short lived JWT, then write a post
record into the repository. Docs: https://docs.bsky.app/docs/advanced-guides/posts
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.platforms.base import BasePlatform, PlatformError, PublishOutcome

POST_COLLECTION = "app.bsky.feed.post"


class BlueskyPlatform(BasePlatform):
    name = "Bluesky"

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        handle: str,
        app_password: str,
        pds_url: str = "https://bsky.social",
    ) -> None:
        super().__init__(client)
        self.handle = handle
        self.app_password = app_password
        self.pds_url = pds_url.rstrip("/")

    async def publish(self, message: str) -> PublishOutcome:
        session = await self._create_session()
        record = {
            "$type": POST_COLLECTION,
            "text": message,
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "langs": ["en"],
        }
        response = await self.client.post(
            f"{self.pds_url}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {session['accessJwt']}"},
            json={
                "repo": session["did"],
                "collection": POST_COLLECTION,
                "record": record,
            },
        )
        self.ensure_success(response, "Creating the Bluesky post")
        payload = self.parse_json(response, "Creating the Bluesky post")

        uri = payload.get("uri") or ""
        rkey = uri.rsplit("/", 1)[-1] if "/" in uri else ""
        posted_url = (
            f"https://bsky.app/profile/{self.handle}/post/{rkey}" if rkey else None
        )
        return PublishOutcome(posted_url=posted_url, public_access=True)

    async def _create_session(self) -> dict:
        response = await self.client.post(
            f"{self.pds_url}/xrpc/com.atproto.server.createSession",
            json={"identifier": self.handle, "password": self.app_password},
        )
        if response.status_code in {400, 401}:
            raise PlatformError(
                "Authentication failed: check BLUESKY_HANDLE and BLUESKY_APP_PASSWORD"
            )
        self.ensure_success(response, "Signing in to Bluesky")
        payload = self.parse_json(response, "Signing in to Bluesky")
        if not payload.get("accessJwt") or not payload.get("did"):
            raise PlatformError("Signing in to Bluesky returned an incomplete session")
        return payload
