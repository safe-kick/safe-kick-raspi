import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_DIR = BASE_DIR / "database"
DB_PATH = DB_DIR / "safe_kick.db"


def get_connection():
    DB_DIR.mkdir(exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kickboard_id TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ended_at TIMESTAMP,
        status TEXT DEFAULT 'active',
        warning_count INTEGER DEFAULT 0
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sensor_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        face_score REAL,
        weight REAL,
        gas REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS warning_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        warning_type TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS face_verification_attempts (
        user_id INTEGER PRIMARY KEY,
        failed_attempts INTEGER NOT NULL DEFAULT 0,
        locked_until REAL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()
    conn.close()
