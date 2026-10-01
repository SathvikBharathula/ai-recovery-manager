# Architecture Specification · AI Recovery Manager

**Commerce Context Stream · Step 5 of 5 · Money Back**

---

## 1. High-Level System Architecture

AI Recovery Manager is architected as a decoupled, multi-tenant recovery engine designed to bridge channel fee reports (Amazon FBA, Walmart WFS, 3PLs) with physical operational evidence produced across four upstream warehouse managers:

1. `01 Receiving Manager` (Condition on arrival, box damage, seal verification)
2. `02 Prep Manager` (Poly-bagging, suffocation warning labels, bubble wrap, FNSKU scanning)
3. `03 Pack Manager` (Weight sensors, dimensions, box seal integrity)
4. `04 Returns Manager` (Customer return inspection, disposition, carrier damage classification)

```mermaid
flowchart TD
    subgraph Data Sources
        FEE[Channel Fee Reports\nCSV / JSON]
        REC[01 Receiving Logs]
        PREP[02 Prep Logs]
        PACK[03 Pack Logs]
        RET[04 Returns Logs]
    end

    subgraph Security & Ingestion Layer
        API[FastAPI REST Server]
        RLS[Tenancy Isolation Guard\norg_demo_alpha vs org_demo_bravo]
    end

    subgraph Core Reasoning Engine
        BRE[Deterministic Rules Engine]
        EXP[LLM Explanation Layer]
    end

    subgraph Storage & Persistence
        DB[(SQLite / PostgreSQL\nCharges, Decisions, Audit Overrides)]
    end

    subgraph Presentation & UI Layer
        WEB[3D WebGL Dashboard\nThree.js + React 18 + Tailwind]
        EXPORT[Claim Exporter\nJSON / CSV / Legal Text]
    end

    FEE --> API
    API --> RLS
    RLS --> BRE
    REC & PREP & PACK & RET --> BRE
    BRE --> EXP
    BRE --> DB
    EXP --> WEB
    DB --> WEB
    WEB --> EXPORT
```

---

## 2. Charge Assessment State Machine

Every charge follows a strict, deterministic state progression. The system is conservative and defensible: **it never invents evidence**, missing data yields `SILENT`, and ambiguous data yields `UNCERTAIN`.

```mermaid
stateDiagram-v2
    [*] --> INGESTED: Fee Report Ingested
    INGESTED --> SEARCHING_EVIDENCE: Match SKU / Shipment / Order / Unit ID

    state SEARCHING_EVIDENCE {
        [*] --> QUERY_UPSTREAM
        QUERY_UPSTREAM --> NO_EVIDENCE_FOUND: 0 Matches
        QUERY_UPSTREAM --> EVIDENCE_FOUND: >= 1 Match
    }

    NO_EVIDENCE_FOUND --> SILENT: Critical Rule (Missing Data = SILENT)

    EVIDENCE_FOUND --> CHECK_CONFLICTS: Evaluate Record Consistency
    CHECK_CONFLICTS --> UNCERTAIN: Conflicting Sensor / Inspection Readings

    CHECK_CONFLICTS --> EVALUATE_RULES: Consistent Operational Proof

    EVALUATE_RULES --> CONTRADICTED: Proof contradicts channel fee (Generate Claim)
    EVALUATE_RULES --> SUPPORTED: Proof confirms operational defect (Valid Fee)

    CONTRADICTED --> CLAIM_FILED: Export Claim / Legal Dispute Generated
    SUPPORTED --> ARCHIVED: Closed / No Claim
    SILENT --> ARCHIVED: Closed / No Claim
    UNCERTAIN --> OPERATOR_OVERRIDE: Manual Review

    OPERATOR_OVERRIDE --> CONTRADICTED: Override to Claim
    OPERATOR_OVERRIDE --> SUPPORTED: Override to Valid Fee
```

---

## 3. Data Models & Database Schema

The database schema enforces tenancy isolation, auditing, and complete traceability.

```mermaid
erDiagram
    Charge ||--o{ ClaimDecision : evaluates
    ClaimDecision ||--o{ OverrideRecord : audits
    
    Charge {
        string charge_id PK
        string tenant_id FK
        string shipment_id
        string order_id
        string unit_id
        string sku
        string reason
        float amount
    }

    ClaimDecision {
        int id PK
        string charge_id FK
        string tenant_id FK
        string assessment
        float claim_amount
        float confidence_score
        text explanation
        text evidence_matched_json
        text supporting_evidence_json
        boolean is_overridden
    }

    OverrideRecord {
        int id PK
        string charge_id FK
        string tenant_id FK
        string original_verdict
        string new_verdict
        string operator_id
        text reason
        datetime timestamp
    }
```

---

## 4. Multi-Tenant Isolation Model (Engineering Rule 1)

Tenancy isolation is enforced before any feature evaluation.
- Every incoming HTTP request must specify `X-Tenant-ID` header or query parameter `tenant_id_query`.
- Allowed tenants: `org_demo_alpha`, `org_demo_bravo`.
- Data isolation is enforced at:
  1. Database queries (`WHERE tenant_id = :tenant`).
  2. In-memory evidence log filtering via `src/core/tenant_security.py`.
  3. Strict cross-tenant security assertions (`assert_tenant_isolation`).

---

## 5. Overrides as Data Architecture (Engineering Rule 6)

When an operator disagrees with the agent verdict:
1. The original verdict in `ClaimDecision` is recorded.
2. An append-only audit record is inserted into `OverrideRecord` containing:
   - `charge_id`
   - `tenant_id`
   - `original_verdict`
   - `new_verdict`
   - `operator_id`
   - `reason`
   - `timestamp`
3. `is_overridden` flag is set to `true`. Original evidence and history are preserved for complete compliance audits.

---

## 6. REST API Endpoint Specification

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | System health check. |
| `GET` | `/tenants` | List available tenant organizations. |
| `POST` | `/upload-report` | Ingest CSV or JSON fee report file. |
| `POST` | `/analyze` | Execute reasoning engine for tenant charges. |
| `GET` | `/results` | Fetch analyzed charge results with status filter. |
| `POST` | `/overrides` | Record operator verdict override. |
| `GET` | `/export` | Export claims in JSON or CSV format. |
| `GET` | `/eval` | Run evaluation suite against ground truth fixtures. |

---

*AI Recovery Manager Architecture Specification*
