"""Shared fixtures: credentials in the environment and an app under test."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.config import get_settings
from app.main import app, get_http_client
from tests.mock_providers import FakeProviders

CREDENTIALS = {
    "BLUESKY_HANDLE": "tester.bsky.social",
    "BLUESKY_APP_PASSWORD": "app-password",
    "MASTODON_INSTANCE_URL": "https://mastodon.test",
    "MASTODON_ACCESS_TOKEN": "mastodon-token",
    "TELEGRAM_BOT_TOKEN": "123456:telegram-token",
    "TELEGRAM_CHAT_ID": "@mychannel",
    "DISCORD_WEBHOOK_URL": "https://discord.test/api/webhooks/123/abc",
    "DEVTO_API_KEY": "devto-key",
    "REDDIT_CLIENT_ID": "reddit-client-id",
    "REDDIT_CLIENT_SECRET": "reddit-client-secret",
    "REDDIT_USERNAME": "reddit-user",
    "REDDIT_PASSWORD": "reddit-pass",
    "REDDIT_SUBREDDIT": "test",
}

VALID_MESSAGE = (
    "Check out our latest business platform and grow your online visibility. "
    "https://example.com"
)


@pytest.fixture
def clean_settings():
    """Reload settings after a test changes the environment."""

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def configured_env(monkeypatch, clean_settings):
    for key, value in CREDENTIALS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("POSTING_PLATFORMS", raising=False)
    get_settings.cache_clear()
    yield CREDENTIALS


@pytest.fixture
def no_credentials(monkeypatch, clean_settings):
    for key in CREDENTIALS:
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield


@pytest.fixture
async def harness(configured_env):
    """An app client talking to fake providers instead of the real APIs."""

    providers = FakeProviders()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(providers.handle)
    ) as upstream:
        app.dependency_overrides[get_http_client] = lambda: upstream
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            yield SimpleNamespace(client=client, providers=providers)
    app.dependency_overrides.clear()
