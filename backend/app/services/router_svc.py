import json
import re
from dataclasses import dataclass
from app.models import Turn
from app.services.llm import LLMClient

INTENTS = {"metric", "narrative", "hybrid", "chitchat", "out_of_scope"}
COMPLEXITIES = {"simple", "analytical"}

ROUTER_SYSTEM = """You are a query router for a chatbot whose ONLY knowledge is Techcombank's FY25 results press release (fiscal year ended 31 Dec 2025, published Jan 2026). Given the conversation and the latest user message, output ONLY a JSON object:
{"intent": "...", "standalone_query": "...", "complexity": "..."}

intent — one of:
- "metric": asks for specific financial figures/ratios (PBT, TOI, CASA, NPL, CAR, NIM, ROE, deposits, credit growth, fees...).
- "narrative": asks about events, strategy, subsidiaries, ratings, awards, explanations described in prose.
- "hybrid": needs both numbers and explanation (e.g. "why did CAR fall?", comparisons with reasons).
- "chitchat": greetings, thanks, meta questions about the bot.
- "out_of_scope": anything not answerable from the FY25 press release: other fiscal years (FY23 and earlier), other companies' data, live market/stock prices, investment advice, future predictions, non-Techcombank topics.

standalone_query — rewrite the message so it is fully self-contained using conversation context: resolve pronouns and elliptical follow-ups ("what about Q3?" after a CASA question becomes "What was the CASA ratio in 3Q25?"). Expand acronyms once (e.g. "CASA (current account savings account)"). For chitchat/out_of_scope, copy the message.

complexity — "simple" for single-fact lookups and short factual answers; "analytical" for explanations, comparisons, multi-part questions, or summaries.

Output the JSON object only. No markdown, no commentary."""

@dataclass
class RouteDecision:
    intent: str
    standalone_query: str
    complexity: str

def parse_decision(text: str) -> RouteDecision | None:
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    intent, query, cx = obj.get("intent"), obj.get("standalone_query"), obj.get("complexity")
    if intent not in INTENTS or cx not in COMPLEXITIES or not isinstance(query, str) or not query:
        return None
    return RouteDecision(intent, query, cx)

def build_router_user_msg(history: list[Turn], message: str) -> str:
    lines = [f"{t.role}: {t.content}" for t in history[-6:]]
    lines.append(f"user (latest): {message}")
    return "\n".join(lines)

def route(llm: LLMClient, model_id: str, history: list[Turn], message: str) -> RouteDecision:
    user_msg = build_router_user_msg(history, message)
    for _ in range(2):  # one re-ask on malformed JSON
        raw = llm.converse(model_id, ROUTER_SYSTEM,
                           [{"role": "user", "content": user_msg}], temperature=0.0, max_tokens=300)
        decision = parse_decision(raw)
        if decision:
            return decision
    return RouteDecision("narrative", message, "analytical")
