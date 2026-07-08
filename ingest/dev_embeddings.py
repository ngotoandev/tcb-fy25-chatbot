"""DEV/TEST ONLY. Generates a DETERMINISTIC seeded-random embeddings.npz aligned
to chunks.json so the retrieval/pipeline code can be built and tested OFFLINE
while AWS Bedrock model access is pending. These are NOT real semantic vectors.
Real embeddings come from `python -m ingest.run` (Titan v2) and MUST be
regenerated before evaluation and deployment.

Run: python -m ingest.dev_embeddings
"""
import json
from pathlib import Path
import numpy as np

ARTIFACTS = Path("data/artifacts")


def main() -> None:
    chunks = json.loads((ARTIFACTS / "chunks.json").read_text(encoding="utf-8"))
    n = len(chunks)

    rng = np.random.default_rng(42)
    vectors = rng.standard_normal((n, 1024)).astype(np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)  # unit-norm rows, like the real ones

    chunk_ids = np.array([c["chunk_id"] for c in chunks])
    np.savez_compressed(ARTIFACTS / "embeddings.npz",
                        vectors=vectors,
                        chunk_ids=chunk_ids,
                        placeholder=np.array([True]))

    print(f"PLACEHOLDER embeddings written for {n} chunks -> {ARTIFACTS / 'embeddings.npz'} {vectors.shape}")
    print("These are deterministic seeded-random vectors, NOT real semantic embeddings.")
    print("Regenerate with `python -m ingest.run` once Bedrock access is available.")


if __name__ == "__main__":
    main()
