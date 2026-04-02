from nicegui import ui
from theme import PRIMARY, ACCENT, BG_PAGE, BORDER, SURFACE, TEXT_BODY, TEXT_MUTED

PAGE_INDEX = "/"
PAGE_SETUP = "/setup"
PAGE_GRAPH = "/graph"


def shared_head():
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


def section_header(text: str):
    ui.label(text).classes("text-sm font-semibold tracking-wide").style(
        f"color:{PRIMARY}; letter-spacing:0.06em; text-transform:uppercase;"
    )


def section_divider():
    ui.separator().style(f"background:{BORDER};")
