from nicegui import ui, run

from generator import stream_outline, revise_outline
from articles import OUTLINES_DIR, Article, slugify, commit_edit, init_article_repo, current_branch
from daily import suggest_topics
from graph_enrichment.clustering import get_cluster_notes
from graph_enrichment.embeddings import retrieve
from theme import (
    PRIMARY, ACCENT, SURFACE, BG_PAGE, BG_PANEL, BORDER,
    TEXT_BODY, TEXT_MUTED, TEXT_SUBTLE,
)
import settings
from .shared import shared_head, section_header, section_divider, PAGE_SETUP, PAGE_GRAPH


def _section_cluster_browse() -> dict:
    section_header("Browse Cluster")
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
    section_header("Generate Outline")
    topic_input = ui.input(placeholder="Article topic…").classes("w-full").style(
        f"color:{PRIMARY};"
    )
    btn = ui.button("Generate").props("unelevated").classes("w-full").style(
        f"background:{PRIMARY}; color:{SURFACE};"
    )
    return {"btn": btn, "topic_input": topic_input}


def _section_article_actions() -> dict:
    root = ui.column().classes("w-full gap-3")
    with root:
        section_divider()
        section_header("Article Actions")
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


def register(page_index: str):
    @ui.page(page_index)
    def index():
        if not settings.is_configured():
            ui.navigate.to(PAGE_SETUP)
            return

        shared_head()
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

        with ui.splitter(value=72).classes("w-full h-screen") as inner:

            with inner.before:
                with ui.column().classes("w-full h-full gap-0").style(f"background:{SURFACE};"):
                    with ui.row().classes("w-full items-center px-5 py-2 gap-3").style(
                        f"min-height:52px; border-bottom: 1px solid {BORDER}; background:{SURFACE};"
                    ):
                        ui.button(icon="hub", on_click=lambda: ui.navigate.to(PAGE_GRAPH)).props(
                            "flat dense"
                        ).style(f"color:{PRIMARY};").tooltip("Graph Explorer")
                        article_label = ui.label("").classes(
                            "text-sm font-mono flex-1 truncate"
                        ).style(f"color:{PRIMARY};")
                        status = ui.label("").classes("text-xs").style(f"color:{TEXT_MUTED};")
                        save_btn = ui.button("Save").props("dense unelevated").style(
                            f"background:{PRIMARY}; color:{SURFACE}; padding: 4px 18px;"
                        )
                    editor = ui.codemirror(
                        value="", language="markdown", line_wrapping=True,
                    ).classes("w-full flex-1").style(f"background:{SURFACE};")

            with inner.after:
                with ui.column().classes("w-full h-full p-5 gap-4").style(
                    f"background:{BG_PAGE}; border-left: 1px solid {BORDER};"
                ):
                    daily_w  = _section_cluster_browse()
                    section_divider()
                    gen_w    = _section_generate()
                    action_w = _section_article_actions()

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

        save_btn.on("click", on_save)
        daily_w["btn"].on("click", on_browse_cluster)
        gen_w["btn"].on("click", on_generate)
        action_w["improve_btn"].on("click", on_improve)
        action_w["direction_btn"].on("click", on_new_direction)
