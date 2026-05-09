"""Smoke tests for the OpenAPI spec + Swagger UI endpoints."""

from __future__ import annotations

import yaml


def test_openapi_yaml_served(client):
    resp = client.get("/openapi.yaml")
    assert resp.status_code == 200
    assert resp.mimetype == "application/yaml"
    spec = yaml.safe_load(resp.data)
    assert spec["openapi"].startswith("3.")
    assert "/analyse_risk" in spec["paths"]
    assert "/run_scan" in spec["paths"]
    assert "/analyses" in spec["paths"]


def test_docs_page_served(client):
    resp = client.get("/docs")
    assert resp.status_code == 200
    assert "swagger-ui" in resp.get_data(as_text=True)
