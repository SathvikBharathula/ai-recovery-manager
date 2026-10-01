import pytest
from src.core.tenant_security import filter_by_tenant, validate_tenant_id, assert_tenant_isolation, TenancyException
from src.core.rules_engine import RecoveryRulesEngine

def test_tenant_filtering_isolation():
    data = [
        {"id": 1, "tenant_id": "org_demo_alpha", "val": "alpha_secret"},
        {"id": 2, "tenant_id": "org_demo_bravo", "val": "bravo_secret"}
    ]

    alpha_res = filter_by_tenant(data, "org_demo_alpha")
    assert len(alpha_res) == 1
    assert alpha_res[0]["val"] == "alpha_secret"

    bravo_res = filter_by_tenant(data, "org_demo_bravo")
    assert len(bravo_res) == 1
    assert bravo_res[0]["val"] == "bravo_secret"

def test_rules_engine_cross_tenant_prevention():
    # Alpha has prep evidence for UNIT-0001
    prep_alpha = [{
        "record_id": "PREP-ALPHA-01",
        "tenant_id": "org_demo_alpha",
        "unit_id": "UNIT-0001",
        "packaging_check": "PASS"
    }]
    engine = RecoveryRulesEngine([], prep_alpha, [], [])

    # Bravo charges for the same UNIT-0001
    bravo_charge = {
        "charge_id": "CHG-BRAVO-999",
        "tenant_id": "org_demo_bravo",
        "unit_id": "UNIT-0001",
        "reason": "packaging defect",
        "amount": 50.00
    }

    # Bravo analysis MUST NOT see Alpha's evidence -> must yield SILENT
    result = engine.analyze_charge(bravo_charge)
    assert result["assessment"] == "SILENT"
    assert result["claim_amount"] == 0.0
    assert len(result["supporting_evidence"]) == 0

def test_tenant_security_exception():
    with pytest.raises(TenancyException):
        assert_tenant_isolation("org_demo_alpha", "org_demo_bravo")
