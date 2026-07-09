import json
import logging
import random
import time
import boto3
import numpy as np
from app.config import Settings

EMBED_MODEL = "amazon.titan-embed-text-v2:0"
RETRYABLE = {"ThrottlingException", "ServiceUnavailableException", "ModelTimeoutException",
             "InternalServerException"}
MOCK_ROUTER_JSON = json.dumps({"intent": "narrative", "standalone_query": "mock", "complexity": "simple"})
logger = logging.getLogger(__name__)

class LLMClient:
    """Provider-agnostic chat client. `bedrock` uses the AWS Converse API (with
    Titan embeddings); `anthropic` / `openai` call the vendor API directly and
    have no embeddings, so retrieval degrades to BM25-only. Mock mode needs no
    provider client at all (canned responses)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._provider = settings.llm_provider
        self._client = None
        if settings.mock_llm:
            return
        if self._provider == "bedrock":
            self._client = boto3.client("bedrock-runtime", region_name=settings.bedrock_region)
        elif self._provider == "anthropic":
            import anthropic  # lazy: only needed when this provider is active
            self._client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        elif self._provider == "openai":
            from openai import OpenAI
            self._client = OpenAI()  # reads OPENAI_API_KEY from env
        else:
            raise ValueError(f"unknown llm_provider: {self._provider!r} (bedrock|anthropic|openai)")

    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def converse(self, model_id: str, system: str, messages: list[dict],
                 temperature: float = 0.0, max_tokens: int = 1024) -> str:
        if self._settings.mock_llm:
            return MOCK_ROUTER_JSON if "intent" in system else \
                "[MOCK] This is a canned grounded answer for UI testing. [p.1]"
        if self._provider == "anthropic":
            # system is a top-level param; message content is a plain string.
            # The SDK auto-retries throttles/5xx internally (max_retries).
            resp = self._client.messages.create(
                model=model_id, max_tokens=max_tokens, system=system, temperature=temperature,
                messages=[{"role": m["role"], "content": m["content"]} for m in messages],
            )
            return "".join(b.text for b in resp.content if b.type == "text")
        if self._provider == "openai":
            resp = self._client.chat.completions.create(
                model=model_id, max_tokens=max_tokens, temperature=temperature,
                messages=[{"role": "system", "content": system},
                          *({"role": m["role"], "content": m["content"]} for m in messages)],
            )
            return resp.choices[0].message.content or ""
        # bedrock (default): manual retry/backoff on the boto ClientError shape.
        last_err: Exception | None = None
        for attempt in range(4):
            try:
                resp = self._client.converse(
                    modelId=model_id,
                    system=[{"text": system}],
                    messages=[{"role": m["role"], "content": [{"text": m["content"]}]}
                              for m in messages],
                    inferenceConfig={"temperature": temperature, "maxTokens": max_tokens},
                )
                return resp["output"]["message"]["content"][0]["text"]
            except Exception as e:  # boto ClientError shape
                code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
                if code in RETRYABLE and attempt < 3:
                    self._sleep(min(8.0, 2 ** attempt) + random.random())
                    last_err = e
                    continue
                raise
        raise last_err  # pragma: no cover

    def embed_query(self, text: str) -> np.ndarray | None:
        # Embeddings come from Titan (Bedrock only). Mock and the direct
        # anthropic/openai providers return None → retrieval uses BM25 alone.
        if self._settings.mock_llm or self._provider != "bedrock":
            return None
        try:
            body = json.dumps({"inputText": text[:8000], "dimensions": 1024, "normalize": True})
            resp = self._client.invoke_model(modelId=EMBED_MODEL, body=body)
            return np.asarray(json.loads(resp["body"].read())["embedding"], dtype=np.float32)
        except Exception as exc:
            logger.warning("embed_query failed, falling back to BM25-only retrieval: %s", exc)
            return None  # degrade to BM25-only retrieval
