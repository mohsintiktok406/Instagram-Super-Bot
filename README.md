# Instagram Super Bot (starter)

A modular, self-hosted Instagram creator assistant starter. The first integration uses Meta's official Instagram API for supported messaging/comment workflows. This project does **not** scrape private endpoints, collect passwords, recover unsent messages, or bypass View Once/disappearing-media protections.

## Current modules

- Official Meta webhook receiver for supported DM/comment events
- Reusable keyword triggers for DMs, comments and received story-reply events
- SQLite inbox persistence for inbound/outbound events
- Optional OpenAI-compatible AI fallback (off by default)
- Meta Graph API helpers for comment replies and listing media owned by the connected account
- Optional unofficial `instagrapi` own-account session connector (local interactive login; separate from Meta webhooks)
- Allowlist support for controlled testing
- Bounded downloader for ordinary image/video/audio attachments; disappearing media is metadata-only
- Attachment-event metadata with per-attachment idempotency (`UNIQUE(message_id, attachment_index)`)
- Pluggable notification function (logging adapter by default)

## Attachment processing

Attachment processing is disabled by default. Set `VIEW_ONCE_ENABLED=true` to enable the ordinary attachment pipeline and metadata classification. Despite the legacy setting name, this flag does not authorize archiving View Once content.

For each inbound attachment or unsupported-content message:

1. Each attachment row stores `is_view_once` (`0` or `1`) so downstream notification adapters can make an informed decision. Only explicit disappearing-media markers set it to `1`.
2. Meta's `message.is_unsupported` means the message contains unsupported content; it does **not** identify View Once specifically. If this marker arrives with no attachments, the event is still recorded as `unsupported_media`, status `unsupported`, reason `meta_unsupported_no_payload`, `file_path=NULL`, and a notification is emitted.
3. A zero-attachment event is classified as View Once only if a separate explicit View Once marker is present; then it is recorded as `view_once` with reason `view_once_no_payload`. Do not infer View Once solely from `is_unsupported`.
4. Explicitly identified View Once/disappearing media is not archived. Ordinary supported attachments must have a type of `image`, `video`, or `audio` before any download is attempted. Missing ordinary URLs are recorded as `unsupported` with reason `attachment_url_missing`.
5. Ordinary media URLs are fetched over HTTP(S), with no redirects, an 8-second timeout, up to three attempts, and a `MEDIA_MAX_BYTES` cap (15 MiB by default).
6. The response MIME type must be recognized and determines the saved file extension. Extension-less/unknown-MIME files are rejected.
7. Each attachment has its own idempotency key: `f"{message_id}:{attachment_index}"`. Multiple attachments in one message are stored independently.

Status values are `pending`, `captured`, `expired`, and `unsupported`. Old `pending` rows are included in retention cleanup so interrupted downloads do not remain pending forever. The SQLite initializer migrates earlier schemas, adds `is_view_once INTEGER NOT NULL DEFAULT 0`, and preserves existing records with attachment index `0`.

## Notifications

`backend/notifications.py` exposes:

```python
notify(thread_id, sender, media_type, path_or_none, status)
```

The current implementation logs notifications. Replace the function body with a permitted push, email, or webhook adapter when one is configured. Notifications are emitted for final attachment outcomes; pending reservation is not sent as a user-facing notification.

## Webhook diagnostics

`VIEW_ONCE_DEBUG_RAW=true` enables one **redacted structural probe per webhook payload**. It logs field names and whether an attachment URL is present, never full message text or signed attachment URLs. It is deliberately not a raw JSON dump because webhook payloads can contain private message data and short-lived credentials.

## Retention

`VIEW_ONCE_RETENTION_DAYS` controls retention (default 30; `0` disables cleanup). The app performs a cleanup pass during FastAPI lifespan startup. For continuous cleanup, schedule `purge_old_attachment_files()` externally. Captured files are deleted and audit rows retained; stale pending rows are marked `expired`.

## Platform limitations

- Meta may not deliver a webhook event for every disappearing-media interaction. The bot cannot process an event it never receives.
- Ordinary attachment URLs may be short-lived; expiry, timeout, missing permissions, or token issues can prevent retrieval.
- `message.is_unsupported` is a generic unsupported-content marker, not a View Once discriminator. Events with no attachment payload are recorded and notified rather than silently dropped.
- Explicit disappearing-media markers are metadata-only and excluded from downloading.
- This project never archives View Once/disappearing media, even when a webhook includes a URL.

## Optional unofficial Instagram account connection

This is an opt-in, separate private-API login path for **your own account only**. It does not replace the Meta webhook receiver: Instagram will not automatically send webhook events to this private session, and this starter does not yet route DMs through the unofficial client. Unofficial endpoints can change, trigger login challenges, or cause temporary account restrictions; use a test account and accept that risk.

Install the optional dependency and run the local prompt (the password is hidden and is never placed in `.env` or sent to ChatGPT):

```bash
pip install -r requirements-unofficial.txt
python -m backend.connect_instagram
```

The connector validates the login, prints the account identity, and saves a private session to `data/instagram_private_session.json` with owner-only file permissions where supported. The session file is an account credential: do not share it, upload it, commit it, or put it in logs. Revoke the session from Instagram's login activity if it is exposed. For account safety, do not repeatedly retry failed logins; resolve any Instagram app/email/SMS/2FA challenge on your own device first.

This unofficial connector is not an Instagram-approved API and may stop working without notice. It does not scrape other accounts, bypass access controls, or archive View Once/disappearing media.

## Requirements

- Python 3.11+
- Meta Developer app + Instagram Professional account for supported official API features
- HTTPS webhook endpoint reachable by Meta
- Optional AI provider key (keep it server-side)

## Local setup

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
```

Webhook endpoint: `/webhook` (GET verification + POST event receiver). The POST handler validates signature/JSON, schedules processing with FastAPI `BackgroundTasks`, and acknowledges the webhook.

## Security

- Never commit `.env`, access tokens, app secrets, session cookies, or account passwords.
- For the official integration, use Meta OAuth and access tokens. The optional unofficial connector prompts locally for your own account credentials and never asks you to paste them into ChatGPT.
- Verify webhook signatures in production.
- Configure a narrow allowlist while testing.
- Respect messaging windows, permissions, rate limits, opt-outs and user privacy.
- Thread identifiers used in file paths are sanitized to portable lowercase `[a-z0-9_-]` characters and limited to 60 characters.
- View Once/disappearing media is never archived by this project.

## Status

This is an **early development build**, not a production-ready Instagram bot. Meta app configuration, app review, production database migration, AI provider configuration, deployment and end-to-end tests remain to be completed.

## Docker

```bash
docker build -t instagram-super-bot .
docker run --env-file .env -p 8000:8000 instagram-super-bot
```

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the staged implementation plan. GitHub Actions runs the unit tests on pushes and pull requests.
