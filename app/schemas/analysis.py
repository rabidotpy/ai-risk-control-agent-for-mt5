"""Request and response schemas for /analyse_risk.

The request body is either one snapshot or a list — Alex now sends one
bulk pull covering many accounts. The response is a flat list of
`RiskFinding` rows, one per (mt5_login, risk_type), with each row carrying
the per-run verdict plus the AI-produced rolling `behavior_summary`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from .snapshot import AccountSnapshot, RiskLevel, TriggerType


class AnalyseRiskRequest(BaseModel):
    """Top-level request envelope.

    The envelope accepts any of these shapes (auto-normalised before
    validation), so manual curl tests and Alex's adapter both work
    without fiddling:

      * `{"snapshots": [ {...}, {...} ]}`   — canonical, list of snapshots
      * `{"snapshots": {...}}`              — a single object, auto-wrapped
      * `{"snapshot": {...}}`               — singular alias, auto-wrapped

    `include_history` overrides `settings.include_history_default` for
    this request. When False, no prior `RiskHistorySummary` is loaded
    into the prompt and no summary is upserted afterwards.

    `enqueue_and_callback` (default False) flips the request into async
    mode: the server enqueues the job, returns `202 Accepted` with a
    `run_id`, and a background worker performs the analysis and POSTs
    the result to `settings.callback_url` when done. The client may
    also poll `GET /runs/{run_id}` for status. When False, the request
    runs synchronously and the response body carries the findings.
    """

    model_config = ConfigDict(extra="forbid")

    snapshots: list[AccountSnapshot]
    include_history: bool | None = None
    enqueue_and_callback: bool = False

    @model_validator(mode="before")
    @classmethod
    def _normalise_snapshots(cls, data: Any) -> Any:
        """Accept singular `snapshot` and bare-object `snapshots`.

        Lifts both into the canonical `snapshots: [obj]` shape before
        the strict per-field validation runs. Keeps `extra="forbid"`
        useful for catching real typos.
        """
        if not isinstance(data, dict):
            return data
        # Singular alias: {"snapshot": {...}} → {"snapshots": [{...}]}
        if "snapshot" in data and "snapshots" not in data:
            data = {**data, "snapshots": [data["snapshot"]]}
            data.pop("snapshot")
        # Bare object under plural key: {"snapshots": {...}} → {"snapshots": [{...}]}
        if isinstance(data.get("snapshots"), dict):
            data = {**data, "snapshots": [data["snapshots"]]}
        return data


class EnqueuedJob(BaseModel):
    """Response body for the async enqueue path."""

    model_config = ConfigDict(extra="forbid")

    run_id: int
    status: str
    poll_url: str
    snapshot_count: int


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
