import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from src.core.tenant_security import filter_by_tenant, validate_tenant_id, TenancySecurityError

logger = logging.getLogger("rules_engine")

DEFAULT_DISPUTE_WINDOW_DAYS = 60

class RecoveryRulesEngine:
    """
    Production-grade hybrid reasoning engine for AI Recovery Manager.
    Enforces conservative, defensible matching between fee charges and operational evidence logs.
    Implements Schema A netting rules, 5 Manager check keys, granularity handling,
    filing window checks, uncertainty handling, fail-open execution, and batch optimization.
    """

    def __init__(
        self,
        receiving_logs: List[Dict[str, Any]],
        prep_logs: List[Dict[str, Any]],
        pack_logs: List[Dict[str, Any]],
        returns_logs: List[Dict[str, Any]],
        reimbursements: Optional[List[Dict[str, Any]]] = None,
        dispute_window_days: int = DEFAULT_DISPUTE_WINDOW_DAYS
    ):
        self.receiving_logs = receiving_logs
        self.prep_logs = prep_logs
        self.pack_logs = pack_logs
        self.returns_logs = returns_logs
        self.reimbursements = reimbursements or []
        self.dispute_window_days = dispute_window_days

        # Pre-build indexed lookup caches for single-pass batch performance (Engineering Rule 2)
        self._index_caches()

    def _index_caches(self):
        """Index evidence logs by unit_id, shipment_id, order_id for O(1) batch matching."""
        self.rec_by_unit = {}
        self.rec_by_ship = {}
        for r in self.receiving_logs:
            if r.get("unit_id"):
                self.rec_by_unit.setdefault(r["unit_id"], []).append(r)
            if r.get("shipment_id"):
                self.rec_by_ship.setdefault(r["shipment_id"], []).append(r)

        self.prep_by_unit = {}
        self.prep_by_ship = {}
        for p in self.prep_logs:
            if p.get("unit_id"):
                self.prep_by_unit.setdefault(p["unit_id"], []).append(p)
            if p.get("shipment_id"):
                self.prep_by_ship.setdefault(p["shipment_id"], []).append(p)

        self.pack_by_unit = {}
        self.pack_by_ship = {}
        for k in self.pack_logs:
            if k.get("unit_id"):
                self.pack_by_unit.setdefault(k["unit_id"], []).append(k)
            if k.get("shipment_id"):
                self.pack_by_ship.setdefault(k["shipment_id"], []).append(k)

        self.ret_by_unit = {}
        self.ret_by_order = {}
        for t in self.returns_logs:
            if t.get("unit_id"):
                self.ret_by_unit.setdefault(t["unit_id"], []).append(t)
            if t.get("order_id"):
                self.ret_by_order.setdefault(t["order_id"], []).append(t)

        self.reimb_by_charge = {}
        self.reimb_by_ship = {}
        for rm in self.reimbursements:
            if rm.get("charge_id"):
                self.reimb_by_charge.setdefault(rm["charge_id"], []).append(rm)
            if rm.get("shipment_id"):
                self.reimb_by_ship.setdefault(rm["shipment_id"], []).append(rm)

    def _find_evidence_for_charge(self, charge: Dict[str, Any], tenant_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """Look up all relevant evidence logs matching unit_id, shipment_id, or order_id strictly scoped by tenant."""
        unit_id = charge.get("unit_id")
        shipment_id = charge.get("shipment_id")
        order_id = charge.get("order_id")

        matched_rec = []
        if unit_id and unit_id in self.rec_by_unit:
            matched_rec.extend(self.rec_by_unit[unit_id])
        if shipment_id and shipment_id in self.rec_by_ship:
            matched_rec.extend(self.rec_by_ship[shipment_id])

        matched_prep = []
        if unit_id and unit_id in self.prep_by_unit:
            matched_prep.extend(self.prep_by_unit[unit_id])
        if shipment_id and shipment_id in self.prep_by_ship:
            matched_prep.extend(self.prep_by_ship[shipment_id])

        matched_pack = []
        if unit_id and unit_id in self.pack_by_unit:
            matched_pack.extend(self.pack_by_unit[unit_id])
        if shipment_id and shipment_id in self.pack_by_ship:
            matched_pack.extend(self.pack_by_ship[shipment_id])

        matched_ret = []
        if unit_id and unit_id in self.ret_by_unit:
            matched_ret.extend(self.ret_by_unit[unit_id])
        if order_id and order_id in self.ret_by_order:
            matched_ret.extend(self.ret_by_order[order_id])

        # Enforce tenant isolation filtering
        rec_filtered = filter_by_tenant(list({r.get("record_id", id(r)): r for r in matched_rec}.values()), tenant_id)
        prep_filtered = filter_by_tenant(list({p.get("record_id", id(p)): p for p in matched_prep}.values()), tenant_id)
        pack_filtered = filter_by_tenant(list({k.get("record_id", id(k)): k for k in matched_pack}.values()), tenant_id)
        ret_filtered = filter_by_tenant(list({t.get("record_id", id(t)): t for t in matched_ret}.values()), tenant_id)

        return {
            "receiving": rec_filtered,
            "prep": prep_filtered,
            "pack": pack_filtered,
            "returns": ret_filtered
        }

    def _is_out_of_window(self, timestamp_str: Optional[str]) -> bool:
        """Check if charge date exceeds the claim filing window limit (e.g. 60 days)."""
        if not timestamp_str:
            return False
        try:
            # Parse ISO string
            ts_str = str(timestamp_str).replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            days_diff = (now - dt).days
            return days_diff > self.dispute_window_days
        except Exception as e:
            logger.debug(f"Timestamp parsing note: {e}")
            return False

    def analyze_charge(self, charge: Dict[str, Any], seen_charges: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Processes a single charge against operational evidence & reimbursement netting rules.
        """
        charge_id = charge.get("charge_id", "UNKNOWN_CHG")
        tenant_id = validate_tenant_id(charge.get("tenant_id"))
        shipment_id = charge.get("shipment_id")
        order_id = charge.get("order_id")
        unit_id = charge.get("unit_id")
        reason = (charge.get("reason") or "").strip().lower()
        amount = float(charge.get("amount", 0.0))
        timestamp = charge.get("timestamp")
        granularity = charge.get("granularity") or ("unit" if unit_id else "shipment" if shipment_id else "order")

        # 0. Check Filing Window Expiry (out_of_window check)
        if self._is_out_of_window(timestamp):
            return {
                "charge_id": charge_id,
                "shipment_id": shipment_id,
                "tenant_id": tenant_id,
                "reason": charge.get("reason"),
                "amount": amount,
                "granularity": granularity,
                "evidence_matched": [],
                "assessment": "out_of_window",
                "claim_amount": 0.0,
                "confidence_score": 1.0,
                "explanation": f"Charge date '{timestamp}' exceeds the maximum allowed claim filing window of {self.dispute_window_days} days. Verdict: out_of_window.",
                "supporting_evidence": []
            }

        # 1. Schema A Netting Rules: Already Reimbursed Check
        reimb_records = filter_by_tenant(
            self.reimb_by_charge.get(charge_id, []) + self.reimb_by_ship.get(shipment_id, []),
            tenant_id
        )
        for rm in reimb_records:
            reimb_amount = float(rm.get("amount_total", rm.get("amount", 0.0)))
            orig_reimb_id = rm.get("original_reimbursement_id")
            # If active reimbursement exists without reversal
            if reimb_amount >= amount and not orig_reimb_id:
                return {
                    "charge_id": charge_id,
                    "shipment_id": shipment_id,
                    "tenant_id": tenant_id,
                    "reason": charge.get("reason"),
                    "amount": amount,
                    "granularity": granularity,
                    "evidence_matched": [rm.get("reimbursement_id", "REIMB-MATCH")],
                    "assessment": "already_reimbursed",
                    "claim_amount": 0.0,
                    "confidence_score": 1.0,
                    "explanation": f"Charge {charge_id} was already reimbursed ${reimb_amount:.2f} by channel under reimbursement record {rm.get('reimbursement_id')}. Verdict: already_reimbursed.",
                    "supporting_evidence": [{
                        "source": "channel_reimbursements",
                        "record_id": rm.get("reimbursement_id"),
                        "timestamp": rm.get("timestamp"),
                        "notes": f"Reimbursement of ${reimb_amount:.2f} matches charge amount."
                    }]
                }

        # Check for duplicate charge in batch
        if seen_charges:
            for prev in seen_charges:
                if (prev.get("charge_id") != charge_id and 
                    prev.get("unit_id") == unit_id and unit_id is not None and
                    prev.get("reason", "").lower() == reason and 
                    abs(float(prev.get("amount", 0.0)) - amount) < 0.01):
                    return {
                        "charge_id": charge_id,
                        "shipment_id": shipment_id,
                        "tenant_id": tenant_id,
                        "reason": charge.get("reason"),
                        "amount": amount,
                        "granularity": granularity,
                        "evidence_matched": ["DUPLICATE_BATCH_CLAIM"],
                        "assessment": "CONTRADICTED",
                        "claim_amount": amount,
                        "confidence_score": 0.99,
                        "explanation": f"Duplicate fee charge detected. Same charge reason '{reason}' and amount ${amount:.2f} was already billed in charge {prev.get('charge_id')}.",
                        "supporting_evidence": [{
                            "source": "fee_report_audit",
                            "record_id": prev.get("charge_id"),
                            "timestamp": prev.get("timestamp"),
                            "notes": "Identified duplicate billing entry for identical unit and shipment."
                        }]
                    }

        evidence = self._find_evidence_for_charge(charge, tenant_id)
        
        all_matched_records = []
        for stage, recs in evidence.items():
            for r in recs:
                rec_id = r.get("record_id") or f"{stage.upper()}-REC"
                all_matched_records.append({
                    "source": f"0{list(evidence.keys()).index(stage)+1}_{stage}_manager",
                    "record_id": rec_id,
                    "timestamp": r.get("timestamp"),
                    "check_type": r.get("check_type") or f"{stage}_verification",
                    "result": r.get("result") or r.get("packaging_check") or r.get("barcode_check") or r.get("box_condition") or r.get("polybag_present"),
                    "photo_ref": r.get("photo_ref"),
                    "notes": r.get("notes") or f"Stage {stage} log matched for charge {charge_id}"
                })

        evidence_matched_ids = [e["record_id"] for e in all_matched_records]

        # 2. CRITICAL RULE: If evidence is missing -> SILENT / insufficient_evidence
        if not all_matched_records:
            return {
                "charge_id": charge_id,
                "shipment_id": shipment_id,
                "tenant_id": tenant_id,
                "reason": charge.get("reason"),
                "amount": amount,
                "granularity": granularity,
                "evidence_matched": [],
                "assessment": "SILENT",
                "verdict_alias": "insufficient_evidence",
                "claim_amount": 0.0,
                "confidence_score": 0.0,
                "explanation": f"No operational evidence found in Receiving, Prep, Pack, or Returns logs for unit/shipment '{unit_id or shipment_id}'. Per conservative rules, missing data yields SILENT (insufficient_evidence) verdict.",
                "supporting_evidence": []
            }

        rec_rec = evidence["receiving"][0] if evidence["receiving"] else {}
        prep_rec = evidence["prep"][0] if evidence["prep"] else {}
        pack_rec = evidence["pack"][0] if evidence["pack"] else {}
        ret_rec = evidence["returns"][0] if evidence["returns"] else {}

        # 3. Rule 4 Conflict check: Conflicting evidence or UNCERTAIN verdict
        has_moisture = rec_rec.get("box_condition") == "MOISTURE_EXPOSURE"
        has_box_tear = pack_rec.get("box_tear_detected") is True
        prep_pass = (prep_rec.get("packaging_check") == "PASS" or prep_rec.get("polybag_present") == "PASS")
        is_uncertain_check = (prep_rec.get("result") == "UNCERTAIN" or rec_rec.get("result") == "UNCERTAIN" or pack_rec.get("result") == "UNCERTAIN")

        if is_uncertain_check or ((has_moisture or has_box_tear) and prep_pass and ("packaging" in reason or "defect" in reason)):
            return {
                "charge_id": charge_id,
                "shipment_id": shipment_id,
                "tenant_id": tenant_id,
                "reason": charge.get("reason"),
                "amount": amount,
                "granularity": granularity,
                "evidence_matched": evidence_matched_ids,
                "assessment": "UNCERTAIN",
                "verdict_alias": "insufficient_evidence",
                "claim_amount": 0.0,
                "confidence_score": 0.45,
                "explanation": "Ambiguous operational data or UNCERTAIN check verdict recorded across multi-manager logs. Routed for manual operator review under conservative rules.",
                "supporting_evidence": all_matched_records
            }

        # Weight sensor ambiguity check
        rec_weight = rec_rec.get("weight_sensor_lbs")
        pack_weight = pack_rec.get("weight_sensor_lbs")
        if rec_weight and pack_weight and abs(float(rec_weight) - float(pack_weight)) > 2.0:
            return {
                "charge_id": charge_id,
                "shipment_id": shipment_id,
                "tenant_id": tenant_id,
                "reason": charge.get("reason"),
                "amount": amount,
                "granularity": granularity,
                "evidence_matched": evidence_matched_ids,
                "assessment": "UNCERTAIN",
                "verdict_alias": "insufficient_evidence",
                "claim_amount": 0.0,
                "confidence_score": 0.50,
                "explanation": f"Weight discrepancy conflict: Receiving logged {rec_weight} lbs while Pack scale logged {pack_weight} lbs. Hardware scale calibration conflict requires operator audit.",
                "supporting_evidence": all_matched_records
            }

        # 4. Granularity Handling: Shipment-level charge with passing units
        if granularity == "shipment" or (not unit_id and shipment_id):
            total_ship_units = len(evidence["prep"]) + len(evidence["receiving"]) + len(evidence["pack"])
            if total_ship_units > 0:
                # Check if all available logs for shipment pass quality checks
                all_prep_pass = all((p.get("polybag_present") == "PASS" or p.get("packaging_check") == "PASS" or p.get("barcode_check") == "PASS") for p in evidence["prep"]) if evidence["prep"] else True
                all_rec_pass = all((r.get("box_condition") == "INTACT" or r.get("unit_undamaged") == "PASS") for r in evidence["receiving"]) if evidence["receiving"] else True
                all_pack_pass = all((k.get("all_items_present") == "PASS" or k.get("box_tear_detected") is not True) for k in evidence["pack"]) if evidence["pack"] else True

                if all_prep_pass and all_rec_pass and all_pack_pass:
                    return {
                        "charge_id": charge_id,
                        "shipment_id": shipment_id,
                        "tenant_id": tenant_id,
                        "reason": charge.get("reason"),
                        "amount": amount,
                        "granularity": "shipment",
                        "evidence_matched": evidence_matched_ids,
                        "assessment": "CONTRADICTED",
                        "verdict_alias": "contested",
                        "claim_amount": amount,
                        "confidence_score": 0.98,
                        "explanation": f"Shipment-level audit of shipment '{shipment_id}' verified {total_ship_units} passing unit records across receiving, prep, and pack. Filable claim generated at shipment level.",
                        "supporting_evidence": all_matched_records
                    }

        # 5. Check Keys Contradiction Matching Across 5 Managers

        # Check Key 1: Prep Manager (polybag_present, packaging_check, suffocation_warning, bubble_wrap_check)
        if "packaging" in reason or "polybag" in reason or "unbagged" in reason:
            polybag = prep_rec.get("polybag_present") or prep_rec.get("packaging_check")
            bubble = prep_rec.get("bubble_wrap_check")
            if polybag == "PASS" or bubble == "PASS":
                return {
                    "charge_id": charge_id,
                    "shipment_id": shipment_id,
                    "tenant_id": tenant_id,
                    "reason": charge.get("reason"),
                    "amount": amount,
                    "granularity": granularity,
                    "evidence_matched": evidence_matched_ids,
                    "assessment": "CONTRADICTED",
                    "verdict_alias": "contested",
                    "claim_amount": amount,
                    "confidence_score": 0.98,
                    "explanation": f"Prep Manager record {prep_rec.get('record_id')} verifies polybag/packaging check passed FBA specifications. Channel fee is contradicted by operational proof.",
                    "supporting_evidence": all_matched_records
                }
            elif polybag == "FAIL" or bubble == "FAIL":
                return {
                    "charge_id": charge_id,
                    "shipment_id": shipment_id,
                    "tenant_id": tenant_id,
                    "reason": charge.get("reason"),
                    "amount": amount,
                    "granularity": granularity,
                    "evidence_matched": evidence_matched_ids,
                    "assessment": "SUPPORTED",
                    "verdict_alias": "supported",
                    "claim_amount": 0.0,
                    "confidence_score": 0.95,
                    "explanation": f"Prep Manager record {prep_rec.get('record_id')} confirms packaging failure during prep inspection. Channel fee is valid.",
                    "supporting_evidence": all_matched_records
                }

        # Check Key 2: Receiving Manager (unit_undamaged, box_condition, seal_verified)
        if "carton" in reason or "inbound defect" in reason or "warehouse damaged" in reason or "unsealed" in reason:
            unit_undamaged = rec_rec.get("unit_undamaged")
            box_cond = rec_rec.get("box_condition")
            seal_ver = rec_rec.get("seal_verified")
            if unit_undamaged == "PASS" or box_cond == "INTACT" or seal_ver is True:
                return {
                    "charge_id": charge_id,
                    "shipment_id": shipment_id,
                    "tenant_id": tenant_id,
                    "reason": charge.get("reason"),
                    "amount": amount,
                    "granularity": granularity,
                    "evidence_matched": evidence_matched_ids,
                    "assessment": "CONTRADICTED",
                    "verdict_alias": "contested",
                    "claim_amount": amount,
                    "confidence_score": 0.98,
                    "explanation": f"Receiving Manager record {rec_rec.get('record_id')} confirms unit/box was undamaged upon dock receipt. Fee is contradicted by operational proof.",
                    "supporting_evidence": all_matched_records
                }
            elif unit_undamaged == "FAIL" or box_cond == "DAMAGED":
                return {
                    "charge_id": charge_id,
                    "shipment_id": shipment_id,
                    "tenant_id": tenant_id,
                    "reason": charge.get("reason"),
                    "amount": amount,
                    "granularity": granularity,
                    "evidence_matched": evidence_matched_ids,
                    "assessment": "SUPPORTED",
                    "verdict_alias": "supported",
                    "claim_amount": 0.0,
                    "confidence_score": 0.95,
                    "explanation": f"Receiving Manager record {rec_rec.get('record_id')} confirmed unit/box arrived damaged. Channel fee is valid.",
                    "supporting_evidence": all_matched_records
                }

        # Check Key 3: Pack Manager (all_items_present, item_count_matches, weight_sensor_lbs)
        if "missing item" in reason or "mis-ship" in reason or "shortage" in reason or "weight" in reason or "dimension" in reason:
            all_present = pack_rec.get("all_items_present") or pack_rec.get("item_count_matches")
            verified_weight = pack_rec.get("weight_sensor_lbs")
            if all_present == "PASS" or verified_weight is not None:
                return {
                    "charge_id": charge_id,
                    "shipment_id": shipment_id,
                    "tenant_id": tenant_id,
                    "reason": charge.get("reason"),
                    "amount": amount,
                    "granularity": granularity,
                    "evidence_matched": evidence_matched_ids,
                    "assessment": "CONTRADICTED",
                    "verdict_alias": "contested",
                    "claim_amount": amount,
                    "confidence_score": 0.97,
                    "explanation": f"Pack Manager record {pack_rec.get('record_id')} confirms all items were present and verified on calibrated sensor scale. Fee is contradicted.",
                    "supporting_evidence": all_matched_records
                }

        # Check Key 4: Returns Manager (condition_grade, return_disposition)
        if "damaged inventory" in reason or "return" in reason or "expired" in reason or "sellable" in reason:
            cond_grade = ret_rec.get("condition_grade")
            disp = ret_rec.get("return_disposition")
            if cond_grade in ["SELLABLE", "NEW"] or disp == "CARRIER_DAMAGE":
                return {
                    "charge_id": charge_id,
                    "shipment_id": shipment_id,
                    "tenant_id": tenant_id,
                    "reason": charge.get("reason"),
                    "amount": amount,
                    "granularity": granularity,
                    "evidence_matched": evidence_matched_ids,
                    "assessment": "CONTRADICTED",
                    "verdict_alias": "contested",
                    "claim_amount": amount,
                    "confidence_score": 0.99,
                    "explanation": f"Returns Manager inspection {ret_rec.get('record_id')} verified item grade as '{cond_grade or disp}'. Seller defect fee is contradicted.",
                    "supporting_evidence": all_matched_records
                }

        # Check Key 5: Barcode / Labeling (barcode_scanned, fnsku_scanned)
        if "label" in reason or "barcode" in reason or "unlabelled" in reason:
            bc_check = prep_rec.get("barcode_check") or prep_rec.get("barcode_scanned")
            fnsku = prep_rec.get("fnsku_scanned")
            if bc_check == "PASS" or fnsku is not None:
                return {
                    "charge_id": charge_id,
                    "shipment_id": shipment_id,
                    "tenant_id": tenant_id,
                    "reason": charge.get("reason"),
                    "amount": amount,
                    "granularity": granularity,
                    "evidence_matched": evidence_matched_ids,
                    "assessment": "CONTRADICTED",
                    "verdict_alias": "contested",
                    "claim_amount": amount,
                    "confidence_score": 0.97,
                    "explanation": f"Prep Manager record {prep_rec.get('record_id')} confirms barcode scannability (FNSKU: {fnsku or 'scanned'}). Fee is contradicted.",
                    "supporting_evidence": all_matched_records
                }

        # Fallback for unmapped matched evidence -> UNCERTAIN
        return {
            "charge_id": charge_id,
            "shipment_id": shipment_id,
            "tenant_id": tenant_id,
            "reason": charge.get("reason"),
            "amount": amount,
            "granularity": granularity,
            "evidence_matched": evidence_matched_ids,
            "assessment": "UNCERTAIN",
            "verdict_alias": "insufficient_evidence",
            "claim_amount": 0.0,
            "confidence_score": 0.50,
            "explanation": f"Operational logs found for charge '{charge_id}' but charge reason '{charge.get('reason')}' could not be deterministically confirmed or contradicted. Requires human audit.",
            "supporting_evidence": all_matched_records
        }

    def analyze_charge_with_llm_fallback(self, charge: Dict[str, Any], llm_func: Optional[Any] = None) -> Dict[str, Any]:
        """
        Rule 3 Compliance (Fail-Open Execution):
        Simulates LLM API timeout or service failure during analysis; ensures engine falls back
        gracefully to deterministic rule engine without throwing uncaught exceptions, setting status to pending_review/UNCERTAIN.
        """
        try:
            if llm_func is not None:
                return llm_func(charge)
        except Exception as exc:
            logger.warning(f"LLM API failure/timeout detected: {exc}. Executing fail-open deterministic fallback.")
            res = self.analyze_charge(charge)
            res["assessment"] = "UNCERTAIN"
            res["status"] = "pending_review"
            res["explanation"] = f"LLM API service fallback: {exc}. Case routed to pending_review under fail-open rule."
            return res

        return self.analyze_charge(charge)

    def analyze_batch(self, charges: List[Dict[str, Any]], tenant_id: str) -> List[Dict[str, Any]]:
        """
        Single-pass batch processing across all charges for a given tenant.
        Enforces Engineering Rule 2: Single-pass batch evaluation per shipment/order.
        Enforces Engineering Rule 1: Scoped to tenant_id.
        """
        tenant = validate_tenant_id(tenant_id)
        tenant_charges = filter_by_tenant(charges, tenant)

        results = []
        seen = []
        for charge in tenant_charges:
            res = self.analyze_charge(charge, seen_charges=seen)
            results.append(res)
            seen.append(charge)
        return results
