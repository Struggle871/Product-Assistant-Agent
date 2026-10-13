import json

import httpx
import pytest

from app.config import Settings
from app.infrastructure.chat import complete_json


@pytest.mark.asyncio
async def test_chat_can_constrain_available_citations_with_json_schema() -> None:
    settings = Settings.model_validate(
        {
            "chat_provider": "openai",
            "chat_api_key": "test",
            "chat_base_url": "https://example.test/v1",
        }
    )
    schema: dict[str, object] = {"type": "object", "additionalProperties": False}

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["response_format"]["json_schema"]["schema"] == schema
        assert payload["response_format"]["json_schema"]["strict"] is True
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]}
        )

    assert (
        await complete_json(
            "JSON",
            "data",
            settings=settings,
            json_schema=schema,
            transport=httpx.MockTransport(respond),
        )
        == "{}"
    )
