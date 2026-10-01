import pytest
from src.core.evaluator import RecoveryEvaluator

def test_evaluator_metrics():
    analysis = [
        {"charge_id": "C1", "tenant_id": "org_demo_alpha", "assessment": "CONTRADICTED"},
        {"charge_id": "C2", "tenant_id": "org_demo_alpha", "assessment": "SUPPORTED"},
        {"charge_id": "C3", "tenant_id": "org_demo_alpha", "assessment": "SILENT"}
    ]
    gt = [
        {"charge_id": "C1", "tenant_id": "org_demo_alpha", "expected_assessment": "CONTRADICTED", "is_truly_recoverable": True},
        {"charge_id": "C2", "tenant_id": "org_demo_alpha", "expected_assessment": "SUPPORTED", "is_truly_recoverable": False},
        {"charge_id": "C3", "tenant_id": "org_demo_alpha", "expected_assessment": "SILENT", "is_truly_recoverable": False}
    ]

    metrics = RecoveryEvaluator.evaluate(analysis, gt, tenant_id="org_demo_alpha")
    assert metrics["claim_precision"] == 1.0
    assert metrics["true_positives"] == 1
    assert metrics["false_positives"] == 0
    assert metrics["silent_count"] == 1
