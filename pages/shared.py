from nicegui import ui, run
from theme import PRIMARY, ACCENT, BG_PAGE, BORDER, SURFACE, TEXT_BODY, TEXT_MUTED

PAGE_INDEX = "/"
PAGE_SETUP = "/setup"
PAGE_GRAPH = "/graph"

EDGE_COLORS = {
    'links':        '#6366f1',
    'tag_links':    '#10b981',
    'bib_coupling': '#f59e0b',
    'cocitation':   '#ef4444',
}
EDGE_LABELS = {
    'links':        'Wikilinks',
    'tag_links':    'Tags',
    'bib_coupling': 'Often refer to the same things',
    'cocitation':   'Often cited together',
}


def shared_head():
    ui.add_head_html(f"""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;1,9..40,300&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
    <style>
      * {{ font-family: 'DM Sans', sans-serif !important; }}
      .material-icons, .material-icons-outlined, .material-icons-round, .material-icons-sharp,
      .q-icon {{ font-family: 'Material Icons' !important; }}
      body {{ background: {BG_PAGE} !important; margin: 0; padding: 0; }}
      .q-btn  {{ border-radius: 10px !important; }}
      .q-field__control {{ border-radius: 10px !important; }}
    </style>
    """)
    ui.colors(primary=PRIMARY, secondary=ACCENT, accent=ACCENT)


def section_header(text: str):
    ui.label(text).classes("text-sm font-semibold tracking-wide").style(
        f"color:{PRIMARY}; letter-spacing:0.06em; text-transform:uppercase;"
    )


def section_divider():
    ui.separator().style(f"background:{BORDER};")


def build_echart_option(data: dict, active_types: set, highlight_ids: set | None = None) -> dict:
    """Pure function: build an ECharts force-graph option dict from graph data.

    highlight_ids: set of echart node name strings (e.g. {'n1', 'n42'}).
    When provided, cluster nodes are vivid+large; all others are dimmed.
    When None, all nodes render normally.
    """
    visible_ids = {n['id'] for n in data.get('nodes', [])}
    has_highlight = highlight_ids is not None and len(highlight_ids) > 0

    nodes = []
    for n in data.get('nodes', []):
        if n['id'] not in visible_ids:
            continue
        is_tag = n['group'] == 'tag'
        is_lit = not has_highlight or n['id'] in highlight_ids

        if is_lit:
            nodes.append({
                'name': n['id'],
                'value': n['label'],
                'symbolSize': 10 if is_tag else 18,
                'label': {'show': True, 'formatter': n['label'][:25], 'fontSize': 10, 'color': '#334155'},
                'itemStyle': {
                    'color': '#10b981' if is_tag else '#38bdf8',
                    'borderColor': '#059669' if is_tag else '#0369a1',
                    'borderWidth': 2,
                    'opacity': 1.0,
                },
                'symbol': 'diamond' if is_tag else 'circle',
            })
        else:
            nodes.append({
                'name': n['id'],
                'value': n['label'],
                'symbolSize': 5 if is_tag else 8,
                'label': {'show': False},
                'itemStyle': {
                    'color': '#e2e8f0',
                    'borderColor': '#94a3b8',
                    'borderWidth': 1,
                    'opacity': 0.25,
                },
                'symbol': 'diamond' if is_tag else 'circle',
            })

    links = []
    for t in active_types:
        color = EDGE_COLORS.get(t, '#888')
        for e in data.get('edges', {}).get(t, []):
            if e['from'] in visible_ids and e['to'] in visible_ids:
                both_lit = not has_highlight or (e['from'] in highlight_ids and e['to'] in highlight_ids)
                links.append({
                    'source': e['from'],
                    'target': e['to'],
                    'lineStyle': {
                        'color': color,
                        'opacity': 0.6 if both_lit else 0.05,
                        'width': min(0.5 + e.get('value', 1) * 0.4, 4) if both_lit else 0.5,
                    },
                })
    return {
        'backgroundColor': BG_PAGE,
        'tooltip': {'show': True, 'formatter': '{b}'},
        'series': [{
            'type': 'graph',
            'layout': 'force',
            'roam': True,
            'draggable': True,
            'data': nodes,
            'links': links,
            'force': {
                'repulsion': 120,
                'gravity': 0.08,
                'edgeLength': 100,
                'layoutAnimation': True,
            },
            'emphasis': {'focus': 'adjacency'},
            'lineStyle': {'curveness': 0.1},
        }],
    }


def render_graph_panel(height_class: str = "h-64") -> dict:
    """
    Render an ECharts graph panel with compact enrichment toggles and a note popup.

    Must be called inside a NiceGUI page context.
    Returns {'set_data': fn} — call set_data(data_dict) to update the displayed graph.
    """
    import frontmatter as fm
    from graph_enrichment.read_files import VAULT_DIR

    _state = {
        'data': {'nodes': [], 'edges': {}},
        'active_types': set(EDGE_COLORS.keys()),
        'highlight_ids': None,
    }

    def _option():
        return build_echart_option(_state['data'], _state['active_types'], _state['highlight_ids'])

    # Toggle strip + chart
    with ui.column().classes(f"w-full {height_class} gap-1"):
        with ui.row().classes("w-full gap-x-4 gap-y-0 flex-wrap items-center"):
            for key, label in EDGE_LABELS.items():
                color = EDGE_COLORS[key]

                def make_toggle(k):
                    def toggle(e):
                        if e.value:
                            _state['active_types'].add(k)
                        else:
                            _state['active_types'].discard(k)
                        chart.options.update(_option())
                        chart.update()
                    return toggle

                ui.checkbox(label, value=True, on_change=make_toggle(key)).style(
                    f"color:{color}; font-size:0.7rem;"
                ).props("dense")

        chart = ui.echart(_option()).classes("w-full flex-1")

    # Note popup (dialog overlays the page regardless of DOM position)
    with ui.dialog() as note_dialog:
        with ui.card().classes("gap-0").style(
            f"width:540px; max-width:90vw; max-height:80vh; background:{SURFACE};"
        ):
            with ui.row().classes("w-full items-center justify-between px-5 py-3").style(
                f"border-bottom: 1px solid {BORDER};"
            ):
                note_title = ui.label("").classes(
                    "text-sm font-semibold flex-1 truncate"
                ).style(f"color:{PRIMARY};")
                ui.button(icon="close", on_click=note_dialog.close).props(
                    "flat dense"
                ).style(f"color:{TEXT_MUTED};")
            note_content = ui.markdown("").classes("overflow-auto p-5 text-sm").style(
                f"color:{TEXT_BODY}; max-height:calc(80vh - 60px);"
            )

    async def on_node_click(e):
        args = e.data if isinstance(e.data, dict) else {}
        node_id = args.get('name', '')
        title = args.get('value', '') or args.get('name', '')
        if not node_id or not node_id.startswith('n'):
            return
        note_title.set_text(title)
        note_content.set_content('_Loading…_')
        note_dialog.open()
        path = VAULT_DIR / (title + '.md')
        try:
            post = await run.io_bound(fm.load, path)
            note_content.set_content(post.content or '_Empty note._')
        except Exception:
            note_content.set_content('_Could not load note._')

    chart.on_point_click(on_node_click)

    def set_data(new_data: dict):
        _state['data'] = new_data
        chart.options.update(_option())
        chart.update()

    def set_highlight(ids: set[str]):
        _state['highlight_ids'] = ids
        chart.options.update(_option())
        chart.update()

    return {'set_data': set_data, 'set_highlight': set_highlight}
