import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

import networkx as nx
from dotenv import load_dotenv
import obsidiantools as otools
from langchain_community.document_loaders import ObsidianLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_core.messages import SystemMessage, HumanMessage

load_dotenv()

DOCS_DIR = "/Users/nubrajarial/Library/Mobile Documents/iCloud~md~obsidian/Documents/helterskelter/"
CHROMA_DIR = "./chroma_db"
OUTLINES_DIR = Path("./outlines")

OUTLINE_PROMPT = SystemMessage(content="""You are a writing assistant helping turn personal notes into article outlines.

STRICT RULE: Every idea, claim, or bullet point in the outline MUST come directly from the provided notes. Do not add external knowledge, general advice, or anything not explicitly present in the notes. If an idea is not in the notes, omit it entirely.

For every bullet point, add an inline citation using the note name in [[double brackets]].
Example: "Boredom creates space for lateral thinking [[boredom-and-creativity]]"

Structure:
- Title
- Hook (1 sentence, with citation)
- 4-6 sections, each with:
  - Working section title
  - 2-3 bullet points, each ending with [[note-name]] citation(s)
  - A one-line "connection note" if two of the provided notes explicitly link to each other""")


# ---------------------------------------------------------------------------
# Outline repo helpers
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def git_run(*args, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


def init_article_repo(article_dir: Path):
    """Each article gets its own git repo at outlines/<slug>/."""
    article_dir.mkdir(parents=True, exist_ok=True)
    if not (article_dir / ".git").exists():
        git_run("init", "-b", "main", cwd=article_dir)
        git_run("config", "user.email", "minirag@local", cwd=article_dir)
        git_run("config", "user.name", "minirag", cwd=article_dir)
        # Seed with empty commit so branches have a common base
        (article_dir / "outline.md").touch()
        git_run("add", "outline.md", cwd=article_dir)
        git_run("commit", "-m", "init", cwd=article_dir)


def list_articles(outlines_dir: Path) -> list[dict]:
    """Each subdirectory with a .git is an article."""
    outlines_dir.mkdir(exist_ok=True)
    articles = []
    for article_dir in sorted(d for d in outlines_dir.iterdir() if d.is_dir() and (d / ".git").exists()):
        slug = article_dir.name
        try:
            raw = git_run("branch", "--all", cwd=article_dir)
            branches = [
                b.strip().lstrip("* ").replace("remotes/origin/", "")
                for b in raw.splitlines()
                if b.strip()
            ]
        except RuntimeError:
            branches = ["main"]
        articles.append({"slug": slug, "dir": article_dir, "branches": branches})
    return articles


def save_outline(outlines_dir: Path, slug: str, topic: str, branch: str, content: str) -> str:
    article_dir = outlines_dir / slug
    init_article_repo(article_dir)
    git_run("checkout", "-B", branch, cwd=article_dir)
    frontmatter = (
        f"---\n"
        f"topic: {topic}\n"
        f"generated: {datetime.now().isoformat(timespec='seconds')}\n"
        f"branch: {branch}\n"
        f"---\n\n"
    )
    (article_dir / "outline.md").write_text(frontmatter + content, encoding="utf-8")
    git_run("add", "outline.md", cwd=article_dir)
    git_run("commit", "-m", f"{branch}: {topic}", cwd=article_dir)
    return git_run("rev-parse", "--short", "HEAD", cwd=article_dir)


def show_article(outlines_dir: Path, slug: str, branch: str):
    article_dir = outlines_dir / slug
    git_run("checkout", branch, cwd=article_dir)
    print((article_dir / "outline.md").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# RAG pipeline
# ---------------------------------------------------------------------------

def build_graph():
    vault = otools.api.Vault(Path(DOCS_DIR)).connect().gather()
    return vault.graph


def build_or_load_store():
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    if os.path.exists(CHROMA_DIR):
        return Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)
    loader = ObsidianLoader(path=DOCS_DIR, collect_metadata=True)
    docs = loader.load()
    splitter = RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=20, add_start_index=True)
    splits = splitter.split_documents(docs)
    return Chroma.from_documents(splits, embeddings, persist_directory=CHROMA_DIR)


def expand_with_graph(results, store, graph, hops=1):
    expanded = list(results)
    seen_sources = {doc.metadata.get("source", "") for doc in results}
    for doc in results:
        source = doc.metadata.get("source", "")
        note_name = os.path.splitext(os.path.basename(source))[0]
        if note_name not in graph:
            continue
        ego = nx.ego_graph(graph.to_undirected(), note_name, radius=hops)
        neighbors = set(ego.nodes) - {note_name}
        for neighbor in neighbors:
            neighbor_path = os.path.join(DOCS_DIR, neighbor + ".md")
            if neighbor_path in seen_sources:
                continue
            seen_sources.add(neighbor_path)
            expanded.extend(store.similarity_search(note_name, k=2, filter={"source": neighbor_path}))
    return expanded


def retrieve(store, graph, topic, k=5):
    results = store.similarity_search(topic, k=k)
    return expand_with_graph(results, store, graph)


def generate_outline(topic, docs) -> str:
    seen = set()
    unique_docs = []
    for d in docs:
        src = d.metadata.get("source", "")
        if src not in seen:
            seen.add(src)
            unique_docs.append(d)
    context = "\n\n---\n\n".join(
        f"[[{os.path.splitext(os.path.basename(d.metadata.get('source', 'note')))[0]}]]\n{d.page_content}"
        for d in unique_docs
    )
    llm = ChatOpenAI(model="gpt-4o")
    response = llm.invoke([
        OUTLINE_PROMPT,
        HumanMessage(content=f"Topic: {topic}\n\nNotes:\n{context}"),
    ])
    return response.content


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    OUTLINES_DIR.mkdir(exist_ok=True)
    store = build_or_load_store()
    graph = build_graph()

    # --- Article selection ---
    articles = list_articles(OUTLINES_DIR)
    print()
    if articles:
        print("Existing articles:")
        for i, a in enumerate(articles, 1):
            branches = ", ".join(a["branches"])
            print(f"  [{i}] {a['slug']}  (branches: {branches})")
    print("  [n] New article\n")

    choice = input("> ").strip().lower()

    if choice == "n" or not articles:
        topic = input("Topic: ").strip()
        slug = slugify(topic)
    else:
        idx = int(choice) - 1
        article = articles[idx]
        slug = article["slug"]
        print(f"\nBranches: {', '.join(article['branches'])}")
        branch_to_show = input(f"Show branch [main]: ").strip() or "main"
        print(f"\n{'='*60}\nCurrent outline ({branch_to_show}):\n{'='*60}")
        try:
            show_article(OUTLINES_DIR, slug, branch_to_show)
        except (RuntimeError, FileNotFoundError):
            print("(no existing outline on that branch)")
        print(f"{'='*60}\n")
        topic = input(f"Refine topic [{slug.replace('-', ' ')}]: ").strip() or slug.replace("-", " ")

    branch = input("Branch [main]: ").strip() or "main"

    # --- Retrieve & generate ---
    docs = retrieve(store, graph, topic)
    print(f"\nRetrieved {len(docs)} notes (including graph neighbors)")
    for d in docs:
        print(f"  · {os.path.basename(d.metadata.get('source', 'unknown'))}")

    print(f"\n{'='*60}\nGenerating outline...\n{'='*60}\n")
    outline = generate_outline(topic, docs)
    print(outline)

    # --- Save ---
    save = input("\nSave? [y/n]: ").strip().lower()
    if save == "y":
        commit = save_outline(OUTLINES_DIR, slug, topic, branch, outline)
        print(f"\nSaved: outlines/{slug}.md  branch={branch}  commit={commit}")


if __name__ == "__main__":
    main()
