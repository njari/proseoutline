import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

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


def _build_context(topic, docs):
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
    return [
        OUTLINE_PROMPT,
        HumanMessage(content=f"Topic: {topic}\n\nNotes:\n{context}"),
    ]


def generate_outline(topic, docs) -> str:
    llm = ChatOpenAI(model="gpt-4o")
    return llm.invoke(_build_context(topic, docs)).content


async def stream_outline(topic, docs):
    """Async generator — yields text chunks as they arrive from GPT-4o."""
    llm = ChatOpenAI(model="gpt-4o", streaming=True)
    async for chunk in llm.astream(_build_context(topic, docs)):
        yield chunk.content
