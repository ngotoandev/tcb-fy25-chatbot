from app.models import Turn
from app.services.router_svc import parse_decision, RouteDecision, build_router_user_msg

def test_parse_valid():
    d = parse_decision('{"intent":"metric","standalone_query":"PBT FY25","complexity":"simple"}')
    assert d == RouteDecision("metric", "PBT FY25", "simple")

def test_parse_json_in_prose():
    d = parse_decision('Sure: {"intent":"chitchat","standalone_query":"hi","complexity":"simple"} done')
    assert d.intent == "chitchat"

def test_parse_garbage_returns_none():
    assert parse_decision("not json at all") is None

def test_parse_bad_enum_returns_none():
    assert parse_decision('{"intent":"banana","standalone_query":"x","complexity":"simple"}') is None

def test_build_user_msg_includes_history():
    msg = build_router_user_msg([Turn(role="user", content="CASA in FY25?"),
                                 Turn(role="assistant", content="40.4% [p.13]")],
                                "what about Q3?")
    assert "CASA in FY25?" in msg and "what about Q3?" in msg
