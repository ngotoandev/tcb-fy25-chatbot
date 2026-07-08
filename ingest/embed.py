import json
import boto3
import numpy as np

MODEL_ID = "amazon.titan-embed-text-v2:0"

def embed_texts(texts: list[str], region: str = "us-east-1") -> np.ndarray:
    client = boto3.client("bedrock-runtime", region_name=region)
    vecs = []
    for t in texts:
        body = json.dumps({"inputText": t[:8000], "dimensions": 1024, "normalize": True})
        resp = client.invoke_model(modelId=MODEL_ID, body=body)
        vecs.append(json.loads(resp["body"].read())["embedding"])
    return np.asarray(vecs, dtype=np.float32)
