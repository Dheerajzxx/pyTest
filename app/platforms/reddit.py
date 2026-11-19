"""Reddit integration.

A script app exchanges username/password for an OAuth token and submits a self
post to a subreddit.
Docs: https://www.reddit.com/dev/api/#POST_api_submit
"""

from __future__ import annotations

import httpx

from app.platforms.base import BasePlatform, PlatformError, PublishOutcome
from app.platforms.devto import build_title


class RedditPlatform(BasePlatform):
    name = "Reddit"

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        client_id: str,
        client_secret: str,
        username: str,
        password: str,
        subreddit: str,
        user_agent: str = "automated-posting/1.0",
        public_access: bool = True,
        api_base: str = "https://oauth.reddit.com",
        token_base: str = "https://www.reddit.com",
    ) -> None:
        super().__init__(client)
        self.client_id = client_id
        self.client_secret = client_secret
        self.username = username
        self.password = password
        self.subreddit = subreddit.lstrip("r/")
        self.user_agent = user_agent
        self.public_access = public_access
        self.api_base = api_base.rstrip("/")
        self.token_base = token_base.rstrip("/")

    async def publish(self, message: str) -> PublishOutcome:
        token = await self._access_token()
        response = await self.client.post(
            f"{self.api_base}/api/submit",
            headers={"Authorization": f"bearer {token}", "User-Agent": self.user_agent},
            data={
                "sr": self.subreddit,
                "title": build_title(message),
                "kind": "self",
                "text": message,
                "api_type": "json",
                "resubmit": "false",
            },
        )
        if response.status_code in {401, 403}:
            raise PlatformError(
                "Authentication failed: check the Reddit app credentials and scopes"
            )
        self.ensure_success(response, "Submitting the Reddit post")
        payload = self.parse_json(response, "Submitting the Reddit post")

        body = payload.get("json") or {}
        errors = body.get("errors") or []
        if errors:
            raise PlatformError(f"Submitting the Reddit post failed: {errors}")

        data = body.get("data") or {}
        posted_url = data.get("url")
        if not posted_url and data.get("id"):
            posted_url = f"https://www.reddit.com/r/{self.subreddit}/comments/{data['id']}"

        return PublishOutcome(posted_url=posted_url, public_access=self.public_access)

    async def _access_token(self) -> str:
        response = await self.client.post(
            f"{self.token_base}/api/v1/access_token",
            auth=(self.client_id, self.client_secret),
            data={
                "grant_type": "password",
                "username": self.username,
                "password": self.password,
            },
            headers={"User-Agent": self.user_agent},
        )
        if response.status_code in {400, 401}:
            raise PlatformError(
                "Authentication failed: check the Reddit app credentials and password"
            )
        self.ensure_success(response, "Requesting a Reddit access token")
        payload = self.parse_json(response, "Requesting a Reddit access token")

        token = payload.get("access_token")
        if not token:
            raise PlatformError("Requesting a Reddit access token returned no token")
        return token
