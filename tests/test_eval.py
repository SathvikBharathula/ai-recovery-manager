import pytest
from src.core.evaluator import RecoveryEvaluator
from src.core.rules_engine import RecoveryRulesEngine

def test_evaluator_fixtures_benchmark():
    """
    Runs automated evaluation runner against ground-truth dataset (eval_fixtures.json).
    Computes Claim Precision, Recall, Total Charges Evaluated, Silent/Uncertain rates,
    and verifies zero-leak tenancy isolation.
    """
    fixtures = RecoveryEvaluator.load_eval_fixtures()
    assert len(fixtures) >= 30, f"Expected 30+ fixtures, got {len(fixtures)}"

    # Load upstream logs covering all test cases
    receiving = [
        {"record_id": "REC-01", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-EVAL-01", "box_condition": "INTACT", "seal_verified": True},
        {"record_id": "REC-04", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-EVAL-04", "box_condition": "INTACT", "seal_verified": True},
        {"record_id": "REC-10", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-EVAL-10", "box_condition": "MOISTURE_EXPOSURE"},
        {"record_id": "REC-11", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-EVAL-11", "weight_sensor_lbs": 4.5},
        {"record_id": "REC-18", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-EVAL-18", "seal_verified": True},
        {"record_id": "REC-19", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-EVAL-19", "unit_undamaged": "FAIL"},
        {"record_id": "REC-22", "tenant_id": "org_demo_bravo", "unit_id": "UNIT-BRAVO-22", "expiry_date": "2026-08-01"},
        {"record_id": "REC-26", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-EVAL-26", "unit_undamaged": "FAIL"}
    ]
    
    # Passing prep logs including SHIP-BATCH-400 batch
    prep = [
        {"record_id": "PREP-01", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-EVAL-01", "polybag_present": "PASS", "packaging_check": "PASS"},
        {"record_id": "PREP-02", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-EVAL-02", "barcode_scanned": "PASS", "fnsku_scanned": "X001"},
        {"record_id": "PREP-06", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-EVAL-06", "polybag_present": "FAIL", "packaging_check": "FAIL"},
        {"record_id": "PREP-07", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-EVAL-07", "barcode_check": "FAIL"},
        {"record_id": "PREP-10", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-EVAL-10", "packaging_check": "PASS"},
        {"record_id": "PREP-20", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-EVAL-20", "suffocation_warning": True, "packaging_check": "PASS"},
        {"record_id": "PREP-21", "tenant_id": "org_demo_bravo", "unit_id": "UNIT-BRAVO-21", "bubble_wrap_check": "PASS", "packaging_check": "PASS"},
        {"record_id": "PREP-24", "tenant_id": "org_demo_bravo", "unit_id": "UNIT-BRAVO-24", "polybag_present": "PASS"},
        {"record_id": "PREP-25", "tenant_id": "org_demo_bravo", "shipment_id": "SHIP-BRAVO-05", "polybag_present": "PASS"},
        {"record_id": "PREP-27", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-EVAL-27", "barcode_scanned": "PASS"},
        {"record_id": "PREP-29", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-EVAL-29", "result": "UNCERTAIN"},
        {"record_id": "PREP-32", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-EVAL-32", "bubble_wrap_check": "PASS"}
    ]
    
    # Populate passing prep units for shipment SHIP-BATCH-400
    for i in range(400):
        prep.append({"record_id": f"PREP-SHIP-400-{i}", "tenant_id": "org_demo_alpha", "shipment_id": "SHIP-BATCH-400", "polybag_present": "PASS"})

    pack = [
        {"record_id": "PACK-03", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-EVAL-03", "weight_sensor_lbs": 2.12},
        {"record_id": "PACK-11", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-EVAL-11", "weight_sensor_lbs": 1.2},
        {"record_id": "PACK-16", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-EVAL-16", "all_items_present": "PASS"},
        {"record_id": "PACK-30", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-EVAL-30", "item_count_matches": "PASS"}
    ]
    returns = [
        {"record_id": "RET-05", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-EVAL-05", "return_disposition": "CARRIER_DAMAGE"},
        {"record_id": "RET-17", "tenant_id": "org_demo_alpha", "unit_id": "UNIT-EVAL-17", "condition_grade": "SELLABLE"}
    ]
    reimbursements = [
        {"reimbursement_id": "REIMB-EVAL-13", "charge_id": "CHG-EVAL-013", "tenant_id": "org_demo_alpha", "amount_total": 60.0},
        {"reimbursement_id": "REIMB-EVAL-31", "charge_id": "CHG-EVAL-031", "tenant_id": "org_demo_alpha", "amount_total": 75.0}
    ]

    engine = RecoveryRulesEngine(receiving, prep, pack, returns, reimbursements=reimbursements)

    results_alpha = engine.analyze_batch(fixtures, "org_demo_alpha")
    metrics_alpha = RecoveryEvaluator.evaluate(results_alpha, fixtures, "org_demo_alpha")

    assert metrics_alpha["claim_precision"] == 1.0, f"Expected 1.0 Precision, got {metrics_alpha['claim_precision']}"
    assert metrics_alpha["claim_recall"] == 1.0, f"Expected 1.0 Recall, got {metrics_alpha['claim_recall']}"
    assert metrics_alpha["zero_leak_confirmed"] is True
    assert metrics_alpha["total_charges_evaluated"] > 0

    # Test Markdown report generator
    report_md = RecoveryEvaluator.generate_markdown_report(metrics_alpha)
    assert "Evaluation & Precision Results" in report_md
    assert "100.0%" in report_md
