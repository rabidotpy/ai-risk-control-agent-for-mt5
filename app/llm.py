"""Thin Anthropic wrapper that runs one risk evaluation.

We force tool use so Claude must return structured JSON via the
`report_evaluation` tool. The system prompt is marked with
`cache_control: ephemeral` so repeated requests for the same risk reuse the
cached prompt — meaningful savings since the prompt is the bulk of the
input tokens for a typical request.
"""

from __future__ import annotations

from typing import Any, Protocol

from .config import ANTHROPIC_API_KEY, CLAUDE_MAX_TOKENS, CLAUDE_MODEL
from .risks import REPORT_EVALUATION_TOOL, Risk


class LLMEvaluator(Protocol):
    """Pluggable evaluator. Tests inject a fake; production uses Anthropic."""

    def evaluate(self, risk: Risk, request_payload_json: str) -> dict[str, Any]:
        ...


class AnthropicEvaluator:
    """Production evaluator backed by the Anthropic SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = CLAUDE_MODEL,
        max_tokens: int = CLAUDE_MAX_TOKENS,
    ):
        # Lazy import so the SDK isn't required for unit tests that inject a fake.
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key or ANTHROPIC_API_KEY)
        self._model = model
        self._max_tokens = max_tokens

    def evaluate(self, risk: Risk, request_payload_json: str) -> dict[str, Any]:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=[
                {
                    "type": "text",
                    "text": risk.system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[REPORT_EVALUATION_TOOL],
            tool_choice={"type": "tool", "name": "report_evaluation"},
            messages=[{"role": "user", "content": request_payload_json}],
        )

        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                # `input` is already a dict — Anthropic SDK parses tool input JSON.
                return dict(block.input)  # type: ignore[arg-type]

        raise RuntimeError(
            f"Risk '{risk.key}': model did not return a report_evaluation tool_use block"
        )
