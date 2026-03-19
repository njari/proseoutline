"""
Tests for daily.scan_notes.

Each test creates isolated markdown files in a tmp_path directory so no
real vault is required. The `created` frontmatter field controls date matching.
"""

import textwrap
from datetime import date, timedelta
from pathlib import Path

import pytest

# scan_notes is importable without a .env because settings.vault_dir() falls back to ""
from daily import scan_notes, SKIP_DIRS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today() -> str:
    return date.today().isoformat()


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


def write_note(directory: Path, name: str, created: str, content: str = "") -> Path:
    """Write a minimal frontmatter markdown file."""
    path = directory / f"{name}.md"
    path.write_text(
        textwrap.dedent(f"""\
            ---
            created: {created}
            ---
            {content}
        """)
    )
    return path


# ---------------------------------------------------------------------------
# Basic scanning
# ---------------------------------------------------------------------------

def test_returns_note_created_today(tmp_path):
    write_note(tmp_path, "today-note", _today(), content="Hello world")
    results = scan_notes(days=1, vault_path=str(tmp_path))
    assert len(results) == 1
    assert results[0]["name"] == "today-note"


def test_returns_empty_for_empty_vault(tmp_path):
    results = scan_notes(days=7, vault_path=str(tmp_path))
    assert results == []


def test_excludes_note_older_than_window(tmp_path):
    write_note(tmp_path, "old-note", _days_ago(10))
    results = scan_notes(days=7, vault_path=str(tmp_path))
    assert results == []


def test_includes_notes_within_window(tmp_path):
    write_note(tmp_path, "note-3d-ago", _days_ago(3))
    write_note(tmp_path, "note-6d-ago", _days_ago(6))
    write_note(tmp_path, "note-8d-ago", _days_ago(8))
    results = scan_notes(days=7, vault_path=str(tmp_path))
    names = {r["name"] for r in results}
    assert "note-3d-ago" in names
    assert "note-6d-ago" in names
    assert "note-8d-ago" not in names


def test_note_without_created_field_is_excluded(tmp_path):
    path = tmp_path / "no-date.md"
    path.write_text("---\ntitle: No date\n---\nContent here\n")
    results = scan_notes(days=7, vault_path=str(tmp_path))
    assert results == []


# ---------------------------------------------------------------------------
# SKIP_DIRS filtering
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("skip_dir", list(SKIP_DIRS))
def test_skips_notes_in_skip_dirs(tmp_path, skip_dir):
    skip_path = tmp_path / skip_dir
    skip_path.mkdir()
    write_note(skip_path, "skipped", _today())
    results = scan_notes(days=1, vault_path=str(tmp_path))
    assert results == []


def test_non_skip_dir_note_is_included(tmp_path):
    sub = tmp_path / "Essays"
    sub.mkdir()
    write_note(sub, "essay", _today(), content="Some text")
    results = scan_notes(days=1, vault_path=str(tmp_path))
    assert len(results) == 1
    assert results[0]["name"] == "essay"


# ---------------------------------------------------------------------------
# return_params — field selection
# ---------------------------------------------------------------------------

def test_default_returns_all_fields(tmp_path):
    write_note(tmp_path, "full", _today(), content="Body text")
    results = scan_notes(days=1, vault_path=str(tmp_path))
    assert set(results[0].keys()) == {"name", "path", "content", "metadata"}


def test_return_params_name_only(tmp_path):
    write_note(tmp_path, "slim", _today())
    results = scan_notes(days=1, vault_path=str(tmp_path), return_params={"fields": ["name"]})
    assert set(results[0].keys()) == {"name"}
    assert results[0]["name"] == "slim"


def test_return_params_name_and_path(tmp_path):
    write_note(tmp_path, "partial", _today())
    results = scan_notes(days=1, vault_path=str(tmp_path), return_params={"fields": ["name", "path"]})
    assert set(results[0].keys()) == {"name", "path"}
    assert results[0]["path"].endswith("partial.md")


def test_return_params_content_is_stripped(tmp_path):
    write_note(tmp_path, "padded", _today(), content="  trimmed  ")
    results = scan_notes(days=1, vault_path=str(tmp_path), return_params={"fields": ["content"]})
    assert results[0]["content"] == "trimmed"


def test_return_params_metadata_contains_created(tmp_path):
    created = _today()
    write_note(tmp_path, "meta", created)
    results = scan_notes(days=1, vault_path=str(tmp_path), return_params={"fields": ["metadata"]})
    assert str(results[0]["metadata"].get("created", "")) == created


def test_return_params_none_is_same_as_all_fields(tmp_path):
    write_note(tmp_path, "note", _today(), content="hi")
    with_none  = scan_notes(days=1, vault_path=str(tmp_path), return_params=None)
    without    = scan_notes(days=1, vault_path=str(tmp_path))
    assert with_none == without
    assert set(with_none[0].keys()) == {"name", "path", "content", "metadata"}


# ---------------------------------------------------------------------------
# Multiple notes
# ---------------------------------------------------------------------------

def test_returns_all_matching_notes(tmp_path):
    for i in range(5):
        write_note(tmp_path, f"note-{i}", _today(), content=f"Content {i}")
    results = scan_notes(days=1, vault_path=str(tmp_path))
    assert len(results) == 5


def test_nested_directories_are_scanned(tmp_path):
    sub = tmp_path / "Projects" / "AI"
    sub.mkdir(parents=True)
    write_note(sub, "deep-note", _today(), content="Deep")
    results = scan_notes(days=1, vault_path=str(tmp_path))
    assert len(results) == 1
    assert results[0]["name"] == "deep-note"
