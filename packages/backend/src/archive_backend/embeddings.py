"""Embeddings for semantic search: one Titan v2 vector per dataset, from its title, description
and keywords.

`with_embedding` is the one way an embedding is set on a dataset item. The reindex and Plan 7's
publish call it before they write the item, so a later put never erases an embedding.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

MODEL = "amazon.titan-embed-text-v2:0"
DIMENSIONS = 1024


class Bedrock(Protocol):
    """The Bedrock runtime call made here (boto3-stubs has no bedrock-runtime extra installed)."""

    def invoke_model(self, **kwargs: Any) -> dict[str, Any]: ...


def embedding_text(manifest: dict[str, Any]) -> str:
    """The title, description and keywords, one to a line."""
    keywords = manifest.get("keywords")
    parts = [manifest.get("title"), manifest.get("description")]
    parts += keywords if isinstance(keywords, list) else []
    return "\n".join(str(p) for p in parts if p)


def embed(bedrock: Bedrock, text: str) -> list[float]:
    """The text's normalized Titan v2 vector."""
    body = {"inputText": text, "dimensions": DIMENSIONS, "normalize": True}
    answer = bedrock.invoke_model(
        modelId=MODEL,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    vector: list[float] = json.loads(answer["body"].read())["embedding"]
    return vector


def vector_attribute(vector: list[float]) -> list[dict[str, str]]:
    """A vector as a DynamoDB list's members, as items and `SearchVector` take it."""
    return [{"N": str(v)} for v in vector]


def with_embedding(
    item: dict[str, Any], manifest: dict[str, Any], bedrock: Bedrock
) -> dict[str, Any]:
    """A copy of the DynamoDB-JSON dataset item with `embedding` set from its manifest."""
    vector = embed(bedrock, embedding_text(manifest))
    return item | {"embedding": {"L": vector_attribute(vector)}}
