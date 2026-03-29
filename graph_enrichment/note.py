import re
import time
from pathlib import Path

import frontmatter

from .dbconn import get_db

VAULT_DIR = Path('/Users/nubrajarial/Library/Mobile Documents/iCloud~md~obsidian/Documents/helterskelter/')


WIKILINK_RE = re.compile(r'\[\[([^\]]+)\]\]')


class Note:
    def __init__(self, note_id):
        self._conn = get_db()
        self._post = None
        row = self._conn.execute(
            'SELECT id, note_title, path, last_modified, indexed_at FROM notes WHERE id = ?', (note_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f'No note found with id {note_id}')
        self.id, self.note_title, self.last_modified, self.indexed_at = row[0], row[1], row[3], row[4]
        self._path = VAULT_DIR / row[2]

    def _load(self):
        if self._post is None:
            self._post = frontmatter.load(self._path)

    @property
    def frontmatter(self):
        self._load()
        return dict(self._post.metadata)

    @property
    def content(self):
        self._load()
        return self._post.content

    @property
    def links(self):
        rows = self._conn.execute('''
            SELECT n.id FROM notes n
            JOIN links l ON l.to_id = n.id
            WHERE l.from_id = ? AND l.realized = 1
        ''', (self.id,)).fetchall()
        return [Note(row[0]) for row in rows]

    @property
    def backlinks(self):
        rows = self._conn.execute('''
            SELECT n.id FROM notes n
            JOIN links l ON l.from_id = n.id
            WHERE l.to_id = ? AND l.realized = 1
        ''', (self.id,)).fetchall()
        return [Note(row[0]) for row in rows]

    def __repr__(self):
        return f'<Note {self.id}: {self.note_title}>'


def extract_wikilinks(text):
    matches = WIKILINK_RE.findall(text)
    return {m.split('|')[0].split('#')[0].strip() for m in matches}


def index_file(note_id, file_path):
    if not file_path.exists():
        return
    conn = get_db()
    try:
        post = frontmatter.load(file_path)
    except Exception:
        return
    print(post.metadata)

    links = extract_wikilinks(str(post.metadata))
    links |= extract_wikilinks(post.content)

    for link_title in links:
        row = conn.execute('SELECT id FROM notes WHERE note_title = ?', (link_title,)).fetchone()
        if row:
            conn.execute('INSERT OR IGNORE INTO links (from_id, to_id, realized) VALUES (?, ?, 1)', (note_id, row[0]))
        else:
            conn.execute('INSERT OR IGNORE INTO unrealized_notes (title) VALUES (?)', (link_title,))
            unrealized_id = conn.execute('SELECT id FROM unrealized_notes WHERE title = ?', (link_title,)).fetchone()[0]
            conn.execute('INSERT OR IGNORE INTO links (from_id, to_id, realized) VALUES (?, ?, 0)', (note_id, unrealized_id))

    conn.execute('UPDATE notes SET indexed_at = ? WHERE id = ?', (int(time.time()), note_id))
    conn.commit()
