from pathlib import Path
import sqlite3

DB_PATH = Path(__file__).parent / 'notes.db'

_conn = None

def get_db():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH)
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                title         TEXT NOT NULL UNIQUE,
                last_modified INTEGER,
                indexed_at    INTEGER,
                seen_at       INTEGER,
                type          INTEGER NOT NULL DEFAULT 0
            )
        """)
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS links (
                from_id  INTEGER NOT NULL,
                to_id    INTEGER NOT NULL,
                PRIMARY KEY (from_id, to_id)
            )
        """)
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                tag  TEXT NOT NULL UNIQUE
            )
        """)
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS tag_links (
                note_id  INTEGER NOT NULL,
                tag_id   INTEGER NOT NULL,
                PRIMARY KEY (note_id, tag_id)
            )
        """)
        _conn.commit()
    return _conn
