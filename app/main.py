"""FastAPI application exposing the posting endpoint."""

from __future__ import annotations

import logging
from typing import AsyncIterator

import httpx
from fastapi import Depends, FastAPI, HTTPException, status

from app import __version__
from app.config import Settings, get_settings
from app.platforms import build_platforms, configured_platform_keys
from app.schemas import PostRequest, PostResponse
from app.services import PostingService

logger = logging.getLogger(__name__)

DESCRIPTION = """
Publishes a single short message containing one call-to-action link to every
configured third-party platform, then reports the outcome of each attempt.

Platforms are chosen by the application from the credentials available in the
environment, so the caller only sends the message.
"""

tags_metadata = [
    {"name": "posting", "description": "Publish a message across platforms."},
    {"name": "ops", "description": "Health and configuration visibility."},
]

app = FastAPI(
    title="Automated Multi-Platform Posting API",
    version=__version__,
    description=DESCRIPTION,
    openapi_tags=tags_metadata,
)


async def get_http_client() -> AsyncIterator[httpx.AsyncClient]:
    """One connection pool per request, so every platform can post in parallel."""

    settings = get_settings()
    async with httpx.AsyncClient(
        timeout=settings.request_timeout,
        follow_redirects=True,
        headers={"User-Agent": settings.user_agent},
    ) as client:
        yield client


def get_current_settings() -> Settings:
    return get_settings()


@app.get("/health", tags=["ops"], summary="Service health and configured platforms")
async def health(settings: Settings = Depends(get_current_settings)) -> dict:
    platform_keys = configured_platform_keys(settings)
    return {
        "status": "ok",
        "version": __version__,
        "platforms": platform_keys,
        "platform_count": len(platform_keys),
    }


@app.post(
    "/posting",
    response_model=PostResponse,
    status_code=status.HTTP_200_OK,
    tags=["posting"],
    summary="Publish a message to every configured platform",
    responses={
        422: {"description": "Message failed validation"},
        503: {"description": "No platform credentials are configured"},
    },
)
async def publish_post(
    payload: PostRequest,
    client: httpx.AsyncClient = Depends(get_http_client),
    settings: Settings = Depends(get_current_settings),
) -> PostResponse:
    platforms = build_platforms(settings, client)
    if not platforms:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No posting platforms are configured. Add platform credentials "
                "to the environment (see .env.example) and restart the service."
            ),
        )

    service = PostingService(platforms, timeout=settings.request_timeout)
    results = await service.publish_all(payload.message)

    published = [result for result in results if result.status == "success"]
    logger.info(
        "Message published to %d/%d platforms", len(published), len(results)
    )

    return PostResponse(success=bool(published), results=results)
