"""Run: python -m backend.connect_instagram (credentials are prompted locally)."""
import getpass
import os
from pathlib import Path

from .unofficial_instagram import connect_own_account, InstagramConnectionError


def main() -> int:
    username = input("Instagram username (your own account): ").strip()
    password = getpass.getpass("Instagram password (hidden; never sent to ChatGPT): ")
    session_path = Path(os.getenv("INSTAGRAM_PRIVATE_SESSION", "data/instagram_private_session.json"))
    try:
        result = connect_own_account(username, password, session_path)
    except (ValueError, InstagramConnectionError) as exc:
        print(f"Connection not completed: {exc}")
        return 1
    print("Instagram account session verified.")
    print(f"Username: @{result['username']}")
    print(f"User ID: {result['user_id'] or 'not supplied'}")
    print(f"Private session saved: {result['session_file']}")
    print("Keep this file private. Do not upload or share it.")
    print("Note: this verifies a private API session; it does not enable webhook delivery or View Once archiving.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
