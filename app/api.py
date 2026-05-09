"""Flask app factory and the HTTP endpoints.

Endpoints:
  POST /analyse_risk    — Phase A passthrough: run analysis on a snapshot
                          payload supplied by the caller (no Alex pull).
                          Re-runs always overwrite stored rows.
  POST /run_scan        — Phase B: pull from Alex for a 6h window, bucket
                          by login, build historical context, analyse,
                          persist, and POST the batch to the callback.
                          Body is optional — defaults to the latest
                          completed 6h window. Body fields:
                            { "start_time": iso, "end_time": iso }
  GET  /analyses        — fetch already-analysed data for (mt5_login, start_time).
  GET  /healthz         — liveness.

Tests inject a fake LLM evaluator, a fake callback, a mongomock client,
and a stub Alex client via `create_app(...)`.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from flask import Flask, Response, jsonify, request
from pydantic import ValidationError
from pymongo import MongoClient

from . import callback as default_callback
from . import config, engine
from .db import client as db_client
from .db import repo as db_repo
from .ingest.alex_client import AlexClient, get_default_client
from .jobs.scan_job import run_scan
from .llm import LLMEvaluator
from .schemas import AccountSnapshot

logger = logging.getLogger(__name__)


def _dispatch_callback(callback_fn: Callable[[list], dict], body: list, *, blocking: bool) -> None:
    """Run the user-supplied callback. Fire-and-forget in production.

    The HTTP response already carries the analysis body, so a slow or hung
    callback URL must not block the caller's `/analyse_risk` round-trip.
    Tests use `blocking=True` so assertions on `callback_capture.calls` run
    against a stable post-state.
    """
    if blocking:
        try:
            callback_fn(body)
        except Exception:  # noqa: BLE001
            logger.exception("callback raised")
        return

    def _run() -> None:
        try:
            callback_fn(body)
        except Exception:  # noqa: BLE001 — callback failures must not surface
            logger.exception("callback raised in background thread")

    threading.Thread(target=_run, name="callback-deliver", daemon=True).start()


def _make_default_evaluator() -> LLMEvaluator:
    from .llm import AnthropicEvaluator

    return AnthropicEvaluator()


def _make_default_mongo_client() -> Any:
    if config.MONGODB_URI.startswith("mongomock://"):
        # Local dev / docs-only mode: in-process Mongo, no external service.
        import mongomock  # local import keeps prod cold-start lean

        logger.warning(
            "MONGODB_URI=%s — using in-process mongomock; data is NOT persisted",
            config.MONGODB_URI,
        )
        return mongomock.MongoClient()
    return MongoClient(config.MONGODB_URI)


def _parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _serialize_doc(doc: dict[str, Any]) -> dict[str, Any]:
    """Convert datetime fields to ISO strings for JSON output."""
    out: dict[str, Any] = {}
    for k, v in doc.items():
        if isinstance(v, datetime):
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def create_app(
    evaluator: LLMEvaluator | None = None,
    callback_fn: Callable[[list], dict] | None = None,
    mongo_client: Any | None = None,
    alex_client: AlexClient | None = None,
) -> Flask:
    app = Flask(__name__)
    app.config["EVALUATOR"] = evaluator
    app.config["CALLBACK_FN"] = callback_fn or default_callback.deliver
    app.config["ALEX_CLIENT"] = alex_client

    mongo = mongo_client or _make_default_mongo_client()
    coll = db_client.get_collection(mongo)
    db_client.ensure_indexes(coll)
    app.config["MONGO_COLL"] = coll
    app.config["MONGO_CLIENT"] = mongo

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    _OPENAPI_PATH = Path(__file__).parent / "openapi.yaml"

    @app.get("/openapi.yaml")
    def openapi_spec():
        try:
            spec = _OPENAPI_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            return jsonify({"error": "openapi_spec_missing"}), 404
        return Response(spec, mimetype="application/yaml")

    @app.get("/docs")
    def swagger_ui():
        # Self-contained Swagger UI page; pulls assets from a public CDN.
        html = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>AI Risk Control Agent — API Docs</title>
  <link rel=\"stylesheet\" href=\"https://unpkg.com/swagger-ui-dist@5/swagger-ui.css\" />
</head>
<body>
  <div id=\"swagger-ui\"></div>
  <script src=\"https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js\"></script>
  <script>
    window.ui = SwaggerUIBundle({
      url: '/openapi.yaml',
      dom_id: '#swagger-ui',
      deepLinking: true,
    });
  </script>
</body>
</html>"""
        return Response(html, mimetype="text/html")

    @app.post("/analyse_risk")
    def analyse_risk():
        if not request.is_json:
            return (
                jsonify({"error": "request body must be application/json"}),
                415,
            )

        try:
            snapshot = AccountSnapshot.model_validate(request.get_json())
        except ValidationError as e:
            return (
                jsonify({"error": "validation_error", "details": e.errors()}),
                400,
            )

        ev = app.config["EVALUATOR"]
        if ev is None:
            ev = _make_default_evaluator()
            app.config["EVALUATOR"] = ev

        # Always run — re-POSTs overwrite the stored rows.
        results = engine.analyse(snapshot, ev)

        db_repo.save_results(
            app.config["MONGO_COLL"],
            mt5_login=snapshot.mt5_login,
            start_time=snapshot.start_time,
            end_time=snapshot.end_time,
            results=results,
        )

        body = [r.model_dump(mode="json") for r in results]
        _dispatch_callback(
            app.config["CALLBACK_FN"],
            body,
            blocking=bool(app.config.get("TESTING")),
        )
        return jsonify(body), 200

    @app.post("/run_scan")
    def run_scan_endpoint():
        # Body is optional; if absent, default to the latest completed window.
        payload: dict[str, Any] = {}
        if request.data:
            if not request.is_json:
                return (
                    jsonify({"error": "request body must be application/json"}),
                    415,
                )
            payload = request.get_json() or {}

        start_time = None
        end_time = None
        try:
            if "start_time" in payload:
                start_time = _parse_iso_datetime(payload["start_time"])
            if "end_time" in payload:
                end_time = _parse_iso_datetime(payload["end_time"])
        except (TypeError, ValueError):
            return (
                jsonify(
                    {
                        "error": "invalid_window",
                        "expected": "ISO-8601 start_time / end_time (e.g. 2026-05-08T00:00:00Z)",
                    }
                ),
                400,
            )
        if (start_time is None) ^ (end_time is None):
            return (
                jsonify(
                    {"error": "start_time and end_time must be provided together"}
                ),
                400,
            )

        ev = app.config["EVALUATOR"]
        if ev is None:
            ev = _make_default_evaluator()
            app.config["EVALUATOR"] = ev

        ax = app.config["ALEX_CLIENT"]
        if ax is None:
            ax = get_default_client()
            app.config["ALEX_CLIENT"] = ax

        summary = run_scan(
            mongo_client=app.config["MONGO_CLIENT"],
            evaluator=ev,
            alex_client=ax,
            callback_fn=app.config["CALLBACK_FN"],
            start_time=start_time,
            end_time=end_time,
            trigger_type="manual_run",
            deliver_callback_blocking=bool(app.config.get("TESTING")),
        )
        status = 200 if summary.error is None else 502
        return jsonify(summary.to_dict()), status

    @app.get("/analyses")
    def get_analyses():
        mt5_login = request.args.get("mt5_login", type=int)
        start_time_str = request.args.get("start_time")
        if mt5_login is None or not start_time_str:
            return (
                jsonify(
                    {
                        "error": "missing_query_params",
                        "required": ["mt5_login", "start_time"],
                    }
                ),
                400,
            )
        try:
            start_time = _parse_iso_datetime(start_time_str)
        except ValueError:
            return (
                jsonify(
                    {
                        "error": "invalid_start_time",
                        "expected": "ISO-8601 (e.g. 2026-05-08T00:00:00Z)",
                    }
                ),
                400,
            )

        cached = db_repo.get_results(
            app.config["MONGO_COLL"],
            mt5_login=mt5_login,
            start_time=start_time,
        )
        if not cached:
            return (
                jsonify(
                    {
                        "error": "not_found",
                        "mt5_login": mt5_login,
                        "start_time": start_time.isoformat(),
                    }
                ),
                404,
            )
        return jsonify([_serialize_doc(d) for d in cached]), 200

    return app


# Flask factory pattern: run with `flask --app app.api run`. Flask auto-detects
# `create_app` so we deliberately do NOT instantiate at module level.
