from nicegui import ui, run

from daily import suggest_topics
from graph_enrichment.realtimeclustering import cluster_realtime, get_working_set_note_ids
from graph_enrichment.graph_data import get_graph_data_for_note_ids
from graph_enrichment.embeddings import sync_and_embed
from theme import (
    PRIMARY, ACCENT, SURFACE, BG_PAGE, BG_PANEL, BORDER,
    TEXT_BODY, TEXT_MUTED,
)
import settings
from .shared import shared_head, PAGE_SETUP, PAGE_GRAPH, render_graph_panel


def register(page_index: str):
    @ui.page(page_index)
    def index():
        if not settings.is_configured():
            ui.navigate.to(PAGE_SETUP)
            return

        shared_head()
        ui.add_head_html(f"""
        <style>
          ::-webkit-scrollbar {{ width: 5px; }}
          ::-webkit-scrollbar-track {{ background: transparent; }}
          ::-webkit-scrollbar-thumb {{ background: {BORDER}; border-radius: 6px; }}
        </style>
        """)
        ui.query("body").style("margin:0; padding:0; overflow:hidden;")

        _clusters: list[list[dict]] = []

        # ── Full-screen column ────────────────────────────────────────────────
        with ui.column().classes("w-full h-screen gap-0"):

            # ── Middle row: insights | graph | icon strip ─────────────────────
            with ui.row().classes("w-full gap-0").style("height:85vh; min-height:0;"):

                # LEFT — insights panel
                with ui.column().classes("h-full p-5 gap-4 overflow-y-auto shrink-0").style(
                    f"width:300px; background:{BG_PANEL}; border-right:1px solid {BORDER};"
                ):
                    ui.label("Insights").classes("text-xs font-semibold tracking-widest").style(
                        f"color:{PRIMARY}; text-transform:uppercase; letter-spacing:0.12em;"
                    )
                    insights_area = ui.markdown(
                        "_Run **Find insights** to generate ideas from the highlighted cluster._"
                    ).classes("text-sm leading-relaxed").style(f"color:{TEXT_BODY};")

                # CENTER — graph fills remaining space
                with ui.column().classes("flex-1 h-full gap-0").style(f"background:{BG_PAGE};"):
                    graph_panel = render_graph_panel("flex-1 h-full")

                # RIGHT — icon strip
                with ui.column().classes("h-full items-center py-5 gap-5 shrink-0").style(
                    f"width:56px; background:{BG_PANEL}; border-left:1px solid {BORDER};"
                ):
                    ui.button(on_click=lambda: ui.navigate.to(PAGE_GRAPH)).props(
                        "flat round dense icon=account_tree"
                    ).style(f"color:{PRIMARY}; font-size:1.3rem;").tooltip("Full graph view")

                    embed_spinner = ui.spinner("dots", size="sm").style(f"color:{ACCENT};")
                    embed_spinner.set_visibility(False)

                    async def on_embed():
                        embed_spinner.set_visibility(True)
                        await run.io_bound(sync_and_embed)
                        embed_spinner.set_visibility(False)

                    ui.button(on_click=on_embed).props(
                        "flat round dense icon=sync"
                    ).style(f"color:{PRIMARY}; font-size:1.3rem;").tooltip("Re-embed notes")

            # ── Bottom bar ────────────────────────────────────────────────────
            with ui.row().classes("w-full items-center px-6 gap-4 shrink-0").style(
                f"background:{SURFACE}; border-top:1px solid {BORDER}; height:15vh;"
            ):
                status_label = ui.label("").classes("text-xs flex-1").style(f"color:{TEXT_MUTED};")

                cluster_select = ui.select(options=[], label="Cluster").props(
                    "outlined dense hide-dropdown-icon"
                ).style(f"min-width:170px; color:{PRIMARY}; font-size:0.85rem;")
                cluster_select.set_visibility(False)

                clusters_btn = ui.button("See related note clusters").props(
                    "unelevated no-caps"
                ).style(f"background:{BG_PANEL}; color:{PRIMARY}; border:1px solid {BORDER};")

                find_btn = ui.button("Find insights").props(
                    "unelevated no-caps"
                ).style(f"background:{PRIMARY}; color:{SURFACE};")

        # ── Handlers ─────────────────────────────────────────────────────────

        def _highlight_cluster(cluster_notes: list[dict]):
            graph_panel["set_highlight"]({f'n{n["id"]}' for n in cluster_notes})

        async def on_load_clusters():
            status_label.set_text("Clustering working set…")
            clusters = await run.io_bound(cluster_realtime)
            _clusters.clear()
            _clusters.extend(clusters)
            if not clusters:
                status_label.set_text("No recent notes with embeddings. Try re-embedding first.")
                cluster_select.set_visibility(False)
                return
            working_ids = await run.io_bound(get_working_set_note_ids)
            data = await run.io_bound(get_graph_data_for_note_ids, working_ids)
            graph_panel["set_data"](data)
            options = {i: f"Cluster {i+1}  ({len(c)} notes)" for i, c in enumerate(clusters)}
            cluster_select.set_options(options, value=0)
            cluster_select.set_visibility(True)
            status_label.set_text(f"{len(clusters)} clusters · last 30 days")
            _highlight_cluster(clusters[0])

        async def on_cluster_change(e):
            idx = cluster_select.value
            if idx is None or not _clusters or idx >= len(_clusters):
                return
            _highlight_cluster(_clusters[idx])

        async def on_find_insights():
            idx = cluster_select.value
            if idx is None or not _clusters:
                insights_area.set_content("_Load clusters first._")
                return
            notes = _clusters[idx]
            insights_area.set_content(f"_Generating insights for cluster {idx + 1}…_")
            ideas = await run.io_bound(suggest_topics, notes)
            insights_area.set_content(ideas)

        clusters_btn.on("click", on_load_clusters)
        cluster_select.on("update:model-value", on_cluster_change)
        find_btn.on("click", on_find_insights)
