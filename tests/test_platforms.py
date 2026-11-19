"""Unit tests for the individual platform integrations."""

from __future__ import annotations

import json

import httpx
import pytest

from app.platforms.base import BasePlatform, PlatformError, PublishOutcome
from app.platforms.bluesky import BlueskyPlatform
from app.platforms.devto import DevToPlatform, build_title
from app.platforms.discord import DiscordPlatform
from app.platforms.mastodon import MastodonPlatform
from app.platforms.reddit import RedditPlatform
from app.platforms.telegram import TelegramPlatform
from app.services.posting_service import PostingService
from tests.mock_providers import BSKY_SESSION

MESSAGE = "Grow your online visibility https://example.com"


def body_of(request: httpx.Request) -> dict:
    return json.loads(request.content.decode() or "{}")


async def test_bluesky_signs_in_then_creates_the_post():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("createSession"):
            return httpx.Response(200, json=BSKY_SESSION)
        return httpx.Response(
            200,
            json={
                "uri": "at://did:plc:tester/app.bsky.feed.post/3krkey",
                "cid": "bafyreitest",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        platform = BlueskyPlatform(
            client, handle="tester.bsky.social", app_password="app-password"
        )
        outcome = await platform.publish(MESSAGE)

    session_request, record_request = seen
    assert body_of(session_request) == {
        "identifier": "tester.bsky.social",
        "password": "app-password",
    }
    record_body = body_of(record_request)
    assert record_body["repo"] == "did:plc:tester"
    assert record_body["collection"] == "app.bsky.feed.post"
    assert record_body["record"]["text"] == MESSAGE
    assert record_body["record"]["createdAt"].endswith("Z")
    assert record_request.headers["authorization"] == "Bearer access-jwt"
    assert outcome.posted_url == (
        "https://bsky.app/profile/tester.bsky.social/post/3krkey"
    )
    assert outcome.public_access is True


async def test_bluesky_reports_bad_credentials():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "AuthenticationRequired"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        platform = BlueskyPlatform(
            client, handle="tester.bsky.social", app_password="wrong"
        )
        with pytest.raises(PlatformError, match="Authentication failed"):
            await platform.publish(MESSAGE)


async def test_mastodon_posts_a_public_status():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200, json={"url": "https://mastodon.test/@tester/111", "id": "111"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        platform = MastodonPlatform(
            client,
            instance_url="https://mastodon.test",
            access_token="token",
            visibility="public",
        )
        outcome = await platform.publish(MESSAGE)

    request = captured[0]
    assert request.url.path == "/api/v1/statuses"
    assert request.headers["authorization"] == "Bearer token"
    assert body_of(request) == {"status": MESSAGE, "visibility": "public"}
    assert outcome.posted_url == "https://mastodon.test/@tester/111"
    assert outcome.public_access is True


async def test_mastodon_private_visibility_is_not_public():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"url": "https://mastodon.test/@tester/1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        platform = MastodonPlatform(
            client,
            instance_url="https://mastodon.test",
            access_token="token",
            visibility="private",
        )
        outcome = await platform.publish(MESSAGE)

    assert outcome.public_access is False


async def test_telegram_public_channel_gets_a_shareable_link():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={"ok": True, "result": {"message_id": 42, "chat": {"username": "news"}}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        platform = TelegramPlatform(
            client, bot_token="123:abc", chat_id="@news", api_base="https://telegram.test"
        )
        outcome = await platform.publish(MESSAGE)

    request = captured[0]
    assert request.url.path == "/bot123:abc/sendMessage"
    assert body_of(request)["disable_web_page_preview"] is False
    assert outcome.posted_url == "https://t.me/news/42"
    assert outcome.public_access is True


async def test_telegram_numeric_chat_id_is_not_public_by_default():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"ok": True, "result": {"message_id": 7, "chat": {"id": 5}}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        platform = TelegramPlatform(client, bot_token="123:abc", chat_id="-100999")
        outcome = await platform.publish(MESSAGE)

    assert outcome.posted_url is None
    assert outcome.public_access is False


async def test_telegram_api_error_payload_is_surfaced():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"ok": False, "description": "chat not found"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        platform = TelegramPlatform(client, bot_token="123:abc", chat_id="@news")
        with pytest.raises(PlatformError, match="chat not found"):
            await platform.publish(MESSAGE)


async def test_discord_waits_for_the_message_and_builds_a_jump_link():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"id": "900", "channel_id": "555", "guild_id": "777"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        platform = DiscordPlatform(
            client, webhook_url="https://discord.test/api/webhooks/1/token"
        )
        outcome = await platform.publish(MESSAGE)

    request = captured[0]
    assert request.url.params["wait"] == "true"
    assert body_of(request)["allowed_mentions"] == {"parse": []}
    assert outcome.posted_url == "https://discord.com/channels/777/555/900"
    assert outcome.public_access is False


async def test_discord_revoked_webhook_is_reported():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Unknown Webhook", "code": 10015})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        platform = DiscordPlatform(client, webhook_url="https://discord.test/x")
        with pytest.raises(PlatformError, match="Authentication failed"):
            await platform.publish(MESSAGE)


async def test_devto_publishes_an_article_with_a_derived_title():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(201, json={"id": 7, "url": "https://dev.to/tester/post-7"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        platform = DevToPlatform(client, api_key="devto-key")
        outcome = await platform.publish(MESSAGE)

    request = captured[0]
    assert request.headers["api-key"] == "devto-key"
    assert request.headers["accept"] == "application/vnd.forem.api-v1+json"
    article = body_of(request)["article"]
    assert article["title"] == "Grow your online visibility"
    assert article["body_markdown"] == MESSAGE
    assert article["published"] is True
    assert outcome.posted_url == "https://dev.to/tester/post-7"


@pytest.mark.parametrize(
    "message, expected",
    [
        ("Short update https://example.com", "Short update"),
        ("https://example.com", "New update"),
        ("A" * 120, "A" * 77 + "..."),
    ],
)
def test_build_title(message, expected):
    assert build_title(message) == expected


async def test_reddit_uses_a_password_grant_then_submits_a_self_post():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path.endswith("/api/v1/access_token"):
            return httpx.Response(200, json={"access_token": "reddit-token"})
        return httpx.Response(
            200,
            json={
                "json": {
                    "errors": [],
                    "data": {"url": "https://www.reddit.com/r/test/comments/abc1/post/"},
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        platform = RedditPlatform(
            client,
            client_id="id",
            client_secret="secret",
            username="user",
            password="pass",
            subreddit="r/test",
            user_agent="automated-posting/1.0",
        )
        outcome = await platform.publish(MESSAGE)

    token_request, submit_request = captured
    assert token_request.url.host == "www.reddit.com"
    assert token_request.headers["authorization"].startswith("Basic ")
    assert b"grant_type=password" in token_request.content
    assert submit_request.url.path == "/api/submit"
    assert submit_request.headers["authorization"] == "bearer reddit-token"
    form = submit_request.content.decode()
    assert "sr=test" in form
    assert "kind=self" in form
    assert outcome.posted_url == "https://www.reddit.com/r/test/comments/abc1/post/"


async def test_reddit_submit_errors_are_reported():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/v1/access_token"):
            return httpx.Response(200, json={"access_token": "reddit-token"})
        return httpx.Response(
            200, json={"json": {"errors": [["SUBREDDIT_NOTALLOWED", "no access", "sr"]]}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        platform = RedditPlatform(
            client,
            client_id="id",
            client_secret="secret",
            username="user",
            password="pass",
            subreddit="test",
        )
        with pytest.raises(PlatformError, match="SUBREDDIT_NOTALLOWED"):
            await platform.publish(MESSAGE)


class ExplodingPlatform(BasePlatform):
    name = "Exploding"

    async def publish(self, message: str) -> PublishOutcome:
        raise RuntimeError("integration bug")


class OKPlatform(BasePlatform):
    name = "OK"

    async def publish(self, message: str) -> PublishOutcome:
        return PublishOutcome(posted_url="https://ok.test/1", public_access=True)


async def test_service_isolates_unexpected_errors():
    service = PostingService([ExplodingPlatform(httpx.AsyncClient()), OKPlatform(httpx.AsyncClient())])

    results = await service.publish_all(MESSAGE)

    assert results[0].status == "failed"
    assert "Unexpected error" in results[0].error
    assert results[1].status == "success"
    assert results[1].posted_url == "https://ok.test/1"
