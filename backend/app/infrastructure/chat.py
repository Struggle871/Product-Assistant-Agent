"""OpenAI-compatible structured chat. Provider errors never include response bodies."""

from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from app.config import Settings, get_settings


class ChatError(RuntimeError):
    pass


class ChatMessage(BaseModel):
    content: str = Field(min_length=1)


class ChatChoice(BaseModel):
    message: ChatMessage
    finish_reason: str


class ChatResponse(BaseModel):
    choices: list[ChatChoice] = Field(min_length=1)


async def complete_json(
    system: str,
    user: str,
    *,
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    json_schema: dict[str, object] | None = None,
) -> str:
    active = settings or get_settings()
    if active.chat_provider == "disabled":
        raise ChatError("Chat model is not configured")
    if not active.chat_api_key:
        raise ChatError("CHAT_API_KEY is required for the configured service")
    payload: dict[str, object] = {
        "model": active.chat_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.6 if active.chat_enable_thinking else 0,
        "max_tokens": active.chat_max_tokens,
        "response_format": {"type": "json_object"},
    }
    if json_schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "semantic_selection",
                "strict": True,
                "schema": json_schema,
            },
        }
    # This SiliconFlow extension is optional on other compatible endpoints.
    if httpx.URL(active.chat_base_url).host == "api.siliconflow.cn":
        payload["enable_thinking"] = active.chat_enable_thinking
        if active.chat_enable_thinking:
            payload["thinking_budget"] = active.chat_thinking_budget
    async with httpx.AsyncClient(
        timeout=active.chat_timeout_seconds, transport=transport, follow_redirects=False
    ) as client:
        try:
            response = await client.post(
                f"{active.chat_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {active.chat_api_key}"},
                json=payload,
            )
            response.raise_for_status()
            parsed = ChatResponse.model_validate(response.json())
        except httpx.HTTPStatusError as exc:
            raise ChatError(f"Chat service returned HTTP {exc.response.status_code}") from None
        except httpx.RequestError:
            raise ChatError("Chat service is unavailable or timed out") from None
        except ValueError:
            raise ChatError("Chat service returned an invalid response") from None
    choice = parsed.choices[0]
    if choice.finish_reason != "stop":
        raise ChatError("Chat service returned an incomplete response")
    return choice.message.content
