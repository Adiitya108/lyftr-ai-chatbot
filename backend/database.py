"""Database layer using aiosqlite."""

import json
import aiosqlite
import os
from datetime import datetime, timezone
from typing import List, Optional
from models import MessageRecord

# Parse DATABASE_URL like sqlite:////data/app.db → /data/app.db
_raw_url = os.getenv("DATABASE_URL", "sqlite:///./app.db")
if _raw_url.startswith("sqlite:///"):
    DB_PATH = _raw_url[len("sqlite:///"):]
    if DB_PATH.startswith("//"):
        DB_PATH = "/" + DB_PATH.lstrip("/")
else:
    DB_PATH = "./app.db"


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL
);
"""


async def init_db() -> None:
    """Create tables if they don't exist."""
    global DB_PATH
    parent = os.path.dirname(DB_PATH)
    if parent and not os.path.exists(parent):
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError:
            DB_PATH = "./app.db"

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(CREATE_TABLE_SQL)
            await db.commit()
    except Exception:
        DB_PATH = "./app.db"
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(CREATE_TABLE_SQL)
            await db.commit()


async def save_message(
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[dict] = None,
) -> None:
    """Persist a single message to the database."""
    created_at = datetime.now(timezone.utc).isoformat()
    metadata_str = json.dumps(metadata) if metadata is not None else None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (session_id, role, content, metadata, created_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, metadata_str, created_at),
        )
        await db.commit()


async def get_session_messages(session_id: str) -> Optional[List[MessageRecord]]:
    """
    Return all messages for a session, ordered by id.
    Returns None if the session does not exist at all.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT role, content, metadata FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        return None  # session not found

    messages: List[MessageRecord] = []
    for row in rows:
        meta = json.loads(row["metadata"]) if row["metadata"] else None
        messages.append(MessageRecord(role=row["role"], content=row["content"], metadata=meta))

    return messages


async def session_exists(session_id: str) -> bool:
    """Check whether a session has any messages stored."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM messages WHERE session_id = ? LIMIT 1",
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
    return row is not None


async def get_history_messages(session_id: str) -> List[dict]:
    """Return prior conversation as list of {role, content} dicts for LLM context."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in rows]
