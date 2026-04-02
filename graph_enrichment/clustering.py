import networkx as nx
import community as community_louvain
import numpy as np
import umap
import hdbscan
from sklearn.manifold import SpectralEmbedding
from sklearn.cluster import KMeans

from .dbconn import get_db


def build_graph():
    conn = get_db()
    G = nx.Graph()

    for a, b, score in conn.execute('SELECT note_a_id, note_b_id, score FROM bib_coupling'):
        if G.has_edge(a, b):
            G[a][b]['weight'] += score
        else:
            G.add_edge(a, b, weight=score)

    for a, b, score in conn.execute('SELECT note_a_id, note_b_id, score FROM cocitation'):
        if G.has_edge(a, b):
            G[a][b]['weight'] += score
        else:
            G.add_edge(a, b, weight=score)

    return G


def cluster_louvain():
    conn = get_db()
    G = build_graph()

    if G.number_of_edges() == 0:
        print("No edges found — run enrichments first")
        return

    partition = community_louvain.best_partition(G, weight='weight')

    conn.execute("DELETE FROM clusters WHERE algorithm = 'louvain'")
    for note_id, cluster_id in partition.items():
        conn.execute(
            'INSERT INTO clusters (note_id, cluster_id, algorithm) VALUES (?, ?, ?)',
            (note_id, cluster_id, 'louvain')
        )
    conn.commit()
    print(f"Louvain: {len(set(partition.values()))} clusters across {len(partition)} notes")


def cluster_kmeans(k=5):
    conn = get_db()
    G = build_graph()

    if G.number_of_edges() == 0:
        print("No edges found — run enrichments first")
        return

    node_ids = list(G.nodes())
    adjacency = nx.to_numpy_array(G, nodelist=node_ids, weight='weight')

    embedding = SpectralEmbedding(n_components=k, affinity='precomputed')
    vectors = embedding.fit_transform(adjacency)

    labels = KMeans(n_clusters=k, n_init='auto').fit_predict(vectors)

    conn.execute("DELETE FROM clusters WHERE algorithm = 'kmeans'")
    for note_id, cluster_id in zip(node_ids, labels):
        conn.execute(
            'INSERT INTO clusters (note_id, cluster_id, algorithm) VALUES (?, ?, ?)',
            (note_id, int(cluster_id), 'kmeans')
        )
    conn.commit()
    print(f"K-Means (k={k}): {k} clusters across {len(node_ids)} notes")


def get_cluster_note_ids(algorithm: str, rank: int) -> set[int]:
    """Return the set of note_ids in the rank-th largest cluster (1-indexed)."""
    conn = get_db()
    row = conn.execute('''
        SELECT cluster_id FROM clusters
        WHERE algorithm = ?
        GROUP BY cluster_id
        ORDER BY COUNT(*) DESC
        LIMIT 1 OFFSET ?
    ''', (algorithm, rank - 1)).fetchone()
    if row is None:
        return set()
    cluster_id = row[0]
    rows = conn.execute(
        'SELECT note_id FROM clusters WHERE algorithm = ? AND cluster_id = ?',
        (algorithm, cluster_id)
    ).fetchall()
    return {r[0] for r in rows}


def get_cluster_notes(algorithm: str, rank: int) -> list[dict]:
    """Return notes in the rank-th largest cluster (1-indexed) as dicts with name + content."""
    import frontmatter as fm
    from .read_files import VAULT_DIR

    conn = get_db()
    row = conn.execute('''
        SELECT cluster_id FROM clusters
        WHERE algorithm = ?
        GROUP BY cluster_id
        ORDER BY COUNT(*) DESC
        LIMIT 1 OFFSET ?
    ''', (algorithm, rank - 1)).fetchone()
    if row is None:
        return []
    cluster_id = row[0]
    rows = conn.execute('''
        SELECT n.title FROM notes n
        JOIN clusters c ON c.note_id = n.id
        WHERE c.algorithm = ? AND c.cluster_id = ?
    ''', (algorithm, cluster_id)).fetchall()

    results = []
    for (title,) in rows:
        path = VAULT_DIR / (title + '.md')
        try:
            post = fm.load(path)
            results.append({'name': title, 'content': post.content.strip()})
        except Exception:
            results.append({'name': title, 'content': ''})
    return results


def cluster_hdbscan(umap_components=15, min_cluster_size=5):
    from .embeddings import get_collection
    conn = get_db()
    collection = get_collection()

    result = collection.get(include=['embeddings', 'metadatas'])
    if not result['ids']:
        print("No embeddings found — run embed_notes() first")
        return

    note_ids = [int(i) for i in result['ids']]
    vectors  = np.array(result['embeddings'])

    reduced = umap.UMAP(n_components=umap_components, metric='cosine').fit_transform(vectors)
    labels  = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size).fit_predict(reduced)

    conn.execute("DELETE FROM clusters WHERE algorithm = 'hdbscan'")
    for note_id, cluster_id in zip(note_ids, labels):
        conn.execute(
            'INSERT INTO clusters (note_id, cluster_id, algorithm) VALUES (?, ?, ?)',
            (note_id, int(cluster_id), 'hdbscan')
        )
    conn.commit()

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise    = list(labels).count(-1)
    print(f"HDBSCAN: {n_clusters} clusters, {n_noise} noise notes, {len(note_ids)} total")


if __name__ == '__main__':
    # cluster_louvain()
    # cluster_kmeans(k=5)
    cluster_hdbscan()
