import time
import numpy as np
import umap
import hdbscan
import frontmatter as fm

from .dbconn import get_db
from vault_management import VAULT_DIR


def _get_recent_note_ids(days: int = 7) -> set[int]:
    cutoff = int(time.time()) - days * 24 * 3600
    conn = get_db()
    rows = conn.execute(
        'SELECT id FROM notes WHERE type = 0 AND last_modified >= ?', (cutoff,)
    ).fetchall()
    return {r[0] for r in rows}


def _expand_note_ids(seed_ids: set[int], max_hops: int = 3) -> set[int]:
    """BFS through wikilinks from seed_ids up to max_hops levels."""
    conn = get_db()
    visited = set(seed_ids)
    frontier = set(seed_ids)

    for _ in range(max_hops):
        if not frontier:
            break
        ph = ','.join('?' * len(frontier))
        ids = list(frontier)
        rows = conn.execute(
            f'SELECT to_id FROM links WHERE from_id IN ({ph}) '
            f'UNION SELECT from_id FROM links WHERE to_id IN ({ph})',
            ids + ids,
        ).fetchall()
        candidates = {r[0] for r in rows} - visited
        if not candidates:
            break
        ph2 = ','.join('?' * len(candidates))
        realized = conn.execute(
            f'SELECT id FROM notes WHERE id IN ({ph2}) AND type = 0',
            list(candidates),
        ).fetchall()
        new_ids = {r[0] for r in realized}
        visited |= new_ids
        frontier = new_ids

    return visited


def get_working_set_note_ids(days: int = 30, max_hops: int = 3) -> set[int]:
    """Return all note IDs in the working set (recent seeds + BFS expansion)."""
    seed_ids = _get_recent_note_ids(days)
    if not seed_ids:
        return set()
    return _expand_note_ids(seed_ids, max_hops)


def cluster_realtime(
    days: int = 30,
    max_hops: int = 3,
    umap_components: int = 10,
    min_cluster_size: int = 3,
) -> list[list[dict]]:
    """
    On-the-fly HDBSCAN clustering over recently modified notes and their neighbors.

    1. Find notes with last_modified in the past `days` days
    2. BFS-expand through wikilinks up to `max_hops` hops
    3. Fetch embeddings from ChromaDB for the expanded set
    4. UMAP + HDBSCAN cluster
    5. Return list of clusters sorted by size desc; each cluster is list[{name, content}]

    Returns [] if there is not enough data to cluster.
    """
    from .embeddings import get_collection

    conn = get_db()

    seed_ids = _get_recent_note_ids(days)
    if not seed_ids:
        return []

    note_ids = _expand_note_ids(seed_ids, max_hops)
    if len(note_ids) < 2:
        return []

    collection = get_collection()
    chroma_result = collection.get(
        ids=[str(i) for i in note_ids],
        include=['embeddings', 'metadatas'],
    )
    if not chroma_result['ids'] or len(chroma_result['ids']) < 2:
        return []

    fetched_ids = [int(i) for i in chroma_result['ids']]
    vectors = np.array(chroma_result['embeddings'])

    n_components = min(umap_components, len(fetched_ids) - 1)
    reduced = umap.UMAP(n_components=n_components, metric='cosine').fit_transform(vectors)
    labels = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size).fit_predict(reduced)

    clusters: dict[int, list[int]] = {}
    for nid, label in zip(fetched_ids, labels):
        if label != -1:
            clusters.setdefault(label, []).append(nid)

    sorted_clusters = sorted(clusters.values(), key=len, reverse=True)[:5]

    id_to_title = dict(conn.execute(
        'SELECT id, title FROM notes WHERE id IN (%s)' % ','.join('?' * len(fetched_ids)),
        fetched_ids,
    ).fetchall())

    result_clusters = []
    for group in sorted_clusters:
        notes = []
        for nid in group:
            title = id_to_title.get(nid)
            if not title:
                continue
            path = VAULT_DIR / (title + '.md')
            try:
                post = fm.load(path)
                notes.append({'id': nid, 'name': title, 'content': post.content.strip()})
            except Exception:
                notes.append({'id': nid, 'name': title, 'content': ''})
        if notes:
            result_clusters.append(notes)

    return result_clusters
