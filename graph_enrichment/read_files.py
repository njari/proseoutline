from pathlib import Path

from .dbconn import get_db
from .note import index_file



VAULT_DIR = Path('/Users/nubrajarial/Library/Mobile Documents/iCloud~md~obsidian/Documents/helterskelter/')


def add_files_to_table():
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


def main():
    add_files_to_table()
    conn = get_db()
    cursor = conn.execute('SELECT id, path FROM notes WHERE indexed_at IS NULL OR indexed_at < last_modified')
    for note_id, rel_path in cursor.fetchall():
        index_file(note_id, VAULT_DIR / rel_path)
    print(f"Done")


if __name__ == "__main__":
    main()
