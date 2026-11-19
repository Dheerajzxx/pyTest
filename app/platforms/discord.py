"""Discord integration through channel webhooks.

Webhook messages need no bot account or OAuth flow, which keeps the
integration to a single request. `wait=true` makes Discord return the created
message so we can build a jump link.
Docs: https://discord.com/developers/docs/resources/webhook#execute-webhook
"""

from __future__ import annotations

import httpx

from app.platforms.base import BasePlatform, PlatformError, PublishOutcome


class DiscordPlatform(BasePlatform):
    name = "Discord"

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        webhook_url: str,
        public_access: bool = False,
    ) -> None:
        super().__init__(client)
        self.webhook_url = webhook_url.strip()
        self.public_access = public_access

    async def publish(self, message: str) -> PublishOutcome:
        response = await self.client.post(
            self.webhook_url,
            params={"wait": "true"},
            json={"content": message, "allowed_mentions": {"parse": []}},
        )
        if response.status_code in {401, 403, 404}:
            raise PlatformError(
                "Authentication failed: check DISCORD_WEBHOOK_URL "
                f"({response.status_code})"
            )
        self.ensure_success(response, "Posting the Discord message")
        payload = self.parse_json(response, "Posting the Discord message")

        message_id = payload.get("id")
        channel_id = payload.get("channel_id")
        guild_id = payload.get("guild_id")
        posted_url = None
        if message_id and channel_id and guild_id:
            posted_url = (
                f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
            )

        return PublishOutcome(posted_url=posted_url, public_access=self.public_access)
