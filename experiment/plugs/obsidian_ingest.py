"""
Plug: obsidian_ingest

Reads .md files from an Obsidian vault directory (input_path) and writes one
JSON file per note to output_path.  Replaces ObsidianLoader usage in datalayer.py.

Output format (one <slug>.json per note):
{
  "source": "/absolute/path/to/note.md",
  "name":   "Note Name",
  "content": "... raw markdown ...",
  "metadata": { ...frontmatter key/value pairs... }
}
"""

import json
import re
from pathlib import Path

import yaml

from experiment.registry import plug


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML frontmatter from body. Returns (metadata, body)."""
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?", text, re.DOTALL)
    if match:
        try:
            meta = yaml.safe_load(match.group(1)) or {}
        except Exception:
            meta = {}
        body = text[match.end():]
        return meta, body
    return {}, text


@plug("obsidian_ingest")
def run(input_path: Path, output_path: Path, config: dict) -> None:
    """
    Walk input_path for .md files and write one JSON file per note to output_path.
    config keys: none required.
    """
    md_files = sorted(input_path.rglob("*.md"))
    for md_path in md_files:
        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            continue

        metadata, body = _parse_frontmatter(text)
        record = {
            "source": str(md_path),
            "name": md_path.stem,
            "content": body,
            "metadata": metadata,
        }

        # Preserve relative structure: output/<relative_dir>/<stem>.json
        rel = md_path.relative_to(input_path).with_suffix(".json")
        out_file = output_path / rel
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[obsidian_ingest] wrote {len(md_files)} notes to {output_path}")
