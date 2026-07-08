import os
os.environ["MOCK_LLM"] = "true"          # before app import
os.environ["SESSION_STORE"] = "memory"

from fastapi.testclient import TestClient
from app.main import create_app

client = TestClient(create_app())

def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["chunks"] > 0 and body["mock"] is True

def test_chat_roundtrip_and_session_continuity():
    r1 = client.post("/api/chat", json={"message": "What was PBT in FY25?"})
    assert r1.status_code == 200
    b1 = r1.json()
    assert b1["reply"] and b1["session_id"] and b1["route"] and b1["model"]
    r2 = client.post("/api/chat", json={"session_id": b1["session_id"], "message": "and in 4Q25?"})
    assert r2.status_code == 200
    assert r2.json()["session_id"] == b1["session_id"]

def test_validation_rejects_empty():
    assert client.post("/api/chat", json={"message": ""}).status_code == 422

def test_rate_limiter_thread_safe_exact_under_concurrency():
    # FastAPI runs the sync /api/chat endpoint on a thread pool, so _rate_limited
    # is called concurrently. With the lock, exactly per_min requests to one key
    # are allowed and the rest blocked, regardless of interleaving. Without it,
    # racing threads can both pass the check and allow more than per_min.
    import threading
    from app.api import chat as chat_mod

    with chat_mod._hits_lock:
        chat_mod._hits.clear()
    key, per_min, n = "concurrent-key", 20, 100
    results: list[bool] = []
    results_lock = threading.Lock()
    barrier = threading.Barrier(n)

    def worker():
        barrier.wait()  # release all threads together to maximize contention
        limited = chat_mod._rate_limited(key, per_min)
        with results_lock:
            results.append(limited)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    allowed = results.count(False)
    assert allowed == per_min, f"expected exactly {per_min} allowed, got {allowed}"
    with chat_mod._hits_lock:
        chat_mod._hits.clear()
