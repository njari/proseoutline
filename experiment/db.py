"""
experiment/db.py — SQLite helpers for experiment run tracking.

Mirrors datalayer.py's _open_db() pattern: tables are created on first call,
a single connection is returned, and the caller is responsible for closing it.

Constants
---------
EXPERIMENTS_DB   : str   — path to experiment.db
EXPERIMENTS_ROOT : Path  — root workspace directory for output directories
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from experiment.models import Experiment, ExperimentRun, Plug, PlugResult, RunStatus

_BASE_DIR        = Path(__file__).parent.parent   # project root
EXPERIMENTS_DB   = str(_BASE_DIR / "experiment.db")
EXPERIMENTS_ROOT = _BASE_DIR / "experiments"


# ---------------------------------------------------------------------------
# Connection / schema bootstrap
# ---------------------------------------------------------------------------

def _open_db() -> sqlite3.Connection:
    con = sqlite3.connect(EXPERIMENTS_DB)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS experiments (
            experiment_id  TEXT PRIMARY KEY,
            name           TEXT NOT NULL,
            input_path     TEXT NOT NULL,
            first_run_at   TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS experiment_runs (
            run_id         TEXT PRIMARY KEY,
            experiment_id  TEXT NOT NULL REFERENCES experiments(experiment_id),
            status         TEXT NOT NULL,
            started_at     TEXT NOT NULL,
            finished_at    TEXT
        );

        CREATE TABLE IF NOT EXISTS plug_results (
            result_id      TEXT PRIMARY KEY,
            run_id         TEXT NOT NULL REFERENCES experiment_runs(run_id),
            plug_id        TEXT NOT NULL,
            plug_key       TEXT NOT NULL,
            "order"        INTEGER NOT NULL,
            input_path     TEXT NOT NULL,
            output_path    TEXT NOT NULL,
            status         TEXT NOT NULL,
            input_hash     TEXT NOT NULL,
            started_at     TEXT NOT NULL,
            finished_at    TEXT,
            error          TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_plug_idempotency
            ON plug_results (plug_id, input_hash, status);
    """)
    con.commit()
    return con


# ---------------------------------------------------------------------------
# Experiment registration
# ---------------------------------------------------------------------------

def upsert_experiment(con: sqlite3.Connection, experiment_cls: type[Experiment]) -> None:
    """Register an experiment class in the DB on its first run (no-op on re-runs)."""
    now = datetime.now(timezone.utc).isoformat()
    con.execute(
        """INSERT INTO experiments (experiment_id, name, input_path, first_run_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(experiment_id) DO NOTHING""",
        (experiment_cls.id, experiment_cls.__name__, experiment_cls.input_path, now),
    )
    con.commit()


def list_experiments(con: sqlite3.Connection) -> list[dict]:
    rows = con.execute(
        "SELECT experiment_id, name, input_path, first_run_at FROM experiments"
    ).fetchall()
    return [
        {"experiment_id": r[0], "name": r[1], "input_path": r[2], "first_run_at": r[3]}
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Run helpers
# ---------------------------------------------------------------------------

def save_run(con: sqlite3.Connection, run: ExperimentRun) -> None:
    con.execute(
        """INSERT INTO experiment_runs (run_id, experiment_id, status, started_at, finished_at)
           VALUES (?, ?, ?, ?, ?)""",
        (run.run_id, run.experiment_id, run.status.value, run.started_at, run.finished_at),
    )
    con.commit()


def update_run_status(
    con: sqlite3.Connection,
    run_id: str,
    status: RunStatus,
    finished_at: str | None = None,
) -> None:
    con.execute(
        "UPDATE experiment_runs SET status = ?, finished_at = ? WHERE run_id = ?",
        (status.value, finished_at, run_id),
    )
    con.commit()


def list_runs(con: sqlite3.Connection, experiment_id: str) -> list[ExperimentRun]:
    rows = con.execute(
        "SELECT run_id, experiment_id, status, started_at, finished_at "
        "FROM experiment_runs WHERE experiment_id = ? ORDER BY started_at",
        (experiment_id,),
    ).fetchall()
    return [
        ExperimentRun(
            experiment_id=r[1],
            run_id=r[0],
            status=RunStatus(r[2]),
            started_at=r[3],
            finished_at=r[4],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# PlugResult helpers
# ---------------------------------------------------------------------------

def save_plug_result(con: sqlite3.Connection, result: PlugResult) -> None:
    con.execute(
        """INSERT INTO plug_results
           (result_id, run_id, plug_id, plug_key, "order",
            input_path, output_path, status, input_hash,
            started_at, finished_at, error)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            result.result_id, result.run_id, result.plug_id, result.plug_key,
            result.order, result.input_path, result.output_path,
            result.status.value, result.input_hash,
            result.started_at, result.finished_at, result.error,
        ),
    )
    con.commit()


def update_plug_result(con: sqlite3.Connection, result: PlugResult) -> None:
    con.execute(
        """UPDATE plug_results
           SET status = ?, finished_at = ?, error = ?, output_path = ?
           WHERE result_id = ?""",
        (result.status.value, result.finished_at, result.error,
         result.output_path, result.result_id),
    )
    con.commit()


def find_cached_result(
    con: sqlite3.Connection, plug_id: str, input_hash: str
) -> PlugResult | None:
    """Return the most recent SUCCESS result for this plug_id + input_hash, or None."""
    row = con.execute(
        """SELECT result_id, run_id, plug_id, plug_key, "order",
                  input_path, output_path, status, input_hash,
                  started_at, finished_at, error
           FROM plug_results
           WHERE plug_id = ? AND input_hash = ? AND status = 'success'
           ORDER BY finished_at DESC
           LIMIT 1""",
        (plug_id, input_hash),
    ).fetchone()
    if row is None:
        return None
    return PlugResult(
        result_id=row[0], run_id=row[1], plug_id=row[2], plug_key=row[3],
        order=row[4], input_path=row[5], output_path=row[6],
        status=RunStatus(row[7]), input_hash=row[8],
        started_at=row[9], finished_at=row[10], error=row[11],
    )


def load_plug_results_for_run(con: sqlite3.Connection, run_id: str) -> list[PlugResult]:
    rows = con.execute(
        """SELECT result_id, run_id, plug_id, plug_key, "order",
                  input_path, output_path, status, input_hash,
                  started_at, finished_at, error
           FROM plug_results WHERE run_id = ? ORDER BY "order" """,
        (run_id,),
    ).fetchall()
    return [
        PlugResult(
            result_id=r[0], run_id=r[1], plug_id=r[2], plug_key=r[3],
            order=r[4], input_path=r[5], output_path=r[6],
            status=RunStatus(r[7]), input_hash=r[8],
            started_at=r[9], finished_at=r[10], error=r[11],
        )
        for r in rows
    ]
