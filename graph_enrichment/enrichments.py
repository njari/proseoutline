import abc

from .dbconn import get_db
from .note import Note, NoteType, extract_wikilinks


class Enrichment(abc.ABC):
    @abc.abstractmethod
    def enrich(self, note: Note) -> None: ...


class BaseEnrichment(Enrichment):
    """Wikilink extraction → `links` table."""

    def __init__(self):
        self._realized = None
        self._unrealized = None

    def _load(self):
        if self._realized is None:
            conn = get_db()
            self._realized = {r[0]: r[1] for r in conn.execute(
                'SELECT title, id FROM notes WHERE type = ?', (NoteType.REALIZED,))}
            self._unrealized = {r[0]: r[1] for r in conn.execute(
                'SELECT title, id FROM notes WHERE type = ?', (NoteType.UNREALIZED,))}

    def enrich(self, note):
        self._load()
        conn = get_db()
        links = extract_wikilinks(str(note.frontmatter)) | extract_wikilinks(note.content)
        for title in links:
            if title in self._realized:
                to_id = self._realized[title]
            elif title in self._unrealized:
                to_id = self._unrealized[title]
            else:
                conn.execute('INSERT OR IGNORE INTO notes (title, type) VALUES (?, ?)',
                             (title, NoteType.UNREALIZED))
                to_id = conn.execute('SELECT id FROM notes WHERE title = ?', (title,)).fetchone()[0]
                self._unrealized[title] = to_id
            conn.execute('INSERT OR IGNORE INTO links (from_id, to_id) VALUES (?, ?)',
                         (note.id, to_id))


class TagEnrichment(Enrichment):
    """Tag extraction → `tags` + `tag_links` tables."""

    def enrich(self, note):
        self._load()
        conn = get_db()
        note_tags = note.frontmatter.get('tags') or []
        for tag in note_tags:
            conn.execute('INSERT OR IGNORE INTO tags (tag) VALUES (?)', (tag,))
            tag_id = conn.execute('SELECT id FROM tags WHERE tag = ?', (tag,)).fetchone()[0]
            conn.execute('INSERT OR IGNORE INTO tag_links (note_id, tag_id) VALUES (?, ?)',
                         (note.id, tag_id))


ENRICHMENTS = [BaseEnrichment(), TagEnrichment()]
