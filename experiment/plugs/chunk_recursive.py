"""
Plug: chunk_recursive

Reads JSON note files from input_path (produced by obsidian_ingest) and writes
chunked JSON files to output_path.  Replaces RecursiveCharacterTextSplitter
usage in datalayer.py.

Output format (one <stem>_chunk_<n>.json per chunk):
{
  "source":       "/absolute/path/to/note.md",
  "name":         "Note Name",
  "chunk_index":  0,
  "start_index":  0,
  "content":      "... chunk text ...",
  "metadata":     { ...frontmatter... }
}
"""

import json
from pathlib import Path

from experiment.registry import plug

_DEFAULT_CHUNK_SIZE    = 200
_DEFAULT_CHUNK_OVERLAP = 20


def _split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[tuple[int, str]]:
    """
    Simple recursive character splitter.  Returns list of (start_index, chunk_text).
    Splits on paragraph boundaries first, then sentences, then words, then characters
    — mirrors LangChain's RecursiveCharacterTextSplitter separators.
    """
    separators = ["\n\n", "\n", " ", ""]
    chunks: list[tuple[int, str]] = []
    _split(text, 0, separators, chunk_size, chunk_overlap, chunks)
    return chunks


def _split(
    text: str,
    offset: int,
    separators: list[str],
    chunk_size: int,
    overlap: int,
    out: list[tuple[int, str]],
) -> None:
    if len(text) <= chunk_size:
        if text.strip():
            out.append((offset, text))
        return

    sep = separators[0] if separators else ""
    remaining = separators[1:] if separators else []

    if sep and sep in text:
        parts = text.split(sep)
        current = ""
        current_offset = offset
        for part in parts:
            candidate = current + (sep if current else "") + part
            if len(candidate) <= chunk_size:
                current = candidate
            else:
                if current.strip():
                    out.append((current_offset, current))
                # Start new chunk with overlap
                overlap_text = current[-overlap:] if overlap and current else ""
                current_offset = offset + text.index(part) - len(overlap_text)
                current = overlap_text + part
        if current.strip():
            out.append((current_offset, current))
    else:
        # No separator found at this level — recurse into smaller separator
        if remaining:
            _split(text, offset, remaining, chunk_size, overlap, out)
        else:
            # Character-level fallback
            start = 0
            while start < len(text):
                chunk = text[start:start + chunk_size]
                if chunk.strip():
                    out.append((offset + start, chunk))
                start += chunk_size - overlap


@plug("chunk_recursive")
def run(input_path: Path, output_path: Path, config: dict) -> None:
    """
    Split each note JSON from input_path into chunks and write to output_path.

    config keys:
        chunk_size    (int, default 200)
        chunk_overlap (int, default 20)
    """
    chunk_size    = int(config.get("chunk_size", _DEFAULT_CHUNK_SIZE))
    chunk_overlap = int(config.get("chunk_overlap", _DEFAULT_CHUNK_OVERLAP))

    json_files = sorted(input_path.rglob("*.json"))
    total_chunks = 0

    for json_path in json_files:
        try:
            record = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        content = record.get("content", "")
        chunks = _split_text(content, chunk_size, chunk_overlap)

        # Mirror relative directory structure
        rel_dir = json_path.relative_to(input_path).parent
        stem = json_path.stem
        out_dir = output_path / rel_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        for i, (start_idx, chunk_text) in enumerate(chunks):
            chunk_record = {
                "source":      record.get("source", ""),
                "name":        record.get("name", stem),
                "chunk_index": i,
                "start_index": start_idx,
                "content":     chunk_text,
                "metadata":    record.get("metadata", {}),
            }
            out_file = out_dir / f"{stem}_chunk_{i:04d}.json"
            out_file.write_text(
                json.dumps(chunk_record, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            total_chunks += 1

    print(
        f"[chunk_recursive] {len(json_files)} notes → {total_chunks} chunks "
        f"(size={chunk_size}, overlap={chunk_overlap})"
    )
