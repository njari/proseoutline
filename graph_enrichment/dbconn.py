from pathlib import Path
import sqlite3

DB_PATH = Path(__file__).parent / 'notes.db'

_conn = None

def get_db():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH)
        _conn.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY AUTOINCREMENT, note_title TEXT NOT NULL, path TEXT NOT NULL UNIQUE, last_modified INTEGER NOT NULL, indexed_at INTEGER)")
        _conn.execute("CREATE TABLE IF NOT EXISTS unrealized_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL UNIQUE)")
        _conn.execute("CREATE TABLE IF NOT EXISTS links (from_id INTEGER NOT NULL, to_id INTEGER NOT NULL, realized INTEGER NOT NULL, PRIMARY KEY (from_id, to_id, realized))")
        _conn.commit()
    return _conn

