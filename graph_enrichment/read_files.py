import sqlite3
from pathlib import Path

VAULT_DIR = Path('/Users/nubrajarial/Library/Mobile Documents/iCloud~md~obsidian/Documents/helterskelter/')
DB_PATH = Path(__file__).parent / 'notes.db'


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS notes (id            INTEGER PRIMARY KEY AUTOINCREMENT, note_title    TEXT NOT NULL,path          TEXT NOT NULL UNIQUE,last_modified INTEGER NOT NULL,indexed_at INTEGER )")
    conn.commit()
    return conn


def main():
    conn = get_db()
    for file_path in VAULT_DIR.rglob('*'):
        if not file_path.is_file():
            continue
        rel_path = file_path.relative_to(VAULT_DIR)
        last_modified = int(file_path.stat().st_mtime)
        conn.execute('''
            INSERT INTO notes (note_title, path, last_modified)
            VALUES (?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                note_title    = excluded.note_title,
                last_modified = excluded.last_modified
        ''', (file_path.stem, str(rel_path), last_modified))
    conn.commit()
    conn.close()
    print(f"Done. Database saved to {DB_PATH}")


if __name__ == "__main__":
    main()
