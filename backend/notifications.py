"""Pluggable attachment notification interface (logging implementation for now)."""
import logging
from pathlib import Path

logger = logging.getLogger("instagram_super_bot.notifications")


def notify(thread_id: str, sender: str, media_type: str, path: str | Path | None,
           status: str, is_view_once: bool = False) -> None:
    """Emit an attachment event; replace this function with a push/webhook adapter later."""
    logger.info("Attachment notification thread=%s sender=%s type=%s path=%s status=%s is_view_once=%s",
                thread_id, sender, media_type, str(path) if path else None, status, is_view_once)
