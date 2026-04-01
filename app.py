from pathlib import Path

from nicegui import ui, app as nicegui_app, run

from vault import retrieve
from generator import stream_outline, revise_outline
from articles import (
    OUTLINES_DIR, Article, slugify, list_articles,
    commit_edit, init_article_repo, current_branch,
)
from daily import scan_notes, suggest_topics
from graph_enrichment.clustering import get_cluster_notes
from graph_enrichment.graph_data import get_graph_data
import state
from state import KnowledgeMap, BuildStatus
from theme import (
    PRIMARY, ACCENT, SURFACE, BG_PAGE, BG_PANEL, BORDER,
    TEXT_BODY, TEXT_MUTED, TEXT_SUBTLE, SUCCESS, WARNING, ERROR,
)
import settings


@nicegui_app.on_startup
async def startup():
    if not settings.is_configured():
        return

    def on_status(s: BuildStatus) -> None:
        state.build_status = s

    state.knowledge_map = await KnowledgeMap.build(on_status)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
PAGE_INDEX   = "/"
PAGE_LOADING = "/loading"
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


def _build_article_list(articles_list, load_cb, open_actions_cb):
    """Populate the articles list. Call again to refresh."""
    articles_list.clear()
    with articles_list:
        for a in list_articles(OUTLINES_DIR):
            slug = a.slug
            item = ui.item(slug, on_click=lambda s=slug: load_cb(s)).classes(
                "cursor-pointer rounded-lg text-sm font-mono"
            ).style(f"color:{PRIMARY}; transition: background 0.15s;")
            item.on("dblclick", lambda e, s=slug: open_actions_cb(s))


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@ui.page(PAGE_INDEX)
def index():
    if not settings.is_configured():
        ui.navigate.to(PAGE_SETUP)
        return
    if state.knowledge_map is None:
        ui.navigate.to(PAGE_LOADING)
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
    with ui.splitter(value=18).classes("w-full h-screen") as outer:

        with outer.before:
            with ui.column().classes("w-full h-full p-4 gap-2").style(
                f"background:{BG_PANEL}; border-right: 1px solid {BORDER};"
            ):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label("Articles").classes("text-sm font-semibold tracking-wide").style(
                        f"color:{PRIMARY}; letter-spacing:0.06em; text-transform:uppercase;"
                    )
                    ui.button(icon="hub", on_click=lambda: ui.navigate.to(PAGE_GRAPH)).props(
                        "flat dense"
                    ).style(f"color:{PRIMARY};").tooltip("Explore graph")
                articles_list = ui.list().classes("w-full gap-1")

        with outer.after:
            with ui.splitter(value=72).classes("w-full h-full") as inner:

                with inner.before:
                    with ui.column().classes("w-full h-full gap-0").style(
                        f"background:{SURFACE};"
                    ):
                        with ui.row().classes("w-full items-center px-5 py-2 gap-3").style(
                            f"min-height:52px; border-bottom: 1px solid {BORDER}; background:{SURFACE};"
                        ):
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

    async def load_article(slug: str):
        article.slug = slug
        article.alias = await run.io_bound(current_branch, OUTLINES_DIR, slug)
        outline_path = OUTLINES_DIR / slug / "outline.md"
        try:
            content = await run.io_bound(outline_path.read_text, "utf-8")
        except (FileNotFoundError, OSError):
            content = ""
        editor.value = content
        article_label.set_text(slug)
        status.set_text(f"Loaded {slug}")

    async def open_actions(slug: str):
        await load_article(slug)
        action_w["feedback"].value = ""
        action_w["root"].set_visibility(True)

    def refresh_articles():
        _build_article_list(articles_list, load_article, open_actions)

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
        docs = await run.io_bound(retrieve, state.knowledge_map.store, state.knowledge_map.graph, topic)
        status.set_text(f"Generating from {len(docs)} notes…")
        editor.value = ""
        async for chunk in stream_outline(topic, docs):
            editor.value += chunk
        status.set_text("Done — edit and save when ready.")
        refresh_articles()

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
        docs = await run.io_bound(
            retrieve, state.knowledge_map.store, state.knowledge_map.graph, article.slug
        )
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
        docs = await run.io_bound(
            retrieve, state.knowledge_map.store, state.knowledge_map.graph, topic
        )
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

    refresh_articles()


@ui.page(PAGE_LOADING)
def loading():
    _shared_head()
    ui.query("body").style("margin:0; padding:0;")

    with ui.column().classes("w-full h-screen items-center justify-center gap-4").style(
        f"background:{BG_PAGE};"
    ):
        ui.spinner(size="xl", color=PRIMARY)
        status_label = ui.label("Starting up...").classes("text-sm").style(
            f"color:{PRIMARY};"
        )

    def poll():
        msg = state.build_status.value
        if msg:
            status_label.set_text(msg)
        if state.knowledge_map is not None:
            t.cancel()
            ui.navigate.to(PAGE_INDEX)

    t = ui.timer(0.5, poll)


def _shared_head():
    ui.add_head_html(f"""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;1,9..40,300&display=swap" rel="stylesheet">
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
    ui.add_head_html("""
    <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
      #graph-canvas { width: 100%; height: 100%; }
      .vis-network:focus { outline: none; }
    </style>
    """)
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

    import json
    nodes_json = json.dumps(data['nodes'])
    edges_json = json.dumps(data['edges'])
    colors_json = json.dumps(EDGE_COLORS)

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
            _section_header("Enrichments")

            for key, label in EDGE_LABELS.items():
                color = EDGE_COLORS[key]
                with ui.row().classes("items-center gap-2"):
                    cb = ui.checkbox(value=True).style(f"color:{color};")
                    ui.label(label).classes("text-sm").style(f"color:{TEXT_BODY};")
                    cb.on('update:model-value', js_handler=f"""
                        (v) => {{
                            window._graphToggle('{key}', v);
                        }}
                    """)

            ui.separator().style(f"background:{BORDER};")
            _section_header("Physics")
            physics_toggle = ui.switch("Enabled", value=True).style(f"color:{PRIMARY};")
            physics_toggle.on('update:model-value', js_handler="""
                (v) => { window._graphPhysics(v); }
            """)

            ui.separator().style(f"background:{BORDER};")
            node_label = ui.label("Click a node").classes("text-xs").style(
                f"color:{TEXT_MUTED}; word-break:break-word;"
            )

        # --- Canvas ---
        with ui.column().classes("flex-1 h-full"):
            ui.html('<div id="graph-canvas"></div>').classes("w-full h-full")

    ui.run_javascript(f"""
    (function() {{
        const allNodes = {nodes_json};
        const allEdgesByType = {edges_json};
        const colors = {colors_json};

        let edgeId = 0;
        let activeTypes = new Set(['links','tag_links','bib_coupling','cocitation']);

        const nodeDataset = new vis.DataSet(allNodes.map(n => ({{
            ...n,
            color: n.group === 'tag'
                ? {{ background:'#10b981', border:'#059669', highlight:{{background:'#34d399'}} }}
                : {{ background:'#e0f2fe', border:'#1e3a8a', highlight:{{background:'#bae6fd'}} }},
            font: {{ size: n.group === 'tag' ? 10 : 12, color: '#334155' }},
            shape: n.group === 'tag' ? 'diamond' : 'dot',
            size: n.group === 'tag' ? 8 : 12,
        }})));

        function buildEdges() {{
            let result = [];
            for (const [type, edges] of Object.entries(allEdgesByType)) {{
                if (!activeTypes.has(type)) continue;
                for (const e of edges) {{
                    result.push({{
                        ...e,
                        id: edgeId++,
                        _type: type,
                        color: {{ color: colors[type], opacity: 0.6 }},
                        width: e.value ? Math.min(1 + e.value * 0.5, 5) : 1,
                        arrows: type === 'links' ? 'to' : undefined,
                        smooth: {{ type: 'continuous' }},
                    }});
                }}
            }}
            return result;
        }}

        const edgeDataset = new vis.DataSet(buildEdges());

        const container = document.getElementById('graph-canvas');
        const network = new vis.Network(container, {{
            nodes: nodeDataset,
            edges: edgeDataset,
        }}, {{
            physics: {{ enabled: true, stabilization: {{ iterations: 150 }} }},
            interaction: {{ hover: true, tooltipDelay: 100 }},
        }});

        network.on('click', (params) => {{
            if (params.nodes.length) {{
                const node = nodeDataset.get(params.nodes[0]);
                emitEvent('node-click', node.label);
            }}
        }});

        window._graphToggle = (type, enabled) => {{
            if (enabled) activeTypes.add(type);
            else activeTypes.delete(type);
            edgeDataset.clear();
            edgeDataset.add(buildEdges());
        }};

        window._graphPhysics = (enabled) => {{
            network.setOptions({{ physics: {{ enabled }} }});
        }};
    }})();
    """)

    ui.on('node-click', lambda e: node_label.set_text(e.args))


def serve():
    ui.run(title="ProseOutline", port=8080, reload=False)


if __name__ in {"__main__", "__mp_main__"}:
    serve()
