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
import json
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
# Pre-scan helpers
# ---------------------------------------------------------------------------

def _is_excalidraw(path: Path) -> bool:
    """Read just the frontmatter of a .md file and check for excalidraw tag."""
    import re
    import yaml
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            head = "".join(f.readline() for _ in range(40))
        match = re.match(r"^---\r?\n(.*?)\r?\n---", head, re.DOTALL)
        if not match:
            return False
        meta = yaml.safe_load(match.group(1)) or {}
        tags = meta.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        return any("excalidraw" in str(t).lower() for t in tags)
    except Exception:
        return False


def _prescan(input_path: Path, n: int | None) -> list[Path]:
    """
    Walk input_path for .md files, exclude excalidraw files by frontmatter,
    and return the first `n` paths (all if n is None).
    """
    selected: list[Path] = []
    for md_path in sorted(input_path.rglob("*.md")):
        if _is_excalidraw(md_path):
            continue
        selected.append(md_path)
        if n is not None and len(selected) >= n:
            break
    return selected


def _load_file(path: Path, vault_root: Path) -> dict | None:
    """Read a single .md file and return a JSON-serialisable record."""
    import re
    import yaml
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?", text, re.DOTALL)
    if match:
        try:
            meta = yaml.safe_load(match.group(1)) or {}
        except Exception:
            meta = {}
        body = text[match.end():]
    else:
        meta, body = {}, text
    return {
        "source":   str(path),
        "name":     meta.get("title") or path.stem,
        "content":  body,
        "metadata": meta,
    }


# ---------------------------------------------------------------------------
# Built-in loading step
# ---------------------------------------------------------------------------

def _record_load_result(
    con,
    run: ExperimentRun,
    load_plug_id: str,
    input_path: Path,
    output_path: Path,
    input_hash: str,
    status: RunStatus,
) -> None:
    result = PlugResult(
        run_id=run.run_id,
        plug_id=load_plug_id,
        plug_key="__loaded",
        order=-1,
        input_path=str(input_path),
        output_path=str(output_path),
        status=status,
        input_hash=input_hash,
        started_at=_now(),
        finished_at=_now(),
    )
    save_plug_result(con, result)
    run.plug_results.append(result)


def _load_vault(
    con,
    run: ExperimentRun,
    experiment_cls,
    workspace: Path,
    force: bool,
    limit: int | None = None,
) -> Path:
    """
    Pre-scan the vault (frontmatter only) to exclude excalidraw files, load
    the first (limit + 50) candidates, write one JSON file per note to
    workspace/loaded/, then trim to `limit`. Returns that directory.
    Idempotent: skipped if input_path hash is unchanged and force=False.
    """
    import re as _re

    loaded_dir   = workspace / "loaded"
    input_path   = Path(experiment_cls.input_path)
    input_hash   = _hash_directory(input_path)
    load_plug_id = f"{experiment_cls.id}::loaded"

    if not force:
        cached = find_cached_result(con, load_plug_id, input_hash)
        if cached is not None:
            print("[experiment] SKIPPED loaded (input unchanged)")
            _record_load_result(
                con, run, load_plug_id, input_path,
                Path(cached.output_path), input_hash, RunStatus.SKIPPED,
            )
            return Path(cached.output_path)

    if loaded_dir.exists():
        shutil.rmtree(loaded_dir)
    loaded_dir.mkdir(parents=True)

    # 1. Pre-scan: filter excalidraw, fetch limit+50 candidates
    n_to_scan = (limit + 50) if limit is not None else None
    candidates = _prescan(input_path, n_to_scan)
    print(f"[experiment] pre-scan selected {len(candidates)} file(s) (excalidraw excluded)")

    # 2. Load candidates fully, trim to limit
    records = [r for p in candidates if (r := _load_file(p, input_path)) is not None]
    if limit is not None:
        records = records[:limit]

    # 3. Write JSON output
    for record in records:
        source = record["source"]
        raw_stem  = Path(source).stem
        safe_stem = _re.sub(r"[^a-zA-Z0-9_-]", "_", raw_stem)[:80]
        short_hash = hashlib.sha256(source.encode()).hexdigest()[:8]
        out_file = loaded_dir / f"{safe_stem}_{short_hash}.json"
        print(record)
        print("__________________________")
        # out_file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    _record_load_result(
        con, run, load_plug_id, input_path,
        loaded_dir, input_hash, RunStatus.SUCCESS,
    )
    print(f"[experiment] LOADED {len(records)} docs → {loaded_dir}")
    return loaded_dir


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
    limit: int | None = None,
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

        current_input = _load_vault(con, run, experiment_cls, workspace, force, limit)
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
