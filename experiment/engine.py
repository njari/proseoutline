"""
experiment/engine.py — execution engine for Experiment pipelines.

Public API
----------
run_experiment(experiment_cls, force=False) -> ExperimentRun
    Run all Plugs defined on an Experiment subclass sequentially,
    passing each plug's output directory as the next plug's input.
    Idempotent by default: plugs whose input directory hash matches a prior
    successful run are skipped and their cached output is reused.
"""

import hashlib
import shutil
import traceback
from datetime import datetime, timezone
from pathlib import Path

from experiment.db import (
    EXPERIMENTS_ROOT,
    _open_db,
    find_cached_result,
    load_plug_results_for_run,
    save_plug_result,
    save_run,
    update_plug_result,
    update_run_status,
    upsert_experiment,
)
from experiment.models import Experiment, ExperimentRun, Plug, PlugResult, RunStatus
from experiment.registry import get_plug


# ---------------------------------------------------------------------------
# Directory hashing — mirrors datalayer._hash_file extended to directories
# ---------------------------------------------------------------------------

def _hash_directory(path: Path) -> str:
    """
    Deterministic SHA-256 of all files in `path`, sorted by relative path.
    Mirrors the 65536-byte chunk loop in datalayer._hash_file.
    Returns a fixed sentinel hash for empty/non-existent directories.
    """
    h = hashlib.sha256()
    if not path.exists():
        return h.hexdigest()
    files = sorted(f for f in path.rglob("*") if f.is_file())
    if not files:
        return h.hexdigest()
    for f in files:
        rel = str(f.relative_to(path))
        h.update(rel.encode())
        with open(f, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate(experiment_cls: type[Experiment]) -> None:
    missing = [
        attr for attr in ("id", "input_path", "plugs")
        if not hasattr(experiment_cls, attr)
    ]
    if missing:
        raise ValueError(
            f"{experiment_cls.__name__} is missing required class attributes: {missing}"
        )
    if not experiment_cls.plugs:
        raise ValueError(f"{experiment_cls.__name__}.plugs must not be empty.")


def _mark_remaining_failed(
    con, run: ExperimentRun, plugs: list[Plug], after_order: int
) -> None:
    """Write FAILED PlugResult rows for all plugs after `after_order`."""
    for p in sorted(plugs, key=lambda x: x.order):
        if p.order <= after_order:
            continue
        output_dir = (
            EXPERIMENTS_ROOT
            / run.experiment_id
            / f"step_{p.order:02d}_{p.plug_key}"
        )
        result = PlugResult(
            run_id=run.run_id,
            plug_id=p.plug_id,
            plug_key=p.plug_key,
            order=p.order,
            input_path="",
            output_path=str(output_dir),
            status=RunStatus.FAILED,
            input_hash="",
            started_at=_now(),
            finished_at=_now(),
            error="upstream plug failed",
        )
        save_plug_result(con, result)
        run.plug_results.append(result)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_experiment(
    experiment_cls: type[Experiment],
    force: bool = False,
) -> ExperimentRun:
    """
    Execute all plugs defined on `experiment_cls` in order.

    Parameters
    ----------
    experiment_cls : type[Experiment]
        An Experiment subclass (not an instance).
    force : bool
        If True, re-run all plugs regardless of cached results.

    Returns
    -------
    ExperimentRun
        The completed run record with all PlugResults attached.
    """
    _validate(experiment_cls)

    con = _open_db()
    try:
        upsert_experiment(con, experiment_cls)

        workspace = EXPERIMENTS_ROOT / experiment_cls.id
        workspace.mkdir(parents=True, exist_ok=True)

        run = ExperimentRun(
            experiment_id=experiment_cls.id,
            status=RunStatus.RUNNING,
        )
        save_run(con, run)

        current_input = Path(experiment_cls.input_path)
        plugs = sorted(experiment_cls.plugs, key=lambda p: p.order)

        for plug_def in plugs:
            input_hash = _hash_directory(current_input)
            output_dir = workspace / f"step_{plug_def.order:02d}_{plug_def.plug_key}"

            # --- Idempotency check ---
            if not force:
                cached = find_cached_result(con, plug_def.plug_id, input_hash)
                if cached is not None:
                    result = PlugResult(
                        run_id=run.run_id,
                        plug_id=plug_def.plug_id,
                        plug_key=plug_def.plug_key,
                        order=plug_def.order,
                        input_path=str(current_input),
                        output_path=cached.output_path,
                        status=RunStatus.SKIPPED,
                        input_hash=input_hash,
                        started_at=_now(),
                        finished_at=_now(),
                    )
                    save_plug_result(con, result)
                    run.plug_results.append(result)
                    current_input = Path(cached.output_path)
                    print(
                        f"[experiment] SKIPPED {plug_def.plug_key} "
                        f"(input unchanged, reusing {cached.output_path})"
                    )
                    continue

            # --- Prepare output directory ---
            if output_dir.exists():
                shutil.rmtree(output_dir)
            output_dir.mkdir(parents=True)

            plug_fn = get_plug(plug_def.plug_key)
            result = PlugResult(
                run_id=run.run_id,
                plug_id=plug_def.plug_id,
                plug_key=plug_def.plug_key,
                order=plug_def.order,
                input_path=str(current_input),
                output_path=str(output_dir),
                status=RunStatus.RUNNING,
                input_hash=input_hash,
                started_at=_now(),
            )
            save_plug_result(con, result)

            try:
                print(f"[experiment] RUNNING {plug_def.plug_key} ...")
                plug_fn(current_input, output_dir, plug_def.config)
                result.status = RunStatus.SUCCESS
                result.finished_at = _now()
                current_input = output_dir
                print(f"[experiment] SUCCESS {plug_def.plug_key}")
            except Exception:
                result.status = RunStatus.FAILED
                result.error = traceback.format_exc()
                result.finished_at = _now()
                update_plug_result(con, result)
                run.plug_results.append(result)
                print(f"[experiment] FAILED  {plug_def.plug_key}\n{result.error}")
                _mark_remaining_failed(con, run, plugs, plug_def.order)
                run.status = RunStatus.FAILED
                break

            update_plug_result(con, result)
            run.plug_results.append(result)
        else:
            run.status = RunStatus.SUCCESS

        run.finished_at = _now()
        update_run_status(con, run.run_id, run.status, run.finished_at)
        print(f"[experiment] RUN {run.status.value.upper()} ({run.run_id})")
        return run

    finally:
        con.close()
