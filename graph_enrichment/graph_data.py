from .dbconn import get_db


def get_graph_data_for_note_ids(note_ids: set[int]) -> dict:
    """
    Return graph data filtered to the given set of note IDs.
    Includes notes, their connected tags, and all edges between included nodes.
    """
    if not note_ids:
        return {'nodes': [], 'edges': {'links': [], 'tag_links': [], 'bib_coupling': [], 'cocitation': []}}

    conn = get_db()
    ph = ','.join('?' * len(note_ids))
    ids = list(note_ids)

    note_rows = conn.execute(
        f'SELECT id, title FROM notes WHERE type = 0 AND id IN ({ph})', ids
    ).fetchall()
    present_ids = {r[0] for r in note_rows}

    # Tags connected to these notes
    ph2 = ','.join('?' * len(present_ids))
    tag_link_rows = conn.execute(
        f'SELECT tl.note_id, t.id, t.tag FROM tag_links tl '
        f'JOIN tags t ON t.id = tl.tag_id WHERE tl.note_id IN ({ph2})',
        list(present_ids),
    ).fetchall() if present_ids else []

    seen_tag_ids: set[int] = set()
    nodes = [{'id': f'n{r[0]}', 'label': r[1], 'group': 'note'} for r in note_rows]
    for _, tid, tname in tag_link_rows:
        if tid not in seen_tag_ids:
            nodes.append({'id': f't{tid}', 'label': tname, 'group': 'tag'})
            seen_tag_ids.add(tid)

    # Edges — filter to nodes present in this subgraph
    link_rows = conn.execute('SELECT from_id, to_id FROM links').fetchall()
    bib_rows  = conn.execute('SELECT note_a_id, note_b_id, score FROM bib_coupling').fetchall()
    cocit_rows = conn.execute('SELECT note_a_id, note_b_id, score FROM cocitation').fetchall()

    return {
        'nodes': nodes,
        'edges': {
            'links': [
                {'from': f'n{r[0]}', 'to': f'n{r[1]}'}
                for r in link_rows if r[0] in present_ids and r[1] in present_ids
            ],
            'tag_links': [
                {'from': f'n{r[0]}', 'to': f't{r[1]}'}
                for r in tag_link_rows
            ],
            'bib_coupling': [
                {'from': f'n{r[0]}', 'to': f'n{r[1]}', 'value': r[2]}
                for r in bib_rows if r[0] in present_ids and r[1] in present_ids
            ],
            'cocitation': [
                {'from': f'n{r[0]}', 'to': f'n{r[1]}', 'value': r[2]}
                for r in cocit_rows if r[0] in present_ids and r[1] in present_ids
            ],
        },
    }


def get_graph_data() -> dict:
    """
    Return all nodes and edges for the graph explorer.

    Nodes:
      - type 'note'  → from notes table (realized only)
      - type 'tag'   → from tags table

    Edges (keyed by enrichment type):
      - 'links'        → note → note (wikilinks)
      - 'tag_links'    → note → tag
      - 'bib_coupling' → note ↔ note (shared outgoing links)
      - 'cocitation'   → note ↔ note (shared incoming links)
    """
    conn = get_db()

    note_rows = conn.execute(
        'SELECT id, title FROM notes WHERE type = 0'
    ).fetchall()
    tag_rows = conn.execute(
        'SELECT id, tag FROM tags'
    ).fetchall()

    nodes = [{'id': f'n{r[0]}', 'label': r[1], 'group': 'note'} for r in note_rows]
    nodes += [{'id': f't{r[0]}', 'label': r[1], 'group': 'tag'} for r in tag_rows]

    edges = {
        'links': [
            {'from': f'n{r[0]}', 'to': f'n{r[1]}'}
            for r in conn.execute('SELECT from_id, to_id FROM links').fetchall()
        ],
        'tag_links': [
            {'from': f'n{r[0]}', 'to': f't{r[1]}'}
            for r in conn.execute('SELECT note_id, tag_id FROM tag_links').fetchall()
        ],
        'bib_coupling': [
            {'from': f'n{r[0]}', 'to': f'n{r[1]}', 'value': r[2]}
            for r in conn.execute('SELECT note_a_id, note_b_id, score FROM bib_coupling').fetchall()
        ],
        'cocitation': [
            {'from': f'n{r[0]}', 'to': f'n{r[1]}', 'value': r[2]}
            for r in conn.execute('SELECT note_a_id, note_b_id, score FROM cocitation').fetchall()
        ],
    }

    return {'nodes': nodes, 'edges': edges}
