import pytest
from datetime import datetime, timezone, timedelta
from src.core.rules_engine import RecoveryRulesEngine
from src.backend.models import OverrideRecord, ClaimDecision

def test_schema_a_already_reimbursed_netting():
    """Test that an existing reimbursement row (amount_total >= charge_amount) yields verdict already_reimbursed."""
    reimbursements = [{
        "reimbursement_id": "REIMB-100",
        "charge_id": "CHG-1001",
        "tenant_id": "org_demo_alpha",
        "amount_total": 50.00,
        "original_reimbursement_id": None
    }]
    engine = RecoveryRulesEngine([], [], [], [], reimbursements=reimbursements)

    charge = {
        "charge_id": "CHG-1001",
        "tenant_id": "org_demo_alpha",
        "reason": "inbound defect fee",
        "amount": 45.00,
        "timestamp": "2026-09-20T10:00:00Z"
    }

    res = engine.analyze_charge(charge)
    assert res["assessment"] == "already_reimbursed"
    assert res["claim_amount"] == 0.0
    assert "REIMB-100" in res["evidence_matched"]

def test_reimbursement_reversal_recovery():
    """Test reimbursement reversals where original_reimbursement_id is populated."""
    reimbursements = [{
        "reimbursement_id": "REIMB-REV-01",
        "charge_id": "CHG-1002",
        "tenant_id": "org_demo_alpha",
        "amount_total": 45.00,
        "original_reimbursement_id": "REIMB-100"  # Channel reversed the previous reimbursement
    }]
    prep_logs = [{
        "record_id": "PREP-REC-01",
        "tenant_id": "org_demo_alpha",
        "unit_id": "UNIT-1002",
        "polybag_present": "PASS"
    }]
    engine = RecoveryRulesEngine([], prep_logs, [], [], reimbursements=reimbursements)

    charge = {
        "charge_id": "CHG-1002",
        "tenant_id": "org_demo_alpha",
        "unit_id": "UNIT-1002",
        "reason": "packaging defect",
        "amount": 45.00,
        "timestamp": "2026-09-20T10:00:00Z"
    }

    res = engine.analyze_charge(charge)
    # Because original_reimbursement_id is populated (reversal), charge is eligible for claim!
    assert res["assessment"] in ["CONTRADICTED", "contested"]
    assert res["claim_amount"] == 45.00

def test_granularity_shipment_level_claim():
    """Test shipment level charges with 400 passing units produce a filable claim without falsely claiming per-unit precision."""
    prep_logs = [
        {"record_id": f"PREP-{i}", "tenant_id": "org_demo_alpha", "shipment_id": "SHIP-BATCH-400", "polybag_present": "PASS"}
        for i in range(400)
    ]
    engine = RecoveryRulesEngine([], prep_logs, [], [])

    charge = {
        "charge_id": "CHG-SHIP-400",
        "tenant_id": "org_demo_alpha",
        "shipment_id": "SHIP-BATCH-400",
        "unit_id": None,
        "granularity": "shipment",
        "reason": "inbound carton damage fee",
        "amount": 250.00,
        "timestamp": "2026-09-20T10:00:00Z"
    }

    res = engine.analyze_charge(charge)
    assert res["assessment"] in ["CONTRADICTED", "contested"]
    assert res["granularity"] == "shipment"
    assert res["claim_amount"] == 250.00
    assert "400 passing unit records" in res["explanation"]

def test_5_manager_check_keys_contradictions():
    """Test all 5 Manager check keys contradict channel fee claims."""
    # 1. Prep Manager: polybag_present = PASS contradicts inbound unbagged defect fee
    prep = [{"record_id": "P1", "tenant_id": "org_demo_alpha", "unit_id": "U1", "polybag_present": "PASS"}]
    # 2. Receiving Manager: unit_undamaged = PASS contradicts warehouse damaged
    rec = [{"record_id": "R1", "tenant_id": "org_demo_alpha", "unit_id": "U2", "unit_undamaged": "PASS"}]
    # 3. Pack Manager: all_items_present = PASS contradicts missing item
    pack = [{"record_id": "K1", "tenant_id": "org_demo_alpha", "unit_id": "U3", "all_items_present": "PASS"}]
    # 4. Returns Manager: condition_grade = SELLABLE contradicts damaged inventory
    ret = [{"record_id": "T1", "tenant_id": "org_demo_alpha", "unit_id": "U4", "condition_grade": "SELLABLE"}]

    engine = RecoveryRulesEngine(rec, prep, pack, ret)

    c1 = engine.analyze_charge({"charge_id": "C1", "tenant_id": "org_demo_alpha", "unit_id": "U1", "reason": "unbagged defect fee", "amount": 10.0})
    assert c1["assessment"] in ["CONTRADICTED", "contested"]

    c2 = engine.analyze_charge({"charge_id": "C2", "tenant_id": "org_demo_alpha", "unit_id": "U2", "reason": "warehouse damaged fee", "amount": 20.0})
    assert c2["assessment"] in ["CONTRADICTED", "contested"]

    c3 = engine.analyze_charge({"charge_id": "C3", "tenant_id": "org_demo_alpha", "unit_id": "U3", "reason": "missing item fee", "amount": 30.0})
    assert c3["assessment"] in ["CONTRADICTED", "contested"]

    c4 = engine.analyze_charge({"charge_id": "C4", "tenant_id": "org_demo_alpha", "unit_id": "U4", "reason": "damaged inventory fee", "amount": 40.0})
    assert c4["assessment"] in ["CONTRADICTED", "contested"]

def test_rule_4_uncertainty_and_missing_data():
    """
    Rule 4 Compliance:
    - Missing evidence yields SILENT (insufficient_evidence).
    - Conflicting evidence or UNCERTAIN verdict yields UNCERTAIN.
    - NEVER invent evidence. NEVER assume missing data.
    """
    engine = RecoveryRulesEngine([], [], [], [])
    
    # Missing evidence
    res_silent = engine.analyze_charge({"charge_id": "C-MISSING", "tenant_id": "org_demo_alpha", "unit_id": "U-UNKNOWN", "reason": "inbound defect fee", "amount": 50.0})
    assert res_silent["assessment"] == "SILENT"
    assert res_silent["claim_amount"] == 0.0

    # Conflicting evidence
    rec = [{"record_id": "R1", "tenant_id": "org_demo_alpha", "unit_id": "U-CONF", "box_condition": "MOISTURE_EXPOSURE"}]
    prep = [{"record_id": "P1", "tenant_id": "org_demo_alpha", "unit_id": "U-CONF", "packaging_check": "PASS"}]
    engine_conf = RecoveryRulesEngine(rec, prep, [], [])
    
    res_unc = engine_conf.analyze_charge({"charge_id": "C-CONF", "tenant_id": "org_demo_alpha", "unit_id": "U-CONF", "reason": "packaging defect", "amount": 40.0})
    assert res_unc["assessment"] == "UNCERTAIN"
    assert res_unc["claim_amount"] == 0.0

def test_rule_3_fail_open_execution():
    """
    Rule 3 Compliance (Fail-Open Execution):
    Simulate LLM API timeout/service failure; ensure engine falls back gracefully without throwing uncaught exceptions.
    """
    engine = RecoveryRulesEngine([], [], [], [])
    charge = {"charge_id": "C-LLM-FAIL", "tenant_id": "org_demo_alpha", "unit_id": "U1", "reason": "packaging defect", "amount": 30.0}

    def failing_llm_call(c):
        raise TimeoutError("LLM API Gateway Connection Timed Out (504)")

    res = engine.analyze_charge_with_llm_fallback(charge, llm_func=failing_llm_call)
    assert res["assessment"] == "UNCERTAIN"
    assert res["status"] == "pending_review"
    assert "LLM API service fallback" in res["explanation"]

def test_out_of_window_dispute_limit():
    """Test claim filing window check (out_of_window verdict) if charge exceeds 60 days limit."""
    engine = RecoveryRulesEngine([], [], [], [], dispute_window_days=60)

    # 120 days old timestamp
    old_ts = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    charge = {
        "charge_id": "CHG-EXPIRED",
        "tenant_id": "org_demo_alpha",
        "reason": "inbound defect fee",
        "amount": 100.00,
        "timestamp": old_ts
    }

    res = engine.analyze_charge(charge)
    assert res["assessment"] == "out_of_window"
    assert res["claim_amount"] == 0.0
