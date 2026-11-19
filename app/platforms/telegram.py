"""Telegram integration.

A bot posts into a channel or group it has been added to. Channels with a
public username get a shareable https://t.me/<name>/<message_id> link.
Docs: https://core.telegram.org/bots/api#sendmessage
"""

from __future__ import annotations

import httpx

from app.platforms.base import BasePlatform, PlatformError, PublishOutcome


class TelegramPlatform(BasePlatform):
    name = "Telegram"

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        bot_token: str,
        chat_id: str,
        public_access: bool = False,
        api_base: str = "https://api.telegram.org",
    ) -> None:
        super().__init__(client)
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.public_access = public_access
        self.api_base = api_base.rstrip("/")

    @property
    def _is_public_channel(self) -> bool:
        if self.chat_id.startswith("@"):
            return True
        return self.public_access

    async def publish(self, message: str) -> PublishOutcome:
        response = await self.client.post(
            f"{self.api_base}/bot{self.bot_token}/sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": message,
                "disable_web_page_preview": False,
            },
        )
        if response.status_code == 401:
            raise PlatformError("Authentication failed: check TELEGRAM_BOT_TOKEN")
        self.ensure_success(response, "Sending the Telegram message")

        payload = self.parse_json(response, "Sending the Telegram message")
        if not payload.get("ok"):
            description = payload.get("description", "unknown error")
            raise PlatformError(f"Sending the Telegram message failed: {description}")

        result = payload.get("result") or {}
        message_id = result.get("message_id")
        chat = result.get("chat") or {}
        username = chat.get("username") or (
            self.chat_id.lstrip("@") if self.chat_id.startswith("@") else ""
        )

        posted_url = None
        if self._is_public_channel and username and message_id:
            posted_url = f"https://t.me/{username}/{message_id}"

        return PublishOutcome(posted_url=posted_url, public_access=self._is_public_channel)
