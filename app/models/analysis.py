"""Tortoise ORM models — three tables, one purpose each.

* AnalysisRun         — one row per /analyse_risk request invocation.
                        Pure audit trail.
* RiskEvaluation      — one row per (run, login, risk_key) verdict.
                        Append-only; per-call results live here.
* RiskHistorySummary  — one row per (login, risk_key). Upserted each call.
                        Holds the AI-produced rolling behaviour summary
                        that gets fed back as prior context next time.

The schema is deliberately risk-key-agnostic: adding a new risk type is a
pure code change under `app.risks.*` — no migration needed.
"""

from __future__ import annotations

from tortoise import fields
from tortoise.models import Model


class AnalysisRun(Model):
    """One row per /analyse_risk HTTP call (covers N snapshots)."""

    id = fields.IntField(primary_key=True)
    trigger_type = fields.CharField(max_length=64)
    snapshot_count = fields.IntField()
    started_at = fields.DatetimeField(auto_now_add=True)
    finished_at = fields.DatetimeField(null=True)
    callback_status = fields.JSONField(null=True)

    evaluations: fields.ReverseRelation["RiskEvaluation"]

    class Meta:
        table = "analysis_run"


class RiskEvaluation(Model):
    """One per-risk verdict for one snapshot in one run.

    `evidence` and `behavior_summary` are stored verbatim from the engine /
    AI output so the audit trail is complete even if the prompt schema
    changes later.
    """

    id = fields.IntField(primary_key=True)
    run: fields.ForeignKeyRelation[AnalysisRun] = fields.ForeignKeyField(
        "models.AnalysisRun", related_name="evaluations", on_delete=fields.CASCADE
    )
    mt5_login = fields.BigIntField()
    risk_key = fields.CharField(max_length=64)
    risk_score = fields.IntField()
    risk_level = fields.CharField(max_length=16)
    trigger_type = fields.CharField(max_length=64)
    evidence = fields.JSONField()
    suggested_action = fields.CharField(max_length=128)
    analysis = fields.TextField()
    behavior_summary = fields.JSONField(null=True)
    window_start = fields.DatetimeField()
    window_end = fields.DatetimeField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "risk_evaluation"
        indexes = (
            ("mt5_login", "risk_key"),
            ("mt5_login", "window_start"),
        )


class RiskHistorySummary(Model):
    """One persistent row per (mt5_login, risk_key).

    The `payload` JSON is whatever the AI returned in `behavior_summary`
    on the most recent run. We do not constrain its shape — risk types
    will grow and the prompt tells the AI to fold prior_summary into a
    new summary in one round-trip.
    """

    id = fields.IntField(primary_key=True)
    mt5_login = fields.BigIntField()
    risk_key = fields.CharField(max_length=64)
    payload = fields.JSONField()
    run_count = fields.IntField(default=0)
    last_score = fields.IntField(default=0)
    last_level = fields.CharField(max_length=16, default="low")
    first_seen_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "risk_history_summary"
        unique_together = (("mt5_login", "risk_key"),)
