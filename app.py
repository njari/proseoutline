from dotenv import load_dotenv
from nicegui import ui, app as nicegui_app, run

from vault import build_graph, build_or_load_store, retrieve
from generator import stream_outline
from articles import (
    OUTLINES_DIR, slugify, list_articles,
    read_article, commit_edit, init_article_repo,
)
from daily import get_todays_notes, suggest_topics

load_dotenv()

# ---------------------------------------------------------------------------
# Shared state — loaded once at startup
# ---------------------------------------------------------------------------
state = {"store": None, "graph": None}


@nicegui_app.on_startup
async def startup():
    state["store"] = await run.io_bound(build_or_load_store)
    state["graph"] = await run.io_bound(build_graph)


# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------
NAVY    = "#1e3a8a"   # primary buttons, headings
SKY     = "#0ea5e9"   # accents, hover highlights
SKY_LT  = "#e0f2fe"   # panel backgrounds
SKY_XLT = "#f0f9ff"   # page background
BORDER  = "#bae6fd"   # subtle borders


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

@ui.page("/")
def index():
    # ---- global styles (font + button rounding + palette) ------------------
    ui.add_head_html("""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;1,9..40,300&display=swap" rel="stylesheet">
    <style>
      * { font-family: 'DM Sans', sans-serif !important; }
      body { background: #f0f9ff !important; margin: 0; padding: 0; }
      .q-btn  { border-radius: 10px !important; }
      .q-field__control { border-radius: 10px !important; }
      .q-item { border-radius: 8px !important; }
      ::-webkit-scrollbar { width: 6px; }
      ::-webkit-scrollbar-track { background: #f0f9ff; }
      ::-webkit-scrollbar-thumb { background: #bae6fd; border-radius: 6px; }
    </style>
    """)
    ui.colors(primary=NAVY, secondary=SKY, accent=SKY)

    ctx = {"slug": None, "alias": "main"}

    editor: ui.codemirror | None = None
    article_label: ui.label | None = None
    status: ui.label | None = None
    ideas_area: ui.markdown | None = None
    notes_count_label: ui.label | None = None
    topic_input: ui.input | None = None
    articles_list: ui.list | None = None

    # -----------------------------------------------------------------------
    # File explorer helpers
    # -----------------------------------------------------------------------

    def refresh_articles():
        articles_list.clear()
        with articles_list:
            for a in list_articles(OUTLINES_DIR):
                slug = a["slug"]
                ui.item(slug, on_click=lambda s=slug: load_article(s)).classes(
                    "cursor-pointer rounded-lg text-sm font-mono"
                ).style(f"color:{NAVY}; transition: background 0.15s;")

    def load_article(slug: str):
        ctx["slug"] = slug
        ctx["alias"] = "main"
        try:
            content = read_article(OUTLINES_DIR, slug, "main")
        except RuntimeError:
            content = ""
        editor.value = content
        article_label.set_text(slug)
        status.set_text(f"Loaded {slug}")

    # -----------------------------------------------------------------------
    # Save — Flow 3
    # -----------------------------------------------------------------------

    async def on_save():
        if not ctx["slug"]:
            status.set_text("Nothing loaded.")
            return
        slug, content = ctx["slug"], editor.value
        commit = await run.io_bound(commit_edit, OUTLINES_DIR, slug, "main", content)
        status.set_text(f"Saved · {commit}")

    # -----------------------------------------------------------------------
    # Generate — Flow 2
    # -----------------------------------------------------------------------

    async def on_generate():
        topic = topic_input.value.strip()
        if not topic:
            status.set_text("Enter a topic first.")
            return
        slug = slugify(topic)
        ctx["slug"] = slug
        ctx["alias"] = "main"
        article_label.set_text(slug)
        await run.io_bound(init_article_repo, OUTLINES_DIR / slug)
        status.set_text(f"Retrieving notes for '{topic}'…")
        docs = await run.io_bound(retrieve, state["store"], state["graph"], topic)
        status.set_text(f"Generating from {len(docs)} notes…")
        editor.value = ""
        async for chunk in stream_outline(topic, docs):
            editor.value += chunk
        status.set_text("Done — edit and save when ready.")
        refresh_articles()

    # -----------------------------------------------------------------------
    # Daily ideas — Flow 1
    # -----------------------------------------------------------------------

    async def on_daily_ideas():
        ideas_area.set_content("_Loading today's notes…_")
        notes = await run.io_bound(get_todays_notes)
        count = len(notes)
        if count == 0:
            notes_count_label.set_text("No notes found for today.")
            notes_count_label.style("color:#94a3b8;")
            ideas_area.set_content("")
            return
        if count < 5:
            notes_count_label.set_text(f"{count} note{'s' if count > 1 else ''} today · too little — you might be generating nonsense!")
            notes_count_label.style("color:#f59e0b;")
        else:
            notes_count_label.set_text(f"{count} notes found today")
            notes_count_label.style(f"color:#64748b;")
        ideas = await run.io_bound(suggest_topics, notes)
        ideas_area.set_content(ideas)

    # -----------------------------------------------------------------------
    # Layout
    # -----------------------------------------------------------------------
    ui.query("body").style("margin:0; padding:0;")

    with ui.splitter(value=18).classes("w-full h-screen") as outer:

        # LEFT — article list
        with outer.before:
            with ui.column().classes("w-full h-full p-4 gap-2").style(
                f"background:{SKY_LT}; border-right: 1px solid {BORDER};"
            ):
                ui.label("Articles").classes("text-sm font-semibold tracking-wide").style(
                    f"color:{NAVY}; letter-spacing:0.06em; text-transform:uppercase;"
                )
                articles_list = ui.list().classes("w-full gap-1")
                refresh_articles()

        with outer.after:
            with ui.splitter(value=72).classes("w-full h-full") as inner:

                # CENTER — editor
                with inner.before:
                    with ui.column().classes("w-full h-full gap-0").style(
                        "background:#ffffff;"
                    ):
                        # Toolbar
                        with ui.row().classes("w-full items-center px-5 py-2 gap-3").style(
                            f"min-height:52px; border-bottom: 1px solid {BORDER}; background:#ffffff;"
                        ):
                            article_label = ui.label("").classes(
                                "text-sm font-mono flex-1 truncate"
                            ).style(f"color:{NAVY};")
                            status = ui.label("").classes("text-xs").style(
                                "color:#64748b;"
                            )
                            ui.button("Save", on_click=on_save).props(
                                "dense unelevated"
                            ).style(
                                f"background:{NAVY}; color:#ffffff; padding: 4px 18px;"
                            )

                        editor = ui.codemirror(
                            value="", language="markdown",
                        ).classes("w-full flex-1").style(
                            "background:#ffffff;"
                        )

                # RIGHT — generate panel
                with inner.after:
                    with ui.column().classes("w-full h-full p-5 gap-4").style(
                        f"background:{SKY_XLT}; border-left: 1px solid {BORDER};"
                    ):
                        # Flow 1 — Today's ideas
                        ui.label("Today's Ideas").classes("text-sm font-semibold tracking-wide").style(
                            f"color:{NAVY}; letter-spacing:0.06em; text-transform:uppercase;"
                        )
                        ui.button(
                            "Suggest from daily notes", on_click=on_daily_ideas
                        ).props("unelevated").classes("w-full").style(
                            f"background:{SKY_LT}; color:{NAVY}; border: 1px solid {BORDER};"
                        )
                        notes_count_label = ui.label("").classes("text-xs")
                        ideas_area = ui.markdown("").classes(
                            "text-sm w-full overflow-auto flex-1 p-3 rounded-xl"
                        ).style(
                            f"background:#ffffff; border: 1px solid {BORDER}; color:#334155; min-height:120px;"
                        )

                        ui.separator().style(f"background:{BORDER};")

                        # Flow 2 — Generate outline
                        ui.label("Generate Outline").classes("text-sm font-semibold tracking-wide").style(
                            f"color:{NAVY}; letter-spacing:0.06em; text-transform:uppercase;"
                        )
                        topic_input = ui.input(
                            placeholder="Article topic…"
                        ).classes("w-full").style(
                            f"color:{NAVY};"
                        )
                        ui.button("Generate", on_click=on_generate).props(
                            "unelevated"
                        ).classes("w-full").style(
                            f"background:{NAVY}; color:#ffffff;"
                        )


def serve():
    ui.run(title="ProseOutline", port=8080, reload=False)


if __name__ in {"__main__", "__mp_main__"}:
    serve()
