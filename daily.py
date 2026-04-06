"""daily.py — surface article topic ideas from recent notes via LLM."""

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

TOPICS_PROMPT = SystemMessage(content="""You are generating LinkedIn post ideas for a senior backend engineer who has been exploring on their own and now is looking for new opportunities.

The following notes are raw, personal, and may include technical learnings, observations, half-formed thoughts, and experiences.
Generate 4 high-quality post ideas that showcase strong thinking and ideation.
Constraints:
- Do NOT generate generic advice or motivational content
- Do NOT mention interviews, job prep, or studying
- Each idea must be rooted in a specific observation, problem, or insight from the notes.
- Prefer ideas that reveal how the author thinks and explores topics around them.

Style: conversational and opinionated. Avoid buzzwords and cliches.

Only include ideas where all of the following are true:
- Specific to the author's experience
- Reveals reasoning, not just knowledge
- Opinion based where others may differ""")


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
