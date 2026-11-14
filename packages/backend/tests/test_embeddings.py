import io
import json
from typing import Any

from archive_backend.embeddings import (
    DIMENSIONS,
    MODEL,
    embed,
    embedding_text,
    vector_attribute,
    with_embedding,
)


class FakeBedrock:
    """Answers `invoke_model` as Titan v2 does: the body is a stream of JSON."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def invoke_model(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        body = json.loads(kwargs["body"])
        vector = [round(0.001 * n, 3) for n in range(body["dimensions"])]
        answer = {"embedding": vector, "inputTextTokenCount": 7}
        return {"body": io.BytesIO(json.dumps(answer).encode()), "contentType": "application/json"}


def _item() -> dict[str, Any]:
    return {
        "PK": {"S": "DATASET#ozone"},
        "SK": {"S": "META"},
        "id": {"S": "ozone"},
        "title": {"S": "Ozone injury"},
        "currentVersion": {"N": "2"},
    }


def test_embedding_text_is_title_description_and_keywords_on_lines() -> None:
    manifest = {"title": "Ozone injury", "description": "Foliar damage", "keywords": ["ozone", "a"]}

    assert embedding_text(manifest) == "Ozone injury\nFoliar damage\nozone\na"
    assert embedding_text({"title": "Only"}) == "Only"


def test_embed_asks_titan_v2_for_a_normalized_1024_vector() -> None:
    bedrock = FakeBedrock()

    vector = embed(bedrock, "air pollution")

    assert len(vector) == DIMENSIONS == 1024
    [call] = bedrock.calls
    assert call["modelId"] == MODEL == "amazon.titan-embed-text-v2:0"
    assert json.loads(call["body"]) == {
        "inputText": "air pollution",
        "dimensions": 1024,
        "normalize": True,
    }


def test_with_embedding_adds_the_vector_and_keeps_every_attribute() -> None:
    item = _item()
    manifest = {"title": "Ozone injury", "description": "Foliar damage"}

    embedded = with_embedding(item, manifest, FakeBedrock())

    assert {k: v for k, v in embedded.items() if k != "embedding"} == _item()
    assert "embedding" not in item
    numbers = embedded["embedding"]["L"]
    assert len(numbers) == 1024
    assert numbers[1] == {"N": "0.001"}


def test_vector_attribute_is_a_list_of_numbers() -> None:
    assert vector_attribute([0.5, -1.0]) == [{"N": "0.5"}, {"N": "-1.0"}]
