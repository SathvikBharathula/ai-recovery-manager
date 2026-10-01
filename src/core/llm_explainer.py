import logging
from typing import Dict, Any, List

logger = logging.getLogger("llm_explainer")

class ClaimExplanationGenerator:
    """
    Secondary explanation layer for generating formal, audit-ready dispute claims
    for channel submission (Amazon Seller Central / 3PL reimbursement portals).
    """

    @staticmethod
    def generate_formal_claim_text(analysis_result: Dict[str, Any]) -> str:
        """
        Synthesizes a structured legal & operational claim dispute statement.
        """
        assessment = analysis_result.get("assessment")
        charge_id = analysis_result.get("charge_id")
        shipment_id = analysis_result.get("shipment_id")
        reason = analysis_result.get("reason")
        amount = analysis_result.get("amount", 0.0)
        claim_amount = analysis_result.get("claim_amount", 0.0)
        explanation = analysis_result.get("explanation")
        evidence = analysis_result.get("supporting_evidence", [])

        if assessment != "CONTRADICTED":
            return f"Status: {assessment}. No claim generated for dispute."

        evidence_bullets = []
        for e in evidence:
            source = e.get("source", "Operational System")
            rec_id = e.get("record_id", "N/A")
            ts = e.get("timestamp", "N/A")
            result = e.get("result", "N/A")
            notes = e.get("notes", "")
            photo = e.get("photo_ref", "")
            bullet = f"• [{source.upper()}] Record {rec_id} at {ts}: Result={result}. Notes: '{notes}'. Photo Proof: {photo}"
            evidence_bullets.append(bullet)

        evidence_str = "\n".join(evidence_bullets) if evidence_bullets else "• Batch audit log match."

        formal_claim = f"""FORMAL REIMBURSEMENT CLAIM DISPUTE
--------------------------------------------------
Charge Reference: {charge_id}
Shipment / Order ID: {shipment_id}
Channel Billed Reason: {reason}
Billed Amount: ${amount:.2f} USD
Requested Recovery Claim Amount: ${claim_amount:.2f} USD

DISPUTE RATIONALE & EVIDENCE SUMMARY:
The fee assessed under Charge ID {charge_id} for '{reason}' is factually contradicted by verified operational records captured at inbound receiving and prep compliance stages.

Primary Finding:
{explanation}

OPERATIONAL EVIDENCE TRAIL:
{evidence_str}

STATEMENT OF COMPLIANCE:
All physical units in Shipment {shipment_id} underwent automated and human quality audits in accordance with Amazon FBA prep and packaging guidelines prior to carrier tender. We respectfully request immediate credit/reimbursement of ${claim_amount:.2f} USD.
"""
        return formal_claim.strip()
