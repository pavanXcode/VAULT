# VAULT Handoff Ledger & Status

**Owner:** Pawan (Harness, backend, product experience)  
**Branch:** `feat/harness-ui`  
**Current Date:** 2026-11-09  
**Release Target:** 2026-11-13  

---

## Current Status

- **Git Branch:** `feat/harness-ui`
- **Core Backend:** FastAPI with document upload, experiment tracking, asynchronous tool execution (AuditKIT, SafeTune, CuratorKIT, Tiny Aya Training Adapter), and local LLM client
- **Scientific Records & Memory (COMPLETE):**
  - Immutable raw laboratory records (`records` table) under SHA-256 content hashes
  - Append-only verification assessment ledger (`assessments` table)
  - Four mandatory scientific verification scenarios (arithmetic mismatch, valid alternative methods, unknown methods, and expired calibrations) verified and passing
  - Dual-layer immutability enforcement: ORM lifecycle event listeners and SQLite database triggers prevent any silent UPDATE or DELETE
  - API endpoints: `/api/records/review`, `/api/records/ingest`, `/api/records/{id}/history`, `/api/records`, `/api/assistant/review-record`, `/api/assistant/ask`
- **Job Pipeline & Worker Infrastructure (COMPLETE - Phase 2):**
  - Enhanced job state machine with truthful statuses (`queued`/`pending`, `running`, `succeeded`/`completed`, `failed`, `cancelled`, `not_tested`, `quarantined`, `interrupted`)
  - Stage tracking: `ingest` -> `verify` -> `curate` -> `baseline` -> `train` -> `harden` -> `audit` -> `release` -> `serve`
  - Bounded retries: max 3 attempts enforced, restart recovery marks orphaned running jobs as `interrupted`
  - Contracts frozen: `contracts/job.schema.json` and `contracts/model_run.schema.json`
  - Trainer worker adapter (`TrainerWorkerRunner`): supports subprocess execution of Rohit's CLI, checks physical presence of `adapter_model.safetensors`, never invents success; emits honest `not_tested` with `is_mock=True` while awaiting Rohit's weights
  - Endpoints: `POST /api/jobs/{id}/retry`, `GET /api/jobs/{id}/events`
- **Interactive UI Dashboard (COMPLETE):**
  - Live single-page interface mounted at `http://127.0.0.1:8000/ui`
  - 4 Navigation Tabs: 🔬 Assistant & Memory, ⚡ Pipeline Runs, ⚖️ Eval & Release, 🌱 New Model
  - Pipeline Runs table with 9-stage progression bar, status badges, config hashes, retry counters, and modal event timelines
- **Test Suite:** 67 passed, 1 skipped, 0 failed
- **Active Integrations:**
  - AuditKIT runner: Available
  - SafeTune runner: Available
  - CuratorKIT runner: Available
  - Trainer adapter: Ready to execute Rohit's CLI script immediately when supplied
  - Vijay data engine: Standalone rule engine active; awaiting updated simulator package from Vijay
  - Rohit model engine: Awaiting Tiny Aya LoRA training script/weights from Rohit

---

## Blockers & Dependencies

1. **Vijay (Data/Verifier):** Pending fresh synthetic lab dataset. Standalone rule engine serves as working adapter.
2. **Rohit (Model/Safety):** Preparing Tiny Aya LoRA training code and weights. The trainer adapter is fully built and tested to plug in Rohit's CLI/script without any backend rewrites.

---

## Next Actions (Phase 3)

1. Implement `release_gates.yaml` with frozen versioned evaluation criteria.
2. Implement `backend/services/release_gate.py` enforcing checkpoint hash matching, required audit evaluations, and human sign-off.
3. Expose `GET /api/models/{id}/report` returning real saved evaluation metrics.
4. Enhance Page 3 (Evaluation & Release) and Page 1 (New Model) in the UI.
