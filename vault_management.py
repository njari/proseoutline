"""vault_management.py — all vault-level operations in one place.

Covers:
  - VAULT_DIR constant
  - Scanning notes from the filesystem (scan_notes)
  - Syncing vault files into the SQLite DB (add_files_to_table)
"""

import time
from datetime import date, timedelta
from pathlib import Path

import frontmatter

import settings
from graph_enrichment.dbconn import get_db
from graph_enrichment.note import NoteType

VAULT_DIR = Path(settings.vault_dir()) if settings.vault_dir() else Path('.')

# ── Filesystem scan ───────────────────────────────────────────────────────────

_SKIP_DIRS = {"Daily", "Templates"}
_ALL_FIELDS = ("name", "path", "content", "metadata")


def _date_range(days: int) -> set[str]:
    today = date.today()
    return {(today - timedelta(days=i)).isoformat() for i in range(days)}


def scan_notes(
    days: int = 7,
    vault_path: str | None = None,
    return_params: dict | None = None,
) -> list[dict]:
    """Scan vault for notes created within the last `days` days."""
    fields = set(return_params.get("fields", _ALL_FIELDS)) if return_params else set(_ALL_FIELDS)
    date_range = _date_range(days)
    root = Path(vault_path) if vault_path else Path(settings.vault_dir())
    results = []

    for md_file in root.rglob("*.md"):
        if any(part in _SKIP_DIRS for part in md_file.parts):
            continue
        try:
            post = frontmatter.load(md_file)
            created = str(post.metadata.get("created", ""))
            if not any(d in created for d in date_range):
                continue
            record: dict = {}
            if "name"     in fields: record["name"]     = md_file.stem
            if "path"     in fields: record["path"]     = str(md_file)
            if "content"  in fields: record["content"]  = post.content.strip()
            if "metadata" in fields: record["metadata"] = post.metadata
            results.append(record)
        except Exception:
            continue

    return results


# ── DB sync ───────────────────────────────────────────────────────────────────

def add_files_to_table():
    """Upsert all .md files in the vault into the notes table."""
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
