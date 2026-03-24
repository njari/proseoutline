"""
experiment — composable directory-in/directory-out pipeline system.

Define an experiment by subclassing Experiment:

    from experiment import Experiment, Plug, run_experiment

    class MyRAG(Experiment):
        id         = "my-rag-v1"
        input_path = "/path/to/vault"
        plugs = [
            Plug("obsidian_ingest", order=0),
            Plug("chunk_recursive",  order=1, config={"chunk_size": 300}),
            Plug("embed_chroma",     order=2),
        ]

    run = run_experiment(MyRAG)
"""

from experiment.models import Experiment, ExperimentRun, Plug, PlugResult, RunStatus
from experiment.registry import get_plug, plug, registered_keys
from experiment.engine import run_experiment
from experiment.db import (
    _open_db,
    find_cached_result,
    list_experiments,
    list_runs,
    load_plug_results_for_run,
    upsert_experiment,
)

# Register all built-in plugs at import time.
import experiment.plugs  # noqa: F401

__all__ = [
    "Experiment",
    "ExperimentRun",
    "Plug",
    "PlugResult",
    "RunStatus",
    "plug",
    "get_plug",
    "registered_keys",
    "run_experiment",
    "_open_db",
    "find_cached_result",
    "list_experiments",
    "list_runs",
    "load_plug_results_for_run",
    "upsert_experiment",
]
