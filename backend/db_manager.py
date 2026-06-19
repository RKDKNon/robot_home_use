import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "robot_local.db")

def get_connection():
    """Returns a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database and creates required tables if they don't exist."""
    with get_connection() as conn:
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
        
        conn.commit()
    print(f"Database initialized at {DB_PATH}")

def add_reminder(time: str, medicine_name: str, dosage: str, repeat: str = 'daily') -> int:
    """Adds a new medication reminder."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO reminders (time, medicine_name, dosage, repeat)
            VALUES (?, ?, ?, ?)
        """, (time, medicine_name, dosage, repeat))
        conn.commit()
        return cursor.lastrowid

def get_active_reminders():
    """Retrieves all pending/unacknowledged reminders."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM reminders WHERE is_acknowledged = 0
            ORDER BY time ASC
        """)
        return [dict(row) for row in cursor.fetchall()]

def acknowledge_reminder(reminder_id: int):
    """Marks a reminder as acknowledged."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE reminders SET is_acknowledged = 1 WHERE id = ?
        """, (reminder_id,))
        conn.commit()

def add_vital(vital_type: str, value: str, unit: str, status: str = 'normal') -> int:
    """Inserts a new vital sign measurement."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO vitals (type, value, unit, status)
            VALUES (?, ?, ?, ?)
        """, (vital_type, value, unit, status))
        conn.commit()
        return cursor.lastrowid

def get_latest_vitals(limit: int = 5):
    """Retrieves the most recent vital sign readings."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM vitals
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

if __name__ == "__main__":
    init_db()
    print("Testing db...")
    rid = add_reminder("20:00", "Paracetamol", "500mg (1 tab)", "daily")
    print(f"Added reminder id: {rid}")
    print("Active reminders:", get_active_reminders())
    vid = add_vital("blood_pressure", "120/80", "mmHg", "normal")
    print(f"Added vital id: {vid}")
    print("Latest vitals:", get_latest_vitals(1))
