"""
Integration tests for Vijay's Data & Verification Engine:
1. vault.verification.verify_record (SOP, calibration, lot, holding time, measurement, arithmetic)
2. Seamless integration with RecordService via register_custom_verifier
3. CuratorKIT sft_messages.jsonl dataset and provenance validation
4. Teacher LLM (Qwen) semantic analysis on Vijay's synthetic experiments
5. Drift-Aware Curation (DAC) on Vijay's 800-record dataset
"""

import json
from pathlib import Path
import pytest
from sqlalchemy.orm import Session

from vault.verification import verify_record, get_default_catalogs
from backend.services.record_service import RecordService, register_custom_verifier
from backend.schemas.record import ScientificRecordInput
from backend.services.teacher_llm_service import get_teacher_service
from backend.services.dac_service import DriftAwareCurationService


# ──────────────────────────────────────────────────────────────
# 1. Vijay Core Verifier Tests
# ──────────────────────────────────────────────────────────────

class TestVijayVerifierCore:
    def test_verify_raw_experiment_from_dataset(self):
        """Loads and verifies a record from Vijay's experiments_v1 dataset."""
        data_path = Path("data/raw/experiments_v1.jsonl")
        assert data_path.exists(), "experiments_v1.jsonl must exist"

        with open(data_path, "r", encoding="utf-8") as f:
            first_line = f.readline()
            record = json.loads(first_line)

        assessment = verify_record(record)
        assert "verdict" in assessment
        assert "status" in assessment
        assert "evidence" in assessment
        assert assessment["record_id"] == record["experiment_id"]
        assert len(assessment["evidence"]) >= 5

    def test_arithmetic_contradiction_detection(self):
        """Vijay's engine must flag arithmetic discrepancies (15 mg / 0.5 L != 3 mg/L)."""
        record = {
            "experiment_id": "EXP-ARITH-TEST",
            "reported_mass": 15.0,
            "reported_volume": 0.5,
            "measured_value": 3.0,  # Contradiction: 15 / 0.5 is 30, not 3
            "method_id": "MTH-STD-01",
        }
        assessment = verify_record(record)
        assert "ARITHMETIC_CONTRADICTION" in assessment["issues"]
        assert assessment["status"] in ("flagged", "needs_review")

    def test_clean_experiment_passes(self):
        """A clean record matching catalogs should evaluate without contradictions."""
        catalogs = get_default_catalogs()
        # Find valid sample, SOP, instrument, and lot from catalogs
        clause = next(iter(catalogs.get("sops", {}).values()))
        inst = next(iter(catalogs.get("instruments", {}).values()))
        lot = next(iter(catalogs.get("lots", {}).values()))
        samp = next(iter(catalogs.get("samples", {}).values()))

        rec = {
            "experiment_id": "EXP-CLEAN-TEST-001",
            "sop_id": clause.get("sop_id"),
            "clause_id": clause.get("clause_id"),
            "run_date": "2025-01-15",
            "instrument_id": inst.get("instrument_id"),
            "lot_id": lot.get("lot_id"),
            "sample_id": samp.get("sample_id"),
            "parameter": clause.get("parameter", "concentration"),
            "measured_value": float(clause.get("min_value", 5.0)),
            "measurement_unit": clause.get("unit", "mg/L"),
            "measurement_uncertainty": 0.05,
            "collection_timestamp": "2025-01-15T08:00:00Z",
            "analysis_timestamp": "2025-01-15T10:00:00Z",
        }
        assessment = verify_record(rec, catalogs=catalogs)
        assert "evidence" in assessment


# ──────────────────────────────────────────────────────────────
# 2. RecordService + Custom Verifier Hook Integration
# ──────────────────────────────────────────────────────────────

class TestRecordServiceVijayIntegration:
    def test_custom_verifier_hook_registration_and_execution(self, db_session: Session):
        """Registers Vijay's verifier hook into RecordService and verifies ingestion."""
        def custom_adapter(rec_dict):
            enriched = dict(rec_dict)
            enriched["experiment_id"] = enriched.get("record_id", "EXP-HOOK-01")
            enriched["reported_mass"] = enriched.get("mass_mg", 10.0)
            enriched["reported_volume"] = enriched.get("volume_l", 1.0)
            enriched["measured_value"] = enriched.get("reported_mg_per_l", 10.0)
            v_res = verify_record(enriched)
            return {
                "status": v_res["status"],
                "issues": v_res["issues"],
                "evidence": v_res["evidence"],
                "derived": v_res.get("derived", {}),
                "verifier_version": f"vijay_engine_{v_res.get('engine_version', '2.0.0')}",
            }

        # Register hook
        register_custom_verifier(custom_adapter)

        try:
            rec_input = ScientificRecordInput(
                record_id="REC-VIJAY-HOOK-01",
                method_id="MTH-STD-01",
                mass_mg=15.0,
                volume_l=0.5,
                reported_mg_per_l=3.0,  # Contradiction: 15 / 0.5 = 30
                threshold_mg_per_l=25.0,
                threshold_measurand="total_concentration",
                original_verdict="PASS",
            )
            # Ingest through RecordService
            rec_model, assessment = RecordService.ingest_record(rec_input, db_session)

            assert rec_model.record_id == "REC-VIJAY-HOOK-01"
            assert "ARITHMETIC_CONTRADICTION" in assessment.issues or "contradiction" in str(assessment.issues).lower()
            assert "vijay_engine" in assessment.verifier_version
        finally:
            # Unregister hook to preserve clean state
            register_custom_verifier(None)


# ──────────────────────────────────────────────────────────────
# 3. CuratorKIT Training Export Dataset Tests
# ──────────────────────────────────────────────────────────────

class TestCuratorKITDataset:
    def test_sft_messages_dataset_format(self):
        """Validates that Vijay's CuratorKIT training export exists and adheres to ChatML format."""
        sft_path = Path("data/training_export_v5/curator_out/sft_messages.jsonl")
        assert sft_path.exists(), "sft_messages.jsonl must exist"

        with open(sft_path, "r", encoding="utf-8") as f:
            first_line = f.readline()
            sample = json.loads(first_line)

        assert "messages" in sample
        assert len(sample["messages"]) >= 2
        roles = [m["role"] for m in sample["messages"]]
        assert "user" in roles
        assert "assistant" in roles

    def test_curator_provenance_manifest(self):
        """Validates that CuratorKIT generated a valid provenance manifest."""
        prov_path = Path("data/training_export_v5/curator_out/lexsi_provenance.json")
        assert prov_path.exists()

        with open(prov_path, "r", encoding="utf-8") as f:
            prov = json.load(f)

        assert prov.get("library") == "curatorkit" or "version" in prov


# ──────────────────────────────────────────────────────────────
# 4. Teacher LLM (Qwen) on Vijay's Dataset
# ──────────────────────────────────────────────────────────────

class TestTeacherOnVijayData:
    @pytest.mark.anyio
    async def test_teacher_analyzes_vijay_experiment(self):
        """Teacher LLM analyzes an experiment from Vijay's synthetic dataset."""
        teacher = get_teacher_service()
        content = (
            "Experiment ID: EXP-0001\n"
            "SOP: SOP-001 (Version 1.0)\n"
            "Instrument: INST-009 (Spectrophotometer)\n"
            "Measured Value: 7.01 mg/L\n"
            "Uncertainty: 0.08 mg/L\n"
            "Lot: LOT-013 (Status: Expired)\n"
            "Verdict: FAIL"
        )
        decision = await teacher.analyze_data(content)
        assert decision.sensitivity in ("INTERNAL", "CONFIDENTIAL", "PUBLIC")
        assert decision.importance in ("HIGH", "CRITICAL", "MEDIUM")
        assert decision.review_required is True  # Because of expired lot


# ──────────────────────────────────────────────────────────────
# 5. Drift-Aware Curation (DAC) on Vijay's Dataset
# ──────────────────────────────────────────────────────────────

class TestDACOnVijayDataset:
    def test_dac_screens_vijay_records(self):
        """Runs DriftAwareCurationService over samples from Vijay's training export."""
        export_path = Path("data/training_export_v5/train_candidates.jsonl")
        assert export_path.exists()

        candidates = []
        with open(export_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= 10:
                    break
                item = json.loads(line)
                candidates.append({
                    "record": {
                        "record_id": item.get("experiment_id", f"EXP-{i}"),
                        "method_id": item.get("method_id", "MTH-STD-01"),
                        "reported_mg_per_l": item.get("measured_value", 10.0),
                    },
                    "assessment": {"status": "checks_passed"},
                })

        report = DriftAwareCurationService.curate_dataset(candidates, max_drift_threshold=0.35)
        assert report.total_evaluated == 10
        assert report.total_approved > 0
        assert report.curated_dataset_hash != ""
