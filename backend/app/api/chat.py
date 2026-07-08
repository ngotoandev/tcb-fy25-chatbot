import time
from collections import defaultdict, deque
from fastapi import APIRouter, HTTPException, Request
from app.models import ChatRequest, ChatResponse

router = APIRouter()
_hits: dict[str, deque] = defaultdict(deque)

def _rate_limited(key: str, per_min: int) -> bool:
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > 60:
        q.popleft()
    if not q:
        del _hits[key]  # bound _hits growth: don't keep empty deques for idle keys
    if len(q) >= per_min:
        return True
    _hits[key].append(now)
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
