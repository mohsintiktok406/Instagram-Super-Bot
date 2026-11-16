"""Opt-in local login helper for the user's own Instagram account.

This adapter only establishes and verifies a private-API session. It does not
read or archive disappearing media, scrape other accounts, or bypass privacy.
"""
from pathlib import Path
import os
from typing import Callable, Any


class InstagramConnectionError(RuntimeError):
    pass


def connect_own_account(
    username: str,
    password: str,
    session_path: str | Path = "data/instagram_private_session.json",
    client_factory: Callable[[], Any] | None = None,
) -> dict:
    if not username or not username.strip():
        raise ValueError("Instagram username is required")
    if not password:
        raise ValueError("Instagram password is required")
    if client_factory is None:
        try:
            from instagrapi import Client
        except ImportError as exc:
            raise InstagramConnectionError(
                "Unofficial connector missing. Install requirements-unofficial.txt"
            ) from exc
        client_factory = Client

    path = Path(session_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    client = client_factory()
    try:
        if path.exists():
            client.load_settings(str(path))
        # instagrapi validates/reuses the saved session when possible.
        client.login(username.strip(), password)
        profile = client.account_info()
        client.dump_settings(str(path))
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return {
            "connected": True,
            "username": getattr(profile, "username", None) or username.strip(),
            "user_id": str(getattr(profile, "pk", "") or getattr(client, "user_id", "")),
            "session_file": str(path),
        }
    except Exception as exc:
        # Do not include request bodies, cookies, credentials or raw server data.
        raise InstagramConnectionError(
            f"Instagram login/verification failed ({type(exc).__name__}). "
            "Check the username, password, 2FA/challenge prompt, and account login alerts."
        ) from exc
