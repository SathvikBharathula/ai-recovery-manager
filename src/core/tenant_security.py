import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("tenant_security")

DEFAULT_TENANT = "org_demo_alpha"
VALID_TENANTS = {"org_demo_alpha", "org_demo_bravo"}

class TenancyException(Exception):
    """Base exception for tenancy violations."""
    pass

class TenancySecurityError(TenancyException):
    """Raised when an illegal cross-tenant access attempt is detected."""
    pass

def validate_tenant_id(tenant_id: Optional[str]) -> str:
    """Validate and sanitize tenant ID."""
    if not tenant_id:
        return DEFAULT_TENANT
    clean_id = str(tenant_id).strip().lower()
    if clean_id not in VALID_TENANTS:
        logger.warning(f"Unknown tenant requested: '{clean_id}'. Defaulting to '{DEFAULT_TENANT}'")
        return DEFAULT_TENANT
    return clean_id

def filter_by_tenant(records: List[Dict[str, Any]], tenant_id: str) -> List[Dict[str, Any]]:
    """
    Filters an in-memory list of dictionary records to ensure strict tenancy isolation.
    Every record must contain a 'tenant_id' matching target tenant_id.
    """
    target_tenant = validate_tenant_id(tenant_id)
    filtered = []
    for record in records:
        rec_tenant = record.get("tenant_id")
        if rec_tenant == target_tenant:
            filtered.append(record)
    return filtered

def assert_tenant_isolation(query_tenant: str, record_tenant: str) -> None:
    """
    Strict security check ensuring query tenant matches record tenant.
    Raises TenancySecurityError if cross-tenant data leak is attempted.
    """
    clean_query = validate_tenant_id(query_tenant)
    clean_record = validate_tenant_id(record_tenant)
    if clean_record != clean_query:
        raise TenancySecurityError(
            f"SECURITY VIOLATION (403): Tenant '{clean_query}' attempted to access data owned by tenant '{clean_record}'."
        )

def verify_asset_access(asset_key: str, requester_tenant_id: str, asset_owner_tenant_id: str) -> None:
    """
    Verifies image path / evidence asset key isolation.
    Raises TenancySecurityError if requester attempts to access another tenant's asset key.
    """
    clean_requester = validate_tenant_id(requester_tenant_id)
    clean_owner = validate_tenant_id(asset_owner_tenant_id)
    if clean_requester != clean_owner:
        raise TenancySecurityError(
            f"SECURITY VIOLATION (403): Tenant '{clean_requester}' denied access to asset '{asset_key}' owned by tenant '{clean_owner}'."
        )

def verify_override_permission(charge_id: str, requester_tenant_id: str, charge_owner_tenant_id: str) -> None:
    """
    Verifies cross-tenant override security.
    Raises TenancySecurityError if an operator attempts to override a charge owned by a different tenant.
    """
    clean_requester = validate_tenant_id(requester_tenant_id)
    clean_owner = validate_tenant_id(charge_owner_tenant_id)
    if clean_requester != clean_owner:
        raise TenancySecurityError(
            f"SECURITY VIOLATION (403): Tenant '{clean_requester}' cannot override decision for charge '{charge_id}' owned by tenant '{clean_owner}'."
        )
