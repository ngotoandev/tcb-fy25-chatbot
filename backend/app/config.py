from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    bedrock_region: str = "us-east-1"
    model_router_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    model_simple_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    model_analytical_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    session_store: str = "memory"          # memory | dynamo
    sessions_table: str = "tcb-chatbot-sessions"
    mock_llm: bool = False
    artifacts_dir: str = "data/artifacts"
    static_dir: str = "static"
    rate_limit_per_min: int = 20
    session_ttl_hours: int = 24

@lru_cache
def get_settings() -> Settings:
    return Settings()
