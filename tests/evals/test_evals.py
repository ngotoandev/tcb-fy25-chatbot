"""Golden evals against real Bedrock. Run: pytest -m eval -s"""
import os
import pathlib
import pytest
import yaml

os.environ.setdefault("SESSION_STORE", "memory")
pytestmark = pytest.mark.eval

from fastapi.testclient import TestClient  # noqa: E402
from app.config import Settings, get_settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.llm import LLMClient  # noqa: E402

CASES = yaml.safe_load(
    (pathlib.Path(__file__).parent / "golden.yaml").read_text(encoding="utf-8"))["cases"]
# get_settings() is a process-wide @lru_cache singleton with no args. This module
# collects alphabetically before tests/test_api_chat.py (and any other test module
# that calls create_app()), so without clearing the cache on both sides, whichever
# module runs first would permanently pin Settings for every module collected after
# it -- e.g. this module's real (mock_llm=False) settings would leak into
# test_api_chat.py's MOCK_LLM=true client. Clear before (read fresh env for our own
# client) and after (don't pin our real settings for modules collected next).
get_settings.cache_clear()
client = TestClient(create_app())
judge = LLMClient(Settings(mock_llm=False))
get_settings.cache_clear()

JUDGE_MODEL = Settings().model_router_id  # cheap configured model for the YES/NO refusal judgment
JUDGE_SYSTEM = ("You judge chatbot replies. Answer with exactly YES or NO. "
                "YES if the reply DECLINES to answer (says the information is not in the "
                "FY25 press release / out of scope / cannot help). NO otherwise.")

def ask(turns: list[str]) -> str:
    sid = None
    reply = ""
    for t in turns:
        r = client.post("/api/chat", json={"session_id": sid, "message": t})
        assert r.status_code == 200, r.text
        body = r.json()
        sid, reply = body["session_id"], body["reply"]
    return reply

@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_golden(case):
    reply = ask(case["turns"])
    low = reply.lower()
    print(f"\n[{case['id']}] {reply[:160]}")
    if case.get("expect_refusal"):
        verdict = judge.converse(
            JUDGE_MODEL, JUDGE_SYSTEM,
            [{"role": "user", "content": f"Reply: {reply}"}], max_tokens=5)
        assert "YES" in verdict.upper(), f"expected refusal, got: {reply}"
    if "expect_any" in case:
        assert any(s.lower() in low for s in case["expect_any"]), reply
    if "expect_all_any" in case:
        for group in case["expect_all_any"]:
            assert any(s.lower() in low for s in group), f"missing {group}: {reply}"
