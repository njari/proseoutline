# ProseOutline

Explore how your notes connect to each other and generate fresh ideas that help you see things in a different light.
## What it does

- Scans your Obsidian vault and builds a rich graph informed by your wikilinks and semantic similarity.
- Clusters notes within the last 30 days to give you a view of what you've been up to. 
- Generates insights and connecting ideas from these clusters. 


## One Click Install

```bash
curl -LsSf https://nubrajarial.com/install.sh | bash
```

That's it. The script installs [uv](https://github.com/astral-sh/uv) (if needed), fetches Python 3.11, and puts `proseoutline` on your PATH — no manual venv setup required.


# In case you want to do this manually

**via pip** (requires Python 3.11+ already installed):

```bash
pip install proseoutline
```

## Usage

```bash
proseoutline        # opens the web UI at localhost:8080
proseoutline-cli    # command-line interface
```

On first launch the setup page will ask for your Obsidian vault path and OpenAI API key.
These are saved locally to a `.env` file — nothing leaves your machine except the OpenAI API call.

## How it works

1. **Graph Enrichment** — Obsidian `.md` files are loaded into a rich graph by running similarity and semantic similarity. This uses the 'text-embedding-3-small' model from OpenAI. Cheap and efficient. 0.2$ approx for a 400 note vault. Model Substitutions coming soon. 
2. **Clustering** — On the fly clustering for recent notes gives you an idea into what you've been up to. You can view connections between these (and create new ones -- soon!). 
3. **Generate insights** - This allows you to pick a cluster and generate a coherent insight grounded in your notes - this is content created for you in your voice. Would love feedback on this. 


