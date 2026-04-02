from nicegui import ui

from pages.shared import PAGE_INDEX, PAGE_SETUP, PAGE_GRAPH
import pages.index
import pages.setup
import pages.graph

pages.index.register(PAGE_INDEX)
pages.setup.register(PAGE_SETUP)
pages.graph.register(PAGE_GRAPH)


def serve():
    ui.run(title="ProseOutline", port=8080, reload=False)


if __name__ in {"__main__", "__mp_main__"}:
    serve()
