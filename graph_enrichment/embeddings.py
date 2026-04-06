import time
from pathlib import Path

import chromadb
from openai import OpenAI

import settings
from .dbconn import get_db
from .note import NoteType
from vault_management import VAULT_DIR, add_files_to_table

CHROMA_PATH = Path(__file__).parent / 'chroma'
COLLECTION  = 'notes'


def get_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return client.get_or_create_collection(COLLECTION)


def sync_and_embed():
    """Scan vault for new/updated notes, add them to the DB, then embed any that are stale."""
    add_files_to_table()
    embed_notes()


def embed_notes():
    conn = get_db()
    collection = get_collection()
    client = OpenAI(api_key=settings.api_key())

    rows = conn.execute('''
        SELECT id, title FROM notes
        WHERE type = ? AND (embedded_at IS NULL OR embedded_at < last_modified)
    ''', (NoteType.REALIZED,)).fetchall()

    print(f"Embedding {len(rows)} notes…")
    for note_id, title in rows:
        path = VAULT_DIR / (title + '.md')
        try:
            text = path.read_text('utf-8')
        except Exception:
            continue

        response = client.embeddings.create(
            model='text-embedding-3-small',
            input=text,
        )
        vector = response.data[0].embedding

        collection.upsert(
            ids=[str(note_id)],
            embeddings=[vector],
            documents=[text],
            metadatas=[{'note_id': note_id, 'title': title}],
        )
        conn.execute('UPDATE notes SET embedded_at = ? WHERE id = ?', (int(time.time()), note_id))
        conn.commit()
        print(f"  ✓ {title}")

    print("Done")


def retrieve(topic: str, k: int = 8) -> list[dict]:
    """Query chroma for the k most relevant notes to topic. Returns list of {name, content}."""
    collection = get_collection()
    client = OpenAI(api_key=settings.api_key())

    response = client.embeddings.create(model='text-embedding-3-small', input=topic)
    vector = response.data[0].embedding

    results = collection.query(query_embeddings=[vector], n_results=k, include=['metadatas', 'documents'])
    notes = []
    for meta, doc in zip(results['metadatas'][0], results['documents'][0]):
        notes.append({'name': meta['title'], 'content': doc or ''})
    return notes


if __name__ == '__main__':
    embed_notes()
