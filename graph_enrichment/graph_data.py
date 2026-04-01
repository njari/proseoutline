from .dbconn import get_db


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
