"""SQLite inbox and inbound attachment event store."""
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(os.getenv("DATABASE_PATH", "data/instagram_super_bot.sqlite3"))
ATTACHMENT_STATUSES = {"pending", "captured", "expired", "unsupported"}


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id TEXT NOT NULL,
            direction TEXT NOT NULL CHECK(direction IN ('inbound','outbound')),
            message_text TEXT NOT NULL,
            event_type TEXT NOT NULL DEFAULT 'dm',
            platform_message_id TEXT UNIQUE,
            created_at TEXT NOT NULL
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id, id)")

        existing = db.execute("PRAGMA table_info(attachment_events)").fetchall()
        if not existing:
            db.execute(_attachment_table_sql("attachment_events"))
        else:
            columns = {row["name"] for row in existing}
            sql_row = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='attachment_events'").fetchone()
            table_sql = (sql_row["sql"] or "") if sql_row else ""
            needs_migration = ("attachment_index" not in columns or "is_view_once" not in columns or "pending" not in table_sql)
            if needs_migration:
                db.execute(_attachment_table_sql("attachment_events_new"))
                index_expr = "attachment_index" if "attachment_index" in columns else "0"
                db.execute(f"""INSERT OR IGNORE INTO attachment_events_new
                    (id,thread_id,sender_id,message_id,attachment_index,is_view_once,media_type,file_path,size_bytes,
                     captured_at,status,reason,created_at)
                    SELECT id,thread_id,sender_id,message_id,{index_expr},0,media_type,file_path,size_bytes,
                           captured_at,
                           CASE WHEN status IN ('captured','expired','unsupported','pending') THEN status ELSE 'unsupported' END,
                           reason,created_at FROM attachment_events""")
                db.execute("DROP TABLE attachment_events")
                db.execute("ALTER TABLE attachment_events_new RENAME TO attachment_events")
        db.execute("CREATE INDEX IF NOT EXISTS idx_attachment_retention ON attachment_events(status, created_at)")


def _attachment_table_sql(name: str) -> str:
    return f"""CREATE TABLE {name} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        thread_id TEXT NOT NULL,
        sender_id TEXT NOT NULL,
        message_id TEXT NOT NULL,
        attachment_index INTEGER NOT NULL DEFAULT 0,
        is_view_once INTEGER NOT NULL DEFAULT 0,
        media_type TEXT NOT NULL,
        file_path TEXT,
        size_bytes INTEGER NOT NULL DEFAULT 0,
        captured_at TEXT,
        status TEXT NOT NULL CHECK(status IN ('pending','captured','expired','unsupported')),
        reason TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(message_id, attachment_index)
    )"""


def save_message(sender_id: str, direction: str, message_text: str,
                 event_type: str = "dm", platform_message_id: str | None = None):
    if direction not in {"inbound", "outbound"}:
        raise ValueError("direction must be inbound or outbound")
    init_db()
    with _connect() as db:
        db.execute("""INSERT OR IGNORE INTO messages
            (sender_id,direction,message_text,event_type,platform_message_id,created_at)
            VALUES (?,?,?,?,?,?)""",
            (sender_id, direction, message_text, event_type, platform_message_id,
             datetime.now(timezone.utc).isoformat()))


def attachment_event_key(message_id: str, attachment_index: int) -> str:
    return f"{message_id}:{attachment_index}"


def save_attachment_event(thread_id: str, sender_id: str, message_id: str,
                          media_type: str, status: str, reason: str | None = None,
                          file_path: str | None = None, size_bytes: int = 0,
                          attachment_index: int = 0, is_view_once: bool = False) -> bool:
    """Insert one attachment idempotently by (message_id, attachment_index)."""
    if status not in ATTACHMENT_STATUSES:
        raise ValueError("invalid attachment status")
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as db:
        cur = db.execute("""INSERT OR IGNORE INTO attachment_events
            (thread_id,sender_id,message_id,attachment_index,is_view_once,media_type,file_path,size_bytes,captured_at,status,reason,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (thread_id, sender_id, message_id, attachment_index, int(is_view_once), media_type, file_path, size_bytes,
             now if status == "captured" else None, status, reason, now))
        return cur.rowcount == 1


def update_attachment_event(event_key: str, *, status: str, file_path: str | None = None,
                            size_bytes: int = 0, reason: str | None = None) -> None:
    if status not in ATTACHMENT_STATUSES:
        raise ValueError("invalid attachment status")
    message_id, separator, index_text = event_key.rpartition(":")
    if not separator or not index_text.isdigit():
        raise ValueError("event key must be '<message_id>:<attachment_index>'")
    init_db()
    with _connect() as db:
        db.execute("""UPDATE attachment_events
            SET status=?, file_path=?, size_bytes=?, captured_at=?, reason=?
            WHERE message_id=? AND attachment_index=?""",
            (status, file_path, size_bytes,
             datetime.now(timezone.utc).isoformat() if status == "captured" else None,
             reason, message_id, int(index_text)))


def recent_messages(sender_id: str, limit: int = 20) -> list[dict]:
    init_db()
    with _connect() as db:
        rows = db.execute("SELECT * FROM messages WHERE sender_id=? ORDER BY id DESC LIMIT ?",
                          (sender_id, max(1, min(limit, 100)))).fetchall()
    return [dict(row) for row in reversed(rows)]


def purge_old_attachment_files(retention_days: int, media_root: Path = Path("media")) -> int:
    """Purge old files and expire stale pending rows while retaining audit records."""
    if retention_days <= 0:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    removed = 0
    init_db()
    with _connect() as db:
        rows = db.execute("""SELECT id,file_path,status FROM attachment_events
            WHERE status IN ('captured','pending') AND created_at<?""", (cutoff,)).fetchall()
        for row in rows:
            if row["file_path"]:
                path = Path(row["file_path"])
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    continue
            reason = "retention_expired" if row["status"] == "captured" else "stale_pending_expired"
            db.execute("""UPDATE attachment_events SET file_path=NULL,status='expired',
                size_bytes=0,reason=? WHERE id=?""", (reason, row["id"]))
            removed += 1
    return removed
