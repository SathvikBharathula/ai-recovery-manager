from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey
from datetime import datetime, timezone
from database import Base

class Charge(Base):
    __tablename__ = "charges"

    id = Column(Integer, primary_key=True, index=True)
    charge_id = Column(String, index=True)
    tenant_id = Column(String, index=True, default="org_demo_alpha")
    shipment_id = Column(String, index=True, nullable=True)
    order_id = Column(String, index=True, nullable=True)
    unit_id = Column(String, index=True, nullable=True)
    sku = Column(String, nullable=True)
    asin = Column(String, nullable=True)
    reason = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="USD")
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class EvidenceRecord(Base):
    __tablename__ = "evidence_records"

    id = Column(Integer, primary_key=True, index=True)
    record_id = Column(String, index=True)
    tenant_id = Column(String, index=True, default="org_demo_alpha")
    stage = Column(String, index=True)  # receiving, prep, pack, returns
    unit_id = Column(String, index=True, nullable=True)
    shipment_id = Column(String, index=True, nullable=True)
    order_id = Column(String, index=True, nullable=True)
    check_type = Column(String, nullable=True)
    result = Column(String, nullable=True)
    photo_ref = Column(String, nullable=True)
    operator_id = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class ClaimDecision(Base):
    __tablename__ = "claim_decisions"

    id = Column(Integer, primary_key=True, index=True)
    charge_id = Column(String, index=True)
    tenant_id = Column(String, index=True, default="org_demo_alpha")
    shipment_id = Column(String, nullable=True)
    reason = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    assessment = Column(String, index=True)  # CONTRADICTED, SUPPORTED, SILENT, UNCERTAIN
    claim_amount = Column(Float, default=0.0)
    confidence_score = Column(Float, default=0.0)
    explanation = Column(Text, nullable=False)
    evidence_matched_json = Column(Text, nullable=True)  # JSON string
    supporting_evidence_json = Column(Text, nullable=True)  # JSON string
    is_overridden = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class OverrideRecord(Base):
    __tablename__ = "override_records"

    id = Column(Integer, primary_key=True, index=True)
    charge_id = Column(String, index=True)
    tenant_id = Column(String, index=True, default="org_demo_alpha")
    original_verdict = Column(String, nullable=False)
    new_verdict = Column(String, nullable=False)
    operator_id = Column(String, nullable=False)
    reason = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True)
    action = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
