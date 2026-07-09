from functools import lru_cache
from pydantic import model_validator
from pydantic_settings import BaseSettings

# Per-provider (router, simple, analytical) model defaults. Two tiers everywhere:
# a cheap model for routing + simple factual answers, a capable one for analytical
# synthesis. The whole system is provider-agnostic — flip LLM_PROVIDER (and supply
# the matching credentials) with no code change.
_PROVIDER_MODELS = {
    # Amazon Nova on Bedrock (default): Amazon's own family, activates with the
    # AWS account (no Anthropic-style access review), Converse-compatible, cheap.
    "bedrock": ("us.amazon.nova-lite-v1:0", "us.amazon.nova-lite-v1:0", "us.amazon.nova-pro-v1:0"),
    # Direct Anthropic API: Haiku for routing + simple, Sonnet for analytical
    # (both accept temperature, so grounded-answer temps port cleanly).
    "anthropic": ("claude-haiku-4-5", "claude-haiku-4-5", "claude-sonnet-4-6"),
    # Direct OpenAI API.
    "openai": ("gpt-4o-mini", "gpt-4o-mini", "gpt-4o"),
}

class Settings(BaseSettings):
    # bedrock (default) | anthropic | openai. Bedrock uses the AWS Converse API +
    # Titan embeddings; anthropic/openai call the vendor API directly and fall back
    # to BM25-only retrieval (neither offers embeddings we use here).
    llm_provider: str = "bedrock"
    bedrock_region: str = "us-east-1"
    # Left blank so the per-provider defaults in _PROVIDER_MODELS apply; each can
    # still be overridden via MODEL_ROUTER_ID / MODEL_SIMPLE_ID / MODEL_ANALYTICAL_ID.
    model_router_id: str = ""
    model_simple_id: str = ""
    model_analytical_id: str = ""
    session_store: str = "memory"          # memory | dynamo
    sessions_table: str = "tcb-chatbot-sessions"
    mock_llm: bool = False
    artifacts_dir: str = "data/artifacts"
    static_dir: str = "static"
    rate_limit_per_min: int = 20
    session_ttl_hours: int = 24

    @model_validator(mode="after")
    def _resolve_models(self) -> "Settings":
        r, s, a = _PROVIDER_MODELS.get(self.llm_provider, _PROVIDER_MODELS["bedrock"])
        # `x or default` keeps any explicit env override and fills the rest.
        self.model_router_id = self.model_router_id or r
        self.model_simple_id = self.model_simple_id or s
        self.model_analytical_id = self.model_analytical_id or a
        return self

@lru_cache
def get_settings() -> Settings:
    return Settings()
