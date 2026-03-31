import time
from pathlib import Path

from .dbconn import get_db
from .enrichments import ENRICHMENTS
from .note import NoteType, index_file


VAULT_DIR = Path('/Users/nubrajarial/Library/Mobile Documents/iCloud~md~obsidian/Documents/helterskelter/')


def add_files_to_table():
    conn = get_db()
    for file_path in VAULT_DIR.glob('*.md'):
        last_modified = int(file_path.stat().st_mtime)
        conn.execute('''
            INSERT INTO notes (title, last_modified, seen_at, type)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(title) DO UPDATE SET
                last_modified = excluded.last_modified,
                seen_at       = excluded.seen_at,
                type          = excluded.type
        ''', (file_path.stem, last_modified, int(time.time()), NoteType.REALIZED))
    conn.commit()


def main():
    add_files_to_table()
    conn = get_db()
    cursor = conn.execute(
        'SELECT id FROM notes WHERE type = ? AND (indexed_at IS NULL OR indexed_at < last_modified)',
        (NoteType.REALIZED,)
    )
    for (note_id,) in cursor.fetchall():
        index_file(note_id, ENRICHMENTS)
    print("Done")


if __name__ == "__main__":
    main()
