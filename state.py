from __future__ import annotations
from enum import Enum
from typing import Callable


class BuildStatus(Enum):
    IDLE            = ""
    BUILDING_STORE  = "Building knowledge base..."
    BUILDING_GRAPH  = "Indexing vault connections..."
    READY           = ""


class KnowledgeMap:
    """
    Immutable RAG infrastructure built once at startup.
    Construct via the async classmethod KnowledgeMap.build().
    """

    def __init__(self, store, graph) -> None:
        object.__setattr__(self, "_store", store)
        object.__setattr__(self, "_graph", graph)

    def __setattr__(self, name: str, value) -> None:
        raise AttributeError("KnowledgeMap is immutable after construction.")

    @classmethod
    async def build(
        cls, on_status: Callable[[BuildStatus], None] = lambda _: None
    ) -> KnowledgeMap:
        from nicegui import run
        from vault import build_or_load_store, build_graph

        on_status(BuildStatus.BUILDING_STORE)
        store = await run.io_bound(build_or_load_store)
        on_status(BuildStatus.BUILDING_GRAPH)
        graph = await run.io_bound(build_graph)
        on_status(BuildStatus.READY)
        return cls(store, graph)

    @property
    def store(self):
        return object.__getattribute__(self, "_store")

    @property
    def graph(self):
        return object.__getattribute__(self, "_graph")


# ---------------------------------------------------------------------------
# Module-level startup coordination (not part of KnowledgeMap)
# ---------------------------------------------------------------------------
build_status: BuildStatus = BuildStatus.IDLE
knowledge_map: KnowledgeMap | None = None
