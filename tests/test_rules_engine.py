import pytest
from src.core.rules_engine import RecoveryRulesEngine

def test_contradicted_verdict():
    receiving = []
    prep = [{
        "record_id": "PREP-01",
        "tenant_id": "org_demo_alpha",
        "unit_id": "UNIT-0001",
        "shipment_id": "SHIP-9001",
        "packaging_check": "PASS",
        "timestamp": "2026-09-15T08:30:00Z"
    }]
    pack = []
    returns = []

    engine = RecoveryRulesEngine(receiving, prep, pack, returns)
    charge = {
        "charge_id": "CHG-1001",
        "tenant_id": "org_demo_alpha",
        "shipment_id": "SHIP-9001",
        "unit_id": "UNIT-0001",
        "reason": "packaging defect",
        "amount": 45.00
    }

    result = engine.analyze_charge(charge)
    assert result["assessment"] == "CONTRADICTED"
    assert result["claim_amount"] == 45.00
    assert result["confidence_score"] >= 0.95
    assert len(result["supporting_evidence"]) == 1

def test_supported_verdict():
    receiving = []
    prep = [{
        "record_id": "PREP-02",
        "tenant_id": "org_demo_alpha",
        "unit_id": "UNIT-0006",
        "packaging_check": "FAIL",
        "notes": "Missing warning label"
    }]
    pack = []
    returns = []

    engine = RecoveryRulesEngine(receiving, prep, pack, returns)
    charge = {
        "charge_id": "CHG-1006",
        "tenant_id": "org_demo_alpha",
        "unit_id": "UNIT-0006",
        "reason": "packaging defect",
        "amount": 25.00
    }

    result = engine.analyze_charge(charge)
    assert result["assessment"] == "SUPPORTED"
    assert result["claim_amount"] == 0.0

def test_silent_verdict():
    engine = RecoveryRulesEngine([], [], [], [])
    charge = {
        "charge_id": "CHG-1008",
        "tenant_id": "org_demo_alpha",
        "unit_id": "UNIT-MISSING",
        "reason": "inbound defect fee",
        "amount": 50.00
    }

    result = engine.analyze_charge(charge)
    assert result["assessment"] == "SILENT"
    assert result["claim_amount"] == 0.0
    assert result["confidence_score"] == 0.0

def test_uncertain_verdict():
    receiving = [{
        "record_id": "REC-10",
        "tenant_id": "org_demo_alpha",
        "unit_id": "UNIT-0010",
        "box_condition": "MOISTURE_EXPOSURE"
    }]
    prep = [{
        "record_id": "PREP-10",
        "tenant_id": "org_demo_alpha",
        "unit_id": "UNIT-0010",
        "packaging_check": "PASS"
    }]
    pack = []
    returns = []

    engine = RecoveryRulesEngine(receiving, prep, pack, returns)
    charge = {
        "charge_id": "CHG-1010",
        "tenant_id": "org_demo_alpha",
        "unit_id": "UNIT-0010",
        "reason": "packaging defect",
        "amount": 40.00
    }

    result = engine.analyze_charge(charge)
    assert result["assessment"] == "UNCERTAIN"
    assert result["claim_amount"] == 0.0
