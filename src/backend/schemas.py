from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict

class ChargeItemSchema(BaseModel):
    charge_id: str
    tenant_id: Optional[str] = "org_demo_alpha"
    shipment_id: Optional[str] = None
    order_id: Optional[str] = None
    unit_id: Optional[str] = None
    sku: Optional[str] = None
    asin: Optional[str] = None
    reason: str
    amount: float
    currency: Optional[str] = "USD"
    timestamp: Optional[str] = None

class ChargeAnalysisResultSchema(BaseModel):
    charge_id: str
    shipment_id: Optional[str] = None
    tenant_id: str
    reason: str
    amount: float
    evidence_matched: List[str] = []
    assessment: str  # CONTRADICTED | SUPPORTED | SILENT | UNCERTAIN
    claim_amount: float
    confidence_score: float
    explanation: str
    supporting_evidence: List[Dict[str, Any]] = []
    is_overridden: Optional[bool] = False

class AnalysisResponseSchema(BaseModel):
    tenant_id: str
    total_charges: int
    contradicted_count: int
    supported_count: int
    silent_count: int
    uncertain_count: int
    total_recoverable_amount: float
    results: List[ChargeAnalysisResultSchema]

class OverrideRequestSchema(BaseModel):
    charge_id: str
    tenant_id: Optional[str] = "org_demo_alpha"
    new_verdict: str  # CONTRADICTED | SUPPORTED | SILENT | UNCERTAIN
    operator_id: str
    reason: str

class EvalResponseSchema(BaseModel):
    tenant_id: str
    total_charges_evaluated: int
    claims_recommended: int
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    silent_count: int
    uncertain_count: int
    claim_precision: float
    claim_recall: float
    silent_rate: float
    uncertain_rate: float
    failure_modes: List[Dict[str, Any]]
