"""Bounded downloader for ordinary, non-disappearing image/video/audio attachments."""
from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

import httpx

MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024
ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_MEDIA_TYPES = {"image", "video", "audio"}
MIME_EXTENSIONS = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp",
    "image/heic": ".heic", "image/heif": ".heif", "video/mp4": ".mp4",
    "video/quicktime": ".mov", "video/webm": ".webm", "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a", "audio/aac": ".aac", "audio/ogg": ".ogg",
    "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/webm": ".webm",
}


def is_view_once(event: dict, attachment: dict | None = None) -> bool:
    """Detect explicit disappearing-media markers; Meta's is_unsupported is broader.

    `message.is_unsupported` only says that the message contains unsupported
    content. It is not a View Once discriminator and is handled separately by
    the webhook processor.
    """
    if not isinstance(event, dict):
        return False
    message = event.get("message") if isinstance(event.get("message"), dict) else event
    candidates = [message, event]
    if isinstance(attachment, dict):
        candidates.append(attachment)
        payload = attachment.get("payload")
        if isinstance(payload, dict):
            candidates.append(payload)
    else:
        payload = event.get("payload")
        if isinstance(payload, dict):
            candidates.append(payload)
        for item in message.get("attachments") or []:
            if not isinstance(item, dict):
                continue
            candidates.append(item)
            item_payload = item.get("payload")
            if isinstance(item_payload, dict):
                candidates.append(item_payload)

    for obj in candidates:
        for key in ("view_mode", "viewMode", "ephemeral", "is_ephemeral", "isEphemeral",
                    "raven_media", "ravenMedia", "is_view_once", "isViewOnce"):
            value = obj.get(key)
            if value is True or (isinstance(value, str) and value.strip().lower() in {
                "once", "view_once", "view-once", "ephemeral", "raven", "one_time"
            }):
                return True
        for key in ("item_type", "itemType", "media_type", "mediaType", "type"):
            value = str(obj.get(key, "")).strip().lower().replace("-", "_")
            if value in {"raven_media", "view_once", "viewonce", "ephemeral_media", "one_time_media"}:
                return True
    return False


def normalize_media_type(value: str) -> str | None:
    value = (value or "").strip().lower().split("/", 1)[0]
    return value if value in ALLOWED_MEDIA_TYPES else None


def _extension_from_mime(content_type: str | None) -> str:
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    extension = MIME_EXTENSIONS.get(mime) or mimetypes.guess_extension(mime)
    if not extension or not extension.startswith(".") or len(extension) > 8:
        raise ValueError(f"unsupported or missing attachment MIME type: {mime or 'missing'}")
    return extension.lower()


async def download_attachment(url: str, destination: Path, *, max_bytes: int = MAX_ATTACHMENT_BYTES,
                              attempts: int = 3) -> tuple[Path, int]:
    """Download an ordinary media URL; final extension is derived from response MIME."""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES or not parsed.netloc:
        raise ValueError("attachment URL must use http or https")
    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(max(1, min(attempts, 3))):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=3.0), follow_redirects=False) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    content_type = response.headers.get("content-type")
                    extension = _extension_from_mime(content_type)
                    length = response.headers.get("content-length")
                    if length and int(length) > max_bytes:
                        raise ValueError("attachment exceeds configured size limit")
                    final_path = destination.with_suffix(extension)
                    total = 0
                    try:
                        with final_path.open("wb") as output:
                            async for chunk in response.aiter_bytes(64 * 1024):
                                total += len(chunk)
                                if total > max_bytes:
                                    raise ValueError("attachment exceeds configured size limit")
                                output.write(chunk)
                    except Exception:
                        final_path.unlink(missing_ok=True)
                        raise
                    return final_path, total
        except (httpx.HTTPError, OSError) as exc:
            last_error = exc
            if attempt < min(attempts, 3) - 1:
                await asyncio.sleep(0.25 * (attempt + 1))
    if last_error:
        raise RuntimeError(f"attachment download failed: {last_error}") from last_error
    raise RuntimeError("attachment download failed")
