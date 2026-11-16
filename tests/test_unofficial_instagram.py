from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.unofficial_instagram import connect_own_account, InstagramConnectionError


class FakeClient:
    def __init__(self):
        self.loaded = None
        self.logged_in = None
        self.dumped = None
        self.user_id = "12345"

    def load_settings(self, path):
        self.loaded = path

    def login(self, username, password):
        self.logged_in = (username, password)

    def account_info(self):
        return SimpleNamespace(username="my_own_account", pk=12345)

    def dump_settings(self, path):
        self.dumped = path
        Path(path).write_text("fake-session")


def test_connect_own_account_saves_session_with_restricted_permissions(tmp_path):
    client = FakeClient()
    session = tmp_path / "data" / "session.json"
    result = connect_own_account("my_own_account", "not-a-real-password", session, lambda: client)
    assert result["connected"] is True
    assert result["username"] == "my_own_account"
    assert result["user_id"] == "12345"
    assert session.exists()
    assert client.logged_in == ("my_own_account", "not-a-real-password")
    assert session.stat().st_mode & 0o077 == 0


def test_existing_session_is_loaded_before_login(tmp_path):
    session = tmp_path / "session.json"
    session.write_text("old")
    client = FakeClient()
    connect_own_account("account", "password", session, lambda: client)
    assert client.loaded == str(session)


def test_missing_credentials_rejected():
    with pytest.raises(ValueError):
        connect_own_account("", "password", "unused", lambda: FakeClient())


def test_login_errors_are_sanitized(tmp_path):
    class BrokenClient(FakeClient):
        def login(self, username, password):
            raise RuntimeError("sensitive cookie/password response")
    with pytest.raises(InstagramConnectionError) as error:
        connect_own_account("account", "secret", tmp_path / "session.json", BrokenClient)
    assert "sensitive cookie" not in str(error.value)
    assert "secret" not in str(error.value)
