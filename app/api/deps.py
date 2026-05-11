"""FastAPI dependencies — pluggable evaluator and callback for tests.

Per the project style guide, deps are exposed as `Annotated[..., Depends(...)]`
aliases so handler signatures stay readable in Swagger.
"""

from __future__ import annotations

from typing import Annotated, Awaitable, Callable

from fastapi import Depends, Request

from ..llm import LLMEvaluator
from ..services import deliver as default_deliver


CallbackFn = Callable[[list[dict]], Awaitable[dict]]


def get_evaluator(request: Request) -> LLMEvaluator:
    ev: LLMEvaluator | None = request.app.state.evaluator
    if ev is None:
        # Lazy default — avoids requiring an Anthropic key in test setups
        # that always inject a fake.
        from ..llm import AsyncAnthropicEvaluator

        ev = AsyncAnthropicEvaluator()
        request.app.state.evaluator = ev
    return ev


def get_callback(request: Request) -> CallbackFn:
    cb: CallbackFn | None = request.app.state.callback_fn
    return cb or default_deliver


EvaluatorDep = Annotated[LLMEvaluator, Depends(get_evaluator)]
CallbackDep = Annotated[CallbackFn, Depends(get_callback)]
