import json

import httpx
import pytest

from app.config import Settings
from app.infrastructure.embeddings import EmbeddingError, embed_texts, embedding_profile


def settings(**overrides: object) -> Settings:
    return Settings.model_validate(
        {
            "embedding_provider": "openai",
            "embedding_api_key": "secret-test-key",
            "embedding_base_url": "https://embedding.example/v1",
            "embedding_dimensions": 1536,
            "embedding_send_dimensions": True,
            **overrides,
        }
    )


@pytest.mark.asyncio
async def test_batches_and_restores_response_order() -> None:
    requests: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": index, "embedding": [float(index + 1)] * 1536}
                    for index in reversed(range(len(payload["input"])))
                ]
            },
        )

    result = await embed_texts(
        ["one", "two", "three"],
        settings=settings(embedding_batch_size=2),
        transport=httpx.MockTransport(respond),
    )
    assert [vector[0] for vector in result] == [1, 2, 1]
    assert [item["input"] for item in requests] == [["one", "two"], ["three"]]
    assert requests[0]["dimensions"] == 1536
    assert requests[0]["encoding_format"] == "float"


@pytest.mark.asyncio
async def test_fixed_dimension_services_can_omit_dimensions_parameter() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert "dimensions" not in json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "data": [{"index": 0, "embedding": [1.0] * 1536}],
            },
        )

    await embed_texts(
        ["manual"],
        settings=settings(embedding_send_dimensions=False),
        transport=httpx.MockTransport(respond),
    )


@pytest.mark.parametrize(
    "data",
    [
        [{"index": 0, "embedding": [1.0]}],
        [{"index": 1, "embedding": [1.0] * 1536}],
        [{"index": 0, "embedding": [0.0] * 1536}],
        [],
    ],
)
@pytest.mark.asyncio
async def test_invalid_vectors_are_rejected(data: list[dict[str, object]]) -> None:
    with pytest.raises(EmbeddingError):
        await embed_texts(
            ["manual"],
            settings=settings(),
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"data": data})),
        )


@pytest.mark.asyncio
async def test_http_errors_do_not_expose_provider_body_or_credentials() -> None:
    with pytest.raises(EmbeddingError, match="HTTP 401") as error:
        await embed_texts(
            ["manual"],
            settings=settings(),
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    401,
                    json={"error": "secret-test-key internal provider details"},
                )
            ),
        )
    assert "secret-test-key" not in str(error.value)


@pytest.mark.asyncio
async def test_timeout_is_sanitized() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret-test-key", request=request)

    with pytest.raises(EmbeddingError, match="unavailable or timed out"):
        await embed_texts(["manual"], settings=settings(), transport=httpx.MockTransport(timeout))


def test_profile_changes_with_provider_model_and_endpoint_but_not_key() -> None:
    original = embedding_profile(settings())
    assert original == embedding_profile(settings(embedding_api_key="different-key"))
    assert original != embedding_profile(settings(embedding_model="another-model"))
    assert original != embedding_profile(settings(embedding_base_url="https://another.example/v1"))
    assert original != embedding_profile(settings(embedding_provider="hash"))


@pytest.mark.asyncio
async def test_hash_mode_is_explicit_and_deterministic() -> None:
    active = settings(embedding_provider="hash")
    first = await embed_texts(["manual"], settings=active)
    assert first == await embed_texts(["manual"], settings=active)
    assert len(first[0]) == 1536


@pytest.mark.asyncio
async def test_siliconflow_bge_m3_uses_1024_dimensions_without_requesting_resize() -> None:
    active = settings(
        embedding_base_url="https://api.siliconflow.cn/v1",
        embedding_model="BAAI/bge-m3",
        embedding_dimensions=1024,
        embedding_send_dimensions=False,
    )

    def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.siliconflow.cn/v1/embeddings"
        payload = json.loads(request.content)
        assert payload["model"] == "BAAI/bge-m3"
        assert "dimensions" not in payload
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0] * 1024}]})

    result = await embed_texts(
        ["产品资料"], settings=active, transport=httpx.MockTransport(respond)
    )
    assert len(result[0]) == 1024


@pytest.mark.asyncio
async def test_bge_m3_rejects_incompatible_1536_dimension_response() -> None:
    active = settings(embedding_dimensions=1024)
    with pytest.raises(EmbeddingError, match="dimensions"):
        await embed_texts(
            ["manual"],
            settings=active,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    json={
                        "data": [{"index": 0, "embedding": [1.0] * 1536}],
                    },
                ),
            ),
        )
