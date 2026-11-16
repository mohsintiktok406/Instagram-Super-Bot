import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.media import (
    _extension_from_mime,
    download_attachment,
    is_view_once,
    normalize_media_type,
)


def test_view_mode_once_marker():
    assert is_view_once({"message": {"view_mode": "once"}})


def test_ephemeral_boolean_marker():
    assert is_view_once({"message": {"ephemeral": True}})


def test_raven_attachment_marker():
    assert is_view_once({"type": "raven_media", "payload": {}})


def test_payload_view_once_marker():
    assert is_view_once({"type": "image", "payload": {"is_view_once": True}})


def test_ordinary_image_is_not_view_once():
    assert not is_view_once({"type": "image", "payload": {"url": "https://cdn.example/image.jpg"}})


def test_plain_text_is_not_view_once():
    assert not is_view_once({"message": {"mid": "m1", "text": "hello"}})


def test_media_type_allowlist():
    assert normalize_media_type("image") == "image"
    assert normalize_media_type("video") == "video"
    assert normalize_media_type("audio") == "audio"
    assert normalize_media_type("file") is None
    assert normalize_media_type("sticker") is None


def test_extension_requires_supported_mime():
    assert _extension_from_mime("image/jpeg; charset=binary") == ".jpg"
    with pytest.raises(ValueError, match="MIME type"):
        _extension_from_mime(None)


def test_rejects_non_http_attachment_url(tmp_path):
    with pytest.raises(ValueError, match="http or https"):
        asyncio.run(download_attachment("file:///etc/passwd", tmp_path / "file"))


def test_attachment_event_multi_item_idempotency_and_update(tmp_path, monkeypatch):
    from backend import inbox

    monkeypatch.setattr(inbox, "DB_PATH", tmp_path / "test.sqlite3")
    assert inbox.save_attachment_event("thread", "sender", "mid-1", "image", "pending", attachment_index=0)
    assert inbox.save_attachment_event("thread", "sender", "mid-1", "video", "pending", attachment_index=1)
    assert not inbox.save_attachment_event("thread", "sender", "mid-1", "image", "pending", attachment_index=0)
    inbox.update_attachment_event("mid-1:1", status="expired", reason="test failure")
    with inbox._connect() as db:
        rows = db.execute("SELECT attachment_index,status,reason FROM attachment_events ORDER BY attachment_index").fetchall()
    assert [(r["attachment_index"], r["status"]) for r in rows] == [(0, "pending"), (1, "expired")]
    assert rows[1]["reason"] == "test failure"


def test_migrates_legacy_message_id_unique_table(tmp_path, monkeypatch):
    import sqlite3
    from backend import inbox

    db_path = tmp_path / "legacy.sqlite3"
    monkeypatch.setattr(inbox, "DB_PATH", db_path)
    with sqlite3.connect(db_path) as db:
        db.execute("""CREATE TABLE attachment_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, thread_id TEXT NOT NULL, sender_id TEXT NOT NULL,
            message_id TEXT NOT NULL UNIQUE, media_type TEXT NOT NULL, file_path TEXT,
            size_bytes INTEGER NOT NULL DEFAULT 0, captured_at TEXT,
            status TEXT NOT NULL CHECK(status IN ('captured','expired','unsupported')),
            reason TEXT, created_at TEXT NOT NULL)""")
        db.execute("INSERT INTO attachment_events(thread_id,sender_id,message_id,media_type,status,created_at) VALUES('t','s','m','image','unsupported',?)", (datetime.now(timezone.utc).isoformat(),))
    inbox.init_db()
    assert inbox.save_attachment_event("t", "s", "m", "video", "pending", attachment_index=1)


def test_pending_rows_are_included_in_retention_purge(tmp_path, monkeypatch):
    from backend import inbox

    monkeypatch.setattr(inbox, "DB_PATH", tmp_path / "purge.sqlite3")
    inbox.save_attachment_event("t", "s", "m", "image", "pending", attachment_index=0)
    old = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    with inbox._connect() as db:
        db.execute("UPDATE attachment_events SET created_at=?", (old,))
    assert inbox.purge_old_attachment_files(1) == 1
    with inbox._connect() as db:
        row = db.execute("SELECT status,reason FROM attachment_events").fetchone()
    assert row["status"] == "expired"
    assert row["reason"] == "stale_pending_expired"


def test_safe_segment_is_portable_and_bounded():
    from backend.app import _safe_segment

    assert _safe_segment("../../C:\\Windows\\System32") == "c__windows_system32"
    assert len(_safe_segment("A" * 100)) == 60
    assert _safe_segment("!!!") == "unknown-thread"


def test_redacted_probe_never_exposes_attachment_url_or_text():
    from backend.app import _redacted_probe

    secret_url = "https://cdn.example/private?signature=secret"
    result = _redacted_probe({"entry": [{"messaging": [{"message": {
        "text": "private message",
        "attachments": [{"type": "image", "payload": {"url": secret_url}}],
    }}]}]})
    rendered = str(result)
    assert secret_url not in rendered
    assert "private message" not in rendered
    assert "url_present" in rendered


def _run_attachment_pipeline(tmp_path, monkeypatch, first_attachment):
    from backend import app as app_module
    from backend import inbox

    monkeypatch.setattr(inbox, "DB_PATH", tmp_path / "pipeline.sqlite3")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app_module.settings, "media_max_bytes", 1024)
    downloaded = []

    async def fake_download(url, destination, *, max_bytes):
        downloaded.append(url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        path = destination.with_suffix(".jpg")
        path.write_bytes(b"ok")
        return path, 2

    monkeypatch.setattr(app_module, "download_attachment", fake_download)
    event = {
        "sender": {"id": "sender"},
        "recipient": {"id": "recipient"},
        "message": {"mid": "multi-1", "attachments": [
            first_attachment,
            {"type": "image", "payload": {"url": "https://cdn.example/ordinary.jpg"}},
        ]},
    }
    asyncio.run(app_module._process_attachment_event(event))
    with inbox._connect() as db:
        rows = db.execute("SELECT attachment_index,is_view_once,status,reason,file_path FROM attachment_events ORDER BY attachment_index").fetchall()
    return downloaded, rows


def test_view_once_with_url_is_metadata_only_and_later_ordinary_is_captured(tmp_path, monkeypatch):
    downloaded, rows = _run_attachment_pipeline(tmp_path, monkeypatch, {
        "type": "image", "payload": {"url": "https://cdn.example/view-once.jpg", "is_view_once": True}
    })
    assert downloaded == ["https://cdn.example/ordinary.jpg"]
    assert rows[0]["is_view_once"] == 1
    assert rows[0]["status"] == "unsupported"
    assert rows[0]["file_path"] is None
    assert rows[1]["is_view_once"] == 0
    assert rows[1]["status"] == "captured"


def test_view_once_without_url_has_specific_reason_and_later_ordinary_is_captured(tmp_path, monkeypatch):
    downloaded, rows = _run_attachment_pipeline(tmp_path, monkeypatch, {
        "type": "image", "payload": {"is_view_once": True}
    })
    assert downloaded == ["https://cdn.example/ordinary.jpg"]
    assert rows[0]["is_view_once"] == 1
    assert rows[0]["status"] == "unsupported"
    assert rows[0]["reason"] == "view_once_no_url"
    assert rows[0]["file_path"] is None
    assert rows[1]["status"] == "captured"


def test_ordinary_download_failure_is_expired_with_original_error(tmp_path, monkeypatch):
    from backend import app as app_module
    from backend import inbox

    monkeypatch.setattr(inbox, "DB_PATH", tmp_path / "failure.sqlite3")
    monkeypatch.chdir(tmp_path)

    async def failed_download(url, destination, *, max_bytes):
        raise RuntimeError("cdn timeout")

    monkeypatch.setattr(app_module, "download_attachment", failed_download)
    event = {"sender": {"id": "s"}, "recipient": {"id": "t"},
             "message": {"mid": "fail-1", "attachments": [
                 {"type": "image", "payload": {"url": "https://cdn.example/file.jpg"}}
             ]}}
    asyncio.run(app_module._process_attachment_event(event))
    with inbox._connect() as db:
        row = db.execute("SELECT status,reason,is_view_once FROM attachment_events").fetchone()
    assert row["status"] == "expired"
    assert row["reason"] == "cdn timeout"
    assert row["is_view_once"] == 0


def test_meta_unsupported_without_attachments_is_recorded_and_notified(tmp_path, monkeypatch):
    from backend import app as app_module
    from backend import inbox

    monkeypatch.setattr(inbox, "DB_PATH", tmp_path / "unsupported.sqlite3")
    notifications = []
    monkeypatch.setattr(app_module, "notify", lambda *args, **kwargs: notifications.append((args, kwargs)))
    event = {
        "sender": {"id": "sender"},
        "recipient": {"id": "recipient"},
        "message": {"mid": "unsupported-1", "is_unsupported": True},
    }
    asyncio.run(app_module._process_attachment_event(event))
    with inbox._connect() as db:
        row = db.execute("SELECT media_type,status,reason,file_path,is_view_once FROM attachment_events").fetchone()
    assert row["media_type"] == "unsupported_media"
    assert row["status"] == "unsupported"
    assert row["reason"] == "meta_unsupported_no_payload"
    assert row["file_path"] is None
    assert row["is_view_once"] == 0  # is_unsupported is not a View Once-specific marker
    assert len(notifications) == 1
    assert notifications[0][0][4] == "unsupported"


def test_meta_unsupported_with_supported_attachment_url_uses_generic_download(tmp_path, monkeypatch):
    from backend import app as app_module
    from backend import inbox

    monkeypatch.setattr(inbox, "DB_PATH", tmp_path / "unsupported-with-url.sqlite3")
    monkeypatch.chdir(tmp_path)
    downloaded = []
    notifications = []

    async def fake_download(url, destination, *, max_bytes):
        downloaded.append(url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        path = destination.with_suffix(".jpg")
        path.write_bytes(b"ok")
        return path, 2

    monkeypatch.setattr(app_module, "download_attachment", fake_download)
    monkeypatch.setattr(app_module, "notify", lambda *args, **kwargs: notifications.append((args, kwargs)))
    event = {
        "sender": {"id": "sender"},
        "recipient": {"id": "recipient"},
        "message": {"mid": "unsupported-url-1", "is_unsupported": True, "attachments": [
            {"type": "image", "payload": {"url": "https://cdn.example/ordinary.jpg"}}
        ]},
    }
    asyncio.run(app_module._process_attachment_event(event))
    with inbox._connect() as db:
        row = db.execute("SELECT status,is_view_once,file_path FROM attachment_events").fetchone()
    assert downloaded == ["https://cdn.example/ordinary.jpg"]
    assert row["status"] == "captured"
    assert row["is_view_once"] == 0
    assert row["file_path"]
    assert notifications[-1][0][4] == "captured"
