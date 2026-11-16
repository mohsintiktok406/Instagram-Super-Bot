import hashlib
import hmac
import json
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from .config import settings
from .meta_api import send_text_message, MetaAPIError
from .replies import keyword_reply
from .automation import match_trigger
from .inbox import (save_message, recent_messages, save_attachment_event,
                    update_attachment_event, attachment_event_key, purge_old_attachment_files)
from .ai_reply import generate_reply
from .media import download_attachment, is_view_once, normalize_media_type
from .notifications import notify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("instagram_super_bot")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.view_once_enabled and settings.view_once_retention_days > 0:
        try:
            count = purge_old_attachment_files(settings.view_once_retention_days)
            if count:
                logger.info("Retention cleanup processed %s old attachment rows", count)
        except Exception:
            logger.exception("Attachment retention cleanup failed")
    yield


app = FastAPI(title="Instagram Super Bot", version="0.1.0", lifespan=lifespan)


def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Validate X-Hub-Signature-256 when app secret is configured."""
    if not settings.meta_app_secret:
        return settings.app_env != "production"
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        settings.meta_app_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def _redacted_probe(payload: dict) -> dict:
    """Return payload shape for debugging without logging message content or URLs."""
    result = {"object": payload.get("object"), "entry": []}
    for entry in payload.get("entry", []):
        clean_entry = {"id": entry.get("id"), "messaging": []}
        for event in entry.get("messaging", []):
            message = event.get("message") or {}
            attachments = []
            for attachment in message.get("attachments", []) or []:
                if not isinstance(attachment, dict):
                    attachments.append({"invalid_attachment": True})
                    continue
                payload_data = attachment.get("payload")
                item = {
                    "type": attachment.get("type"),
                    "keys": sorted(attachment.keys()),
                }
                if isinstance(payload_data, dict):
                    item["payload"] = {
                        "keys": sorted(payload_data.keys()),
                        "url_present": bool(payload_data.get("url")),
                    }
                attachments.append(item)
            clean_entry["messaging"].append({
                "sender_present": bool((event.get("sender") or {}).get("id")),
                "recipient_present": bool((event.get("recipient") or {}).get("id")),
                "message_keys": sorted(message.keys()),
                "is_unsupported": bool(message.get("is_unsupported")),
                "attachments": attachments,
            })
        result["entry"].append(clean_entry)
    return result


def _safe_segment(value: str) -> str:
    """Return a portable, traversal-safe directory segment."""
    cleaned = re.sub(r"[^a-z0-9_-]", "_", str(value).lower())[:60].strip("._-")
    return cleaned or "unknown-thread"


async def _process_attachment_event(event: dict) -> None:
    message = event.get("message") or {}
    sender = str((event.get("sender") or {}).get("id", ""))
    recipient = str((event.get("recipient") or {}).get("id", ""))
    message_id = str(message.get("mid", ""))
    if not sender or not message_id:
        return
    thread_id = _safe_segment(str(event.get("thread_id") or recipient or sender))
    attachments = message.get("attachments") or []

    # Meta's is_unsupported is a generic unsupported-content marker, not proof
    # that the content is View Once. Preserve the otherwise invisible event.
    if not attachments and message.get("is_unsupported"):
        explicit_view_once = is_view_once(event)
        media_type = "view_once" if explicit_view_once else "unsupported_media"
        reason = "view_once_no_payload" if explicit_view_once else "meta_unsupported_no_payload"
        if save_attachment_event(
            thread_id, sender, message_id, media_type, "unsupported",
            reason=reason, attachment_index=0, is_view_once=explicit_view_once,
        ):
            notify(thread_id, sender, media_type, None, "unsupported", is_view_once=explicit_view_once)
            logger.info("Unsupported inbound media recorded mid=%s reason=%s", message_id, reason)
        return

    for index, attachment in enumerate(attachments):
        if not isinstance(attachment, dict):
            continue
        media_type = str(attachment.get("type") or "unknown").lower()
        event_key = attachment_event_key(message_id, index)
        disappearing = is_view_once(event, attachment)

        # Explicitly identified disappearing media is metadata-only.
        if disappearing:
            payload = attachment.get("payload") or {}
            has_url = isinstance(payload, dict) and bool(payload.get("url"))
            reason = "disappearing_media_not_archived" if has_url else "view_once_no_url"
            if save_attachment_event(thread_id, sender, message_id, media_type, "unsupported",
                                     reason=reason, attachment_index=index, is_view_once=True):
                notify(thread_id, sender, media_type, None, "unsupported", is_view_once=True)
            continue

        normalized_type = normalize_media_type(media_type)
        if normalized_type is None:
            if save_attachment_event(thread_id, sender, message_id, media_type, "unsupported",
                                     reason="unsupported_attachment_type", attachment_index=index, is_view_once=False):
                notify(thread_id, sender, media_type, None, "unsupported", is_view_once=False)
            continue

        payload = attachment.get("payload") or {}
        url = payload.get("url") if isinstance(payload, dict) else None
        if not url:
            if save_attachment_event(thread_id, sender, message_id, media_type, "unsupported",
                                     reason="attachment_url_missing", attachment_index=index, is_view_once=False):
                notify(thread_id, sender, media_type, None, "unsupported", is_view_once=False)
            continue

        # Reserve the (message_id, attachment_index) key before network I/O.
        if not save_attachment_event(thread_id, sender, message_id, media_type, "pending",
                                     reason="download_pending", attachment_index=index, is_view_once=False):
            continue
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = Path("media") / "attachments" / thread_id / f"{stamp}_{_safe_segment(message_id)}_{index}"
        try:
            path, size = await download_attachment(str(url), target, max_bytes=settings.media_max_bytes)
            update_attachment_event(event_key, status="captured", file_path=str(path), size_bytes=size)
            notify(thread_id, sender, media_type, path, "captured", is_view_once=False)
            logger.info("Inbound attachment saved: key=%s path=%s bytes=%s", event_key, path, size)
        except Exception as exc:
            reason = str(exc)[:500]
            update_attachment_event(event_key, status="expired", reason=reason)
            notify(thread_id, sender, media_type, None, "expired", is_view_once=False)
            logger.warning("Inbound attachment download failed key=%s: %s", event_key, exc)


async def _process_webhook(payload: dict) -> None:
    if settings.view_once_debug_raw:
        # One redacted structural probe per webhook payload, not once per event.
        logger.info("Attachment webhook probe: %s", json.dumps(_redacted_probe(payload), sort_keys=True))
    for entry in payload.get("entry", []):
        for event in entry.get("messaging", []):
            sender = str((event.get("sender") or {}).get("id", ""))
            message = event.get("message") or {}
            if (message.get("attachments") or message.get("is_unsupported") or is_view_once(event)) and settings.view_once_enabled:
                await _process_attachment_event(event)
            text = message.get("text", "")
            if not sender or not text or message.get("is_echo"):
                continue
            if settings.allowlist and sender not in settings.allowlist:
                continue
            message_id = str(message.get("mid", "")) or None
            event_type = "story_reply" if message.get("reply_to", {}).get("story") else "dm"
            save_message(sender, "inbound", text, event_type, message_id)
            reply_text = match_trigger(text, event_type)
            if not reply_text:
                legacy = keyword_reply(text)
                reply_text = legacy.text if legacy else None
            if not reply_text:
                try:
                    reply_text = await generate_reply(text, recent_messages(sender))
                except Exception as exc:
                    logger.warning("AI fallback failed: %s", exc)
            if reply_text:
                try:
                    await send_text_message(sender, reply_text)
                    save_message(sender, "outbound", reply_text, event_type)
                except MetaAPIError as exc:
                    logger.warning("Could not send reply: %s", exc)
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            if change.get("field") != "comments":
                continue
            sender = str((value.get("from") or {}).get("id", ""))
            comment_text = value.get("text", "")
            comment_id = str(value.get("id", ""))
            if not sender or not comment_text or not comment_id:
                continue
            if settings.allowlist and sender not in settings.allowlist:
                continue
            save_message(sender, "inbound", comment_text, "comment", comment_id)
            comment_reply = match_trigger(comment_text, "comment")
            if comment_reply:
                try:
                    from .meta_api import reply_to_comment
                    await reply_to_comment(comment_id, comment_reply)
                    save_message(sender, "outbound", comment_reply, "comment")
                except MetaAPIError as exc:
                    logger.warning("Could not reply to comment: %s", exc)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "instagram-super-bot", "version": "0.1.0"}


@app.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    if mode == "subscribe" and token and hmac.compare_digest(token, settings.verify_token):
        return challenge or ""
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@app.post("/webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    raw = await request.body()
    signature = request.headers.get("x-hub-signature-256")
    if not verify_signature(raw, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    background_tasks.add_task(_process_webhook, payload)
    return {"received": True}
