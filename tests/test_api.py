import pytest
from fastapi.testclient import TestClient
from src.backend.app import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "HEALTHY"

def test_tenants_endpoint():
    response = client.get("/tenants")
    assert response.status_code == 200
    tenants = response.json()["tenants"]
    assert len(tenants) >= 2
    tenant_ids = [t["id"] for t in tenants]
    assert "org_demo_alpha" in tenant_ids
    assert "org_demo_bravo" in tenant_ids

def test_analyze_and_results_flow():
    # Trigger analysis
    res = client.post("/analyze?tenant_id_query=org_demo_alpha")
    assert res.status_code == 200
    data = res.json()
    assert data["tenant_id"] == "org_demo_alpha"
    assert data["total_charges"] > 0

    # Get results
    results_res = client.get("/results?tenant_id_query=org_demo_alpha")
    assert results_res.status_code == 200
    res_data = results_res.json()
    assert res_data["total"] > 0

def test_eval_endpoint():
    res = client.get("/eval?tenant_id_query=org_demo_alpha")
    assert res.status_code == 200
    data = res.json()
    assert "claim_precision" in data
    assert data["claim_precision"] >= 0.0
