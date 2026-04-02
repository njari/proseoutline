from pathlib import Path

from nicegui import ui, run

from generator import stream_outline, revise_outline
from articles import (
    OUTLINES_DIR, Article, slugify,
    commit_edit, init_article_repo, current_branch,
)
from daily import scan_notes, suggest_topics
from graph_enrichment.clustering import get_cluster_notes, get_cluster_note_ids
from graph_enrichment.graph_data import get_graph_data
from graph_enrichment.embeddings import retrieve
from graph_enrichment.read_files import VAULT_DIR
import frontmatter as _fm
from theme import (
    PRIMARY, ACCENT, SURFACE, BG_PAGE, BG_PANEL, BORDER,
    TEXT_BODY, TEXT_MUTED, TEXT_SUBTLE, SUCCESS, ERROR,
)
import settings


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
PAGE_INDEX   = "/"
PAGE_SETUP   = "/setup"
PAGE_GRAPH   = "/graph"


# ---------------------------------------------------------------------------
# Section builders — pure layout, no event logic
# Each is called within the active NiceGUI `with` context.
# Returns a dict of interactive widget refs for the caller to wire up.
# ---------------------------------------------------------------------------

def _section_header(text: str):
    """Reusable uppercase section label."""
    ui.label(text).classes("text-sm font-semibold tracking-wide").style(
        f"color:{PRIMARY}; letter-spacing:0.06em; text-transform:uppercase;"
    )


def _section_divider():
    ui.separator().style(f"background:{BORDER};")


def _section_cluster_browse() -> dict:
    _section_header("Browse Cluster")
    with ui.row().classes("w-full gap-2 items-center"):
        algo_select = ui.select(
            options=["louvain", "kmeans", "hdbscan"],
            value="louvain",
        ).props("outlined dense hide-dropdown-icon").classes("flex-1").style(
            f"color:{PRIMARY}; font-size:0.85rem;"
        )
        rank_input = ui.number(value=1, min=1, step=1, format="%d").props(
            "outlined dense"
        ).classes("w-16").style(f"color:{PRIMARY}; font-size:0.85rem;")
    btn = ui.button("Suggest from cluster").props("unelevated").classes("w-full").style(
        f"background:{BG_PANEL}; color:{PRIMARY}; border: 1px solid {BORDER};"
    )
    count_label = ui.label("").classes("text-xs").style(f"color:{TEXT_MUTED};")
    ideas_area = ui.markdown("").classes(
        "text-sm w-full overflow-auto flex-1 p-3 rounded-xl"
    ).style(
        f"background:{SURFACE}; border: 1px solid {BORDER}; color:{TEXT_BODY}; min-height:120px;"
    )
    return {
        "btn": btn,
        "algo_select": algo_select,
        "rank_input": rank_input,
        "count_label": count_label,
        "ideas_area": ideas_area,
    }


def _section_generate() -> dict:
    _section_header("Generate Outline")
    topic_input = ui.input(placeholder="Article topic…").classes("w-full").style(
        f"color:{PRIMARY};"
    )
    btn = ui.button("Generate").props("unelevated").classes("w-full").style(
        f"background:{PRIMARY}; color:{SURFACE};"
    )
    return {"btn": btn, "topic_input": topic_input}


def _section_article_actions() -> dict:
    """Hidden by default — revealed on article double-click."""
    root = ui.column().classes("w-full gap-3")
    with root:
        _section_divider()
        _section_header("Article Actions")
        feedback = ui.textarea(placeholder="What's not working? Be specific.").classes(
            "w-full"
        ).style(f"color:{PRIMARY}; min-height:80px;")
        improve_btn = ui.button("Improve with feedback").props("unelevated").classes(
            "w-full"
        ).style(f"background:{ACCENT}; color:{SURFACE};")
        direction_btn = ui.button("Explore new Direction").props("unelevated").classes(
            "w-full"
        ).style(f"background:{BG_PANEL}; color:{PRIMARY}; border: 1px solid {BORDER};")
    root.set_visibility(False)
    return {
        "root": root,
        "feedback": feedback,
        "improve_btn": improve_btn,
        "direction_btn": direction_btn,
    }




# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@ui.page(PAGE_INDEX)
def index():
    if not settings.is_configured():
        ui.navigate.to(PAGE_SETUP)
        return

    _shared_head()
    ui.add_head_html(f"""
    <style>
      .q-item {{ border-radius: 8px !important; }}
      ::-webkit-scrollbar {{ width: 6px; }}
      ::-webkit-scrollbar-track {{ background: {BG_PAGE}; }}
      ::-webkit-scrollbar-thumb {{ background: {BORDER}; border-radius: 6px; }}
    </style>
    """)

    article = Article()
    ui.query("body").style("margin:0; padding:0;")

    # --- Layout skeleton ---
    with ui.splitter(value=72).classes("w-full h-screen") as inner:

        with inner.before:
            with ui.column().classes("w-full h-full gap-0").style(
                f"background:{SURFACE};"
            ):
                with ui.row().classes("w-full items-center px-5 py-2 gap-3").style(
                    f"min-height:52px; border-bottom: 1px solid {BORDER}; background:{SURFACE};"
                ):
                    ui.button(icon="hub", on_click=lambda: ui.navigate.to(PAGE_GRAPH)).props(
                        "flat dense"
                    ).style(f"color:{PRIMARY};").tooltip("Graph Explorer")
                    article_label = ui.label("").classes(
                        "text-sm font-mono flex-1 truncate"
                    ).style(f"color:{PRIMARY};")
                    status = ui.label("").classes("text-xs").style(
                        f"color:{TEXT_MUTED};"
                    )
                    save_btn = ui.button("Save").props("dense unelevated").style(
                        f"background:{PRIMARY}; color:{SURFACE}; padding: 4px 18px;"
                    )
                editor = ui.codemirror(
                    value="", language="markdown",
                    line_wrapping=True,
                ).classes("w-full flex-1").style(f"background:{SURFACE};")

        with inner.after:
            with ui.column().classes("w-full h-full p-5 gap-4").style(
                f"background:{BG_PAGE}; border-left: 1px solid {BORDER};"
            ):
                daily_w    = _section_cluster_browse()
                _section_divider()
                gen_w      = _section_generate()
                action_w   = _section_article_actions()

    # --- Event handlers (close over layout widget refs) ---

    async def on_save():
        if not article.slug:
            status.set_text("Nothing loaded.")
            return
        commit = await run.io_bound(commit_edit, OUTLINES_DIR, article.slug, "main", editor.value)
        status.set_text(f"Saved · {commit}")

    async def on_generate():
        topic = gen_w["topic_input"].value.strip()
        if not topic:
            status.set_text("Enter a topic first.")
            return
        slug = slugify(topic)
        article.slug = slug
        article.alias = "main"
        article_label.set_text(slug)
        await run.io_bound(init_article_repo, OUTLINES_DIR / slug)
        status.set_text(f"Retrieving notes for '{topic}'…")
        docs = await run.io_bound(retrieve, topic)
        status.set_text(f"Generating from {len(docs)} notes…")
        editor.value = ""
        async for chunk in stream_outline(topic, docs):
            editor.value += chunk
        status.set_text("Done — edit and save when ready.")

    async def on_browse_cluster():
        algo = daily_w["algo_select"].value
        rank = int(daily_w["rank_input"].value or 1)
        daily_w["ideas_area"].set_content(f"_Loading cluster {rank} ({algo})…_")
        notes = await run.io_bound(get_cluster_notes, algo, rank)
        count = len(notes)
        if count == 0:
            daily_w["count_label"].set_text(f"No notes found for cluster {rank} ({algo}).")
            daily_w["count_label"].style(f"color:{TEXT_SUBTLE};")
            daily_w["ideas_area"].set_content("")
            return
        daily_w["count_label"].set_text(f"{count} notes in cluster {rank} ({algo})")
        daily_w["count_label"].style(f"color:{TEXT_MUTED};")
        ideas = await run.io_bound(suggest_topics, notes)
        daily_w["ideas_area"].set_content(ideas)

    async def on_improve():
        feedback = action_w["feedback"].value.strip()
        if not feedback or not article.slug:
            status.set_text("Load an article and enter feedback first.")
            return
        docs = await run.io_bound(retrieve, article.slug)
        current = editor.value
        status.set_text("Revising outline…")
        editor.value = ""
        async for chunk in revise_outline(current, feedback, docs):
            editor.value += chunk
        action_w["feedback"].value = ""
        status.set_text("Revised — edit and save when ready.")

    async def on_new_direction():
        if not article.slug:
            status.set_text("Load an article first.")
            return
        topic = article.slug.replace("-", " ")
        docs = await run.io_bound(retrieve, topic)
        status.set_text("Exploring new direction…")
        editor.value = ""
        async for chunk in stream_outline(topic, docs):
            editor.value += chunk
        status.set_text("New direction ready — edit and save when ready.")

    # --- Wire buttons to handlers ---
    save_btn.on("click", on_save)
    daily_w["btn"].on("click", on_browse_cluster)
    gen_w["btn"].on("click", on_generate)
    action_w["improve_btn"].on("click", on_improve)
    action_w["direction_btn"].on("click", on_new_direction)


def _shared_head():
    ui.add_head_html(f"""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;1,9..40,300&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
    <style>
      * {{ font-family: 'DM Sans', sans-serif !important; }}
      body {{ background: {BG_PAGE} !important; margin: 0; padding: 0; }}
      .q-btn  {{ border-radius: 10px !important; }}
      .q-field__control {{ border-radius: 10px !important; }}
    </style>
    """)
    ui.colors(primary=PRIMARY, secondary=ACCENT, accent=ACCENT)


@ui.page(PAGE_SETUP)
def setup():
    _shared_head()
    ui.query("body").style("margin:0; padding:0;")

    result_label: ui.label | None = None
    save_btn: ui.button | None = None

    with ui.column().classes("w-full h-screen items-center justify-center").style(
        f"background:{BG_PAGE};"
    ):
        with ui.card().classes("p-10 gap-6 rounded-2xl shadow-lg").style(
            f"width:480px; background:{SURFACE}; border: 1px solid {BORDER};"
        ):
            ui.label("ProseOutline").classes("text-3xl font-semibold").style(
                f"color:{PRIMARY};"
            )
            ui.label(
                "Connect your Obsidian vault to get started."
            ).classes("text-sm").style(f"color:{TEXT_MUTED};")

            ui.separator().style(f"background:{BORDER};")

            vault_input = ui.input(
                label="Obsidian vault folder path",
                placeholder="/Users/you/Documents/MyVault",
                value=settings.vault_dir(),
            ).classes("w-full")

            api_input = ui.input(
                label="OpenAI API key",
                placeholder="sk-...",
                password=False,
                password_toggle_button=False,
                value=settings.api_key(),
            ).classes("w-full")

            async def on_verify():
                vault_path = vault_input.value.strip()
                if not vault_path or not Path(vault_path).is_dir():
                    result_label.set_text("That path doesn't exist — double-check it.")
                    result_label.style(f"color:{ERROR};")
                    save_btn.disable()
                    return
                result_label.set_text("Scanning vault…")
                result_label.style(f"color:{TEXT_MUTED};")
                results = await run.io_bound(scan_notes, 2, vault_path, {"fields": ["name"]})
                titles = [r["name"] for r in results]
                if not titles:
                    result_label.set_text(
                        "Vault readable — no notes created today (that's fine).\n"
                        "You're good to go!"
                    )
                    result_label.style(f"color:{TEXT_MUTED}; white-space:pre-line;")
                else:
                    preview = "\n".join(f"  · {t}" for t in titles[:5])
                    result_label.set_text(
                        f"Looks like we're ready to take this forward :)\n\n"
                        f"Today's notes ({len(titles)} found):\n{preview}"
                    )
                    result_label.style(f"color:{SUCCESS}; white-space:pre-line;")
                save_btn.enable()

            ui.button("Verify vault", on_click=on_verify).props("unelevated").classes(
                "w-full"
            ).style(f"background:{BG_PANEL}; color:{PRIMARY}; border:1px solid {BORDER};")

            result_label = ui.label("").classes("text-sm").style(f"color:{TEXT_MUTED};")

            ui.separator().style(f"background:{BORDER};")

            def on_save():
                vault_path = vault_input.value.strip()
                api_key = api_input.value.strip()
                if not vault_path or not api_key:
                    result_label.set_text("Please fill in both fields before saving.")
                    result_label.style(f"color:{ERROR};")
                    return
                settings.save(vault_path, api_key)
                result_label.set_text("Config saved! Restart ProseOutline to begin.")
                result_label.style(f"color:{PRIMARY};")
                save_btn.disable()

            save_btn = ui.button("Save & Continue", on_click=on_save).props(
                "unelevated"
            ).classes("w-full").style(f"background:{PRIMARY}; color:{SURFACE};")
            if not settings.is_configured():
                save_btn.disable()


@ui.page(PAGE_GRAPH)
def graph_explorer():
    if not settings.is_configured():
        ui.navigate.to(PAGE_SETUP)
        return

    _shared_head()
    ui.query("body").style("margin:0; padding:0;")

    data = get_graph_data()

    EDGE_COLORS = {
        'links':        '#6366f1',
        'tag_links':    '#10b981',
        'bib_coupling': '#f59e0b',
        'cocitation':   '#ef4444',
    }
    EDGE_LABELS = {
        'links':        'Wikilinks',
        'tag_links':    'Tags',
        'bib_coupling': 'Bib coupling',
        'cocitation':   'Co-citation',
    }

    active_types: set[str] = set(EDGE_COLORS.keys())
    cluster_filter: set[str] | None = None  # set of node ids like 'n42', or None = show all

    def build_option():
        visible_ids = cluster_filter if cluster_filter is not None else {n['id'] for n in data['nodes']}
        nodes = [
            {
                'name': n['id'],
                'value': n['label'],
                'symbolSize': 8 if n['group'] == 'tag' else 14,
                'label': {
                    'show': True,
                    'formatter': n['label'][:25],
                    'fontSize': 10,
                    'color': '#334155',
                },
                'itemStyle': {
                    'color': '#10b981' if n['group'] == 'tag' else '#bae6fd',
                    'borderColor': '#059669' if n['group'] == 'tag' else '#1e3a8a',
                    'borderWidth': 1.5,
                },
                'symbol': 'diamond' if n['group'] == 'tag' else 'circle',
            }
            for n in data['nodes'] if n['id'] in visible_ids
        ]
        links = []
        for t in active_types:
            color = EDGE_COLORS[t]
            for e in data['edges'].get(t, []):
                links.append({
                    'source': e['from'],
                    'target': e['to'],
                    'lineStyle': {
                        'color': color,
                        'opacity': 0.5,
                        'width': min(0.5 + e.get('value', 1) * 0.4, 4),
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

    with ui.row().classes("w-full h-screen gap-0"):

        # --- Sidebar ---
        with ui.column().classes("h-full p-5 gap-4 shrink-0").style(
            f"width:220px; background:{BG_PANEL}; border-right:1px solid {BORDER};"
        ):
            ui.button(icon="arrow_back", on_click=lambda: ui.navigate.to(PAGE_INDEX)).props(
                "flat dense"
            ).style(f"color:{PRIMARY};")
            ui.label("Graph Explorer").classes("text-sm font-semibold tracking-wide").style(
                f"color:{PRIMARY}; letter-spacing:0.06em; text-transform:uppercase;"
            )
            ui.separator().style(f"background:{BORDER};")
            _section_header("Cluster")
            with ui.row().classes("w-full gap-2 items-center"):
                algo_sel = ui.select(
                    options=["louvain", "kmeans", "hdbscan"], value="louvain"
                ).props("outlined dense hide-dropdown-icon").classes("flex-1").style(
                    f"color:{PRIMARY}; font-size:0.85rem;"
                )
                rank_inp = ui.number(value=1, min=1, step=1, format="%d").props(
                    "outlined dense"
                ).classes("w-16").style(f"color:{PRIMARY}; font-size:0.85rem;")
            with ui.row().classes("w-full gap-2"):
                def apply_cluster():
                    nonlocal cluster_filter
                    ids = get_cluster_note_ids(algo_sel.value, int(rank_inp.value or 1))
                    cluster_filter = {f'n{i}' for i in ids}
                    chart.options.update(build_option())
                    chart.update()
                def clear_cluster():
                    nonlocal cluster_filter
                    cluster_filter = None
                    chart.options.update(build_option())
                    chart.update()
                ui.button("View", on_click=apply_cluster).props("unelevated dense").classes(
                    "flex-1"
                ).style(f"background:{PRIMARY}; color:{SURFACE}; font-size:0.8rem;")
                ui.button("Clear", on_click=clear_cluster).props("unelevated dense").classes(
                    "flex-1"
                ).style(f"background:{BG_PANEL}; color:{PRIMARY}; border:1px solid {BORDER}; font-size:0.8rem;")

            ui.separator().style(f"background:{BORDER};")
            _section_header("Enrichments")

            for key, label in EDGE_LABELS.items():
                color = EDGE_COLORS[key]
                def make_toggle(k):
                    def toggle(e):
                        if e.value:
                            active_types.add(k)
                        else:
                            active_types.discard(k)
                        chart.options.update(build_option())
                        chart.update()
                    return toggle
                with ui.row().classes("items-center gap-2"):
                    ui.checkbox(label, value=True, on_change=make_toggle(key)).style(
                        f"color:{color};"
                    )

        # --- Chart ---
        chart = ui.echart(build_option()).classes("flex-1 h-full")

    # --- Note popup ---
    with ui.dialog() as note_dialog:
        with ui.card().classes("gap-0").style(
            f"width:540px; max-width:90vw; max-height:80vh; background:{SURFACE};"
        ):
            with ui.row().classes("w-full items-center justify-between px-5 py-3").style(
                f"border-bottom: 1px solid {BORDER};"
            ):
                note_title = ui.label("").classes("text-sm font-semibold flex-1 truncate").style(
                    f"color:{PRIMARY};"
                )
                ui.button(icon="close", on_click=note_dialog.close).props(
                    "flat dense"
                ).style(f"color:{TEXT_MUTED};")
            note_content = ui.markdown("").classes("overflow-auto p-5 text-sm").style(
                f"color:{TEXT_BODY}; max-height:calc(80vh - 60px);"
            )

    async def on_node_click(e):
        args = e.args if isinstance(e.args, dict) else {}
        node_id = args.get('name', '')
        title = args.get('value', '') or args.get('name', '')
        if not node_id or not node_id.startswith('n'):
            return
        note_title.set_text(title)
        note_content.set_content('_Loading…_')
        note_dialog.open()
        path = VAULT_DIR / (title + '.md')
        try:
            post = await run.io_bound(_fm.load, path)
            note_content.set_content(post.content or '_Empty note._')
        except Exception:
            note_content.set_content('_Could not load note._')

    chart.on('chart:click', on_node_click)


def serve():
    ui.run(title="ProseOutline", port=8080, reload=False)


if __name__ in {"__main__", "__mp_main__"}:
    serve()
