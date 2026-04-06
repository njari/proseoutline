import frontmatter as _fm

from nicegui import ui, run

from graph_enrichment.graph_data import get_graph_data
from graph_enrichment.read_files import VAULT_DIR
import settings
from theme import PRIMARY, SURFACE, BG_PANEL, BORDER, TEXT_BODY, TEXT_MUTED
from .shared import (
    shared_head, section_header, PAGE_INDEX, PAGE_SETUP,
    EDGE_COLORS, EDGE_LABELS, build_echart_option,
)


def register(page_graph: str):
    @ui.page(page_graph)
    def graph_explorer():
        if not settings.is_configured():
            ui.navigate.to(PAGE_SETUP)
            return

        shared_head()
        ui.query("body").style("margin:0; padding:0;")

        data = get_graph_data()
        active_types: set[str] = set(EDGE_COLORS.keys())

        def build_option():
            return build_echart_option(data, active_types)

        ui.add_head_html("""
        <style>
          .graph-locked  { pointer-events: all; }
          .graph-unlocked { pointer-events: none; }
        </style>
        """)

        with ui.row().classes("w-full h-screen gap-0"):

            # --- Sidebar ---
            with ui.column().classes("h-full p-5 gap-4 shrink-0").style(
                f"width:220px; background:{BG_PANEL}; border-right:1px solid {BORDER};"
            ):
                ui.button("Back", on_click=lambda: ui.navigate.to(PAGE_INDEX)).props(
                    "unelevated dense no-caps"
                ).style(f"background:{BG_PANEL}; color:{PRIMARY}; border:1px solid {BORDER};")
                ui.label("Graph Explorer").classes("text-sm font-semibold tracking-wide").style(
                    f"color:{PRIMARY}; letter-spacing:0.06em; text-transform:uppercase;"
                )

                ui.separator().style(f"background:{BORDER};")
                section_header("Enrichments")
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
            chart = ui.echart(build_option()).classes("flex-1 h-full graph-locked")

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
            args = e.data if isinstance(e.data, dict) else {}
            node_id = args.get('name', '')
            title = args.get('value', '') or args.get('name', '')
            if not node_id or not node_id.startswith('n'):
                await ui.run_javascript(
                    "document.querySelector('.graph-locked')?.classList.replace('graph-locked','graph-unlocked')"
                )
                return
            await ui.run_javascript(
                "document.querySelector('.graph-unlocked')?.classList.replace('graph-unlocked','graph-locked')"
            )
            note_title.set_text(title)
            note_content.set_content('_Loading…_')
            note_dialog.open()
            path = VAULT_DIR / (title + '.md')
            try:
                post = await run.io_bound(_fm.load, path)
                note_content.set_content(post.content or '_Empty note._')
            except Exception:
                note_content.set_content('_Could not load note._')

        chart.on_point_click(on_node_click)
