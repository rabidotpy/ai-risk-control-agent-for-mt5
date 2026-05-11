"""Request and response schemas for /analyse_risk.

The request body is either one snapshot or a list — Alex now sends one
bulk pull covering many accounts. The response is a flat list of
`RiskFinding` rows, one per (mt5_login, risk_type), with each row carrying
the per-run verdict plus the AI-produced rolling `behavior_summary`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from .snapshot import AccountSnapshot, RiskLevel, TriggerType


class AnalyseRiskRequest(BaseModel):
    """Top-level request envelope.

    Either:
      * snapshots = [<one AccountSnapshot>, ...] (preferred), or
      * a single AccountSnapshot at the root (handled at the route layer
        before validation reaches this model).

    `include_history` overrides `settings.include_history_default` for
    this request. When False, no prior `RiskHistorySummary` is loaded
    into the prompt and no summary is upserted afterwards.
    """

    model_config = ConfigDict(extra="forbid")

    snapshots: list[AccountSnapshot]
    include_history: bool | None = None


class BehaviorSummary(BaseModel):
    """The AI-produced, free-form rolling summary for one (login, risk_key).

    Shape is deliberately open — risk types will grow, and the AI is the
    aggregator. The only invariant is that `payload` is a JSON object.
    """

    model_config = ConfigDict(extra="forbid")

    payload: dict[str, Any]
    updated_at: datetime
    run_count: int


class RiskFinding(BaseModel):
    """One row of the response — one risk type evaluated for one login."""

    model_config = ConfigDict(extra="ignore")

    mt5_login: int
    risk_type: str
    risk_score: int
    risk_level: RiskLevel
    trigger_type: TriggerType
    evidence: dict[str, Any]
    suggested_action: str
    analysis: str
    behavior_summary: dict[str, Any] | None = None
