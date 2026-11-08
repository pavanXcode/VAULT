# VAULT Handoff Ledger & Status

**Owner:** Pawan (Harness, backend, product experience)  
**Branch:** `feat/harness-ui`  
**Current Date:** 2026-11-08  
**Release Target:** 2026-11-13  

---

## Current Status

- **Git Branch:** `feat/harness-ui`
- **Core Backend:** FastAPI with document upload, experiment tracking, asynchronous tool execution (AuditKIT, SafeTune, CuratorKIT), and local LLM client
- **Scientific Records & Memory (COMPLETE):**
  - Immutable raw laboratory records (`records` table) under SHA-256 content hashes
  - Append-only verification assessment ledger (`assessments` table)
  - Four mandatory scientific verification scenarios (arithmetic mismatch, valid alternative methods, unknown methods, and expired calibrations) verified and passing
  - Dual-layer immutability enforcement: ORM lifecycle event listeners and SQLite database triggers prevent any silent UPDATE or DELETE
  - API endpoints: `/api/records/review`, `/api/records/ingest`, `/api/records/{id}/history`, `/api/records`, `/api/assistant/review-record`, `/api/assistant/ask`
- **Interactive UI Dashboard (COMPLETE):**
  - Live single-page interface mounted at `http://127.0.0.1:8000/ui`
  - 4 Navigation Tabs: 🔬 Assistant & Memory, ⚡ Pipeline Runs, ⚖️ Eval & Release, 🌱 New Model
  - Pre-loaded sample buttons for the mandatory scenarios
  - Chronological history timeline view
- **Test Suite:** 62 passed, 1 skipped, 0 failed
- **Active Integrations:**
  - AuditKIT runner: Available
  - SafeTune runner: Available
  - CuratorKIT runner: Available
  - Vijay data engine: Standalone rule engine active; awaiting updated simulator package from Vijay
  - Rohit model engine: Awaiting Tiny Aya LoRA checkpoints and inference server from Rohit; adapter interface in place

---

## Blockers & Dependencies

1. **Vijay (Data/Verifier):** Pending fresh synthetic lab dataset and expanded `verify_record()` logic. Standalone rule engine serves as working adapter.
2. **Rohit (Model/Safety):** Pending Tiny Aya LoRA weights and AuditKIT evaluation logs. Mock adapter with honest `[MOCK]` tags used for UI integration.

---

## Next Actions

1. Implement `backend/models/record.py` and `backend/models/assessment.py` (immutable scientific records and append-only findings).
2. Implement `backend/services/record_service.py` with content-hashing (SHA-256) and history retrieval.
3. Expose `/api/records/review`, `/api/records/ingest`, `/api/records/{id}/history`, and `/api/assistant/review-record`.
4. Build the minimal Research Assistant UI page.
