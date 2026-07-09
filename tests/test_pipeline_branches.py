import os
os.environ["MOCK_LLM"] = "true"          # before app import
os.environ["SESSION_STORE"] = "memory"

import app.services.pipeline as pipeline_mod
from app.config import Settings
from app.services.pipeline import ChatPipeline
from app.services.router_svc import RouteDecision

# Under MOCK_LLM=true the mock router always classifies as "narrative", so the
# metric/hybrid/chitchat/out_of_scope branches in ChatPipeline.handle() get no
# coverage from the API-level tests. These tests force each intent by
# monkeypatching route() -- must patch app.services.pipeline.route, since
# pipeline.py does `from app.services.router_svc import route`, binding the
# name into its own module namespace.
pipeline = ChatPipeline(Settings(mock_llm=True))

def _fake_route(intent: str, standalone_query: str, complexity: str):
    """route() replacement that always returns a fixed RouteDecision, ignoring
    its (llm, model_id, history, message) arguments."""
    def _route(llm, model_id, history, message):
        return RouteDecision(intent, standalone_query, complexity)
    return _route

def test_chitchat_branch_returns_canned_reply_no_citations(monkeypatch):
    monkeypatch.setattr(pipeline_mod, "route", _fake_route("chitchat", "hi", "simple"))
    resp = pipeline.handle(None, "hi there!")
    assert resp.reply == pipeline_mod.CHITCHAT_REPLY
    assert resp.citations == []
    assert resp.route == "chitchat"

def test_out_of_scope_branch_returns_canned_refusal_no_citations(monkeypatch):
    monkeypatch.setattr(pipeline_mod, "route",
                        _fake_route("out_of_scope", "What was FY23 profit?", "simple"))
    resp = pipeline.handle(None, "What was FY23 profit?")
    assert resp.reply == pipeline_mod.OOS_REPLY
    assert resp.citations == []
    assert resp.route == "out_of_scope"

def test_metric_branch_dividend_cites_page_4_not_13(monkeypatch):
    # Regression test for Fix 1: build_context() used to hardcode Citation(page=13, ...)
    # for ANY non-empty metric_block. The dividend metric's real source page is 4.
    query = "How much dividend was paid in 2025?"
    monkeypatch.setattr(pipeline_mod, "route", _fake_route("metric", query, "simple"))
    resp = pipeline.handle(None, query)
    assert resp.route == "metric"
    assert resp.model == "nova-lite"                # complexity "simple" -> model_simple_id
    pages = [c.page for c in resp.citations]
    assert 4 in pages
    assert 13 not in pages

def test_hybrid_branch_analytical_combines_metric_and_chunk_citations(monkeypatch):
    query = "Why did CAR fall in Q4 2025, and how much dividend was paid?"
    monkeypatch.setattr(pipeline_mod, "route", _fake_route("hybrid", query, "analytical"))
    resp = pipeline.handle(None, query)
    assert resp.route == "hybrid"
    assert resp.model == "nova-pro"                  # complexity "analytical" -> model_analytical_id
    pages = [c.page for c in resp.citations]
    assert len(pages) >= 2
    assert any(p in (4, 13) for p in pages)          # a metric-sourced page (dividend p.4 / CAR p.13)
    assert any(p not in (4, 13) for p in pages)      # a chunk-sourced page (retrieval-only)
