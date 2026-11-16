# Development roadmap

This repository is an API-compliant foundation, not a claim that every Instagram feature is already implemented.

## Phase 1 — foundation (included)
- FastAPI health endpoint and Meta webhook verification/receiver
- HMAC SHA-256 webhook signature validation when an app secret is configured
- Basic keyword auto-replies and sender allowlist
- Official Graph API text-message client
- Unit tests, Dockerfile and GitHub Actions test workflow

## Phase 2 — inbox and automation
- Persistent conversations/messages (SQLite for development, PostgreSQL for deployment)
- Rule CRUD and per-account settings
- Comment webhook parsing and approved comment replies
- Opt-out keywords, per-user cooldowns, duplicate-event idempotency and audit log

## Phase 3 — AI assistant and dashboard
- Provider-neutral AI adapter (OpenAI-compatible endpoint and local Ollama option)
- Human handoff, confidence threshold and safe reply preview
- Web dashboard with inbox, rule editor and analytics

## Phase 4 — publishing and media
- Scheduling only for media types and publishing permissions supported by the current Meta API
- Import/export of content the account owner is authorized to access
- No scraping of private endpoints and no bypass of View Once/disappearing-media controls

## Before production
- Complete Meta app setup, permissions and App Review
- Confirm current Graph API version and supported webhook fields
- Configure HTTPS, persistent database, secrets manager and monitoring
- Add integration tests against a dedicated test account
- Review Meta Platform Terms and rate limits
