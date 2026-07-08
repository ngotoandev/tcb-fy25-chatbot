"""Build all knowledge artifacts from the source PDF. Run: python -m ingest.run

Split into two phases so the JSON artifacts (chunks/metrics/glossary) can be
built with zero AWS dependency, while embeddings need real Bedrock access:

- write_json_artifacts(): parse -> chunk -> write chunks/metrics/glossary JSON.
  No boto3 import anywhere in this path.
- write_embeddings(chunks): embed each chunk via Bedrock Titan and write
  embeddings.npz. Requires AWS credentials with Bedrock model access.

While Bedrock access is pending, use `python -m ingest.dev_embeddings` to
generate a placeholder embeddings.npz instead of write_embeddings(), so
downstream retrieval code can be built/tested offline. Regenerate the real
embeddings via this module's main() before evaluation and deployment.
"""
import json
from pathlib import Path
import numpy as np

from ingest.parse import extract_pages
from ingest.chunker import build_chunks
from ingest.metrics_data import METRICS
from ingest.glossary_data import GLOSSARY

PDF = Path("reports/fy25-press-release-eng-12022026.pdf")
OUT = Path("data/artifacts")


def write_json_artifacts() -> list[dict]:
    """Parse the source PDF and write chunks.json/metrics.json/glossary.json.

    No boto3 import here (module-level or local) -- this must work without
    any AWS credentials or Bedrock access.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    chunks = build_chunks(extract_pages(PDF))
    (OUT / "chunks.json").write_text(json.dumps(chunks, indent=1), encoding="utf-8")
    (OUT / "metrics.json").write_text(json.dumps(METRICS, indent=1), encoding="utf-8")
    (OUT / "glossary.json").write_text(json.dumps(GLOSSARY, indent=1), encoding="utf-8")
    print(f"wrote {len(chunks)} chunks, {len(METRICS)} metrics, {len(GLOSSARY)} glossary entries")
    return chunks


def write_embeddings(chunks: list[dict]) -> None:
    """Embed chunks via Bedrock Titan and write embeddings.npz.

    Real production path; requires AWS credentials with Bedrock model access.
    """
    from ingest.embed import embed_texts  # import here so json artifacts work without boto3 creds

    vectors = embed_texts([f"{c['section']}: {c['text']}" for c in chunks])
    np.savez_compressed(OUT / "embeddings.npz",
                        vectors=vectors,
                        chunk_ids=np.array([c["chunk_id"] for c in chunks]))
    print(f"wrote embeddings {vectors.shape}")


def main() -> None:
    chunks = write_json_artifacts()
    write_embeddings(chunks)


if __name__ == "__main__":
    main()
