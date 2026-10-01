import pytest
from fastapi.testclient import TestClient
from src.backend.app import app
from src.core.tenant_security import (
    filter_by_tenant,
    validate_tenant_id,
    assert_tenant_isolation,
    verify_asset_access,
    verify_override_permission,
    TenancySecurityError
)
from src.core.rules_engine import RecoveryRulesEngine

client = TestClient(app)

@pytest.fixture
def mock_alpha_tenant():
    return "org_demo_alpha"

@pytest.fixture
def mock_bravo_tenant():
    return "org_demo_bravo"

@pytest.fixture
def sample_multi_tenant_records():
    return [
        {"id": "REC-A1", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-0001", "photo_ref": "/photos/alpha_001.jpg"},
        {"id": "REC-A2", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-0002", "photo_ref": "/photos/alpha_002.jpg"},
        {"id": "REC-B1", "tenant_id": "org_demo_bravo", "unit_id": "UNIT-0020", "photo_ref": "/photos/bravo_020.jpg"},
        {"id": "REC-B2", "tenant_id": "org_demo_bravo", "unit_id": "UNIT-0021", "photo_ref": "/photos/bravo_021.jpg"}
    ]

def test_querying_alpha_returns_zero_bravo_rows(sample_multi_tenant_records, mock_alpha_tenant, mock_bravo_tenant):
    """Test that querying charges/evidence under org_demo_alpha returns ZERO rows belonging to org_demo_bravo."""
    alpha_filtered = filter_by_tenant(sample_multi_tenant_records, mock_alpha_tenant)
    assert len(alpha_filtered) == 2
    for r in alpha_filtered:
        assert r["tenant_id"] == mock_alpha_tenant
        assert r["tenant_id"] != mock_bravo_tenant

    bravo_filtered = filter_by_tenant(sample_multi_tenant_records, mock_bravo_tenant)
    assert len(bravo_filtered) == 2
    for r in bravo_filtered:
        assert r["tenant_id"] == mock_bravo_tenant
        assert r["tenant_id"] != mock_alpha_tenant

def test_evidence_asset_key_isolation(mock_alpha_tenant, mock_bravo_tenant):
    """
    Test image path / evidence asset key isolation:
    Verifies that attempting to fetch an asset belonging to org_demo_bravo while authenticated as org_demo_alpha raises TenancySecurityError / HTTP 403.
    """
    asset_key_bravo = "bravo_020.jpg"
    
    # Unit level security check
    with pytest.raises(TenancySecurityError):
        verify_asset_access(asset_key_bravo, requester_tenant_id=mock_alpha_tenant, asset_owner_tenant_id=mock_bravo_tenant)

    # API endpoint HTTP 403 check
    res = client.get(f"/evidence/asset/{asset_key_bravo}", headers={"X-Tenant-ID": mock_alpha_tenant})
    assert res.status_code == 403
    assert "TenancySecurityError" in res.json()["detail"]

def test_cross_tenant_override_security(mock_alpha_tenant, mock_bravo_tenant):
    """
    Test cross-tenant override security:
    Verifies that an operator in org_demo_alpha cannot override a claim decision in org_demo_bravo.
    """
    charge_id_bravo = "CHG-2001"

    # Direct security check
    with pytest.raises(TenancySecurityError):
        verify_override_permission(charge_id=charge_id_bravo, requester_tenant_id=mock_alpha_tenant, charge_owner_tenant_id=mock_bravo_tenant)

    # Trigger analysis for bravo first so charge exists in DB
    client.post("/analyze?tenant_id_query=org_demo_bravo", headers={"X-Tenant-ID": mock_bravo_tenant})

    # Attempt cross-tenant override via API
    res = client.post("/overrides", headers={"X-Tenant-ID": mock_alpha_tenant}, json={
        "charge_id": charge_id_bravo,
        "tenant_id": mock_alpha_tenant,
        "new_verdict": "CONTRADICTED",
        "operator_id": "OP-ILLEGAL-01",
        "reason": "Attempting illegal cross-tenant override"
    })

    assert res.status_code == 403
    assert "TenancySecurityError" in res.json()["detail"]

def test_assert_tenant_isolation_raises():
    """Verify assert_tenant_isolation raises TenancySecurityError when query tenant != record tenant."""
    with pytest.raises(TenancySecurityError):
        assert_tenant_isolation("org_demo_alpha", "org_demo_bravo")
