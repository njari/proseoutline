"""
embedding_creation.py — incremental embedding pipeline with file-hash tracking.

SQLite table `file_index` tracks each vault file's SHA-256 hash and the
timestamp it was last indexed. On each run only new or changed files are
(re-)embedded; unchanged files are skipped entirely.

Public API
----------
build_or_update_store(vault_dir: str) -> Chroma
    Call this instead of the old build_or_load_store().  Returns a ready-to-use
    Chroma store, having embedded only the files that changed since last run.
"""

import hashlib
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from langchain_community.document_loaders import ObsidianLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma

_BASE_DIR   = Path(__file__).parent
CHROMA_DIR  = str(_BASE_DIR / "chroma_db")
INDEX_DB    = str(_BASE_DIR / "file_index.db")

_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=200, chunk_overlap=20, add_start_index=True
)


# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------

def _open_db() -> sqlite3.Connection:
    con = sqlite3.connect(INDEX_DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS file_index (
            path          TEXT PRIMARY KEY,
            hash          TEXT NOT NULL,
            last_indexed  TEXT NOT NULL
        )
    """)
    con.commit()
    return con


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _remove_deleted(con: sqlite3.Connection, existing_paths: set[str]) -> list[str]:
    """Return paths that are in the DB but no longer on disk, then delete them."""
    rows = con.execute("SELECT path FROM file_index").fetchall()
    deleted = [r[0] for r in rows if r[0] not in existing_paths]
    if deleted:
        con.executemany("DELETE FROM file_index WHERE path = ?", [(p,) for p in deleted])
        con.commit()
    return deleted


# ---------------------------------------------------------------------------
# Chroma helpers
# ---------------------------------------------------------------------------

def _embeddings():
    return HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")


def _load_or_create_store() -> Chroma:
    return Chroma(persist_directory=CHROMA_DIR, embedding_function=_embeddings())


def _delete_chunks_for_file(store: Chroma, path: str) -> None:
    """Remove all Chroma chunks whose source metadata matches `path`."""
    existing = store.get(where={"source": path})
    ids = existing.get("ids", [])
    if ids:
        store.delete(ids=ids)


def _embed_file(store: Chroma, path: str) -> int:
    """Load, split, and add one file to the store. Returns chunk count."""
    loader = ObsidianLoader(path=os.path.dirname(path), collect_metadata=True)
    all_docs = loader.load()
    docs = [d for d in all_docs if d.metadata.get("source") == path]
    if not docs:
        return 0
    splits = _SPLITTER.split_documents(docs)
    store.add_documents(splits)
    return len(splits)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_or_update_store(vault_dir: str) -> Chroma:
    """
    Scan `vault_dir` for .md files, embed only those that have changed since
    the last run (or are new), and return the up-to-date Chroma store.
    """
    store = _load_or_create_store()
    con   = _open_db()

    md_files = {str(p) for p in Path(vault_dir).rglob("*.md")}

    # Clean up entries for files that no longer exist on disk
    deleted = _remove_deleted(con, md_files)
    for path in deleted:
        _delete_chunks_for_file(store, path)

    # Bulk-load all known hashes in one query
    stored: dict[str, str] = {
        row[0]: row[1]
        for row in con.execute("SELECT path, hash FROM file_index").fetchall()
    }

    new_count     = 0
    changed_count = 0
    skipped_count = 0
    pending_upserts: list[tuple[str, str]] = []  # (path, hash)

    for path in sorted(md_files):
        try:
            current_hash = _hash_file(path)
        except OSError:
            continue

        stored_hash = stored.get(path)

        if stored_hash is None:
            _embed_file(store, path)
            pending_upserts.append((path, current_hash))
            new_count += 1
        elif stored_hash != current_hash:
            _delete_chunks_for_file(store, path)
            _embed_file(store, path)
            pending_upserts.append((path, current_hash))
            changed_count += 1
        else:
            skipped_count += 1

    if pending_upserts:
        now = datetime.now(timezone.utc).isoformat()
        con.executemany(
            """INSERT INTO file_index (path, hash, last_indexed) VALUES (?, ?, ?)
               ON CONFLICT(path) DO UPDATE SET hash = excluded.hash,
                                               last_indexed = excluded.last_indexed""",
            [(path, h, now) for path, h in pending_upserts],
        )
        con.commit()

    con.close()
    print(
        f"[embedding] new={new_count} updated={changed_count} "
        f"skipped={skipped_count} deleted={len(deleted)}"
    )
    return store
