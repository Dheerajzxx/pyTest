"""Platform registry.

The application, not the caller, decides where a message is published: every
platform with credentials gets it, in a stable order.
"""

from __future__ import annotations

import httpx

from app.config import Settings
from app.platforms.base import BasePlatform
from app.platforms.bluesky import BlueskyPlatform
from app.platforms.devto import DevToPlatform
from app.platforms.discord import DiscordPlatform
from app.platforms.mastodon import MastodonPlatform
from app.platforms.reddit import RedditPlatform
from app.platforms.telegram import TelegramPlatform

PLATFORM_ORDER: tuple[str, ...] = (
    "bluesky",
    "mastodon",
    "telegram",
    "discord",
    "devto",
    "reddit",
)


def configured_platform_keys(settings: Settings) -> list[str]:
    """Keys of the platforms that have complete credentials."""

    return [key for key in PLATFORM_ORDER if getattr(settings, key).is_configured]


def selected_platform_keys(settings: Settings) -> list[str]:
    """Configured platforms, narrowed down by POSTING_PLATFORMS when set."""

    keys = configured_platform_keys(settings)
    if settings.enabled_platforms:
        keys = [key for key in keys if key in settings.enabled_platforms]
    return keys


def _build(key: str, settings: Settings, client: httpx.AsyncClient) -> BasePlatform:
    if key == "bluesky":
        config = settings.bluesky
        return BlueskyPlatform(
            client,
            handle=config.handle,
            app_password=config.app_password,
            pds_url=config.pds_url,
        )
    if key == "mastodon":
        config = settings.mastodon
        return MastodonPlatform(
            client,
            instance_url=config.instance_url,
            access_token=config.access_token,
            visibility=config.visibility,
        )
    if key == "telegram":
        config = settings.telegram
        return TelegramPlatform(
            client,
            bot_token=config.bot_token,
            chat_id=config.chat_id,
            public_access=config.public_access,
            api_base=config.api_base,
        )
    if key == "discord":
        config = settings.discord
        return DiscordPlatform(
            client,
            webhook_url=config.webhook_url,
            public_access=config.public_access,
        )
    if key == "devto":
        config = settings.devto
        return DevToPlatform(client, api_key=config.api_key, api_base=config.api_base)
    if key == "reddit":
        config = settings.reddit
        return RedditPlatform(
            client,
            client_id=config.client_id,
            client_secret=config.client_secret,
            username=config.username,
            password=config.password,
            subreddit=config.subreddit,
            user_agent=config.user_agent,
            public_access=config.public_access,
            api_base=config.api_base,
            token_base=config.token_base,
        )
    raise ValueError(f"Unknown platform: {key}")


def build_platforms(
    settings: Settings, client: httpx.AsyncClient
) -> list[BasePlatform]:
    """Instantiate every platform that should receive the message."""

    return [_build(key, settings, client) for key in selected_platform_keys(settings)]
