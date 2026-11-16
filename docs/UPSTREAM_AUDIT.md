# Upstream audit (reviewed 2026-11-16)

The project integrates selected **patterns and compatible features**, not whole upstream applications. Upstream code is not assumed to be production-ready merely because it is public.

| Repository | Useful features observed | License | Integration decision |
|---|---|---|---|
| [`Hammad69275/InstaBot`](https://github.com/Hammad69275/InstaBot) | AI group chat, public-media commands, music finder, local message store; README also claims Raven/disappearing media and unsent-message tracking | MIT (`LICENSE.md`, copyright Hammad Malik, 2023) | Do not import the unofficial private-API implementation or private-message harvesting. Feature concepts can be reimplemented with supported APIs. |
| [`sirdonvin/instapushdm`](https://github.com/sirdonvin/instapushdm) | DM keyword automation, comment-to-DM concepts, story replies, AI fallback, inbox and dashboard | MIT (`LICENSE`, copyright flexhunt, 2026) | Used as a feature/architecture reference. This Python starter implements a trigger matcher, inbox persistence and optional AI adapter rather than copying its Next.js source tree. |
| [`ayuuxh2/insta-p8`](https://github.com/ayuuxh2/insta-p8) | Same InstaAuto README/product lineage; Next.js, Supabase, DM/comment/story automation | MIT (`LICENSE`, copyright flexhunt, 2026) | Same lineage as above; avoid treating both repositories as independent implementations. |
| [`araneeskhan/instagram-auto-dm`](https://github.com/araneeskhan/instagram-auto-dm) | Official Graph API webhook/DM/comment approach | No license located in prior review | No code copied. |
| [`soics/instagram-bot`](https://github.com/soics/instagram-bot) | Ollama/local AI concepts using unofficial client | No license located in prior review | No code copied. |
| [`aashir-athar/mind-dm-bot`](https://github.com/aashir-athar/mind-dm-bot) | Comment automation | README states no license / all rights reserved | No code copied. |

## Implemented in this project

- Reusable keyword trigger matcher for DMs, comments and story-reply events.
- SQLite inbox storage for inbound/outbound message events.
- Optional OpenAI-compatible AI fallback (disabled until explicitly configured).
- Meta Graph API helpers for replying to comments and listing media from the connected account.
- Existing webhook now persists inbound messages and applies trigger/AI fallback logic.

## Not included

Raven/View Once extraction, unsent-message harvesting, private endpoint scraping, credential-based unofficial login, and downloading private/disappearing media are excluded. The Hammad README advertises these features, but their presence in an upstream repository does not make bypassing another person's privacy controls appropriate. Media listing is restricted to the connected professional account through the configured official API.

## Attribution

MIT license texts are retained in `licenses/UPSTREAM-*.txt`. Any future direct reuse of upstream code must preserve its copyright and permission notice and undergo dependency/security review.
