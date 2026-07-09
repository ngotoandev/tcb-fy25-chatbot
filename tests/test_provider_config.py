"""LLM provider selection resolves the right per-tier model IDs, and explicit
env overrides still win. No network — pure Settings resolution."""
from app.config import Settings


def test_bedrock_defaults_to_nova():
    s = Settings(llm_provider="bedrock")
    assert s.model_router_id == "us.amazon.nova-lite-v1:0"
    assert s.model_simple_id == "us.amazon.nova-lite-v1:0"
    assert s.model_analytical_id == "us.amazon.nova-pro-v1:0"


def test_anthropic_defaults_to_claude():
    s = Settings(llm_provider="anthropic")
    assert s.model_router_id == "claude-haiku-4-5"
    assert s.model_simple_id == "claude-haiku-4-5"
    assert s.model_analytical_id == "claude-sonnet-4-6"


def test_openai_defaults_to_gpt():
    s = Settings(llm_provider="openai")
    assert s.model_router_id == "gpt-4o-mini"
    assert s.model_analytical_id == "gpt-4o"


def test_explicit_env_override_wins(monkeypatch):
    monkeypatch.setenv("MODEL_ROUTER_ID", "custom-router-model")
    s = Settings(llm_provider="anthropic")
    assert s.model_router_id == "custom-router-model"       # env override kept
    assert s.model_analytical_id == "claude-sonnet-4-6"     # rest still provider-defaulted


def test_unknown_provider_falls_back_to_bedrock_models():
    # config resolution is lenient (falls back to bedrock model set); the LLMClient
    # is what rejects an unknown provider at construction time.
    s = Settings(llm_provider="somethingelse")
    assert s.model_router_id == "us.amazon.nova-lite-v1:0"
