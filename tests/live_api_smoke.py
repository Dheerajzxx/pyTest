"""Smoke check of the real provider endpoints with placeholder credentials.

Every integration is pointed at the live API with deliberately invalid
credentials. A correct request shape is answered with an authentication error,
so this confirms the URLs, headers and payloads reach the real services without
publishing anything.

Usage:
    python -m tests.live_api_smoke
"""

from __future__ import annotations

import asyncio

import httpx

from app.platforms.bluesky import BlueskyPlatform
from app.platforms.base import PlatformError
from app.platforms.devto import DevToPlatform
from app.platforms.discord import DiscordPlatform
from app.platforms.mastodon import MastodonPlatform
from app.platforms.reddit import RedditPlatform
from app.platforms.telegram import TelegramPlatform

MESSAGE = "Smoke test post, please ignore. https://example.com"


async def log_response(response: httpx.Response) -> None:
    request = response.request
    print(f"    {request.method} {request.url.scheme}://{request.url.host}{request.url.path}"
          f" -> HTTP {response.status_code}")


async def main() -> None:
    async with httpx.AsyncClient(
        timeout=20.0,
        follow_redirects=True,
        event_hooks={"response": [log_response]},
    ) as client:
        platforms = [
            BlueskyPlatform(client, handle="smoke-test-invalid.bsky.social",
                            app_password="invalid-app-password"),
            MastodonPlatform(client, instance_url="https://mastodon.social",
                             access_token="invalid-token"),
            TelegramPlatform(client, bot_token="000000:invalid-token", chat_id="@invalid"),
            DiscordPlatform(client, webhook_url="https://discord.com/api/webhooks/1/invalid"),
            DevToPlatform(client, api_key="invalid-key"),
            RedditPlatform(client, client_id="invalid", client_secret="invalid",
                           username="invalid", password="invalid", subreddit="test"),
        ]

        for platform in platforms:
            print(f"{platform.name}:")
            try:
                outcome = await platform.publish(MESSAGE)
            except PlatformError as exc:
                print(f"    rejected as expected -> {exc}")
            except httpx.HTTPError as exc:
                print(f"    transport error -> {exc}")
            except Exception as exc:  # keep the remaining checks running
                print(f"    error -> {type(exc).__name__}: {exc}")
            else:
                print(f"    unexpected success -> {outcome}")


if __name__ == "__main__":
    asyncio.run(main())
