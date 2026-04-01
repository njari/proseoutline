from openai import AsyncOpenAI, OpenAI
from langchain_core.messages import SystemMessage, HumanMessage

OUTLINE_PROMPT = SystemMessage(content="""You are helping a senior backend engineer transitioning toward product roles turn their personal notes into a LinkedIn post outline.

STRICT RULE: Every idea, claim, or bullet point MUST come directly from the provided notes. Do not add external knowledge, general advice, or anything not in the notes. If an idea is not in the notes, omit it entirely.

For every bullet point, add an inline citation using the note name in [[double brackets]].
Example: "Boredom creates space for lateral thinking [[boredom-and-creativity]]"

The outline must reflect strong, specific thinking — not generic advice. It should reveal how the author reasons, not just what they know.

Structure:
- Title
- Hook (1-2 lines, curiosity-driven and scroll-stopping, with citation)
- Core argument (the single sharp idea the post will defend)
- 3-5 supporting points, each with:
  - A working section title
  - 2-3 bullet points ending with [[note-name]] citation(s)
  - A one-line connection note if two notes explicitly link to each other
- Closing line (what the reader should walk away thinking or reconsidering)

Style: conversational, opinionated, no buzzwords. Product thinking, system design intuition, or real tradeoffs preferred over abstract lessons.""")


def _build_context(topic, docs):
    context = "\n\n---\n\n".join(
        f"[[{d['name']}]]\n{d['content']}" for d in docs if d.get('content')
    )
    return [
        OUTLINE_PROMPT,
        HumanMessage(content=f"Topic: {topic}\n\nNotes:\n{context}"),
    ]


REVISE_PROMPT = SystemMessage(content="""You are helping a senior backend engineer refine a LinkedIn post outline based on their own feedback.

STRICT RULE: Every idea, claim, or bullet point MUST come from the provided notes. Do not add external knowledge or anything not in the notes.

You will receive the current outline and the author's feedback about what isn't working. Revise the outline to address that feedback directly.

Keep all [[note-name]] citations intact. If a section is removed due to feedback, its citations go with it. Do not invent new points to fill gaps — only use what the notes support.

Style: conversational, opinionated, no buzzwords. The revision should feel like a sharper version of the same thinking, not a different post.""")


import settings as _settings


def _client(): return AsyncOpenAI(api_key=_settings.api_key())


async def stream_outline(topic, docs):
    """Async generator — yields text chunks as they arrive from GPT-4o."""
    msgs = _build_context(topic, docs)
    stream = await _client().chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system" if isinstance(m, SystemMessage) else "user", "content": m.content} for m in msgs],
        stream=True,
    )
    async for chunk in stream:
        yield chunk.choices[0].delta.content or ""


async def revise_outline(current_outline: str, feedback: str, docs):
    """Async generator — streams a revised outline given feedback on the current one."""
    notes_context = "\n\n---\n\n".join(
        f"[[{d['name']}]]\n{d['content']}" for d in docs if d.get('content')
    )
    messages = [
        {"role": "system", "content": REVISE_PROMPT.content},
        {"role": "user", "content": (
            f"Current outline:\n{current_outline}\n\n"
            f"Author feedback: {feedback}\n\n"
            f"Notes:\n{notes_context}"
        )},
    ]
    stream = await _client().chat.completions.create(
        model="gpt-4o", messages=messages, stream=True,
    )
    async for chunk in stream:
        yield chunk.choices[0].delta.content or ""
