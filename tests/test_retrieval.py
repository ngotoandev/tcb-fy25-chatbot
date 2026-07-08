import numpy as np
from app.services.retrieval import Retriever, expand_query

r = Retriever("data/artifacts")

def test_bm25_only_finds_dividend_chunk():
    hits = r.search("cash dividend payment October", query_vec=None, top_k=6)
    assert hits and any("dividend" in h["text"].lower() for h in hits)

def test_vector_path_with_self_embedding():
    # use a chunk's own vector as the query vector -> that chunk must rank #1
    vec = r.vectors[0]
    hits = r.search("zzz nonsense zzz", query_vec=vec, top_k=3)
    assert hits[0]["chunk_id"] == r.chunk_ids[0]

def test_expand_query():
    glossary = {"CASA": "current account savings account"}
    out = expand_query("What is the CASA ratio?", glossary)
    assert "current account savings account" in out

def test_results_have_metadata():
    hits = r.search("marathon", None, top_k=3)
    assert all({"chunk_id", "section", "page", "text", "score"} <= set(h) for h in hits)
