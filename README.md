# Automated Multi-Platform Posting

A small FastAPI service that publishes one short marketing message (200
characters maximum, exactly one call-to-action link) to several third-party
platforms at once and reports what happened on each of them.

The caller only sends the message. Which platforms receive it is decided by the
service from the credentials available in the environment.

## Supported platforms

| Platform | Endpoint used | Authentication | Content created | Posted URL |
|---|---|---|---|---|
| Bluesky | AT Protocol XRPC: `com.atproto.server.createSession` + `com.atproto.repo.createRecord` | handle and app password | `app.bsky.feed.post` record | `https://bsky.app/profile/<handle>/post/<rkey>` |
| Mastodon | `POST /api/v1/statuses` | user token with `write:statuses` | public status | status permalink returned by the instance |
| Telegram | Bot API `sendMessage` | bot token and target chat id | message in a channel or group | `https://t.me/<channel>/<message_id>` for public channels |
| Discord | channel webhook execute (`?wait=true`) | webhook URL | message in the channel | `https://discord.com/channels/<guild>/<channel>/<message>` |
| DEV Community | Forem API v1 `POST /api/articles` | personal API key | published article | article URL |
| Reddit | `POST /api/submit` (self post) | script app password grant | text post in a subreddit | post permalink |

Why these six: they cover four different auth models (app password, bearer
token, webhook, API key, OAuth password grant), they all accept a short plain
text message with a link, and none of them needs a browser-based OAuth consent
flow, which a backend service cannot complete on its own. Every one of them
returns an identifier or permalink that can be handed back to the caller.

Docs used while building the integrations:

- Bluesky: <https://docs.bsky.app/docs/advanced-guides/posts>
- Mastodon: <https://docs.joinmastodon.org/methods/statuses/#create>
- Telegram: <https://core.telegram.org/bots/api#sendmessage>
- Discord: <https://discord.com/developers/docs/resources/webhook#execute-webhook>
- DEV Community: <https://developers.forem.com/api/v1>
- Reddit: <https://www.reddit.com/dev/api/#POST_api_submit>

## Project layout

```
app/
  main.py                  FastAPI app, /posting and /health
  config.py                environment driven settings
  schemas.py               request validation and response models
  platforms/
    base.py                BasePlatform interface and error helpers
    bluesky.py             one module per integration
    mastodon.py
    telegram.py
    discord.py
    devto.py
    reddit.py
    registry.py            builds the platforms that are configured
  services/
    posting_service.py     parallel publishing and per-platform error handling
tests/
  test_validation.py       input rules
  test_posting.py          endpoint behaviour with fake providers
  test_platforms.py        request shape per integration
  stub_api.py              local stand-in for the six provider APIs
  live_api_smoke.py        connectivity check against the real endpoints
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in the credentials for the platforms you want to use. A platform is used
as soon as all of its variables are set; leave the rest empty and it is skipped.

| Platform | Variables | Where to get them |
|---|---|---|
| Bluesky | `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` | Settings > App Passwords (do not use the account password) |
| Mastodon | `MASTODON_INSTANCE_URL`, `MASTODON_ACCESS_TOKEN` | Your instance > Preferences > Development > New application, scope `write:statuses` |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | `@BotFather` for the token, add the bot as admin of the channel for the chat id (`@name` for public channels) |
| Discord | `DISCORD_WEBHOOK_URL` | Channel settings > Integrations > Webhooks > Copy Webhook URL |
| DEV Community | `DEVTO_API_KEY` | Settings > Extensions > DEV Community API Keys |
| Reddit | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USERNAME`, `REDDIT_PASSWORD`, `REDDIT_SUBREDDIT` | <https://www.reddit.com/prefs/apps> > create app > script |

Optional settings: `POSTING_TIMEOUT_SECONDS` (per platform request timeout,
default 15), `POSTING_PLATFORMS` (comma separated allow-list such as
`bluesky,devto`), `MASTODON_VISIBILITY`, `REDDIT_USER_AGENT`, and the
`*_API_BASE` overrides for running behind a proxy.

## Running

```bash
uvicorn app.main:app --host 0.0.0.0 --port 4000
```

Interactive documentation: <http://localhost:4000/docs>

## API

### `POST /posting`

```bash
curl -X POST http://localhost:4000/posting \
  -H "Content-Type: application/json" \
  -d '{"message":"Check out our latest business platform and grow your online visibility. https://example.com"}'
```

```json
{
  "success": true,
  "results": [
    {
      "platform": "Bluesky",
      "status": "success",
      "posted_url": "https://bsky.app/profile/your.handle/post/3kabc",
      "public_access": true,
      "date": "2026-11-17",
      "time": "08:04:54",
      "error": null
    },
    {
      "platform": "Discord",
      "status": "failed",
      "posted_url": null,
      "public_access": false,
      "date": null,
      "time": null,
      "error": "Authentication failed: check DISCORD_WEBHOOK_URL (404)"
    }
  ]
}
```

- `success` is `true` when at least one platform accepted the message.
- `date` and `time` are the UTC posting time, filled in only on success.
- `public_access` reports whether the content can be read without signing in.
  For Discord it is `false` by default because webhook messages are only
  visible to members of the server.
- Platforms are always reported in a stable order, so a failed platform keeps
  its position in the list.

Status codes: `200` when the fan-out was attempted (even if every platform
failed, the per-platform details say why), `422` for invalid input, `503` when
no platform credentials are configured at all.

### Validation rules

| Rule | Behaviour |
|---|---|
| Not empty | whitespace-only messages are rejected |
| 200 characters maximum | longer messages are rejected, the error includes the received length |
| Exactly one call-to-action link | zero or two or more links are rejected |
| Absolute URL | a bare domain such as `example.com` is rejected with a hint to add `http://` or `https://` |
| Valid URL | scheme must be `http` or `https`, host must be plausible, port must be in range |
| Known fields only | extra body fields are rejected |

All of these return `422` with a message naming the rule that failed, for
example `message must be 200 characters or fewer (received 209)`.

### `GET /health`

Returns the service version and the platform keys that currently have
credentials, useful to confirm the deployment picked up its environment.

```bash
curl http://localhost:4000/health
```

```json
{
  "status": "ok",
  "version": "1.0.0",
  "platforms": ["bluesky", "mastodon", "discord"],
  "platform_count": 3
}
```

### Error responses

Invalid input returns `422`. FastAPI wraps the validator message in its own
envelope, so the useful text is in `detail[0].msg`:

```bash
curl -X POST http://localhost:4000/posting \
  -H "Content-Type: application/json" \
  -d '{"message":"No link in this message"}'
```

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "message"],
      "msg": "Value error, message must contain exactly one call-to-action link",
      "input": "No link in this message"
    }
  ]
}
```

When no platform credentials are configured at all, the endpoint returns `503`:

```json
{
  "detail": "No posting platforms are configured. Add platform credentials to the environment (see .env.example) and restart the service."
}
```

## Error handling

- Every platform is published to in parallel, in its own task. A failure,
  an exception, or a timeout on one platform never stops the others and never
  breaks the request.
- Failures carry a short reason: HTTP status plus the provider's own message
  when it sends one, or a hint naming the credential to check. Tokens and
  secrets are never echoed back.
- Failures skip the traceback into the response; unexpected exceptions are
  logged with the platform name and reported as `Unexpected error: ...`.
- Nowhere in the request path is the whole batch retried, so a partially
  published message is reported as such instead of being posted twice.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

`tests/stub_api.py` plus `tests/live_api_smoke.py` are for manual end-to-end
runs; see `TEST_REPORT.md` for the commands and the recorded results.

## Adding a platform

1. Create `app/platforms/<name>.py` with a `BasePlatform` subclass: build the
   request in `publish` and return `PublishOutcome(posted_url, public_access)`.
   Raise `PlatformError` for anything the provider rejects.
2. Add a config dataclass with an `is_configured` property in `app/config.py`
   and fill it in `load_settings`.
3. Register the key in `PLATFORM_ORDER` and the factory in `registry.py`.
4. Document the variables in `.env.example` and add a test with a mocked
   transport, the way the existing integrations are tested.
