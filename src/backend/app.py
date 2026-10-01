import os
import json
import pandas as pd
import io
import logging
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy.orm import Session

from database import engine, Base, get_db
from models import Charge, EvidenceRecord, ClaimDecision, OverrideRecord, AuditLog
from schemas import (
    ChargeItemSchema, ChargeAnalysisResultSchema, AnalysisResponseSchema,
    OverrideRequestSchema, EvalResponseSchema
)
from src.core.tenant_security import validate_tenant_id, filter_by_tenant, assert_tenant_isolation
from src.core.rules_engine import RecoveryRulesEngine
from src.core.llm_explainer import ClaimExplanationGenerator
from src.core.evaluator import RecoveryEvaluator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("recovery_backend")

# Create Database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Recovery Manager API",
    description="Enterprise-grade recovery decision engine and evidence matching platform.",
    version="2.0.0"
)

# Enable CORS for full-stack integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))

def load_upstream_logs() -> tuple:
    """Helper to load upstream evidence logs from JSON files."""
    rec_path = os.path.join(DATA_DIR, "upstream", "01_receiving_records.json")
    prep_path = os.path.join(DATA_DIR, "upstream", "02_prep_records.json")
    pack_path = os.path.join(DATA_DIR, "upstream", "03_pack_records.json")
    ret_path = os.path.join(DATA_DIR, "upstream", "04_returns_records.json")

    receiving = json.load(open(rec_path)) if os.path.exists(rec_path) else []
    prep = json.load(open(prep_path)) if os.path.exists(prep_path) else []
    pack = json.load(open(pack_path)) if os.path.exists(pack_path) else []
    returns = json.load(open(ret_path)) if os.path.exists(ret_path) else []
    return receiving, prep, pack, returns

@app.get("/health")
def health_check():
    return {"status": "HEALTHY", "system": "AI Recovery Manager", "version": "2.0.0"}

@app.get("/tenants")
def list_tenants():
    return {
        "tenants": [
            {"id": "org_demo_alpha", "name": "Alpha Commerce Corp", "description": "Primary FBA Enterprise Seller"},
            {"id": "org_demo_bravo", "name": "Bravo Logistics LLC", "description": "3PL Inbound Operations"}
        ]
    }

@app.post("/upload-report")
async def upload_report(
    file: Optional[UploadFile] = File(None),
    x_tenant_id: Optional[str] = Header("org_demo_alpha"),
    tenant_id_query: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Ingests fee or reimbursement report (CSV or JSON).
    Parses individual charges and stores in database scoped by tenant_id.
    """
    tenant = validate_tenant_id(tenant_id_query or x_tenant_id)
    charges_to_insert = []

    if file:
        content = await file.read()
        filename = file.filename.lower()
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
            for _, row in df.iterrows():
                charges_to_insert.append({
                    "charge_id": str(row.get("charge_id", f"CHG-{len(charges_to_insert)+1000}")),
                    "tenant_id": tenant,
                    "shipment_id": str(row.get("shipment_id", "")) if pd.notna(row.get("shipment_id")) else None,
                    "order_id": str(row.get("order_id", "")) if pd.notna(row.get("order_id")) else None,
                    "unit_id": str(row.get("unit_id", "")) if pd.notna(row.get("unit_id")) else None,
                    "sku": str(row.get("sku", "")) if pd.notna(row.get("sku")) else None,
                    "asin": str(row.get("asin", "")) if pd.notna(row.get("asin")) else None,
                    "reason": str(row.get("reason", "unknown fee")),
                    "amount": float(row.get("amount", 0.0)),
                    "currency": str(row.get("currency", "USD")),
                    "timestamp": str(row.get("timestamp", "")) if pd.notna(row.get("timestamp")) else None
                })
        elif filename.endswith(".json"):
            raw_data = json.loads(content.decode("utf-8"))
            if isinstance(raw_data, list):
                for item in raw_data:
                    item["tenant_id"] = tenant
                    charges_to_insert.append(item)
    else:
        # Load sample report for tenant
        sample_path = os.path.join(DATA_DIR, "fee_reports", f"amazon_inbound_fee_report_{tenant.replace('org_demo_', '')}.csv")
        if not os.path.exists(sample_path):
            sample_path = os.path.join(DATA_DIR, "fee_reports", "sample_fee_report.json")
        
        if sample_path.endswith(".csv"):
            df = pd.read_csv(sample_path)
            for _, row in df.iterrows():
                charges_to_insert.append({
                    "charge_id": str(row.get("charge_id")),
                    "tenant_id": tenant,
                    "shipment_id": str(row.get("shipment_id", "")),
                    "order_id": str(row.get("order_id", "")),
                    "unit_id": str(row.get("unit_id", "")),
                    "sku": str(row.get("sku", "")),
                    "asin": str(row.get("asin", "")),
                    "reason": str(row.get("reason", "")),
                    "amount": float(row.get("amount", 0.0)),
                    "currency": str(row.get("currency", "USD")),
                    "timestamp": str(row.get("timestamp", ""))
                })
        elif sample_path.endswith(".json"):
            charges_to_insert = json.load(open(sample_path))
            for item in charges_to_insert:
                item["tenant_id"] = tenant

    # Clean existing charges for this tenant in DB
    db.query(Charge).filter(Charge.tenant_id == tenant).delete()
    db.commit()

    # Save new charges
    for c in charges_to_insert:
        db_obj = Charge(
            charge_id=c.get("charge_id"),
            tenant_id=tenant,
            shipment_id=c.get("shipment_id"),
            order_id=c.get("order_id"),
            unit_id=c.get("unit_id"),
            sku=c.get("sku"),
            asin=c.get("asin"),
            reason=c.get("reason"),
            amount=float(c.get("amount", 0.0)),
            currency=c.get("currency", "USD")
        )
        db.add(db_obj)
    db.commit()

    return {
        "message": f"Successfully ingested {len(charges_to_insert)} charges for tenant '{tenant}'",
        "tenant_id": tenant,
        "total_charges": len(charges_to_insert)
    }

@app.post("/analyze", response_model=AnalysisResponseSchema)
def analyze_charges(
    x_tenant_id: Optional[str] = Header("org_demo_alpha"),
    tenant_id_query: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Executes the Hybrid Reasoning Engine against ingested fee charges for the tenant.
    Performs multi-manager evidence retrieval, charge matching, and verdict classification.
    """
    tenant = validate_tenant_id(tenant_id_query or x_tenant_id)
    charges_db = db.query(Charge).filter(Charge.tenant_id == tenant).all()

    if not charges_db:
        # Auto-trigger upload if DB empty
        upload_report_sync(tenant, db)
        charges_db = db.query(Charge).filter(Charge.tenant_id == tenant).all()

    charges = [
        {
            "charge_id": c.charge_id,
            "tenant_id": c.tenant_id,
            "shipment_id": c.shipment_id,
            "order_id": c.order_id,
            "unit_id": c.unit_id,
            "sku": c.sku,
            "asin": c.asin,
            "reason": c.reason,
            "amount": c.amount,
            "currency": c.currency,
            "timestamp": str(c.timestamp)
        }
        for c in charges_db
    ]

    receiving, prep, pack, returns = load_upstream_logs()
    engine = RecoveryRulesEngine(receiving, prep, pack, returns)

    results = engine.analyze_batch(charges, tenant)

    # Save analysis decisions to DB
    db.query(ClaimDecision).filter(ClaimDecision.tenant_id == tenant).delete()
    db.commit()

    total_recoverable = 0.0
    cnt_contradicted = 0
    cnt_supported = 0
    cnt_silent = 0
    cnt_uncertain = 0

    for res in results:
        ass = res.get("assessment")
        if ass == "CONTRADICTED":
            cnt_contradicted += 1
            total_recoverable += res.get("claim_amount", 0.0)
        elif ass == "SUPPORTED":
            cnt_supported += 1
        elif ass == "SILENT":
            cnt_silent += 1
        elif ass == "UNCERTAIN":
            cnt_uncertain += 1

        db_dec = ClaimDecision(
            charge_id=res.get("charge_id"),
            tenant_id=tenant,
            shipment_id=res.get("shipment_id"),
            reason=res.get("reason"),
            amount=res.get("amount"),
            assessment=ass,
            claim_amount=res.get("claim_amount", 0.0),
            confidence_score=res.get("confidence_score", 0.0),
            explanation=res.get("explanation"),
            evidence_matched_json=json.dumps(res.get("evidence_matched", [])),
            supporting_evidence_json=json.dumps(res.get("supporting_evidence", [])),
            is_overridden=False
        )
        db.add(db_dec)
    db.commit()

    return {
        "tenant_id": tenant,
        "total_charges": len(results),
        "contradicted_count": cnt_contradicted,
        "supported_count": cnt_supported,
        "silent_count": cnt_silent,
        "uncertain_count": cnt_uncertain,
        "total_recoverable_amount": round(total_recoverable, 2),
        "results": results
    }

def upload_report_sync(tenant: str, db: Session):
    """Internal helper to load sample data if DB is uninitialized."""
    sample_path = os.path.join(DATA_DIR, "fee_reports", f"amazon_inbound_fee_report_{tenant.replace('org_demo_', '')}.csv")
    if not os.path.exists(sample_path):
        sample_path = os.path.join(DATA_DIR, "fee_reports", "sample_fee_report.json")
    
    charges = []
    if sample_path.endswith(".csv"):
        df = pd.read_csv(sample_path)
        for _, row in df.iterrows():
            charges.append(Charge(
                charge_id=str(row["charge_id"]),
                tenant_id=tenant,
                shipment_id=str(row.get("shipment_id", "")),
                order_id=str(row.get("order_id", "")),
                unit_id=str(row.get("unit_id", "")),
                sku=str(row.get("sku", "")),
                asin=str(row.get("asin", "")),
                reason=str(row.get("reason", "")),
                amount=float(row.get("amount", 0.0))
            ))
    elif sample_path.endswith(".json"):
        raw = json.load(open(sample_path))
        for item in raw:
            charges.append(Charge(
                charge_id=item["charge_id"],
                tenant_id=tenant,
                shipment_id=item.get("shipment_id"),
                order_id=item.get("order_id"),
                unit_id=item.get("unit_id"),
                sku=item.get("sku"),
                asin=item.get("asin"),
                reason=item.get("reason"),
                amount=float(item.get("amount", 0.0))
            ))
    db.add_all(charges)
    db.commit()

@app.get("/results")
def get_results(
    assessment: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    x_tenant_id: Optional[str] = Header("org_demo_alpha"),
    tenant_id_query: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Fetches analyzed recovery decision results for the active tenant.
    Supports filtering by assessment status (CONTRADICTED, SUPPORTED, SILENT, UNCERTAIN)
    and text search on charge_id, shipment_id, order_id, or reason.
    """
    tenant = validate_tenant_id(tenant_id_query or x_tenant_id)
    query = db.query(ClaimDecision).filter(ClaimDecision.tenant_id == tenant)

    if assessment:
        query = query.filter(ClaimDecision.assessment == assessment.upper())

    records = query.all()
    
    results = []
    for r in records:
        if search:
            s_term = search.lower()
            match_str = f"{r.charge_id} {r.shipment_id} {r.reason} {r.explanation}".lower()
            if s_term not in match_str:
                continue

        results.append({
            "charge_id": r.charge_id,
            "shipment_id": r.shipment_id,
            "tenant_id": r.tenant_id,
            "reason": r.reason,
            "amount": r.amount,
            "assessment": r.assessment,
            "claim_amount": r.claim_amount,
            "confidence_score": r.confidence_score,
            "explanation": r.explanation,
            "evidence_matched": json.loads(r.evidence_matched_json or "[]"),
            "supporting_evidence": json.loads(r.supporting_evidence_json or "[]"),
            "is_overridden": r.is_overridden
        })

    return {
        "tenant_id": tenant,
        "total": len(results),
        "results": results
    }

@app.get("/evidence/asset/{asset_key:path}")
def get_evidence_asset(
    asset_key: str,
    x_tenant_id: Optional[str] = Header("org_demo_alpha"),
    tenant_id_query: Optional[str] = Query(None)
):
    """
    Engineering Rule 1: Evidence Asset Key Isolation.
    Verifies caller's tenant matches the asset owner's tenant.
    """
    tenant = validate_tenant_id(tenant_id_query or x_tenant_id)
    if "bravo" in asset_key.lower() and tenant == "org_demo_alpha":
        raise HTTPException(
            status_code=403,
            detail=f"TenancySecurityError (403): Tenant '{tenant}' denied access to asset '{asset_key}' owned by tenant 'org_demo_bravo'."
        )
    if "alpha" in asset_key.lower() and tenant == "org_demo_bravo":
        raise HTTPException(
            status_code=403,
            detail=f"TenancySecurityError (403): Tenant '{tenant}' denied access to asset '{asset_key}' owned by tenant 'org_demo_alpha'."
        )
    return {"status": "SUCCESS", "asset_key": asset_key, "tenant_id": tenant}

@app.post("/overrides")
def submit_override(
    override_req: OverrideRequestSchema,
    x_tenant_id: Optional[str] = Header("org_demo_alpha"),
    db: Session = Depends(get_db)
):
    """
    Engineering Rule: Overrides are data.
    Captures operator overrides without mutating original evidence or deleting rows.
    Appends to audit trail.
    """
    tenant = validate_tenant_id(override_req.tenant_id or x_tenant_id)
    
    # Security check: cross-tenant override prevention
    any_decision = db.query(ClaimDecision).filter(ClaimDecision.charge_id == override_req.charge_id).first()
    if any_decision and any_decision.tenant_id != tenant:
        raise HTTPException(
            status_code=403,
            detail=f"TenancySecurityError (403): Tenant '{tenant}' cannot override decision for charge '{override_req.charge_id}' owned by tenant '{any_decision.tenant_id}'."
        )

    decision = db.query(ClaimDecision).filter(
        ClaimDecision.charge_id == override_req.charge_id,
        ClaimDecision.tenant_id == tenant
    ).first()

    if not decision:
        raise HTTPException(status_code=404, detail=f"Charge '{override_req.charge_id}' not found for tenant '{tenant}'")

    orig_verdict = decision.assessment
    new_verdict = override_req.new_verdict.upper()

    # Create audit override record
    override_db = OverrideRecord(
        charge_id=override_req.charge_id,
        tenant_id=tenant,
        original_verdict=orig_verdict,
        new_verdict=new_verdict,
        operator_id=override_req.operator_id,
        reason=override_req.reason
    )
    db.add(override_db)

    # Update decision table
    decision.assessment = new_verdict
    decision.is_overridden = True
    if new_verdict == "CONTRADICTED":
        decision.claim_amount = decision.amount
    else:
        decision.claim_amount = 0.0
    
    db.commit()

    return {
        "status": "SUCCESS",
        "message": f"Recorded operator override for {override_req.charge_id}: '{orig_verdict}' -> '{new_verdict}'",
        "charge_id": override_req.charge_id,
        "original_verdict": orig_verdict,
        "new_verdict": new_verdict,
        "operator_id": override_req.operator_id
    }

@app.get("/export")
def export_claims(
    format: str = Query("json"),
    x_tenant_id: Optional[str] = Header("org_demo_alpha"),
    tenant_id_query: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Exports recommended claims (CONTRADICTED assessment) as JSON or CSV file.
    Includes formal claim dispute text generated by explanation layer.
    """
    tenant = validate_tenant_id(tenant_id_query or x_tenant_id)
    decisions = db.query(ClaimDecision).filter(
        ClaimDecision.tenant_id == tenant,
        ClaimDecision.assessment == "CONTRADICTED"
    ).all()

    export_items = []
    for d in decisions:
        res_dict = {
            "charge_id": d.charge_id,
            "shipment_id": d.shipment_id,
            "tenant_id": d.tenant_id,
            "reason": d.reason,
            "amount": d.amount,
            "assessment": d.assessment,
            "claim_amount": d.claim_amount,
            "explanation": d.explanation,
            "supporting_evidence": json.loads(d.supporting_evidence_json or "[]")
        }
        res_dict["formal_dispute_text"] = ClaimExplanationGenerator.generate_formal_claim_text(res_dict)
        export_items.append(res_dict)

    if format.lower() == "csv":
        if not export_items:
            return Response(content="charge_id,shipment_id,reason,amount,claim_amount\n", media_type="text/csv")
        df = pd.DataFrame(export_items)
        csv_str = df.to_csv(index=False)
        return Response(content=csv_str, media_type="text/csv", headers={
            "Content-Disposition": f"attachment; filename=recovery_claims_{tenant}.csv"
        })

    return {
        "tenant_id": tenant,
        "total_claims": len(export_items),
        "claims": export_items
    }

@app.get("/eval", response_model=EvalResponseSchema)
def run_evaluation(
    x_tenant_id: Optional[str] = Header("org_demo_alpha"),
    tenant_id_query: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Runs automated evaluation suite comparing system predictions against ground truth labels.
    Outputs Claim Precision, Recall, False Positives, False Negatives, and Failure Modes.
    """
    tenant = validate_tenant_id(tenant_id_query or x_tenant_id)
    
    # Run analysis for current tenant
    analysis_res = analyze_charges(x_tenant_id=tenant, db=db)
    results = analysis_res["results"]

    # Ground truth test harness labels for evaluation
    ground_truth = [
        {"charge_id": "CHG-1001", "expected_assessment": "CONTRADICTED", "is_truly_recoverable": True},
        {"charge_id": "CHG-1002", "expected_assessment": "CONTRADICTED", "is_truly_recoverable": True},
        {"charge_id": "CHG-1003", "expected_assessment": "CONTRADICTED", "is_truly_recoverable": True},
        {"charge_id": "CHG-1004", "expected_assessment": "CONTRADICTED", "is_truly_recoverable": True},
        {"charge_id": "CHG-1005", "expected_assessment": "CONTRADICTED", "is_truly_recoverable": True},
        {"charge_id": "CHG-1006", "expected_assessment": "SUPPORTED", "is_truly_recoverable": False},
        {"charge_id": "CHG-1007", "expected_assessment": "SUPPORTED", "is_truly_recoverable": False},
        {"charge_id": "CHG-1008", "expected_assessment": "SILENT", "is_truly_recoverable": False},
        {"charge_id": "CHG-1009", "expected_assessment": "SILENT", "is_truly_recoverable": False},
        {"charge_id": "CHG-1010", "expected_assessment": "UNCERTAIN", "is_truly_recoverable": False},
        {"charge_id": "CHG-1011", "expected_assessment": "UNCERTAIN", "is_truly_recoverable": False},
        {"charge_id": "CHG-1012", "expected_assessment": "CONTRADICTED", "is_truly_recoverable": True},
        {"charge_id": "CHG-2001", "expected_assessment": "CONTRADICTED", "is_truly_recoverable": True},
        {"charge_id": "CHG-2002", "expected_assessment": "SUPPORTED", "is_truly_recoverable": False},
        {"charge_id": "CHG-2003", "expected_assessment": "SILENT", "is_truly_recoverable": False}
    ]

    metrics = RecoveryEvaluator.evaluate(results, ground_truth)
    metrics["tenant_id"] = tenant
    return metrics


# Serve static web frontend UI
INDEX_HTML_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html"))

@app.get("/", response_class=HTMLResponse)
def read_root():
    if os.path.exists(INDEX_HTML_PATH):
        with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>AI Recovery Manager API Server</h1><p>Visit /docs for API Swagger documentation.</p>"
