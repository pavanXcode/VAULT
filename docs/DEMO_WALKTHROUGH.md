# VAULT — Live Demonstration & Verification Walkthrough

**Platform:** VAULT — Safe Scientific Research Assistant & Model Factory  
**Primary Track:** Offline-First, Trustworthy AI for Regulated Laboratory Environments  
**Target Roles:** Researcher, Quality Assurance Officer, System Administrator  
**Version:** 1.0.0-rc1 (`feat/harness-ui`)  

---

## 1. Quickstart & Service Launch

To launch the VAULT backend and interactive web interface:

```powershell
# From D:\VAULT with activated virtual environment
D:\VAULT\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

- **Interactive Dashboard:** [http://127.0.0.1:8000/ui](http://127.0.0.1:8000/ui)
- **Interactive OpenAPI Docs:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Health Check:** `curl http://127.0.0.1:8000/`

---

## 2. Demo Credentials & Token Headers

For API calls or testing role-based data scoping:

| Role | Demo Token | Scoping & Permissions |
|---|---|---|
| **Researcher** | `vault-researcher-token-2026` | Ingest lab records, run evaluations, chat with approved models. Restricted to standard lab domain. |
| **Admin / QA Officer** | `vault-admin-token-2026` | Full system governance, human release sign-off, system metrics, audit inspection. |

In headers:
```http
Authorization: Bearer vault-admin-token-2026
```

---

## 3. The 5-Step Golden Demo Flow

### Step 1: Scientific Record Ingestion & Deterministic Verification
1. Navigate to **🔬 Assistant & Memory** tab at `http://127.0.0.1:8000/ui`.
2. Review a test laboratory record with intentional arithmetic discrepancy (e.g., reported $12.5\text{ mg/L}$ vs calculated $10.0\text{ mg/L}$).
3. Observe:
   - Status immediately changes to **FAIL** with structured findings.
   - Record is stored immutably under canonical SHA-256 content hash.
   - Verification event is appended to the immutable `assessments` ledger.

### Step 2: Training Pipeline Job Dispatch
1. Navigate to **🌱 New Model** tab.
2. Select candidate `M2-gated-lora`, dataset `records-verified-v1`, LoRA rank $r=16$, $\alpha=32$, LR $2\times 10^{-4}$.
3. Click **🚀 Launch Training Pipeline Job**.
4. Navigate to **⚡ Pipeline Runs** tab:
   - Observe the 9-stage progression bar (`ingest` $\rightarrow$ `verify` $\rightarrow$ `curate` $\rightarrow$ `baseline` $\rightarrow$ `train` $\rightarrow$ `harden` $\rightarrow$ `audit` $\rightarrow$ `release` $\rightarrow$ `serve`).
   - Click **Timeline** to view timestamped execution logs, worker IDs, and config digests.

### Step 3: Frozen Release Gate Evaluation
1. Navigate to **⚖️ Eval & Release** tab.
2. View the empirical M0–M3 comparison table (all evaluated with $N=250$ held-out samples):
   - **M0 Baseline:** 20% JSON compliance, 50% decision match, 75% safety refusal.
   - **M1 Plain LoRA:** 70% JSON compliance, 42.9% numeric match, high safety risk.
   - **M2 Evidence-Gated LoRA:** 80% JSON compliance, 50% numeric match, 0% over-refusal, converged loss 0.283.
3. Click **Evaluate Gate** for candidate `M2-gated-lora`:
   - System checks 6 frozen policies in `release_gates.yaml`: SHA-256 match, AuditKIT, SafeTune, domain accuracy $\ge 85\%$, safety $\ge 95\%$, over-refusal $\le 10\%$.
   - Outcome: **PASSED** (Ready for Human Officer Decision).

### Step 4: Governance & Human Officer Sign-Off
1. Under **Human Release Decision Terminal**:
   - Model ID: `M2-gated-lora`
   - Reviewer Name: `Dr. Sarah Chen, QA Lead`
   - Decision: `APPROVE`
   - Notes: `Empirical convergence verified at loss 0.283. AuditKIT and SafeTune safety checks passed.`
2. Click **Submit Official Release Decision**.
3. Observe:
   - Governance event is permanently recorded in `model_releases`.
   - Active release pointer immediately updates: `Approved: M2-gated-lora`.

### Step 5: Evidence-Gated Conversational QA
1. Return to **🔬 Assistant & Memory** tab.
2. Notice the live status badge shows **🟢 Active Serving Model: M2-gated-lora (Human Approved)**.
3. Submit a query:
   > *"What was the finding on record REC-DEMO-001?"*
4. Observe the response:
   - Response is synthesized from immutable records and assessments.
   - Every claim contains a strict citation tag: `[SOURCE:REC-DEMO-001]`.
   - Single-worker GPU lock ensures zero concurrency OOM on 6 GB VRAM hardware.

---

## 4. Key Invariant Demonstrations (Edge Cases)

### Invariant A: LLM / Automated Self-Approval Rejection
- Attempting to sign off a model using an automated agent name (`reviewer_name: "Auto-Agent-LLM"` or `"copilot"`) is **strictly rejected with HTTP 400**:
  ```json
  {"detail": "Automated or LLM agents are strictly prohibited from approving model releases. A named human officer is required."}
  ```

### Invariant B: Unapproved Model Serving Block
- If no candidate model has been approved by a human officer, any call to `/api/assistant/ask` immediately returns:
  ```json
  {"detail": "No model release has been approved by a human officer. Model serving is gated."}
  ```

### Invariant C: Database Immutability Triggers
- Any raw SQL `UPDATE` or `DELETE` executed against `records`, `assessments`, or `ground_truth_validations` tables triggers an SQLite `RAISE(ABORT, 'IMMUTABILITY VIOLATION: ...')` error at the database engine level.

### Invariant D: Restart Crash Recovery
- If the server process is abruptly killed while a training job is `running`, the startup lifespan routine detects the orphaned job and marks it as `interrupted` (with explanation `"Job was interrupted by application shutdown or server restart."`), preventing phantom progress.

---

## 5. Automated Verification Execution

To run all 111 automated tests covering every layer of the platform:

```powershell
D:\VAULT\.venv\Scripts\python.exe -m pytest backend\tests -v
```
Output: **111 passed, 1 skipped, 18 subtests passed in ~20s.**
