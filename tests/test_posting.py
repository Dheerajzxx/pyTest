"""Behaviour of the posting endpoint across all six platforms."""

from __future__ import annotations

import asyncio
import re

import httpx

from app.config import get_settings
from app.main import app, get_http_client
from tests.conftest import VALID_MESSAGE
from tests.mock_providers import FakeProviders

EXPECTED_ORDER = [
    "Bluesky",
    "Mastodon",
    "Telegram",
    "Discord",
    "DEV Community",
    "Reddit",
]


async def test_every_platform_receives_the_message(harness):
    response = await harness.client.post("/posting", json={"message": VALID_MESSAGE})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert [result["platform"] for result in body["results"]] == EXPECTED_ORDER
    assert all(result["status"] == "success" for result in body["results"])
    assert all(result["error"] is None for result in body["results"])
    for result in body["results"]:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", result["date"])
        assert re.fullmatch(r"\d{2}:\d{2}:\d{2}", result["time"])


async def test_posted_urls_and_public_access_flags(harness):
    response = await harness.client.post("/posting", json={"message": VALID_MESSAGE})
    results = {item["platform"]: item for item in response.json()["results"]}

    assert results["Bluesky"]["posted_url"] == (
        "https://bsky.app/profile/tester.bsky.social/post/3kabc"
    )
    assert results["Mastodon"]["posted_url"] == "https://mastodon.test/@tester/111"
    assert results["Telegram"]["posted_url"] == "https://t.me/mychannel/42"
    assert results["Discord"]["posted_url"] == (
        "https://discord.com/channels/777/555/900"
    )
    assert results["DEV Community"]["posted_url"] == (
        "https://dev.to/tester/grow-your-visibility-7abc"
    )
    assert results["Reddit"]["posted_url"] == (
        "https://www.reddit.com/r/test/comments/abc123/post/"
    )

    assert results["Bluesky"]["public_access"] is True
    assert results["Mastodon"]["public_access"] is True
    assert results["Telegram"]["public_access"] is True
    assert results["DEV Community"]["public_access"] is True
    assert results["Reddit"]["public_access"] is True
    # Webhook messages are only visible inside the server.
    assert results["Discord"]["public_access"] is False


async def test_message_text_reaches_each_provider(harness):
    await harness.client.post("/posting", json={"message": VALID_MESSAGE})
    providers = harness.providers

    bsky = providers.body_of(providers.requests_to("createRecord")[0])
    assert bsky["record"]["text"] == VALID_MESSAGE

    mastodon = providers.body_of(providers.requests_to("/api/v1/statuses")[0])
    assert mastodon["status"] == VALID_MESSAGE
    assert mastodon["visibility"] == "public"

    telegram = providers.body_of(providers.requests_to("/sendMessage")[0])
    assert telegram["text"] == VALID_MESSAGE
    assert telegram["chat_id"] == "@mychannel"

    discord = providers.body_of(providers.requests_to("/api/webhooks/")[0])
    assert discord["content"] == VALID_MESSAGE

    devto = providers.body_of(providers.requests_to("/api/articles")[0])
    assert devto["article"]["body_markdown"] == VALID_MESSAGE
    assert devto["article"]["published"] is True

    reddit = providers.requests_to("/api/submit")[0]
    assert "kind=self" in reddit.content.decode().replace("%3D", "=")


async def test_failure_on_one_platform_does_not_stop_the_others(harness):
    harness.providers.fail("mastodon", 401, {"error": "The access token is invalid"})

    response = await harness.client.post("/posting", json={"message": VALID_MESSAGE})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    results = {item["platform"]: item for item in body["results"]}

    mastodon = results["Mastodon"]
    assert mastodon["status"] == "failed"
    assert mastodon["posted_url"] is None
    assert mastodon["public_access"] is False
    assert mastodon["date"] is None
    assert mastodon["time"] is None
    assert mastodon["error"].startswith("Authentication failed")

    assert sum(item["status"] == "success" for item in body["results"]) == 5
    for name in ("Bluesky", "Telegram", "Discord", "DEV Community", "Reddit"):
        assert results[name]["status"] == "success"


async def test_two_failures_are_reported_independently(harness):
    harness.providers.fail("telegram", 403, {"ok": False, "description": "bot was blocked"})
    harness.providers.fail("devto", 401, {"error": "unauthorized"})

    response = await harness.client.post("/posting", json={"message": VALID_MESSAGE})
    body = response.json()
    results = {item["platform"]: item for item in body["results"]}

    assert body["success"] is True
    assert results["Telegram"]["status"] == "failed"
    assert results["DEV Community"]["status"] == "failed"
    assert results["Bluesky"]["status"] == "success"
    assert results["Reddit"]["status"] == "success"


async def test_all_failures_report_success_false(harness):
    for key in ("bluesky", "mastodon", "telegram", "discord", "devto", "reddit"):
        harness.providers.fail(key, 500, {"error": "provider is down"})

    response = await harness.client.post("/posting", json={"message": VALID_MESSAGE})
    body = response.json()

    assert response.status_code == 200
    assert body["success"] is False
    assert all(item["status"] == "failed" for item in body["results"])
    assert all(item["posted_url"] is None for item in body["results"])


async def test_slow_platform_times_out_and_others_continue(
    monkeypatch, configured_env
):
    monkeypatch.setenv("POSTING_TIMEOUT_SECONDS", "0.2")
    get_settings.cache_clear()

    providers = FakeProviders()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/v1/statuses"):
            await asyncio.sleep(2)
        return providers.handle(request)

    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app.dependency_overrides[get_http_client] = lambda: upstream
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.post("/posting", json={"message": VALID_MESSAGE})
    finally:
        app.dependency_overrides.clear()
        await upstream.aclose()

    body = response.json()
    results = {item["platform"]: item for item in body["results"]}
    assert body["success"] is True
    assert results["Mastodon"]["status"] == "failed"
    assert "timed out" in results["Mastodon"]["error"]
    assert results["Bluesky"]["status"] == "success"


async def test_platform_allow_list_limits_the_targets(harness, monkeypatch):
    monkeypatch.setenv("POSTING_PLATFORMS", "bluesky,devto")
    get_settings.cache_clear()

    response = await harness.client.post("/posting", json={"message": VALID_MESSAGE})

    body = response.json()
    assert [item["platform"] for item in body["results"]] == [
        "Bluesky",
        "DEV Community",
    ]


async def test_no_configured_platforms_returns_503(no_credentials):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post("/posting", json={"message": VALID_MESSAGE})

    assert response.status_code == 503
    assert "No posting platforms are configured" in response.json()["detail"]


async def test_health_reports_configured_platforms(harness):
    response = await harness.client.get("/health")

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["platform_count"] == 6
    assert body["platforms"] == [
        "bluesky",
        "mastodon",
        "telegram",
        "discord",
        "devto",
        "reddit",
    ]
