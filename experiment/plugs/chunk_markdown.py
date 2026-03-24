"""
Plug: chunk_markdown

Splits notes using LangChain's MarkdownHeaderTextSplitter — chunks stay within
header boundaries and carry section context as metadata.  Falls back to
character splitting for sections that still exceed max_chunk_size.

Output format (one JSON file per chunk):
{
  "source":       "/absolute/path/to/note.md",
  "name":         "Note Name",
  "chunk_index":  0,
  "content":      "... chunk text ...",
  "metadata":     {
    "Header 1": "Top Section",
    "Header 2": "Sub Section",   # present only if chunk is under a ##
    ...original frontmatter...
  }
}
"""

import json
from pathlib import Path

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from experiment.registry import plug

_HEADERS = [("#", "Header 1"), ("##", "Header 2"), ("###", "Header 3")]
_DEFAULT_MAX_CHUNK = 1000
_DEFAULT_OVERLAP   = 100


@plug("chunk_markdown")
def run(input_path: Path, output_path: Path, config: dict) -> None:
    """
    Split each note JSON from input_path on Markdown headers, with a
    character-based fallback for oversized sections.

    config keys:
        max_chunk_size (int, default 1000)  — fallback split threshold
        chunk_overlap  (int, default 100)   — overlap for fallback splitter
    """
    max_chunk = int(config.get("max_chunk_size", _DEFAULT_MAX_CHUNK))
    overlap   = int(config.get("chunk_overlap",  _DEFAULT_OVERLAP))

    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=_HEADERS,
        strip_headers=False,   # keep headers inside the chunk text for context
    )
    fallback_splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_chunk,
        chunk_overlap=overlap,
        add_start_index=True,
    )

    json_files   = sorted(input_path.rglob("*.json"))
    total_chunks = 0

    for json_path in json_files:
        try:
            record = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        content  = record.get("content", "")
        base_meta = {
            "source": record.get("source", ""),
            **record.get("metadata", {}),
        }

        # Split on headers first
        header_chunks = header_splitter.split_text(content)

        # Fallback: further split any header-chunk that's still too large
        final_chunks = []
        for hc in header_chunks:
            if len(hc.page_content) > max_chunk:
                sub = fallback_splitter.split_documents([hc])
                final_chunks.extend(sub)
            else:
                final_chunks.append(hc)

        rel_dir  = json_path.relative_to(input_path).parent
        stem     = json_path.stem
        out_dir  = output_path / rel_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        for i, chunk in enumerate(final_chunks):
            chunk_meta = {**base_meta, **chunk.metadata}
            chunk_record = {
                "source":      record.get("source", ""),
                "name":        record.get("name", stem),
                "chunk_index": i,
                "content":     chunk.page_content,
                "metadata":    chunk_meta,
            }
            out_file = out_dir / f"{stem}_chunk_{i:04d}.json"
            out_file.write_text(
                json.dumps(chunk_record, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            total_chunks += 1

    print(
        f"[chunk_markdown] {len(json_files)} notes → {total_chunks} chunks "
        f"(max_chunk={max_chunk}, overlap={overlap})"
    )
