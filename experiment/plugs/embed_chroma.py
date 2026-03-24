"""
Plug: embed_chroma

Reads chunked JSON files from input_path (produced by chunk_recursive) and
writes a Chroma persist directory to output_path.  Replaces Chroma +
HuggingFaceEmbeddings usage in datalayer.py.

config keys:
    model_name (str, default "all-MiniLM-L6-v2")
"""

import json
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

from experiment.registry import plug

_DEFAULT_MODEL = "all-MiniLM-L6-v2"


@plug("embed_chroma")
def run(input_path: Path, output_path: Path, config: dict) -> None:
    """
    Embed all chunks from input_path and write a Chroma store to output_path.

    config keys:
        model_name (str, default "all-MiniLM-L6-v2")
    """
    model_name = config.get("model_name", _DEFAULT_MODEL)
    embeddings = HuggingFaceEmbeddings(model_name=model_name)
    store = Chroma(
        persist_directory=str(output_path),
        embedding_function=embeddings,
    )

    json_files = sorted(input_path.rglob("*.json"))
    docs: list[Document] = []

    for json_path in json_files:
        try:
            record = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        docs.append(
            Document(
                page_content=record.get("content", ""),
                metadata={
                    "source":      record.get("source", ""),
                    "name":        record.get("name", ""),
                    "chunk_index": record.get("chunk_index", 0),
                    "start_index": record.get("start_index", 0),
                    **record.get("metadata", {}),
                },
            )
        )

    if docs:
        store.add_documents(docs)

    print(
        f"[embed_chroma] embedded {len(docs)} chunks "
        f"→ {output_path} (model={model_name})"
    )
