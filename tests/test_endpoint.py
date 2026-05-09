"""Flask /analyse_risk + /analyses integration tests with mocked LLM + Mongo."""

from __future__ import annotations

import json

from app.risks import (
    ALL_RISKS,
    BONUS_ABUSE,
    LATENCY_ARBITRAGE,
    SCALPING,
    SWAP_ARBITRAGE,
)

from .fixtures import all_true, first_n_true, sample_snapshot


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_rejects_non_json(client):
    resp = client.post("/analyse_risk", data="not-json", content_type="text/plain")
    assert resp.status_code == 415


def test_validates_request(client):
    resp = client.post(
        "/analyse_risk",
        data=json.dumps({"start_time": "not-a-date"}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "validation_error"


def test_response_is_top_level_array_with_four_results(client, evaluator):
    for risk in ALL_RISKS:
        evaluator.set(risk.key, all_true(risk))

    resp = client.post(
        "/analyse_risk",
        data=sample_snapshot().model_dump_json(),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert isinstance(body, list)
    assert len(body) == 4


def test_each_result_has_the_expected_shape(client, evaluator):
    for risk in ALL_RISKS:
        evaluator.set(risk.key, all_true(risk))

    body = client.post(
        "/analyse_risk",
        data=sample_snapshot().model_dump_json(),
        content_type="application/json",
    ).get_json()

    expected_fields = {
        "mt5_login",
        "risk_type",
        "risk_score",
        "risk_level",
        "trigger_type",
        "evidence",
        "suggested_action",
        "analysis",
    }
    for entry in body:
        assert set(entry.keys()) == expected_fields, entry
        assert entry["mt5_login"] == 200001
        assert entry["trigger_type"] == "scheduled_scan"
        assert entry["risk_score"] == 100
        assert entry["risk_level"] == "critical"
        assert entry["risk_type"] in {
            "latency_arbitrage",
            "scalping",
            "swap_arbitrage",
            "bonus_abuse",
        }


def test_partial_truthiness_in_response(client, evaluator):
    # Phase B denominators: latency/scalping/swap_arb = 5 rules each,
    # bonus_abuse = 6.
    evaluator.set(LATENCY_ARBITRAGE.key, first_n_true(LATENCY_ARBITRAGE, 4))
    evaluator.set(SCALPING.key, first_n_true(SCALPING, 0))
    evaluator.set(SWAP_ARBITRAGE.key, first_n_true(SWAP_ARBITRAGE, 5))
    evaluator.set(BONUS_ABUSE.key, first_n_true(BONUS_ABUSE, 6))

    body = client.post(
        "/analyse_risk",
        data=sample_snapshot().model_dump_json(),
        content_type="application/json",
    ).get_json()

    by_type = {r["risk_type"]: r for r in body}
    assert by_type["latency_arbitrage"]["risk_score"] == 80
    assert by_type["latency_arbitrage"]["risk_level"] == "high"
    assert by_type["latency_arbitrage"]["suggested_action"] == "restrict_opening_pause_withdrawal"
    assert by_type["scalping"]["risk_score"] == 0
    assert by_type["scalping"]["risk_level"] == "low"
    assert by_type["swap_arbitrage"]["risk_score"] == 100
    assert by_type["swap_arbitrage"]["risk_level"] == "critical"
    assert by_type["bonus_abuse"]["risk_score"] == 100


def test_callback_receives_the_same_array(client, evaluator, callback_capture):
    for risk in ALL_RISKS:
        evaluator.set(risk.key, all_true(risk))

    body = client.post(
        "/analyse_risk",
        data=sample_snapshot().model_dump_json(),
        content_type="application/json",
    ).get_json()

    assert len(callback_capture.calls) == 1
    callback_body = callback_capture.calls[0]
    assert callback_body == body


def test_trigger_type_passes_through(client, evaluator):
    for risk in ALL_RISKS:
        evaluator.set(risk.key, all_true(risk))

    snap = sample_snapshot()
    payload = snap.model_dump(mode="json")
    payload["trigger_type"] = "withdrawal_request"

    body = client.post(
        "/analyse_risk",
        data=json.dumps(payload),
        content_type="application/json",
    ).get_json()
    assert all(entry["trigger_type"] == "withdrawal_request" for entry in body)


# ---------------------------------------------------------------------------
# Persistence + overwrite-on-re-run + GET /analyses
# ---------------------------------------------------------------------------


def test_post_persists_results(client, evaluator, collection):
    for risk in ALL_RISKS:
        evaluator.set(risk.key, all_true(risk))

    snap = sample_snapshot()
    client.post(
        "/analyse_risk",
        data=snap.model_dump_json(),
        content_type="application/json",
    )
    # Four rows in the collection now, one per risk.
    assert collection.count_documents({"mt5_login": snap.mt5_login}) == 4


def test_repost_re_runs_engine_and_overwrites(client, evaluator, callback_capture, collection):
    """Per Rabi's spec: re-POST always re-evaluates; latest run wins; no cache short-circuit."""

    for risk in ALL_RISKS:
        evaluator.set(risk.key, all_true(risk))

    snap = sample_snapshot()
    payload = snap.model_dump_json()

    # First POST: 4 LLM calls, 1 callback, 4 stored rows.
    client.post(
        "/analyse_risk", data=payload, content_type="application/json"
    )
    assert len(evaluator.calls) == 4
    assert len(callback_capture.calls) == 1
    assert collection.count_documents({"mt5_login": snap.mt5_login}) == 4

    # Switch the canned LLM responses for the re-POST so we can verify the
    # stored rows reflect the LATEST run, not the original.
    for risk in ALL_RISKS:
        evaluator.set(risk.key, first_n_true(risk, 0))  # all-false this time

    client.post(
        "/analyse_risk", data=payload, content_type="application/json"
    )

    # Engine ran again (4 more calls); callback fired again (2 total).
    assert len(evaluator.calls) == 8
    assert len(callback_capture.calls) == 2
    # Still exactly 4 rows — the unique compound index plus replace_one
    # upsert prevents duplicates and overwrites in place.
    assert collection.count_documents({"mt5_login": snap.mt5_login}) == 4
    # Stored rows reflect the second run (all scores = 0).
    stored = list(collection.find({"mt5_login": snap.mt5_login}, {"_id": False}))
    assert all(row["risk_score"] == 0 for row in stored)


def test_get_analyses_returns_cached_rows(client, evaluator):
    for risk in ALL_RISKS:
        evaluator.set(risk.key, all_true(risk))

    snap = sample_snapshot()
    client.post(
        "/analyse_risk", data=snap.model_dump_json(), content_type="application/json"
    )

    resp = client.get(
        "/analyses",
        query_string={
            "mt5_login": str(snap.mt5_login),
            "start_time": snap.start_time.isoformat(),
        },
    )
    assert resp.status_code == 200
    rows = resp.get_json()
    assert isinstance(rows, list)
    assert len(rows) == 4
    risk_types = sorted(r["risk_type"] for r in rows)
    assert risk_types == [
        "bonus_abuse",
        "latency_arbitrage",
        "scalping",
        "swap_arbitrage",
    ]


def test_get_analyses_404_when_not_yet_analysed(client):
    resp = client.get(
        "/analyses",
        query_string={
            "mt5_login": "999999",
            "start_time": "2026-01-01T00:00:00Z",
        },
    )
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["error"] == "not_found"


def test_get_analyses_400_on_missing_params(client):
    resp = client.get("/analyses", query_string={"mt5_login": "123"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "missing_query_params"


def test_get_analyses_400_on_bad_start_time(client):
    resp = client.get(
        "/analyses",
        query_string={"mt5_login": "123", "start_time": "not-a-date"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_start_time"


def test_get_analyses_accepts_z_suffix(client, evaluator):
    """`2026-05-08T00:00:00Z` should match what was stored as `+00:00`."""

    for risk in ALL_RISKS:
        evaluator.set(risk.key, all_true(risk))

    snap = sample_snapshot()
    client.post(
        "/analyse_risk", data=snap.model_dump_json(), content_type="application/json"
    )

    resp = client.get(
        "/analyses",
        query_string={
            "mt5_login": str(snap.mt5_login),
            "start_time": "2026-05-08T00:00:00Z",
        },
    )
    assert resp.status_code == 200
    assert len(resp.get_json()) == 4
