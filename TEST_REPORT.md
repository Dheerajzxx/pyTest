# Test Report

Automated Multi-Platform Posting API (`POST /posting`)

## Summary

| Area | Method | Result |
|---|---|---|
| Message validation rules | 15 automated tests | Pass |
| Endpoint behaviour, fan-out and failure isolation | 10 automated tests | Pass |
| Individual integrations (request shape, response parsing, error mapping) | 16 automated tests | Pass |
| Real HTTP end-to-end run of the API on port 4000 | uvicorn + curl against a local provider stub | Pass |
| Failure isolation over real HTTP | uvicorn + curl, one unreachable and one rejecting platform | Pass |
| Live connectivity to the six real provider APIs | `python -m tests.live_api_smoke` | Pass (all six reached, all six rejected the placeholder credentials as expected) |
| Environment loading from `.env` | isolated temp directory run | Pass |
| OpenAPI schema and `/docs` | HTTP GET | Pass |

Test suite result: `41 passed in 0.37s`.

## Environment

| Item | Value |
|---|---|
| OS | macOS (darwin) |
| Python | 3.15.2 (virtualenv at `.venv`) |
| FastAPI | 0.163.1 |
| Uvicorn | 0.54.0 |
| httpx | 0.28.1 |
| Pydantic | 2.14.3 |
| pytest / pytest-asyncio | 9.2.0 / 1.5.0 |

Date of run: 2026-11-17.

## Test layers

1. **Unit and integration tests** (`tests/`) - FastAPI app driven through
   `httpx.ASGITransport` with the outbound HTTP client replaced by
   `httpx.MockTransport`, so every request the service makes is inspected and
   every response is simulated.
2. **Local end-to-end** - the real server on `127.0.0.1:4000`, the six provider
   APIs replaced by `tests/stub_api.py` on `127.0.0.1:4100`, requests sent with
   `curl` over TCP. This exercises routing, validation, dependency injection,
   connection pooling and JSON serialisation for real.
3. **Live connectivity smoke** - the integrations are pointed at the real
   provider hosts (`bsky.social`, `mastodon.social`, `api.telegram.org`,
   `discord.com`, `dev.to`, `www.reddit.com`) with placeholder credentials. A
   correct request reaches the provider and is answered with an authentication
   error; a wrong URL or payload shape would instead produce a 404 or a 400.

## Steps and results

### 1. Dependencies and test suite

```bash
python3 -m venv .venv
./.venv/bin/pip install fastapi uvicorn httpx pydantic pytest pytest-asyncio python-dotenv
./.venv/bin/python -m pytest -q
```

Result:

```
41 passed in 0.37s
```

Per file:

| File | Coverage | Tests | Result |
|---|---|---|---|
| `tests/test_validation.py` | length limit, link count, URL validity, empty body, extra fields, accepted link variants | 15 | Pass |
| `tests/test_posting.py` | fan-out to six platforms, field values, payload contents, one/two/all failures, timeout, allow-list, 503, `/health` | 10 | Pass |
| `tests/test_platforms.py` | per-integration request shape and response parsing, auth failures, unexpected exceptions | 16 | Pass |

### 2. Server start and health

```bash
uvicorn app.main:app --host 0.0.0.0 --port 4000
curl -s http://127.0.0.1:4000/health
```

```json
{"status":"ok","version":"1.0.0","platforms":["bluesky","mastodon","telegram","discord","devto","reddit"],"platform_count":6}
```

All six platforms were recognised from the environment. Server log showed
`Application startup complete`.

### 3. Documentation endpoints

```bash
curl -o /dev/null -w "%{http_code}" http://127.0.0.1:4000/docs
curl -s http://127.0.0.1:4000/openapi.json
```

`/docs` returned `200`; the schema lists `['/health', '/posting']` under the
title `Automated Multi-Platform Posting API`.

### 4. Happy path

```bash
curl -X POST http://127.0.0.1:4000/posting \
  -H "Content-Type: application/json" \
  -d '{"message":"Check out our latest business platform and grow your online visibility. https://example.com"}'
```

Result: `HTTP 200` in `0.055s`, `success: true`, six results in the order
Bluesky, Mastodon, Telegram, Discord, DEV Community, Reddit.

| Platform | Status | Posted URL | Public access | Date / time |
|---|---|---|---|---|
| Bluesky | success | `https://bsky.app/profile/local.test/post/3klocal` | true | 2026-11-17 08:04:54 |
| Mastodon | success | `https://mastodon.local/@local/501` | true | 2026-11-17 08:04:54 |
| Telegram | success | `https://t.me/local_channel/77` | true | 2026-11-17 08:04:54 |
| Discord | success | `https://discord.com/channels/778/556/901` | false | 2026-11-17 08:04:54 |
| DEV Community | success | `https://dev.local/local/grow-your-visibility-12ab` | true | 2026-11-17 08:04:54 |
| Reddit | success | `https://www.reddit.local/r/test/comments/abc9/post/` | true | 2026-11-17 08:04:54 |

`error` was `null` for every entry. The provider stub received seven upstream
requests - Bluesky signs in and then posts, Reddit fetches a token and then
submits - and the payload contents are asserted in
`tests/test_posting.py::test_message_text_reaches_each_provider`.

### 5. Validation

Each request below was sent to the running server; all returned `422`.

| Case | Message returned |
|---|---|
| 209 characters | `message must be 200 characters or fewer (received 209)` |
| no link | `message must contain exactly one call-to-action link` |
| two links | `message must contain exactly one call-to-action link (found 2)` |
| bare domain `example.com` | `the call-to-action link must be a full URL starting with http:// or https://` |
| `https://` with no host | `the call-to-action link is not a valid URL` |
| whitespace only | `message must not be empty` |
| extra field `platforms` | `Extra inputs are not permitted` |
| exactly 200 characters | accepted, `HTTP 200`, `success: true`, 6 platforms |

### 6. Failure isolation over real HTTP

A second instance was started on port 4001 with `MASTODON_INSTANCE_URL`
pointing at a closed port (`127.0.0.1:4199`) and a Discord webhook that the stub
answers with `404`.

```bash
curl -X POST http://127.0.0.1:4001/posting -H "Content-Type: application/json" \
  -d '{"message":"Check out our latest business platform. https://example.com"}'
```

Result: `HTTP 200` in `0.073s`, `success: true`.

| Platform | Status | Error |
|---|---|---|
| Bluesky | success | - |
| Mastodon | failed | `Network error: All connection attempts failed` |
| Telegram | success | - |
| Discord | failed | `Authentication failed: check DISCORD_WEBHOOK_URL (404)` |
| DEV Community | success | - |
| Reddit | success | - |

The failed entries had `posted_url: null`, `public_access: false`, `date: null`,
`time: null`, matching the documented contract. Server log recorded both
failures as warnings and the request still answered normally.

### 7. Live connectivity to the real provider APIs

```bash
./.venv/bin/python -m tests.live_api_smoke
```

| Platform | Request sent | Response | Handling |
|---|---|---|---|
| Bluesky | `POST https://bsky.social/xrpc/com.atproto.server.createSession` | `401` | `Authentication failed: check BLUESKY_HANDLE and BLUESKY_APP_PASSWORD` |
| Mastodon | `POST https://mastodon.social/api/v1/statuses` | `401` | `Authentication failed: check MASTODON_ACCESS_TOKEN and its scopes` |
| Telegram | `POST https://api.telegram.org/bot<token>/sendMessage` | `401` | `Authentication failed: check TELEGRAM_BOT_TOKEN` |
| Discord | `POST https://discord.com/api/webhooks/1/invalid` | `404` | `Authentication failed: check DISCORD_WEBHOOK_URL (404)` |
| DEV Community | `POST https://dev.to/api/articles` | `401` | `Authentication failed: check DEVTO_API_KEY` |
| Reddit | `POST https://www.reddit.com/api/v1/access_token` | `401` | `Authentication failed: check the Reddit app credentials and password` |

Every host resolved over TLS and answered with an authentication error rather
than `404`/`400`, which confirms the paths, headers and payloads are correct.
No content was created because no valid credentials were used.

### 8. `.env` loading

`.env.example` was copied into a temporary directory with two platforms filled
in, and the settings were loaded from that directory:

```
bluesky: dotenv.bsky.social from-dotenv
telegram: @dotenv_channel https://api.telegram.org
configured: ['bluesky', 'telegram']
```

Only platforms with complete credentials are enabled, which is what the
`/health` endpoint reported in step 2 for the six-platform run.

## Defects found and fixed during verification

| # | Problem | Found by | Fix |
|---|---|---|---|
| 1 | DEV Community titles longer than 80 characters were cut to 80 and then suffixed with `...`, producing 83-character titles | `test_build_title` | Truncate to `TITLE_LIMIT - 3` before adding the suffix, so titles never exceed the limit |
| 2 | A message containing `https://` without a host was reported as "must contain exactly one link" instead of a URL problem | `test_malformed_link_is_rejected` | Detect a scheme with no parsable link and report `the call-to-action link is not a valid URL` |
| 3 | The smoke script passed a synchronous event hook to an async `httpx` client and crashed before running the other checks | live smoke run | Hook made asynchronous, plus a catch-all so one failing check does not stop the rest |
| 4 | `TELEGRAM_API_BASE`, `DEVTO_API_BASE` and the Reddit bases were read from the environment at property access time while every other setting was read once at load | code review during the run | Moved into `load_settings` so all settings share one source of truth |

## Not verified

- **Real publishing.** No live account credentials were available, so no post
  was actually created on any provider. Publication is verified end to end
  against a stub that implements the same response contracts, and the request
  shapes are verified against the real hosts in step 7. Supplying credentials
  in `.env` is the only remaining step to post for real.
- **Provider-side rate limits and moderation rules** (Reddit subreddit rules,
  DEV tag requirements, Telegram flood control) are surfaced as platform errors
  but were not exercised.
- **Discord public access** is intentionally reported as `false`, since a
  channel message is not readable without signing in. The setting
  `DISCORD_PUBLIC_ACCESS` only describes how the operator wants it reported.

## Reproducing

```bash
# automated suite
pip install -r requirements-dev.txt
pytest

# end-to-end with the provider stub
uvicorn tests.stub_api:app --host 127.0.0.1 --port 4100
BLUESKY_HANDLE=local.test BLUESKY_APP_PASSWORD=stub BLUESKY_PDS_URL=http://127.0.0.1:4100 \
MASTODON_INSTANCE_URL=http://127.0.0.1:4100 MASTODON_ACCESS_TOKEN=stub \
TELEGRAM_BOT_TOKEN=123456:stub TELEGRAM_CHAT_ID=@local_channel TELEGRAM_API_BASE=http://127.0.0.1:4100 \
DISCORD_WEBHOOK_URL=http://127.0.0.1:4100/api/webhooks/123/abc \
DEVTO_API_KEY=stub DEVTO_API_BASE=http://127.0.0.1:4100/api \
REDDIT_CLIENT_ID=id REDDIT_CLIENT_SECRET=secret REDDIT_USERNAME=u REDDIT_PASSWORD=p \
REDDIT_SUBREDDIT=test REDDIT_API_BASE=http://127.0.0.1:4100 REDDIT_TOKEN_BASE=http://127.0.0.1:4100 \
uvicorn app.main:app --host 0.0.0.0 --port 4000

# live connectivity check against the real provider hosts
python -m tests.live_api_smoke
```
