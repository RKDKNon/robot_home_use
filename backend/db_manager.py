import sqlite3
import os
import threading
import time
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "robot_local.db")

# Module-level connection reused across operations (thread-safe for SQLite)
_conn = None
_conn_lock = threading.Lock()

def get_connection():
    """Returns a reusable connection to the SQLite database.
    Uses WAL mode for better concurrent read/write performance."""
    global _conn
    with _conn_lock:
        if _conn is None:
            _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA busy_timeout=5000")
    return _conn

def _execute_with_retry(func, max_retries=3):
    """Retry wrapper for database operations.
    Handles 'database is locked' errors with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return func()
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < max_retries - 1:
                wait = 0.1 * (2 ** attempt)  # 0.1s, 0.2s, 0.4s
                print(f"⚠️ DB locked, retrying in {wait}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue
            raise
        except Exception as e:
            print(f"❌ DB error: {e}")
            raise

def init_db():
    """Initializes the database and creates required tables if they don't exist."""
    def _do_init():
        conn = get_connection()
        cursor = conn.cursor()

        # Create reminders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TEXT NOT NULL,          -- Format: "HH:MM" (e.g., "20:00")
                medicine_name TEXT NOT NULL,  -- e.g., "Paracetamol"
                dosage TEXT,                 -- e.g., "1 tab"
                repeat TEXT DEFAULT 'daily',  -- 'daily', 'weekly', 'none'
                is_acknowledged INTEGER DEFAULT 0, -- 0 = active/pending, 1 = acknowledged
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create vitals table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vitals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                type TEXT NOT NULL,          -- 'blood_pressure', 'heart_rate', 'spo2', 'temperature'
                value TEXT NOT NULL,         -- e.g. "120/80" (BP) or "72" (HR) or "98" (SpO2)
                unit TEXT,                   -- e.g. "mmHg", "bpm", "%", "C"
                status TEXT DEFAULT 'normal'  -- 'normal', 'high', 'low', 'critical'
            )
        """)

        # Create conversation history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,          -- 'user' or 'model'
                content TEXT NOT NULL,        -- text content
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        print(f"Database initialized at {DB_PATH}")

    _execute_with_retry(_do_init)

def add_reminder(time_str: str, medicine_name: str, dosage: str, repeat: str = 'daily') -> int:
    """Adds a new medication reminder."""
    def _do():
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO reminders (time, medicine_name, dosage, repeat)
            VALUES (?, ?, ?, ?)
        """, (time_str, medicine_name, dosage, repeat))
        conn.commit()
        return cursor.lastrowid

    return _execute_with_retry(_do)

def get_active_reminders():
    """Retrieves all pending/unacknowledged reminders."""
    def _do():
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM reminders WHERE is_acknowledged = 0
            ORDER BY time ASC
        """)
        return [dict(row) for row in cursor.fetchall()]

    return _execute_with_retry(_do)

def acknowledge_reminder(reminder_id: int):
    """Marks a reminder as acknowledged."""
    def _do():
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE reminders SET is_acknowledged = 1 WHERE id = ?
        """, (reminder_id,))
        conn.commit()

    _execute_with_retry(_do)

def add_vital(vital_type: str, value: str, unit: str, status: str = 'normal') -> int:
    """Inserts a new vital sign measurement."""
    def _do():
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO vitals (type, value, unit, status)
            VALUES (?, ?, ?, ?)
        """, (vital_type, value, unit, status))
        conn.commit()
        return cursor.lastrowid

    return _execute_with_retry(_do)

def get_latest_vitals(limit: int = 5):
    """Retrieves the most recent vital sign readings."""
    def _do():
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM vitals
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

    return _execute_with_retry(_do)

# --- Conversation History ---

def add_conversation(role: str, content: str):
    """Stores a conversation turn (user or model)."""
    def _do():
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO conversation_history (role, content)
            VALUES (?, ?)
        """, (role, content))
        conn.commit()

    _execute_with_retry(_do)

def get_recent_conversation(limit: int = 50):
    """Retrieves the most recent conversation turns for context restore."""
    def _do():
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT role, content FROM conversation_history
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        # Reverse to chronological order
        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

    return _execute_with_retry(_do)

def clear_conversation():
    """Deletes all conversation history."""
    def _do():
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conversation_history")
        conn.commit()
        print("🗑️ Conversation history cleared.")

    _execute_with_retry(_do)

if __name__ == "__main__":
    init_db()
    print("Testing db...")
    rid = add_reminder("20:00", "Paracetamol", "500mg (1 tab)", "daily")
    print(f"Added reminder id: {rid}")
    print("Active reminders:", get_active_reminders())
    vid = add_vital("blood_pressure", "120/80", "mmHg", "normal")
    print(f"Added vital id: {vid}")
    print("Latest vitals:", get_latest_vitals(1))
