"""In-memory stand-ins for the six provider APIs used by the tests."""

from __future__ import annotations

import json

import httpx

BSKY_SESSION = {
    "accessJwt": "access-jwt",
    "refreshJwt": "refresh-jwt",
    "handle": "tester.bsky.social",
    "did": "did:plc:tester",
}


class FakeProviders:
    """Routes provider URLs to canned responses and records the requests."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.failures: dict[str, tuple[int, dict]] = {}
        self.delay_for: dict[str, float] = {}

    def fail(self, platform: str, status_code: int = 401, payload: dict | None = None) -> None:
        self.failures[platform] = (
            status_code,
            payload or {"error": f"{platform} rejected the request"},
        )

    def requests_to(self, fragment: str) -> list[httpx.Request]:
        return [request for request in self.requests if fragment in str(request.url)]

    def body_of(self, request: httpx.Request) -> dict:
        return json.loads(request.content.decode() or "{}")

    def _platform_for(self, path: str) -> str:
        if path.startswith("/xrpc/com.atproto.server.createSession"):
            return "bluesky"
        if path.startswith("/xrpc/com.atproto.repo.createRecord"):
            return "bluesky"
        if path.endswith("/api/v1/statuses"):
            return "mastodon"
        if "/bot" in path and path.endswith("/sendMessage"):
            return "telegram"
        if "/api/webhooks/" in path:
            return "discord"
        if path.endswith("/api/articles"):
            return "devto"
        if path.endswith("/api/v1/access_token"):
            return "reddit"
        if path.endswith("/api/submit"):
            return "reddit"
        return "unknown"

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        platform = self._platform_for(path)

        if platform in self.failures:
            status_code, payload = self.failures[platform]
            return httpx.Response(status_code, json=payload)

        if path.startswith("/xrpc/com.atproto.server.createSession"):
            return httpx.Response(200, json=BSKY_SESSION)
        if path.startswith("/xrpc/com.atproto.repo.createRecord"):
            return httpx.Response(
                200,
                json={
                    "uri": "at://did:plc:tester/app.bsky.feed.post/3kabc",
                    "cid": "bafyreitest",
                },
            )
        if path.endswith("/api/v1/statuses"):
            return httpx.Response(
                200,
                json={
                    "id": "111",
                    "url": "https://mastodon.test/@tester/111",
                    "uri": "https://mastodon.test/users/tester/statuses/111",
                },
            )
        if path.endswith("/sendMessage"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": {
                        "message_id": 42,
                        "chat": {"id": -100123, "username": "mychannel"},
                    },
                },
            )
        if "/api/webhooks/" in path:
            return httpx.Response(
                200,
                json={"id": "900", "channel_id": "555", "guild_id": "777"},
            )
        if path.endswith("/api/articles"):
            return httpx.Response(
                200,
                json={"id": 7, "url": "https://dev.to/tester/grow-your-visibility-7abc"},
            )
        if path.endswith("/api/v1/access_token"):
            return httpx.Response(200, json={"access_token": "reddit-token"})
        if path.endswith("/api/submit"):
            return httpx.Response(
                200,
                json={
                    "json": {
                        "errors": [],
                        "data": {
                            "url": "https://www.reddit.com/r/test/comments/abc123/post/"
                        },
                    }
                },
            )
        return httpx.Response(404, json={"error": f"no stub route for {path}"})
