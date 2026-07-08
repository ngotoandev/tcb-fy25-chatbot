import json
from app.config import Settings
from app.services.llm import LLMClient

def test_mock_mode_router_and_answer():
    c = LLMClient(Settings(mock_llm=True))
    out = c.converse("any", system="Classify intent as JSON", messages=[{"role": "user", "content": "hi"}])
    assert json.loads(out)["intent"]
    ans = c.converse("any", system="Answer from context", messages=[{"role": "user", "content": "hi"}])
    assert "MOCK" in ans
    assert c.embed_query("hello") is None

def test_retry_then_success(monkeypatch):
    c = LLMClient(Settings(mock_llm=False))
    calls = {"n": 0}
    class Boom(Exception): ...
    def fake_converse(**kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            err = type("E", (Exception,), {"response": {"Error": {"Code": "ThrottlingException"}}})()
            raise err
        return {"output": {"message": {"content": [{"text": "ok"}]}}}
    monkeypatch.setattr(c, "_sleep", lambda s: None)
    monkeypatch.setattr(c._client, "converse", fake_converse, raising=False)
    assert c.converse("m", "sys", [{"role": "user", "content": "x"}]) == "ok"
    assert calls["n"] == 3
