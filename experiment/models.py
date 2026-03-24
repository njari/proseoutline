import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class RunStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED  = "failed"
    SKIPPED = "skipped"   # idempotent — input dir unchanged


@dataclass
class Plug:
    plug_key: str
    order: int
    config: dict = field(default_factory=dict)
    plug_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class Experiment:
    """
    Base class for pipeline definitions. Subclass to define an experiment.

    Example::

        class MyRAG(Experiment):
            id         = "my-rag-v1"
            input_path = "/path/to/vault"
            plugs = [
                Plug("obsidian_ingest", order=0),
                Plug("chunk_recursive", order=1, config={"chunk_size": 300}),
                Plug("embed_chroma",    order=2),
            ]
    """
    id: str           # stable unique string — must be defined in subclass
    input_path: str   # source directory — must be defined in subclass
    plugs: list[Plug] = []


@dataclass
class PlugResult:
    run_id: str
    plug_id: str
    plug_key: str
    order: int
    input_path: str
    output_path: str
    status: RunStatus
    input_hash: str
    started_at: str
    finished_at: str | None = None
    error: str | None = None
    result_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class ExperimentRun:
    experiment_id: str   # = Experiment subclass .id
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: RunStatus = RunStatus.PENDING
    started_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    finished_at: str | None = None
    plug_results: list[PlugResult] = field(default_factory=list)
