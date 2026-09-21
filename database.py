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

        await db.execute("""
            CREATE TABLE IF NOT EXISTS satpam_settings (
                chat_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 0,
                mode TEXT DEFAULT 'admin_only',
                updated_at TEXT NOT NULL
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS satpam_whitelist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                domain TEXT NOT NULL,
                UNIQUE(chat_id, domain)
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

async def get_all_tracked_chats() -> List[int]:
    """Mendapatkan semua chat_id unik yang pernah tersimpan di database."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT DISTINCT chat_id FROM messages") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

# --- Satpam Grup Database Helpers ---

async def get_satpam_settings(chat_id: int) -> Dict[str, Any]:
    """Mendapatkan konfigurasi Satpam Grup."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT enabled, mode FROM satpam_settings WHERE chat_id = ?
        """, (chat_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {"enabled": bool(row["enabled"]), "mode": row["mode"]}
            return {"enabled": False, "mode": "admin_only"}

async def set_satpam_settings(chat_id: int, enabled: bool, mode: str = "admin_only") -> None:
    """Menyetel status dan mode Satpam Grup."""
    now_iso = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO satpam_settings (chat_id, enabled, mode, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                enabled = excluded.enabled,
                mode = excluded.mode,
                updated_at = excluded.updated_at
        """, (chat_id, 1 if enabled else 0, mode, now_iso))
        await db.commit()

async def add_whitelist_domain(chat_id: int, domain: str) -> bool:
    """Menambahkan domain ke whitelist Satpam Grup."""
    clean_domain = domain.strip().lower()
    clean_domain = clean_domain.replace("https://", "").replace("http://", "").split("/")[0]
    if not clean_domain:
        return False
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            await db.execute("""
                INSERT INTO satpam_whitelist (chat_id, domain) VALUES (?, ?)
            """, (chat_id, clean_domain))
            await db.commit()
            return True
        except Exception:
            return False

async def remove_whitelist_domain(chat_id: int, domain: str) -> bool:
    """Menghapus domain dari whitelist Satpam Grup."""
    clean_domain = domain.strip().lower()
    clean_domain = clean_domain.replace("https://", "").replace("http://", "").split("/")[0]
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            DELETE FROM satpam_whitelist WHERE chat_id = ? AND domain = ?
        """, (chat_id, clean_domain))
        await db.commit()
        return cursor.rowcount > 0

async def get_whitelist_domains(chat_id: int) -> List[str]:
    """Mengambil daftar domain whitelist untuk suatu grup."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("""
            SELECT domain FROM satpam_whitelist WHERE chat_id = ? ORDER BY domain ASC
        """, (chat_id,)) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

