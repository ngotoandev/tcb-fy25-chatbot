import json
import random
import time
import boto3
import numpy as np
from app.config import Settings

EMBED_MODEL = "amazon.titan-embed-text-v2:0"
RETRYABLE = {"ThrottlingException", "ServiceUnavailableException", "ModelTimeoutException",
             "InternalServerException"}
MOCK_ROUTER_JSON = json.dumps({"intent": "narrative", "standalone_query": "mock", "complexity": "simple"})

class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = None if settings.mock_llm else boto3.client(
            "bedrock-runtime", region_name=settings.bedrock_region)

    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def converse(self, model_id: str, system: str, messages: list[dict],
                 temperature: float = 0.0, max_tokens: int = 1024) -> str:
        if self._settings.mock_llm:
            return MOCK_ROUTER_JSON if "intent" in system else \
                "[MOCK] This is a canned grounded answer for UI testing. [p.1]"
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
        if self._settings.mock_llm:
            return None
        try:
            body = json.dumps({"inputText": text[:8000], "dimensions": 1024, "normalize": True})
            resp = self._client.invoke_model(modelId=EMBED_MODEL, body=body)
            return np.asarray(json.loads(resp["body"].read())["embedding"], dtype=np.float32)
        except Exception:
            return None  # degrade to BM25-only retrieval
