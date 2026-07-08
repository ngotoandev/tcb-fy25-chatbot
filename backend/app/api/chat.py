import threading
import time
from collections import defaultdict, deque
from fastapi import APIRouter, HTTPException, Request
from app.models import ChatRequest, ChatResponse

router = APIRouter()
# FastAPI runs sync endpoints on a thread pool, so _hits is shared across threads.
# The whole check-evict-record sequence must be atomic under one lock, or two
# concurrent requests for the same key can both pass the limit or corrupt the
# deque. Keys are client IPs, so _hits stays small (one entry per distinct IP).
_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()

def _rate_limited(key: str, per_min: int) -> bool:
    now = time.monotonic()
    with _hits_lock:
        q = _hits[key]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= per_min:
            return True
        q.append(now)
        return False

@router.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request) -> ChatResponse:
    pipeline = request.app.state.pipeline
    # Keyed on connecting IP only -- session_id is an unauthenticated client-supplied
    # field, so including it would let a client bypass the limit by rotating it.
    key = request.client.host if request.client else "anon"
    if _rate_limited(key, pipeline.settings.rate_limit_per_min):
        raise HTTPException(status_code=429, detail="Too many requests — please slow down.")
    try:
        return pipeline.handle(req.session_id, req.message)
    except Exception:
        raise HTTPException(status_code=503,
                            detail="The assistant is busy right now. Please try again shortly.")
