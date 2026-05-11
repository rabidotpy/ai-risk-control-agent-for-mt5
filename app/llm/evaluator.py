"""Async Anthropic wrapper.

Forces tool use so Claude must return structured JSON via the
`report_evaluation` tool. The system prompt is marked
`cache_control: ephemeral` so repeated requests for the same risk reuse
the cached prompt — meaningful savings since the prompt is the bulk of
the input tokens for a typical request.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from ..config import settings
from ..risks import REPORT_EVALUATION_TOOL, Risk


logger = logging.getLogger(__name__)


class LLMEvaluator(Protocol):
    """Pluggable evaluator. Tests inject a fake; production uses Anthropic."""

    async def evaluate(self, risk: Risk, request_payload_json: str) -> dict[str, Any]:
        ...


class AsyncAnthropicEvaluator:
    """Production evaluator backed by the AsyncAnthropic SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
    ):
        # Lazy import so the SDK isn't required for unit tests that inject a fake.
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key or settings.anthropic_api_key)
        self._model = model or settings.claude_model
        self._max_tokens = max_tokens or settings.claude_max_tokens

    async def evaluate(self, risk: Risk, request_payload_json: str) -> dict[str, Any]:
        logger.debug("anthropic call risk=%s model=%s", risk.key, self._model)
        response = await self._client.messages.create(
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
