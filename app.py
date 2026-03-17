import os
from datetime import date
from pathlib import Path

import frontmatter as fm
from dotenv import load_dotenv, set_key
from nicegui import ui, app as nicegui_app, run

from vault import retrieve
from generator import stream_outline
from articles import (
    OUTLINES_DIR, slugify, list_articles,
    read_article, commit_edit, init_article_repo,
)
from daily import get_todays_notes, suggest_topics
import state
from state import KnowledgeMap, BuildStatus
from theme import (
    PRIMARY, ACCENT, SURFACE, BG_PAGE, BG_PANEL, BORDER,
    TEXT_BODY, TEXT_MUTED, TEXT_SUBTLE, SUCCESS, WARNING, ERROR,
)

load_dotenv()

ENV_PATH = Path(__file__).parent / ".env"
OPEN_API_KEY = "OPENAI_API_KEY"
VAULT_DIR = "DOCS_DIR"


def is_configured() -> bool:
    return bool(os.getenv(OPEN_API_KEY)) and bool(os.getenv(VAULT_DIR))


@nicegui_app.on_startup
async def startup():
    if not is_configured():
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


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

@ui.page(PAGE_INDEX)
def index():
    if not is_configured():
        ui.navigate.to(PAGE_SETUP)
        return
    if state.knowledge_map is None:
        ui.navigate.to(PAGE_LOADING)
        return
    # ---- global styles (font + button rounding + palette) ------------------
    _shared_head()
    ui.add_head_html(f"""
    <style>
      .q-item {{ border-radius: 8px !important; }}
      ::-webkit-scrollbar {{ width: 6px; }}
      ::-webkit-scrollbar-track {{ background: {BG_PAGE}; }}
      ::-webkit-scrollbar-thumb {{ background: {BORDER}; border-radius: 6px; }}
    </style>
    """)

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
                ).style(f"color:{PRIMARY}; transition: background 0.15s;")

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
        docs = await run.io_bound(retrieve, state.knowledge_map.store, state.knowledge_map.graph, topic)
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
        ideas_area.set_content("_Loading notes from the last 7 days…_")
        notes = await run.io_bound(get_todays_notes)
        count = len(notes)
        if count == 0:
            notes_count_label.set_text("No notes found in the last 7 days.")
            notes_count_label.style(f"color:{TEXT_SUBTLE};")
            ideas_area.set_content("")
            return
        if count < 5:
            notes_count_label.set_text(f"{count} note{'s' if count > 1 else ''} this week · too little — you might be generating nonsense!")
            notes_count_label.style(f"color:{WARNING};")
        else:
            notes_count_label.set_text(f"{count} notes found this week")
            notes_count_label.style(f"color:{TEXT_MUTED};")
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
                f"background:{BG_PANEL}; border-right: 1px solid {BORDER};"
            ):
                ui.label("Articles").classes("text-sm font-semibold tracking-wide").style(
                    f"color:{PRIMARY}; letter-spacing:0.06em; text-transform:uppercase;"
                )
                articles_list = ui.list().classes("w-full gap-1")
                refresh_articles()

        with outer.after:
            with ui.splitter(value=72).classes("w-full h-full") as inner:

                # CENTER — editor
                with inner.before:
                    with ui.column().classes("w-full h-full gap-0").style(
                        f"background:{SURFACE};"
                    ):
                        # Toolbar
                        with ui.row().classes("w-full items-center px-5 py-2 gap-3").style(
                            f"min-height:52px; border-bottom: 1px solid {BORDER}; background:{SURFACE};"
                        ):
                            article_label = ui.label("").classes(
                                "text-sm font-mono flex-1 truncate"
                            ).style(f"color:{PRIMARY};")
                            status = ui.label("").classes("text-xs").style(
                                f"color:{TEXT_MUTED};"
                            )
                            ui.button("Save", on_click=on_save).props(
                                "dense unelevated"
                            ).style(
                                f"background:{PRIMARY}; color:{SURFACE}; padding: 4px 18px;"
                            )

                        editor = ui.codemirror(
                            value="", language="markdown",
                        ).classes("w-full flex-1").style(
                            f"background:{SURFACE};"
                        )

                # RIGHT — generate panel
                with inner.after:
                    with ui.column().classes("w-full h-full p-5 gap-4").style(
                        f"background:{BG_PAGE}; border-left: 1px solid {BORDER};"
                    ):
                        # Flow 1 — Today's ideas
                        ui.label("Today's Ideas").classes("text-sm font-semibold tracking-wide").style(
                            f"color:{PRIMARY}; letter-spacing:0.06em; text-transform:uppercase;"
                        )
                        ui.button(
                            "Suggest from daily notes", on_click=on_daily_ideas
                        ).props("unelevated").classes("w-full").style(
                            f"background:{BG_PANEL}; color:{PRIMARY}; border: 1px solid {BORDER};"
                        )
                        notes_count_label = ui.label("").classes("text-xs")
                        ideas_area = ui.markdown("").classes(
                            "text-sm w-full overflow-auto flex-1 p-3 rounded-xl"
                        ).style(
                            f"background:{SURFACE}; border: 1px solid {BORDER}; color:{TEXT_BODY}; min-height:120px;"
                        )

                        ui.separator().style(f"background:{BORDER};")

                        # Flow 2 — Generate outline
                        ui.label("Generate Outline").classes("text-sm font-semibold tracking-wide").style(
                            f"color:{PRIMARY}; letter-spacing:0.06em; text-transform:uppercase;"
                        )
                        topic_input = ui.input(
                            placeholder="Article topic…"
                        ).classes("w-full").style(
                            f"color:{PRIMARY};"
                        )
                        ui.button("Generate", on_click=on_generate).props(
                            "unelevated"
                        ).classes("w-full").style(
                            f"background:{PRIMARY}; color:{SURFACE};"
                        )


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


def _scan_vault_for_today(vault_path: str) -> list[str]:
    """Return stems of notes created today in the given vault directory."""
    today = date.today().isoformat()
    skip_dirs = {"Daily", "Templates"}
    titles = []
    for md_file in Path(vault_path).rglob("*.md"):
        if any(part in skip_dirs for part in md_file.parts):
            continue
        try:
            post = fm.load(md_file)
            if today in str(post.metadata.get("created", "")):
                titles.append(md_file.stem)
        except Exception:
            continue
    return titles


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
            # Header
            ui.label("ProseOutline").classes("text-3xl font-semibold").style(
                f"color:{PRIMARY};"
            )
            ui.label(
                "Connect your Obsidian vault to get started."
            ).classes("text-sm").style(f"color:{TEXT_MUTED};")

            ui.separator().style(f"background:{BORDER};")

            # Inputs — pre-fill from saved config
            vault_input = ui.input(
                label="Obsidian vault folder path",
                placeholder="/Users/you/Documents/MyVault",
                value=os.getenv(VAULT_DIR, ""),
            ).classes("w-full")

            api_input = ui.input(
                label="OpenAI API key",
                placeholder="sk-...",
                password=False,
                password_toggle_button=False,
                value=os.getenv(OPEN_API_KEY, ""),
            ).classes("w-full")

            # Verify button
            async def on_verify():
                vault_path = vault_input.value.strip()
                if not vault_path or not Path(vault_path).is_dir():
                    result_label.set_text("That path doesn't exist — double-check it.")
                    result_label.style(f"color:{ERROR};")
                    save_btn.disable()
                    return
                result_label.set_text("Scanning vault…")
                result_label.style(f"color:{TEXT_MUTED};")
                titles = await run.io_bound(_scan_vault_for_today, vault_path)
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

            # Save
            def on_save():
                vault_path = vault_input.value.strip()
                api_key = api_input.value.strip()
                if not vault_path or not api_key:
                    result_label.set_text("Please fill in both fields before saving.")
                    result_label.style(f"color:{ERROR};")
                    return
                ENV_PATH.touch()
                set_key(str(ENV_PATH), VAULT_DIR, vault_path)
                set_key(str(ENV_PATH), OPEN_API_KEY, api_key)
                result_label.set_text(
                    "Config saved! Restart ProseOutline to begin."
                )
                result_label.style(f"color:{PRIMARY};")
                save_btn.disable()

            save_btn = ui.button("Save & Continue", on_click=on_save).props(
                "unelevated"
            ).classes("w-full").style(f"background:{PRIMARY}; color:{SURFACE};")
            if not (os.getenv(VAULT_DIR) and os.getenv(OPEN_API_KEY)):
                save_btn.disable()


def serve():
    ui.run(title="ProseOutline", port=8080, reload=False)


if __name__ in {"__main__", "__mp_main__"}:
    serve()
