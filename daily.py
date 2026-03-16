"""
daily.py — surface article topic ideas from recent Obsidian notes.

Replicates the Daily.base filter: notes whose `created` frontmatter date
falls within the last 7 days. Keeps topic suggestion separate from outline
generation — call suggest_topics() to get ideas, then hand a chosen topic
to vault.retrieve() + generator.generate_outline().
"""

from datetime import date, timedelta
from pathlib import Path

import frontmatter
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from vault import DOCS_DIR

TOPICS_PROMPT = SystemMessage(content="""You are a writing assistant reviewing a person's notes from today.

Your job is to suggest 5 article topic ideas that could be written from these notes (collected over the last 7 days).

Rules:
- Every suggested topic must be directly rooted in the notes provided
- Each topic should have a 1-sentence angle (not just a label)
- Prefer topics that connect two or more notes in an unexpected way
- Output as a numbered list: topic title + one-sentence angle
- Do not add topics that aren't supported by the notes""")


def get_todays_notes(date_str: str | None = None) -> list[dict]:
    """
    Return notes whose `created` frontmatter falls within the last 7 days.
    Mirrors the Daily.base filter logic.
    Excludes Daily/ and Templates/ folders.
    """
    today = date.fromisoformat(date_str) if date_str else date.today()
    cutoff = today - timedelta(days=7)
    date_range = {(cutoff + timedelta(days=i)).isoformat() for i in range(8)}

    docs_path = Path(DOCS_DIR)
    skip_dirs = {"Daily", "Templates"}
    results = []

    for md_file in docs_path.rglob("*.md"):
        if any(part in skip_dirs for part in md_file.parts):
            continue
        try:
            post = frontmatter.load(md_file)
            created = str(post.metadata.get("created", ""))
            if any(d in created for d in date_range):
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
        return "No notes found in the last 7 days."

    context = "\n\n---\n\n".join(
        f"[[{n['name']}]]\n{n['content']}" for n in notes if n["content"]
    )
    llm = ChatOpenAI(model="gpt-4o")
    response = llm.invoke([
        TOPICS_PROMPT,
        HumanMessage(content=f"Notes from the last 7 days:\n\n{context}"),
    ])
    return response.content
