from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any

from openai import OpenAI
import requests


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0


class OpenAIProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        input_cost_per_million: float = 0.0,
        output_cost_per_million: float = 0.0,
    ):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.input_cost_per_million = input_cost_per_million
        self.output_cost_per_million = output_cost_per_million

    def _usage(self, input_tokens: int = 0, output_tokens: int = 0) -> Usage:
        return Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=(
                input_tokens * self.input_cost_per_million
                + output_tokens * self.output_cost_per_million
            )
            / 1_000_000,
        )

    def json_completion(self, prompt: str, operation: str) -> tuple[dict, Usage]:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a rigorous research analyst. Return valid JSON only and never invent citations.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        usage = response.usage
        return json.loads(content), self._usage(
            getattr(usage, "prompt_tokens", 0) or 0,
            getattr(usage, "completion_tokens", 0) or 0,
        )

    def embeddings(self, texts: list[str], model: str) -> tuple[list[list[float]], Usage]:
        response = self.client.embeddings.create(model=model, input=texts)
        return [item.embedding for item in response.data], self._usage(
            getattr(response.usage, "prompt_tokens", 0) or 0
        )


class GoogleSearchProvider:
    def __init__(self, api_key: str, engine_id: str):
        self.api_key = api_key
        self.engine_id = engine_id

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        response = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params={
                "key": self.api_key,
                "cx": self.engine_id,
                "q": query,
                "num": min(limit, 10),
            },
            timeout=20,
        )
        response.raise_for_status()
        return [
            {
                "url": item["link"],
                "title": item.get("title"),
                "snippet": item.get("snippet"),
                "display_link": item.get("displayLink"),
            }
            for item in response.json().get("items", [])
            if item.get("link")
        ]
