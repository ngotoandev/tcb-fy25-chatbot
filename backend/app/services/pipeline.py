import json
import time
import uuid
from pathlib import Path
from app.config import Settings
from app.models import ChatResponse, Citation, Turn
from app.services import answerer
from app.services.llm import LLMClient
from app.services.metrics_store import MetricsStore
from app.services.retrieval import Retriever, expand_query
from app.services.router_svc import route
from app.stores import make_store

CHITCHAT_REPLY = ("Hi! I answer questions about Techcombank's FY25 results "
                  "(fiscal year ended 31 Dec 2025) based on the official press release. "
                  "Try: “What was profit before tax in FY25?”")
OOS_REPLY = ("I can only answer from Techcombank's FY25 results press release, so I can't help "
             "with that. I can cover FY25/quarterly financials, subsidiaries (TCBS, Techcom Life, "
             "TCGI), ratings, and business highlights.")

def _model_label(model_id: str) -> str:
    for fam in ("haiku", "sonnet", "opus"):
        if fam in model_id:
            return fam
    return model_id.split(".")[-1]

class ChatPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.llm = LLMClient(settings)
        self.retriever = Retriever(settings.artifacts_dir)
        self.metrics = MetricsStore(Path(settings.artifacts_dir) / "metrics.json")
        self.glossary: dict[str, str] = json.loads(
            (Path(settings.artifacts_dir) / "glossary.json").read_text(encoding="utf-8"))
        self.store = make_store(settings)

    def handle(self, session_id: str | None, message: str) -> ChatResponse:
        t0 = time.monotonic()
        sid = session_id or uuid.uuid4().hex
        history = self.store.get(sid)
        decision = route(self.llm, self.settings.model_router_id, history, message)

        citations: list[Citation] = []
        model_used = self.settings.model_router_id
        metric_block = ""
        metric_hits: list[dict] = []
        chunks: list[dict] = []
        if decision.intent == "chitchat":
            reply = CHITCHAT_REPLY
        elif decision.intent == "out_of_scope":
            reply = OOS_REPLY
        else:
            if decision.intent in ("metric", "hybrid"):
                metric_hits = self.metrics.lookup(decision.standalone_query)
                metric_block = self.metrics.render(metric_hits, decision.standalone_query)
            if decision.intent in ("narrative", "hybrid") or not metric_block:
                q = expand_query(decision.standalone_query, self.glossary)
                chunks = self.retriever.search(q, self.llm.embed_query(q), top_k=6)
            context, citations = answerer.build_context(metric_block, metric_hits, chunks)
            model_used = (self.settings.model_simple_id if decision.complexity == "simple"
                          else self.settings.model_analytical_id)
            reply = answerer.answer(self.llm, model_used, history,
                                    decision.standalone_query, context)

        self.store.append(sid, Turn(role="user", content=message))
        self.store.append(sid, Turn(role="assistant", content=reply))
        return ChatResponse(session_id=sid, reply=reply, citations=citations,
                            route=decision.intent, model=_model_label(model_used),
                            latency_ms=int((time.monotonic() - t0) * 1000))
