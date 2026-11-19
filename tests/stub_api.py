"""Local stand-in for the six provider APIs, used for end-to-end runs.

Start it with:
    uvicorn tests.stub_api:app --host 127.0.0.1 --port 4100

and point the posting service at it with the *_API_BASE overrides. Any Discord
webhook whose token is "fail" answers 404 so failure handling can be exercised
over real HTTP as well.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Provider stub", docs_url=None, redoc_url=None)


@app.post("/xrpc/com.atproto.server.createSession")
async def create_session(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "accessJwt": "stub-jwt",
            "refreshJwt": "stub-refresh",
            "handle": "local.test",
            "did": "did:plc:local",
        }
    )


@app.post("/xrpc/com.atproto.repo.createRecord")
async def create_record(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "uri": "at://did:plc:local/app.bsky.feed.post/3klocal",
            "cid": "bafylocal",
        }
    )


@app.post("/api/v1/statuses")
async def mastodon_status(request: Request) -> JSONResponse:
    return JSONResponse({"id": "501", "url": "https://mastodon.local/@local/501"})


@app.post("/bot{token}/sendMessage")
async def telegram_send(token: str, request: Request) -> JSONResponse:
    return JSONResponse(
        {"ok": True, "result": {"message_id": 77, "chat": {"username": "local_channel"}}}
    )


@app.post("/api/webhooks/{webhook_id}/{webhook_token}")
async def discord_webhook(
    webhook_id: str, webhook_token: str, request: Request
) -> JSONResponse:
    if webhook_token == "fail":
        return JSONResponse({"message": "Unknown Webhook", "code": 10015}, status_code=404)
    return JSONResponse({"id": "901", "channel_id": "556", "guild_id": "778"})


@app.post("/api/articles")
async def devto_article(request: Request) -> JSONResponse:
    return JSONResponse(
        {"id": 12, "url": "https://dev.local/local/grow-your-visibility-12ab"},
        status_code=201,
    )


@app.post("/api/v1/access_token")
async def reddit_token(request: Request) -> JSONResponse:
    return JSONResponse({"access_token": "stub-reddit-token", "token_type": "bearer"})


@app.post("/api/submit")
async def reddit_submit(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "json": {
                "errors": [],
                "data": {"url": "https://www.reddit.local/r/test/comments/abc9/post/"},
            }
        }
    )
