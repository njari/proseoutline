"""
daily.py — surface article topic ideas from recent Obsidian notes.

Notes are matched by their `created` frontmatter date falling within a
rolling window of N days ending today. Call scan_notes(days=N) to
fetch notes, then pass them to suggest_topics() for LLM-generated ideas.
"""

from datetime import date, timedelta
from pathlib import Path

import frontmatter
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

import settings

TOPICS_PROMPT = SystemMessage(content="""You are generating LinkedIn post ideas for a senior backend engineer who has been exploring on their own and now is looking for new opportunities. 

The following notes are raw, personal, and may include technical learnings, observations, half-formed thoughts, and experiences.
Generate 4 high-quality LinkedIn post ideas that showcase strong thinking, not interview preparation.
Constraints:
- Do NOT generate generic advice or motivational content
- Do NOT mention interviews, job prep, or studying
- Each idea must be rooted in a specific observation, problem, or insight from the notes.
- Prefer ideas that reveal how the author thinks and explores topics around them. 

Style: conversational and opinionated. Avoid buzzwords and cliches.

Only include ideas where all of the following are true:
- Specific to the author's experience
- Reveals reasoning, not just knowledge
- A hiring manager would learn something about how this person thinks""")

SKIP_DIRS = {"Daily", "Templates"}

_ALL_FIELDS = ("name", "path", "content", "metadata")


def _date_range(days: int) -> set[str]:
    """ISO date strings for the last `days` days, ending today (inclusive)."""
    today = date.today()
    return {(today - timedelta(days=i)).isoformat() for i in range(days)}


def scan_notes(
    days: int = 7,
    vault_path: str | None = None,
    return_params: dict | None = None,
) -> list[dict]:
    """
    Scan vault for notes created within the last `days` days.

    Args:
        days: Rolling window of days ending today (inclusive).
        vault_path: Path to scan. Defaults to global DOCS_DIR.
        return_params: Dict controlling which fields to include per record.
            {"fields": ["name", "path", "content", "metadata"]}
            Omit or pass None to include all fields.

    Returns:
        list of dicts, each containing the requested fields.
    """
    fields = set(return_params.get("fields", _ALL_FIELDS)) if return_params else set(_ALL_FIELDS)
    date_range = _date_range(days)
    root = Path(vault_path) if vault_path else Path(settings.vault_dir())
    results = []

    for md_file in root.rglob("*.md"):
        if any(part in SKIP_DIRS for part in md_file.parts):
            continue
        try:
            post = frontmatter.load(md_file)
            created = str(post.metadata.get("created", ""))
            if not any(d in created for d in date_range):
                continue
            record: dict = {}
            if "name"     in fields: record["name"]     = md_file.stem
            if "path"     in fields: record["path"]     = str(md_file)
            if "content"  in fields: record["content"]  = post.content.strip()
            if "metadata" in fields: record["metadata"] = post.metadata
            results.append(record)
        except Exception:
            continue

    return results


def suggest_topics(notes: list[dict]) -> str:
    """
    Given recent notes, ask GPT-4o to suggest article topic ideas.
    Returns the raw LLM response string.
    """
    if not notes:
        return "No notes found in the selected date range."

    context = "\n\n---\n\n".join(
        f"[[{n['name']}]]\n{n['content']}" for n in notes if n["content"]
    )
    llm = ChatOpenAI(model="gpt-4o")
    response = llm.invoke([
        TOPICS_PROMPT,
        HumanMessage(content=f"Here are my notes from the last 7 days. Generate LinkedIn post ideas from these.\n\n{context}"),
    ])
    return response.content
