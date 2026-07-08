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
