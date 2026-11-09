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
- **Release Gate & Governance (COMPLETE - Phase 3):**
  - Frozen versioned policy file `release_gates.yaml` defining cryptographic checkpoint SHA-256 validation, mandatory evaluation suites (`AuditKIT` and `SafeTune`), minimum domain accuracy ($\ge 85\%$), safety compliance ($\ge 95\%$), over-refusal limits ($\le 10\%$), and mandatory human officer sign-off.
  - Release governance database table `model_releases` tracking candidate evaluations, rejection reasons, check telemetry, and official human reviewer decisions.
  - `ReleaseGateService` enforcing governance invariants: automated or LLM self-approvals (e.g., `llm`, `assistant`, `agent`, `system`, `auto`, `copilot`) are strictly rejected.
  - Model catalog endpoint `GET /api/models`, detailed report endpoint `GET /api/models/{id}/report` conforming to `contracts/model_run.schema.json`, gate check evaluation endpoint `POST /api/models/{id}/evaluate`, and human sign-off endpoint `POST /api/models/{id}/release-decision`.
  - Active model serving pointer endpoint `GET /api/models/releases/active` providing authoritative model release status for inference.
- **Interactive UI Dashboard (COMPLETE - Phase 3):**
  - Live single-page interface mounted at `http://127.0.0.1:8000/ui`
  - 4 Navigation Tabs: 🔬 Assistant & Memory, ⚡ Pipeline Runs, ⚖️ Eval & Release, 🌱 New Model
  - Pipeline Runs table with 9-stage progression bar, status badges, config hashes, retry counters, and modal event timelines
  - Evaluation & Release page featuring live M0-M3 model comparison matrix with sample size denominators ($N=250$), live 6-point policy gate checklist, official human sign-off terminal, and append-only governance audit trail
  - New Model page with full parameter and hyperparameter configuration (learning rate, epochs, batch size, LoRA $r$, LoRA $\alpha$), stage selection, and automatic pipeline job dispatch
- **Test Suite:** 78 passed, 1 skipped, 0 failed (11 release gate tests covering hash mismatch, missing audits, low accuracy, mock rejection, governance invariants, and API endpoints)
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

## Next Actions (Phase 4)

1. Implement `backend/services/inference_service.py` with `approved_checkpoint` verification (rejects chat if no approved release exists).
2. Evidence retrieval service with SQLite FTS5 index on scientific records and append-only assessments.
3. Role-based demo authentication (`researcher`, `admin`) preventing cross-scope data retrieval.
4. Assistant chat UI enhancements with clickable record citations.
