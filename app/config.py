"""Settings for the posting service, read from the environment.

Every credential lives in the environment (or a local .env file) so nothing
sensitive is hard-coded. A platform is considered available as soon as all of
its required credentials are present; the API itself decides which platforms a
message goes to, callers never pick platforms.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

DEFAULT_USER_AGENT = "automated-posting/1.0"


def _text(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _flag(name: str, default: bool) -> bool:
    raw = _text(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _number(name: str, default: float) -> float:
    raw = _text(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class BlueskyConfig:
    """Bluesky talks to a PDS over the AT Protocol; app passwords are enough."""

    handle: str = ""
    app_password: str = ""
    pds_url: str = "https://bsky.social"

    @property
    def is_configured(self) -> bool:
        return bool(self.handle and self.app_password)


@dataclass(frozen=True)
class MastodonConfig:
    instance_url: str = ""
    access_token: str = ""
    visibility: str = "public"

    @property
    def is_configured(self) -> bool:
        return bool(self.instance_url and self.access_token)

    @property
    def public_access(self) -> bool:
        return self.visibility in {"public", "unlisted"}


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str = ""
    chat_id: str = ""
    public_access: bool = False
    api_base: str = "https://api.telegram.org"

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)


@dataclass(frozen=True)
class DiscordConfig:
    webhook_url: str = ""
    public_access: bool = False

    @property
    def is_configured(self) -> bool:
        return bool(self.webhook_url)


@dataclass(frozen=True)
class DevToConfig:
    api_key: str = ""
    api_base: str = "https://dev.to/api"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class RedditConfig:
    client_id: str = ""
    client_secret: str = ""
    username: str = ""
    password: str = ""
    subreddit: str = ""
    user_agent: str = ""
    public_access: bool = True
    api_base: str = "https://oauth.reddit.com"
    token_base: str = "https://www.reddit.com"

    @property
    def is_configured(self) -> bool:
        return bool(
            self.client_id
            and self.client_secret
            and self.username
            and self.password
            and self.subreddit
        )


@dataclass(frozen=True)
class Settings:
    bluesky: BlueskyConfig = field(default_factory=BlueskyConfig)
    mastodon: MastodonConfig = field(default_factory=MastodonConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    devto: DevToConfig = field(default_factory=DevToConfig)
    reddit: RedditConfig = field(default_factory=RedditConfig)
    request_timeout: float = 15.0
    user_agent: str = DEFAULT_USER_AGENT
    enabled_platforms: tuple[str, ...] = ()


def _enabled_platforms() -> tuple[str, ...]:
    raw = _text("POSTING_PLATFORMS")
    if not raw:
        return ()
    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())


def load_settings() -> Settings:
    """Build a Settings object from the current environment."""

    return Settings(
        bluesky=BlueskyConfig(
            handle=_text("BLUESKY_HANDLE"),
            app_password=_text("BLUESKY_APP_PASSWORD"),
            pds_url=_text("BLUESKY_PDS_URL", "https://bsky.social").rstrip("/"),
        ),
        mastodon=MastodonConfig(
            instance_url=_text("MASTODON_INSTANCE_URL").rstrip("/"),
            access_token=_text("MASTODON_ACCESS_TOKEN"),
            visibility=_text("MASTODON_VISIBILITY", "public").lower(),
        ),
        telegram=TelegramConfig(
            bot_token=_text("TELEGRAM_BOT_TOKEN"),
            chat_id=_text("TELEGRAM_CHAT_ID"),
            public_access=_flag("TELEGRAM_PUBLIC_ACCESS", False),
            api_base=_text("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/"),
        ),
        discord=DiscordConfig(
            webhook_url=_text("DISCORD_WEBHOOK_URL"),
            public_access=_flag("DISCORD_PUBLIC_ACCESS", False),
        ),
        devto=DevToConfig(
            api_key=_text("DEVTO_API_KEY"),
            api_base=_text("DEVTO_API_BASE", "https://dev.to/api").rstrip("/"),
        ),
        reddit=RedditConfig(
            client_id=_text("REDDIT_CLIENT_ID"),
            client_secret=_text("REDDIT_CLIENT_SECRET"),
            username=_text("REDDIT_USERNAME"),
            password=_text("REDDIT_PASSWORD"),
            subreddit=_text("REDDIT_SUBREDDIT"),
            user_agent=_text("REDDIT_USER_AGENT", "automated-posting/1.0"),
            public_access=_flag("REDDIT_PUBLIC_ACCESS", True),
            api_base=_text("REDDIT_API_BASE", "https://oauth.reddit.com").rstrip("/"),
            token_base=_text("REDDIT_TOKEN_BASE", "https://www.reddit.com").rstrip("/"),
        ),
        request_timeout=_number("POSTING_TIMEOUT_SECONDS", 15.0),
        user_agent=_text("POSTING_USER_AGENT", DEFAULT_USER_AGENT),
        enabled_platforms=_enabled_platforms(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings, loaded once per process."""

    return load_settings()
