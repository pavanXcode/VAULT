# VAULT Decision Log

Format: Date | Decision | Reason | Owner | Affected Contracts | Rollback

- 2026-11-08 | Initialize `feat/harness-ui` branch | Pawan's harness, API, and UI workspace setup | Pawan | None | `git checkout main`
- 2026-11-08 | Decouple ground-truth validation from local simulator folder | Vijay will provide updated simulator dataset later; internal rule engine functions standalone | Pawan / Vijay | `contracts/record.schema.json` | Revert to simulator submodule
- 2026-11-08 | Add scientific records and append-only assessment models | Required for immutable scientific memory (Playbook P1/P2/V7) | Pawan | `contracts/assessment.schema.json` | Drop tables `records`, `assessments`
- 2026-11-08 | Adapter pattern for model training worker | Rohit will supply Tiny Aya checkpoints later; adapter supports mock/CLI interchangeably | Pawan / Rohit | `contracts/model_run.schema.json` | Remove worker registry entry
- 2026-11-09 | Add bounded retries and stage timing to Job state machine | Prevent runaway retries (capped at 3) and provide stage-level observability | Pawan | `contracts/job.schema.json` | Revert job model changes
- 2026-11-09 | Standardize model_run.schema.json contract for Rohit handoff | Freeze interface for Tiny Aya M0-M3 training artifacts before weights arrive | Pawan / Rohit | `contracts/model_run.schema.json` | Revert schema
- 2026-11-09 | Implement frozen release gate policy in `release_gates.yaml` | Require SHA-256 match, AuditKIT/SafeTune suites, domain accuracy >= 85%, and safety >= 95% | Pawan | `release_gates.yaml` | Restore manual promotion
- 2026-11-09 | Mandatory named human officer sign-off with LLM rejection | Governance invariant: automated agents or LLMs strictly forbidden from approving release candidates | Pawan | `backend/models/release.py` | Allow automated approval flag
- 2026-11-09 | Evaluation dashboard M0-M3 comparison with explicit sample denominators | Truthful metrics with sample denominators (N=250), zero fabricated progress or fake numbers | Pawan | `frontend/app.js` | Revert to static cards
- 2026-11-09 | Integrate Rohit's vault_ml engine and empirical evaluations | Unify QLoRA training artifacts, M0 baseline, M1/M2 runs, and SafeTune evaluations | Pawan / Rohit | `vault_ml/`, `experiments/` | Revert to mock adapter
- 2026-11-09 | Implement approved model inference engine and evidence citation allowlist | Strictly block unapproved serving; serialize GPU inference; cite verified records only | Pawan | `backend/services/inference_service.py` | Direct ungrounded LLM generation
