import aiosqlite
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from config import DATABASE_PATH

logger = logging.getLogger(__name__)

async def init_db() -> None:
    """Inisialisasi tabel SQLite jika belum ada."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                user_id INTEGER,
                username TEXT,
                full_name TEXT,
                text TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
        """)
        
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_chat_time 
            ON messages (chat_id, timestamp);
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_metadata (
                chat_id INTEGER PRIMARY KEY,
                last_summary_time TEXT,
                schedule_hours INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL
            );
        """)
        
        await db.commit()
        logger.info("Database initialized successfully at %s", DATABASE_PATH)

async def save_message(
    chat_id: int,
    message_id: int,
    user_id: Optional[int],
    username: Optional[str],
    full_name: Optional[str],
    text: str,
    timestamp: datetime
) -> None:
    """Menyimpan pesan chat baru ke database."""
    if not text or not text.strip():
        return

    ts_iso = timestamp.astimezone(timezone.utc).isoformat()
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO messages (chat_id, message_id, user_id, username, full_name, text, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (chat_id, message_id, user_id, username, full_name, text.strip(), ts_iso))
        await db.commit()

async def get_messages_since(
    chat_id: int,
    since_timestamp: datetime
) -> List[Dict[str, Any]]:
    """Mengambil semua pesan chat sejak timestamp tertentu, diurutkan kronologis."""
    since_iso = since_timestamp.astimezone(timezone.utc).isoformat()
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT message_id, user_id, username, full_name, text, timestamp
            FROM messages
            WHERE chat_id = ? AND timestamp >= ?
            ORDER BY timestamp ASC
        """, (chat_id, since_iso)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_last_summary_time(chat_id: int) -> Optional[datetime]:
    """Mendapatkan waktu terakhir ringkasan dibuat untuk suatu grup."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT last_summary_time FROM chat_metadata WHERE chat_id = ?
        """, (chat_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row["last_summary_time"]:
                return datetime.fromisoformat(row["last_summary_time"])
            return None

async def update_last_summary_time(chat_id: int, summary_time: datetime) -> None:
    """Memperbarui timestamp ringkasan terakhir untuk grup."""
    ts_iso = summary_time.astimezone(timezone.utc).isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO chat_metadata (chat_id, last_summary_time, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                last_summary_time = excluded.last_summary_time,
                updated_at = excluded.updated_at
        """, (chat_id, ts_iso, now_iso))
        await db.commit()

async def set_chat_schedule(chat_id: int, schedule_hours: int) -> None:
    """Menyetel interval ringkasan otomatis (0 = matikan)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO chat_metadata (chat_id, schedule_hours, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                schedule_hours = excluded.schedule_hours,
                updated_at = excluded.updated_at
        """, (chat_id, schedule_hours, now_iso))
        await db.commit()

async def get_all_active_schedules() -> List[Dict[str, Any]]:
    """Mendapatkan semua chat yang mengaktifkan ringkasan terjadwal."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT chat_id, schedule_hours, last_summary_time
            FROM chat_metadata
            WHERE schedule_hours > 0
        """) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def cleanup_old_messages(days: int = 30) -> int:
    """Menghapus pesan lama di atas X hari agar database tetap efisien dan hemat storage."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            DELETE FROM messages WHERE timestamp < ?
        """, (cutoff,))
        deleted = cursor.rowcount
        await db.commit()
        return deleted
