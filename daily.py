"""
daily.py — surface article topic ideas from today's Obsidian notes.

Replicates the Daily.base filter: notes whose `created` frontmatter date
matches the daily note filename (YYYY-MM-DD). Keeps topic suggestion
separate from outline generation — call suggest_topics() to get ideas,
then hand a chosen topic to vault.retrieve() + generator.generate_outline().
"""

from datetime import date
from pathlib import Path

import frontmatter
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from vault import DOCS_DIR

TOPICS_PROMPT = SystemMessage(content="""You are a writing assistant reviewing a person's notes from today.

Your job is to suggest 5 article topic ideas that could be written from these notes.

Rules:
- Every suggested topic must be directly rooted in the notes provided
- Each topic should have a 1-sentence angle (not just a label)
- Prefer topics that connect two or more notes in an unexpected way
- Output as a numbered list: topic title + one-sentence angle
- Do not add topics that aren't supported by the notes""")


def get_todays_notes(date_str: str | None = None) -> list[dict]:
    """
    Return notes whose `created` frontmatter contains date_str.
    Mirrors the Daily.base filter logic.
    Excludes Daily/ and Templates/ folders.
    """
    if date_str is None:
        date_str = date.today().isoformat()  # e.g. "2026-03-10"

    docs_path = Path(DOCS_DIR)
    skip_dirs = {"Daily", "Templates"}
    results = []

    for md_file in docs_path.rglob("*.md"):
        if any(part in skip_dirs for part in md_file.parts):
            continue
        try:
            post = frontmatter.load(md_file)
            created = str(post.metadata.get("created", ""))
            if date_str in created:
                results.append({
                    "name": md_file.stem,
                    "path": str(md_file),
                    "content": post.content.strip(),
                    "metadata": post.metadata,
                })
        except Exception:
            continue  # skip unparseable files

    return results


def suggest_topics(notes: list[dict]) -> str:
    """
    Given today's notes, ask GPT-4o to suggest article topic ideas.
    Returns the raw LLM response string.
    """
    if not notes:
        return "No notes found for today."

    context = "\n\n---\n\n".join(
        f"[[{n['name']}]]\n{n['content']}" for n in notes if n["content"]
    )
    llm = ChatOpenAI(model="gpt-4o")
    response = llm.invoke([
        TOPICS_PROMPT,
        HumanMessage(content=f"Today's notes:\n\n{context}"),
    ])
    return response.content
