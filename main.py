import os
from datetime import date
from dotenv import load_dotenv

from vault import build_graph, build_or_load_store, retrieve
from generator import generate_outline
from articles import OUTLINES_DIR, slugify, list_articles, save_outline, show_article
from daily import scan_notes, suggest_topics

load_dotenv()


def run_daily_ideas(store, graph):
    """Surface topic ideas from today's notes, then optionally generate an outline."""
    notes = scan_notes(days=7)

    if not notes:
        print("\nNo notes found in the last 7 days.")
        return

    print(f"\nFound {len(notes)} note(s) from today:")
    for n in notes:
        print(f"  · {n['name']}")

    print(f"\n{'='*60}\nSuggesting topics...\n{'='*60}\n")
    ideas = suggest_topics(notes)
    print(ideas)

    go = input("\nGenerate outline for one of these? [y/n]: ").strip().lower()
    if go == "y":
        topic = input("Topic (copy/paste or rephrase): ").strip()
        branch = input("Branch [main]: ").strip() or "main"
        slug = slugify(topic)
        docs = retrieve(store, graph, topic)
        print(f"\nRetrieved {len(docs)} notes")
        outline = generate_outline(topic, docs)
        print(f"\n{'='*60}\n{outline}")
        save = input("\nSave? [y/n]: ").strip().lower()
        if save == "y":
            commit = save_outline(OUTLINES_DIR, slug, topic, branch, outline)
            print(f"\nSaved: outlines/{slug}/outline.md  branch={branch}  commit={commit}")


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
    print("  [n] New article")
    print("  [d] Today's ideas\n")

    choice = input("> ").strip().lower()

    if choice == "d":
        run_daily_ideas(store, graph)
        return

    if choice == "n" or not articles:
        topic = input("Topic: ").strip()
        slug = slugify(topic)
    else:
        idx = int(choice) - 1
        article = articles[idx]
        slug = article["slug"]
        print(f"\nBranches: {', '.join(article['branches'])}")
        branch_to_show = input("Show branch [main]: ").strip() or "main"
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
        print(f"\nSaved: outlines/{slug}/outline.md  branch={branch}  commit={commit}")


if __name__ == "__main__":
    main()
