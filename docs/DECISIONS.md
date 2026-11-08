# VAULT Decision Log

Format: Date | Decision | Reason | Owner | Affected Contracts | Rollback

- 2026-11-08 | Initialize `feat/harness-ui` branch | Pawan's harness, API, and UI workspace setup | Pawan | None | `git checkout main`
- 2026-11-08 | Decouple ground-truth validation from local simulator folder | Vijay will provide updated simulator dataset later; internal rule engine functions standalone | Pawan / Vijay | `contracts/record.schema.json` | Revert to simulator submodule
- 2026-11-08 | Add scientific records and append-only assessment models | Required for immutable scientific memory (Playbook P1/P2/V7) | Pawan | `contracts/assessment.schema.json` | Drop tables `records`, `assessments`
- 2026-11-08 | Adapter pattern for model training worker | Rohit will supply Tiny Aya checkpoints later; adapter supports mock/CLI interchangeably | Pawan / Rohit | `contracts/model_run.schema.json` | Remove worker registry entry
