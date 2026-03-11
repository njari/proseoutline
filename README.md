# ProseOutline

Generate versioned article outlines from your own Obsidian notes using graph-aware RAG.

## What it does

- Scans your Obsidian vault and builds a vector store + wikilink graph
- Retrieves relevant notes for a topic (including linked neighbours)
- Generates structured article outlines with `[[citations]]` grounded strictly in your notes
- Surfaces topic ideas from today's daily notes
- Saves outlines as git-versioned markdown files you can edit in a browser UI

## Install

```bash
curl -LsSf https://nubrajarial.com/install.sh | bash
```

That's it. The script installs [uv](https://github.com/astral-sh/uv) (if needed), fetches Python 3.11, and puts `proseoutline` on your PATH — no manual venv setup required.

**Or via pip** (requires Python 3.11+ already installed):

```bash
pip install proseoutline
```

Requires Git and an OpenAI API key.

## Usage

```bash
proseoutline        # opens the web UI at localhost:8080
proseoutline-cli    # command-line interface
```

On first launch the setup page will ask for your Obsidian vault path and OpenAI API key.
These are saved locally to a `.env` file — nothing leaves your machine except the OpenAI API call.

## How it works

1. **Vault indexing** — Obsidian `.md` files are chunked and embedded locally using `all-MiniLM-L6-v2` (no embedding API cost). Stored in a local Chroma database.
2. **Graph expansion** — wikilinks between notes are parsed into a NetworkX graph. Retrieval expands results to include linked neighbours.
3. **Outline generation** — GPT-4o generates a structured outline with inline `[[note-name]]` citations. Every claim must come from your notes.
4. **Versioning** — each article is its own git repo under `outlines/`. Edits are committed on save.
