from pathlib import Path

from nicegui import ui, run

from daily import scan_notes
import settings
from theme import PRIMARY, SURFACE, BG_PAGE, BG_PANEL, BORDER, TEXT_MUTED, SUCCESS, ERROR
from .shared import shared_head, PAGE_SETUP


def register(page_setup: str):
    @ui.page(page_setup)
    def setup():
        shared_head()
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
