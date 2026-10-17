"""Small LangChain chat model using OpenRouter's free-only API route."""

from __future__ import annotations

import os
from typing import Any

import httpx
from pydantic import Field, SecretStr
from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

load_dotenv()


class OpenRouterFreeChatModel(BaseChatModel):
    model_name: str = "openrouter/free"
    max_tokens: int = 400
    request_timeout: float = 15.0
    api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)

    @property
    def _llm_type(self) -> str:
        return "openrouter-free"

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None,
        run_manager: Any = None, **kwargs: Any,
    ) -> ChatResult:
        if self.model_name != "openrouter/free" and not self.model_name.endswith(":free"):
            raise ValueError("Only free OpenRouter models are allowed")
        key = self.api_key.get_secret_value() if self.api_key else os.getenv("OPENROUTER_API_KEY")
        if not key:
            raise ValueError("OPENROUTER_API_KEY is not set")
        roles = []
        for message in messages:
            if isinstance(message, SystemMessage):
                role = "system"
            elif isinstance(message, HumanMessage):
                role = "user"
            elif isinstance(message, AIMessage):
                role = "assistant"
            else:
                raise ValueError("Unsupported message type")
            roles.append({"role": role, "content": str(message.content)})
        with httpx.Client(timeout=self.request_timeout) as client:
            response = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": self.model_name, "messages": roles, "max_tokens": self.max_tokens,
                      "temperature": 0},
            )
        response.raise_for_status()
        payload = response.json()
        choice = payload.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content") or ""
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])
