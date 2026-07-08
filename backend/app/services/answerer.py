from app.models import Citation, Turn
from app.services.llm import LLMClient

ANSWER_SYSTEM = """You are Techcombank's FY25 results assistant. Your ONLY knowledge is the CONTEXT below, taken from the official FY25 press release (fiscal year ended 31 Dec 2025).

Rules — non-negotiable:
1. Answer ONLY with facts present in CONTEXT. Never use outside knowledge or invent figures.
2. If the answer is not in CONTEXT, reply: "I don't have that information in the FY25 press release." — optionally point to what related information IS available.
3. Cite the source page after each fact, using the [p.N] tags present in CONTEXT.
4. Keep units exactly as the source (VND bn / VND trillion / %). Never convert currencies.
5. Be concise: 1-4 sentences for facts, a short structured answer for analysis.
6. This is factual reporting, not financial advice; refuse advice requests."""

def build_context(metric_block: str, chunks: list[dict]) -> tuple[str, list[Citation]]:
    parts: list[str] = []
    citations: list[Citation] = []
    if metric_block:
        parts.append("VERIFIED FINANCIAL METRICS (exact figures):\n" + metric_block)
        citations.append(Citation(page=13, snippet="FY25 financial summary table (verified figures)"))
    for c in chunks:
        parts.append(f"[p.{c['page']}] ({c['section']})\n{c['text']}")
        citations.append(Citation(page=c["page"], snippet=c["text"][:200]))
    return "\n\n---\n\n".join(parts), citations

def answer(llm: LLMClient, model_id: str, history: list[Turn],
           standalone_query: str, context: str) -> str:
    messages = [{"role": t.role, "content": t.content} for t in history[-6:]]
    messages.append({"role": "user",
                     "content": f"CONTEXT:\n{context}\n\nQUESTION: {standalone_query}"})
    return llm.converse(model_id, ANSWER_SYSTEM, messages, temperature=0.1, max_tokens=1024)
