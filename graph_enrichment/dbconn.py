from pathlib import Path
import sqlite3

DB_PATH = Path(__file__).parent / 'notes.db'

_conn = None

def get_db():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                title         TEXT NOT NULL UNIQUE,
                last_modified INTEGER,
                indexed_at    INTEGER,
                embedded_at   INTEGER,
                seen_at       INTEGER,
                type          INTEGER NOT NULL DEFAULT 0
            )
        """)
        try:
            _conn.execute("ALTER TABLE notes ADD COLUMN embedded_at INTEGER")
        except sqlite3.OperationalError:
            pass
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
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS bib_coupling (
                note_a_id  INTEGER NOT NULL,
                note_b_id  INTEGER NOT NULL,
                score      INTEGER NOT NULL,
                PRIMARY KEY (note_a_id, note_b_id)
            )
        """)
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS cocitation (
                note_a_id  INTEGER NOT NULL,
                note_b_id  INTEGER NOT NULL,
                score      INTEGER NOT NULL,
                PRIMARY KEY (note_a_id, note_b_id)
            )
        """)
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS clusters (
                note_id     INTEGER NOT NULL,
                cluster_id  INTEGER NOT NULL,
                algorithm   TEXT NOT NULL,
                PRIMARY KEY (note_id, algorithm)
            )
        """)
        _conn.commit()
    return _conn
