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
- **Model Engineering & vault_ml Integration (COMPLETE - Rohit Handoff):**
  - Integrated Rohit's `vault_ml` engine and complete experimental artifacts from `https://github.com/opensourcecodedesigner/vault-`.
  - Genuine empirical evaluations recorded in `experiments/`:
    - M0 Baseline: Evaluated across held-out science (`experiments/baseline/real-M0-science/`) and safety (`experiments/safety/real-M0/`).
    - M1 Conventional LoRA: Trained 20 steps (5,120 tokens) on unverified records. Adapter SHA-256 `f71f0f9d97aceba32e454eedc05ff32f653a1a30131748b8e40707455d0910b7`. Final loss: 0.773, peak VRAM: 4.68 GB. Evaluated across held-out science and safety.
    - M2 Evidence-Gated LoRA: Trained 20 steps (strictly matched 5,120 tokens) exclusively on verifier-approved records. Adapter SHA-256 `37799d61ce1f5511ed72adf5ff8fa94689c9018fc1e8a1ea17a76d24e44be8c4`. Converged to final loss: 0.283, 80% JSON compliance, 0% over-refusal. Evaluated across held-out science and safety.
    - M3 SafeTune: Cloud 16GB+ Linux GPU training specification in `experiments/training/cloud-16gb.json`. SafeTune offline evaluation metric suite (`HarmfulnessClassifier`, `OverRefusalMetric`) integrated.
  - Complete comparative ledger in `experiments/comparison.json` with status `complete`.
- **Approved Model Inference & Evidence Retrieval (COMPLETE - Phase 4):**
  - `InferenceService` (`backend/services/inference_service.py`):
    - Concurrency lock (`asyncio.Lock`) serializing model inference to respect laptop 6 GB VRAM constraints.
    - Gate Authorization Check: Strictly blocks inference serving if no candidate model is approved by a human officer.
    - Evidence Grounding: Retrieves evidence from immutable `records` and `assessments` tables, enforcing `[SOURCE:id]` citation allowlisting conforming to `INTEGRATION_CONTRACT.md`.
    - Integrated with `/api/assistant/ask` and Web UI `#page-assistant`.
    - Live active model badge in Assistant UI (`Approved: M2-gated-lora` vs `Gate: Unapproved`).
- **Test Suite:** **111 passed, 1 skipped, 18 subtests passed, 0 failed** (includes full backend, release gate, trainer worker, inference service, auth and scoping, crash recovery, golden demo flow, and Rohit's 22 ML tests).
- **Active Integrations:**
  - AuditKIT runner: Available
  - SafeTune runner: Available
  - CuratorKIT runner: Available
  - Trainer adapter: Directly invokes `vault_ml.train` or local CLI
  - Rohit model engine: **Fully integrated** (`vault_ml/`, `experiments/`, M0/M1/M2 checkpoints and evaluation artifacts)
  - Vijay data engine: Standalone rule engine active; awaiting updated simulator package from Vijay (hook `register_custom_verifier` ready)

---

## Blockers & Dependencies

1. **Vijay (Data/Verifier):**
   - *Current State:* Platform is 100% operational and test-passing today using the built-in deterministic verification rule engine (`RecordService.verify_record_logic`).
   - *When Vijay's Work is Needed:* A fresh synthetic lab dataset or external simulator script from Vijay is needed before the final demonstration code freeze (scheduled for Nov 11–12).
   - *Handoff Mechanism:* Vijay's script or verifier function plugs directly into `register_custom_verifier()` in `backend/services/record_service.py` with zero architectural refactoring required.
2. **Rohit (Model/Safety):** **RESOLVED & INTEGRATED.** All model training code, empirical runs, QLoRA weights, evaluation suites, and documentation are integrated into `vault_ml/`, `experiments/`, and backend services.

---

## Next Actions

1. Review and polish end-to-end user experience in Web UI.
2. Prepare demonstration script and final presentation walkthrough.
