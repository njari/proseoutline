import re
import time
from enum import IntEnum
from pathlib import Path

import frontmatter

from .dbconn import get_db

VAULT_DIR = Path('/Users/nubrajarial/Library/Mobile Documents/iCloud~md~obsidian/Documents/helterskelter/')

WIKILINK_RE = re.compile(r'\[\[([^\]]+)\]\]')


class NoteType(IntEnum):
    REALIZED = 0
    UNREALIZED = 1


class Note:
    def __init__(self, note_id):
        self._conn = get_db()
        self._post = None
        row = self._conn.execute(
            'SELECT id, title, last_modified, indexed_at, type FROM notes WHERE id = ?', (note_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f'No note found with id {note_id}')
        self.id, self.title, self.last_modified, self.indexed_at = row[0], row[1], row[2], row[3]
        self.type = NoteType(row[4])
        self._path = VAULT_DIR / (self.title + '.md') if self.type == NoteType.REALIZED else None

    def _load(self):
        if self._post is None:
            self._post = frontmatter.load(self._path)

    @property
    def frontmatter(self):
        if self.type == NoteType.UNREALIZED:
            raise AttributeError('Unrealized notes have no frontmatter')
        self._load()
        return dict(self._post.metadata)

    @property
    def content(self):
        if self.type == NoteType.UNREALIZED:
            raise AttributeError('Unrealized notes have no content')
        self._load()
        return self._post.content

    @property
    def links(self):
        rows = self._conn.execute('''
            SELECT n.id FROM notes n
            JOIN links l ON l.to_id = n.id
            WHERE l.from_id = ?
        ''', (self.id,)).fetchall()
        return [Note(row[0]) for row in rows]

    @property
    def backlinks(self):
        rows = self._conn.execute('''
            SELECT n.id FROM notes n
            JOIN links l ON l.from_id = n.id
            WHERE l.to_id = ?
        ''', (self.id,)).fetchall()
        return [Note(row[0]) for row in rows]

    def __repr__(self):
        return f'<Note {self.id} [{self.type.name}]: {self.title}>'


def extract_wikilinks(text):
    matches = WIKILINK_RE.findall(text)
    return {m.split('|')[0].split('#')[0].strip() for m in matches}


def index_file(note_id, enrichments):
    note = Note(note_id)
    if not note._path.exists():
        return
    try:
        note._load()
    except Exception:
        return
    for strategy in enrichments:
        strategy.enrich(note)
    conn = get_db()
    conn.execute('UPDATE notes SET indexed_at = ? WHERE id = ?', (int(time.time()), note_id))
    conn.commit()
