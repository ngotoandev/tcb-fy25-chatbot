import json
import logging
import re
from pathlib import Path
import numpy as np
from rank_bm25 import BM25Okapi

TOKEN_RE = re.compile(r"[a-z0-9]+")
RRF_K = 60

def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())

def expand_query(query: str, glossary: dict[str, str]) -> str:
    extras = [exp for acro, exp in glossary.items()
              if re.search(rf"\b{re.escape(acro)}\b", query, flags=re.IGNORECASE)]
    return query + (" (" + "; ".join(extras) + ")" if extras else "")

class Retriever:
    def __init__(self, artifacts_dir: str | Path) -> None:
        d = Path(artifacts_dir)
        self.chunks: list[dict] = json.loads((d / "chunks.json").read_text(encoding="utf-8"))
        npz = np.load(d / "embeddings.npz", allow_pickle=False)
        self.vectors: np.ndarray = npz["vectors"]          # (n, 1024) normalized
        self.chunk_ids: list[str] = [str(x) for x in npz["chunk_ids"]]
        assert [c["chunk_id"] for c in self.chunks] == self.chunk_ids, "artifacts out of sync"
        if "placeholder" in npz.files and bool(npz["placeholder"][0]):
            logging.getLogger(__name__).warning(
                "Retriever loaded PLACEHOLDER embeddings (not real Titan vectors) — "
                "regenerate via `python -m ingest.run` before evaluation/deploy."
            )
        self._bm25 = BM25Okapi([_tokens(c["section"] + " " + c["text"]) for c in self.chunks])

    def search(self, query: str, query_vec: np.ndarray | None, top_k: int = 6) -> list[dict]:
        n = len(self.chunks)
        bm25_rank = np.argsort(-np.asarray(self._bm25.get_scores(_tokens(query))))
        rrf = np.zeros(n)
        for rank, idx in enumerate(bm25_rank):
            rrf[idx] += 1.0 / (RRF_K + rank)
        if query_vec is not None:
            cos_rank = np.argsort(-(self.vectors @ query_vec.astype(np.float32)))
            for rank, idx in enumerate(cos_rank):
                rrf[idx] += 1.0 / (RRF_K + rank)
        order = np.argsort(-rrf)[:top_k]
        return [{**self.chunks[i], "score": float(rrf[i])} for i in order]
