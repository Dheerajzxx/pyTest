"""Posting orchestration.

Each platform is published to independently so one broken integration never
stops the message from reaching the others.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Iterable

import httpx

from app.platforms.base import BasePlatform, PlatformError
from app.schemas import PostResult

logger = logging.getLogger(__name__)


class PostingService:
    """Fans a message out to every configured platform."""

    def __init__(self, platforms: Iterable[BasePlatform], timeout: float = 15.0) -> None:
        self.platforms = list(platforms)
        self.timeout = timeout

    async def publish_all(self, message: str) -> list[PostResult]:
        if not self.platforms:
            return []
        results = await asyncio.gather(
            *(self._publish_one(platform, message) for platform in self.platforms)
        )
        return list(results)

    async def _publish_one(self, platform: BasePlatform, message: str) -> PostResult:
        try:
            outcome = await asyncio.wait_for(platform.publish(message), self.timeout)
        except asyncio.TimeoutError:
            return self._failure(platform, f"Request timed out after {self.timeout:g}s")
        except PlatformError as exc:
            return self._failure(platform, str(exc))
        except httpx.TimeoutException:
            return self._failure(platform, f"Request timed out after {self.timeout:g}s")
        except httpx.HTTPError as exc:
            return self._failure(platform, f"Network error: {exc}")
        except Exception as exc:  # keep one integration from breaking the request
            logger.exception("Unexpected error while posting to %s", platform.name)
            return self._failure(platform, f"Unexpected error: {exc}")

        posted_at = datetime.now(timezone.utc)
        return PostResult(
            platform=platform.name,
            status="success",
            posted_url=outcome.posted_url,
            public_access=outcome.public_access,
            date=posted_at.strftime("%Y-%m-%d"),
            time=posted_at.strftime("%H:%M:%S"),
            error=None,
        )

    @staticmethod
    def _failure(platform: BasePlatform, error: str) -> PostResult:
        logger.warning("Posting to %s failed: %s", platform.name, error)
        return PostResult(
            platform=platform.name,
            status="failed",
            posted_url=None,
            public_access=False,
            date=None,
            time=None,
            error=error[:500],
        )
