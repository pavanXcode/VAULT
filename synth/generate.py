"""Deterministic synthetic laboratory data simulator for VAULT.

Generates realistic datasets for SOP clauses, instruments, reagent lots,
samples, and experiment runs with diverse scenario families.
"""

from datetime import date, datetime, timedelta
import os
import random
from typing import Any, Dict, List, Optional, Tuple

from synth.units import CANONICAL_UNITS, convert_value
from synth.utils import (
    compute_dataset_hashes,
    load_config,
    save_csv,
    save_jsonl,
)

GENERATOR_VERSION = "1.0.0"

EXPERIMENT_FIELDNAMES = [
    "experiment_id",
    "scenario_family",
    "run_date",
    "collected_at",
    "analyzed_at",
    "sop_id",
    "sop_version",
    "clause_id",
    "instrument_id",
    "lot_id",
    "sample_id",
    "measured_value",
    "measurement_unit",
    "measurement_uncertainty",
]

# Mapping parameter types to compatible instrument types
PARAMETER_INSTRUMENT_MAP = {
    "Dissolved Oxygen": ["Spectrophotometer"],
    "pH": ["pH Meter"],
    "Turbidity": ["Turbidimeter"],
    "Conductivity": ["Conductivity Meter"],
    "Active Ingredient Concentration": ["HPLC"],
    "Impurity A": ["HPLC"],
    "Assay Purity": ["HPLC"],
    "Lead Concentration": ["Atomic Absorption Spectrometer"],
    "Cadmium Concentration": ["Atomic Absorption Spectrometer"],
    "Arsenic Concentration": ["Atomic Absorption Spectrometer"],
    "Ethanol Residue": ["Gas Chromatograph"],
    "Methanol Residue": ["Gas Chromatograph"],
    "Acetone Residue": ["Gas Chromatograph"],
    "Chemical Oxygen Demand": ["Spectrophotometer"],
    "Nitrate Concentration": ["Spectrophotometer"],
    "Phosphate Concentration": ["Spectrophotometer"],
    "Total Suspended Solids": ["Analytical Balance"],
    "Protein Concentration": ["Spectrophotometer"],
    "Aggregate Percentage": ["HPLC"],
    "Formulation pH": ["pH Meter"],
    "Osmolality": ["Conductivity Meter"],
    "Chloride Limit": ["Spectrophotometer"],
    "Sulfate Limit": ["Spectrophotometer"],
    "Absorbance at 280nm": ["Spectrophotometer"],
    "Endotoxin Level": ["Spectrophotometer"],
    "Total Viable Count": ["Analytical Balance"],
    "Bioburden Limit": ["Analytical Balance"],
    "Moisture Content": ["Analytical Balance"],
}

# Mapping parameter to typical reagent lot keywords
PARAMETER_REAGENT_KEYWORDS = {
    "Dissolved Oxygen": ["Phosphate", "Deionized"],
    "pH": ["Buffer Solution pH 7.00", "Hydrochloric", "Sodium Hydroxide"],
    "Turbidity": ["Turbidity Standard"],
    "Conductivity": ["Potassium Chloride"],
    "Active Ingredient Concentration": ["Methanol", "Acetonitrile"],
    "Impurity A": ["Acetonitrile", "Methanol"],
    "Assay Purity": ["Methanol", "Acetonitrile"],
    "Lead Concentration": ["Lead Nitrate", "Nitric Acid"],
    "Cadmium Concentration": ["Cadmium Standard", "Nitric Acid"],
    "Arsenic Concentration": ["Nitric Acid"],
    "Ethanol Residue": ["Ethanol Reference"],
    "Methanol Residue": ["Methanol HPLC"],
    "Acetone Residue": ["Methanol HPLC"],
    "Chemical Oxygen Demand": ["Sulfuric Acid"],
    "Nitrate Concentration": ["Phosphate Standard"],
    "Phosphate Concentration": ["Phosphate Standard"],
    "Total Suspended Solids": ["Deionized"],
    "Protein Concentration": ["Bovine Serum Albumin"],
    "Aggregate Percentage": ["Phosphate Buffer"],
    "Formulation pH": ["Buffer Solution pH 7.00"],
    "Osmolality": ["Potassium Chloride"],
    "Chloride Limit": ["Hydrochloric"],
    "Sulfate Limit": ["Sulfuric Acid"],
    "Absorbance at 280nm": ["Bovine Serum Albumin"],
    "Endotoxin Level": ["Deionized"],
    "Total Viable Count": ["Deionized"],
    "Bioburden Limit": ["Deionized"],
    "Moisture Content": ["Deionized"],
}


def _iso_date(dt: date) -> str:
    return dt.strftime("%Y-%m-%d")


def _iso_datetime(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_sops(count: int = 40, rng: Optional[random.Random] = None) -> List[Dict[str, Any]]:
    """Generate deterministic SOP clause records with versioning and realistic limits."""
    if rng is None:
        rng = random.Random(42)

    # Pre-defined domain clauses spanning 8 SOP documents
    # Includes multiple versions (v1.0 superseded by v2.0) and intentional overlaps
    sops_definitions = [
        # SOP-001: Water Quality Analysis (v1.0 superseded on 2025-04-30 by v2.0)
        {"sop_id": "SOP-001", "clause_id": "CLAUSE-001", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": "2025-04-30", "parameter": "Dissolved Oxygen", "minimum_value": 4.0, "maximum_value": 9.0, "canonical_unit": "mg/L", "measurement_precision": 2},
        {"sop_id": "SOP-001", "clause_id": "CLAUSE-002", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": "2025-04-30", "parameter": "pH", "minimum_value": 6.5, "maximum_value": 8.5, "canonical_unit": "pH", "measurement_precision": 2},
        {"sop_id": "SOP-001", "clause_id": "CLAUSE-003", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": "2025-04-30", "parameter": "Turbidity", "minimum_value": 0.1, "maximum_value": 4.0, "canonical_unit": "NTU", "measurement_precision": 2},
        {"sop_id": "SOP-001", "clause_id": "CLAUSE-004", "sop_version": "2.0", "effective_date": "2025-05-01", "superseded_date": None, "parameter": "Dissolved Oxygen", "minimum_value": 4.5, "maximum_value": 9.5, "canonical_unit": "mg/L", "measurement_precision": 2},
        {"sop_id": "SOP-001", "clause_id": "CLAUSE-005", "sop_version": "2.0", "effective_date": "2025-05-01", "superseded_date": None, "parameter": "pH", "minimum_value": 6.8, "maximum_value": 8.2, "canonical_unit": "pH", "measurement_precision": 2},
        {"sop_id": "SOP-001", "clause_id": "CLAUSE-006", "sop_version": "2.0", "effective_date": "2025-05-01", "superseded_date": None, "parameter": "Turbidity", "minimum_value": 0.1, "maximum_value": 3.0, "canonical_unit": "NTU", "measurement_precision": 2},

        # SOP-002: Pharmaceutical Finished Product Assay (v1.0 superseded on 2025-06-30 by v2.0)
        {"sop_id": "SOP-002", "clause_id": "CLAUSE-007", "sop_version": "1.0", "effective_date": "2024-02-01", "superseded_date": "2025-06-30", "parameter": "Active Ingredient Concentration", "minimum_value": 45.0, "maximum_value": 55.0, "canonical_unit": "mg/L", "measurement_precision": 2},
        {"sop_id": "SOP-002", "clause_id": "CLAUSE-008", "sop_version": "1.0", "effective_date": "2024-02-01", "superseded_date": "2025-06-30", "parameter": "Impurity A", "minimum_value": 0.01, "maximum_value": 0.50, "canonical_unit": "mg/L", "measurement_precision": 3},
        {"sop_id": "SOP-002", "clause_id": "CLAUSE-009", "sop_version": "1.0", "effective_date": "2024-02-01", "superseded_date": "2025-06-30", "parameter": "Assay Purity", "minimum_value": 98.0, "maximum_value": 100.0, "canonical_unit": "%", "measurement_precision": 2},
        {"sop_id": "SOP-002", "clause_id": "CLAUSE-010", "sop_version": "2.0", "effective_date": "2025-07-01", "superseded_date": None, "parameter": "Active Ingredient Concentration", "minimum_value": 47.5, "maximum_value": 52.5, "canonical_unit": "mg/L", "measurement_precision": 2},
        {"sop_id": "SOP-002", "clause_id": "CLAUSE-011", "sop_version": "2.0", "effective_date": "2025-07-01", "superseded_date": None, "parameter": "Impurity A", "minimum_value": 0.01, "maximum_value": 0.35, "canonical_unit": "mg/L", "measurement_precision": 3},
        {"sop_id": "SOP-002", "clause_id": "CLAUSE-012", "sop_version": "2.0", "effective_date": "2025-07-01", "superseded_date": None, "parameter": "Assay Purity", "minimum_value": 98.5, "maximum_value": 100.0, "canonical_unit": "%", "measurement_precision": 2},

        # SOP-003: Heavy Metal Trace Contaminants (Overlapping versions: v1.0 superseded 2025-05-31, v2.0 effective 2025-05-15)
        {"sop_id": "SOP-003", "clause_id": "CLAUSE-013", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": "2025-05-31", "parameter": "Lead Concentration", "minimum_value": 0.5, "maximum_value": 10.0, "canonical_unit": "µg/L", "measurement_precision": 2},
        {"sop_id": "SOP-003", "clause_id": "CLAUSE-014", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": "2025-05-31", "parameter": "Cadmium Concentration", "minimum_value": 0.1, "maximum_value": 2.0, "canonical_unit": "µg/L", "measurement_precision": 2},
        {"sop_id": "SOP-003", "clause_id": "CLAUSE-015", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": "2025-05-31", "parameter": "Arsenic Concentration", "minimum_value": 0.2, "maximum_value": 5.0, "canonical_unit": "µg/L", "measurement_precision": 2},
        {"sop_id": "SOP-003", "clause_id": "CLAUSE-016", "sop_version": "2.0", "effective_date": "2025-05-15", "superseded_date": None, "parameter": "Lead Concentration", "minimum_value": 0.5, "maximum_value": 8.0, "canonical_unit": "µg/L", "measurement_precision": 2},
        {"sop_id": "SOP-003", "clause_id": "CLAUSE-017", "sop_version": "2.0", "effective_date": "2025-05-15", "superseded_date": None, "parameter": "Cadmium Concentration", "minimum_value": 0.1, "maximum_value": 1.5, "canonical_unit": "µg/L", "measurement_precision": 2},
        {"sop_id": "SOP-003", "clause_id": "CLAUSE-018", "sop_version": "2.0", "effective_date": "2025-05-15", "superseded_date": None, "parameter": "Arsenic Concentration", "minimum_value": 0.2, "maximum_value": 3.5, "canonical_unit": "µg/L", "measurement_precision": 2},

        # SOP-004: Volatile Organic Compounds (v1.0 superseded on 2025-03-31 by v2.0)
        {"sop_id": "SOP-004", "clause_id": "CLAUSE-019", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": "2025-03-31", "parameter": "Ethanol Residue", "minimum_value": 10.0, "maximum_value": 500.0, "canonical_unit": "mg/L", "measurement_precision": 1},
        {"sop_id": "SOP-004", "clause_id": "CLAUSE-020", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": "2025-03-31", "parameter": "Methanol Residue", "minimum_value": 5.0, "maximum_value": 50.0, "canonical_unit": "mg/L", "measurement_precision": 2},
        {"sop_id": "SOP-004", "clause_id": "CLAUSE-021", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": "2025-03-31", "parameter": "Acetone Residue", "minimum_value": 5.0, "maximum_value": 100.0, "canonical_unit": "mg/L", "measurement_precision": 1},
        {"sop_id": "SOP-004", "clause_id": "CLAUSE-022", "sop_version": "2.0", "effective_date": "2025-04-01", "superseded_date": None, "parameter": "Ethanol Residue", "minimum_value": 10.0, "maximum_value": 400.0, "canonical_unit": "mg/L", "measurement_precision": 1},
        {"sop_id": "SOP-004", "clause_id": "CLAUSE-023", "sop_version": "2.0", "effective_date": "2025-04-01", "superseded_date": None, "parameter": "Methanol Residue", "minimum_value": 5.0, "maximum_value": 30.0, "canonical_unit": "mg/L", "measurement_precision": 2},
        {"sop_id": "SOP-004", "clause_id": "CLAUSE-024", "sop_version": "2.0", "effective_date": "2025-04-01", "superseded_date": None, "parameter": "Acetone Residue", "minimum_value": 5.0, "maximum_value": 75.0, "canonical_unit": "mg/L", "measurement_precision": 1},

        # SOP-005: Environmental Effluent Monitoring (Current v1.0)
        {"sop_id": "SOP-005", "clause_id": "CLAUSE-025", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": None, "parameter": "Chemical Oxygen Demand", "minimum_value": 10.0, "maximum_value": 120.0, "canonical_unit": "mg/L", "measurement_precision": 1},
        {"sop_id": "SOP-005", "clause_id": "CLAUSE-026", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": None, "parameter": "Nitrate Concentration", "minimum_value": 1.0, "maximum_value": 25.0, "canonical_unit": "mg/L", "measurement_precision": 2},
        {"sop_id": "SOP-005", "clause_id": "CLAUSE-027", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": None, "parameter": "Phosphate Concentration", "minimum_value": 0.2, "maximum_value": 5.0, "canonical_unit": "mg/L", "measurement_precision": 2},
        {"sop_id": "SOP-005", "clause_id": "CLAUSE-028", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": None, "parameter": "Total Suspended Solids", "minimum_value": 5.0, "maximum_value": 50.0, "canonical_unit": "mg/L", "measurement_precision": 1},

        # SOP-006: Biopharmaceutical Formulation Stability (Current v1.0)
        {"sop_id": "SOP-006", "clause_id": "CLAUSE-029", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": None, "parameter": "Protein Concentration", "minimum_value": 1.0, "maximum_value": 10.0, "canonical_unit": "g/L", "measurement_precision": 2},
        {"sop_id": "SOP-006", "clause_id": "CLAUSE-030", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": None, "parameter": "Aggregate Percentage", "minimum_value": 0.05, "maximum_value": 2.50, "canonical_unit": "%", "measurement_precision": 2},
        {"sop_id": "SOP-006", "clause_id": "CLAUSE-031", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": None, "parameter": "Formulation pH", "minimum_value": 6.2, "maximum_value": 7.4, "canonical_unit": "pH", "measurement_precision": 2},
        {"sop_id": "SOP-006", "clause_id": "CLAUSE-032", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": None, "parameter": "Osmolality", "minimum_value": 260.0, "maximum_value": 340.0, "canonical_unit": "µS/cm", "measurement_precision": 1},

        # SOP-007: Analytical Reagent Qualification (Current v1.0)
        {"sop_id": "SOP-007", "clause_id": "CLAUSE-033", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": None, "parameter": "Chloride Limit", "minimum_value": 5.0, "maximum_value": 100.0, "canonical_unit": "mg/L", "measurement_precision": 1},
        {"sop_id": "SOP-007", "clause_id": "CLAUSE-034", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": None, "parameter": "Sulfate Limit", "minimum_value": 10.0, "maximum_value": 150.0, "canonical_unit": "mg/L", "measurement_precision": 1},
        {"sop_id": "SOP-007", "clause_id": "CLAUSE-035", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": None, "parameter": "Conductivity", "minimum_value": 50.0, "maximum_value": 300.0, "canonical_unit": "µS/cm", "measurement_precision": 1},
        {"sop_id": "SOP-007", "clause_id": "CLAUSE-036", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": None, "parameter": "Absorbance at 280nm", "minimum_value": 0.100, "maximum_value": 1.000, "canonical_unit": "AU", "measurement_precision": 3},

        # SOP-008: Microbiological & Bioburden Assays (Current v1.0)
        {"sop_id": "SOP-008", "clause_id": "CLAUSE-037", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": None, "parameter": "Endotoxin Level", "minimum_value": 0.01, "maximum_value": 0.50, "canonical_unit": "mg/L", "measurement_precision": 3},
        {"sop_id": "SOP-008", "clause_id": "CLAUSE-038", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": None, "parameter": "Total Viable Count", "minimum_value": 0.0, "maximum_value": 100.0, "canonical_unit": "mg/L", "measurement_precision": 1},
        {"sop_id": "SOP-008", "clause_id": "CLAUSE-039", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": None, "parameter": "Bioburden Limit", "minimum_value": 0.0, "maximum_value": 50.0, "canonical_unit": "mg/L", "measurement_precision": 1},
        {"sop_id": "SOP-008", "clause_id": "CLAUSE-040", "sop_version": "1.0", "effective_date": "2024-01-01", "superseded_date": None, "parameter": "Moisture Content", "minimum_value": 0.5, "maximum_value": 5.0, "canonical_unit": "%", "measurement_precision": 2},
    ]

    records = sops_definitions[:count]
    return records


def generate_instruments(count: int = 25, rng: Optional[random.Random] = None) -> List[Dict[str, Any]]:
    """Generate deterministic instrument records with varying calibration dates and validity."""
    if rng is None:
        rng = random.Random(42)

    instrument_types = [
        "Spectrophotometer",
        "pH Meter",
        "Turbidimeter",
        "Conductivity Meter",
        "HPLC",
        "Atomic Absorption Spectrometer",
        "Gas Chromatograph",
        "Analytical Balance",
    ]

    records = []
    # Base simulation date anchors:
    # 10 instruments have early calibrations that expire early in 2025 (useful for expiry scenarios)
    # 15 instruments have calibrations valid throughout 2025
    for i in range(count):
        inst_id = f"INST-{i+1:03d}"
        inst_type = instrument_types[i % len(instrument_types)]

        if i < 10:
            # Calibrated in late 2024 with 90-day validity -> expires Jan-Feb 2025
            cal_day_offset = (i * 7)
            cal_date = date(2024, 10, 15) + timedelta(days=cal_day_offset)
            validity = 90
            status = "EXPIRED"
        elif i < 18:
            # Calibrated early 2025 with 180-day validity
            cal_day_offset = ((i - 10) * 12)
            cal_date = date(2025, 1, 5) + timedelta(days=cal_day_offset)
            validity = 180
            status = "CALIBRATED"
        else:
            # Calibrated early 2025 with 365-day validity
            cal_day_offset = ((i - 18) * 10)
            cal_date = date(2025, 1, 10) + timedelta(days=cal_day_offset)
            validity = 365
            status = "CALIBRATED"

        records.append({
            "instrument_id": inst_id,
            "instrument_type": inst_type,
            "calibration_date": _iso_date(cal_date),
            "validity_days": validity,
            "calibration_status": status,
        })

    return records


def generate_lots(count: int = 40, rng: Optional[random.Random] = None) -> List[Dict[str, Any]]:
    """Generate deterministic reagent lot records with varied manufacture and expiry dates."""
    if rng is None:
        rng = random.Random(42)

    reagent_names = [
        "Buffer Solution pH 7.00",
        "Potassium Chloride 0.01M",
        "Turbidity Standard 4.0 NTU",
        "Methanol HPLC Grade",
        "Acetonitrile HPLC Grade",
        "Sulfuric Acid 0.1N",
        "Sodium Hydroxide 0.1N",
        "Lead Nitrate Standard 1000 ppm",
        "Cadmium Standard 1000 ppm",
        "Bovine Serum Albumin Standard",
        "Ethanol Reference Standard",
        "Nitric Acid TraceMetal Grade",
        "Phosphate Standard Solution",
        "Hydrochloric Acid 1.0M",
        "Deionized Reagent Water",
    ]

    records = []
    for i in range(count):
        lot_id = f"LOT-{i+1:03d}"
        reagent = reagent_names[i % len(reagent_names)]

        if i < 12:
            # Lots manufactured early 2024, expired in early/mid 2025 (Feb to April 2025)
            mfg_date = date(2024, 2, 1) + timedelta(days=i * 10)
            exp_date = date(2025, 2, 15) + timedelta(days=i * 7)
        elif i < 28:
            # Lots valid throughout late 2025
            mfg_date = date(2024, 8, 1) + timedelta(days=(i - 12) * 8)
            exp_date = date(2025, 11, 30) + timedelta(days=(i - 12) * 5)
        else:
            # Lots valid well into 2026
            mfg_date = date(2025, 1, 15) + timedelta(days=(i - 28) * 10)
            exp_date = date(2026, 6, 30) + timedelta(days=(i - 28) * 15)

        records.append({
            "lot_id": lot_id,
            "reagent_name": reagent,
            "manufacture_date": _iso_date(mfg_date),
            "expiry_date": _iso_date(exp_date),
        })

    return records


def generate_samples(count: int = 150, rng: Optional[random.Random] = None) -> List[Dict[str, Any]]:
    """Generate deterministic sample records collected throughout the simulation period."""
    if rng is None:
        rng = random.Random(42)

    sample_types = [
        "Purified Water",
        "Finished Product Formulation",
        "Environmental Groundwater",
        "Industrial Effluent",
        "Raw Material Assay",
        "In-Process Intermediate",
    ]

    holding_hours_options = [24, 48, 72]

    records = []
    base_start = datetime(2025, 1, 15, 8, 0, 0)
    for i in range(count):
        sample_id = f"SMP-{i+1:04d}"
        sample_type = sample_types[i % len(sample_types)]
        max_holding = holding_hours_options[i % len(holding_hours_options)]

        # Spread collection dates deterministically across Jan-Oct 2025
        day_offset = int((i * 240) / count)
        hour_offset = (i * 3) % 8
        minute_offset = (i * 17) % 60
        collected_at = base_start + timedelta(days=day_offset, hours=hour_offset, minutes=minute_offset)

        records.append({
            "sample_id": sample_id,
            "collected_at": _iso_datetime(collected_at),
            "max_holding_hours": max_holding,
            "sample_type": sample_type,
        })

    return records


def _find_matching_instrument(clause: Dict[str, Any], instruments: List[Dict[str, Any]], require_calibrated_on: Optional[date] = None, require_expired_on: Optional[date] = None) -> Dict[str, Any]:
    param = clause["parameter"]
    compatible_types = PARAMETER_INSTRUMENT_MAP.get(param, ["Spectrophotometer"])

    candidates = [inst for inst in instruments if inst["instrument_type"] in compatible_types]
    if not candidates:
        candidates = instruments

    if require_expired_on:
        expired = []
        for inst in candidates:
            cal_dt = date.fromisoformat(inst["calibration_date"])
            expiry_dt = cal_dt + timedelta(days=inst["validity_days"])
            if expiry_dt < require_expired_on:
                expired.append(inst)
        if expired:
            return expired[0]

    if require_calibrated_on:
        valid = []
        for inst in candidates:
            cal_dt = date.fromisoformat(inst["calibration_date"])
            expiry_dt = cal_dt + timedelta(days=inst["validity_days"])
            if cal_dt <= require_calibrated_on <= expiry_dt:
                valid.append(inst)
        if valid:
            return valid[0]
        for inst in instruments:
            cal_dt = date.fromisoformat(inst["calibration_date"])
            expiry_dt = cal_dt + timedelta(days=inst["validity_days"])
            if cal_dt <= require_calibrated_on <= expiry_dt:
                return inst

    return candidates[0]


def _find_matching_lot(clause: Dict[str, Any], lots: List[Dict[str, Any]], require_valid_on: Optional[date] = None, require_expired_on: Optional[date] = None) -> Dict[str, Any]:
    param = clause["parameter"]
    keywords = PARAMETER_REAGENT_KEYWORDS.get(param, ["Deionized"])

    candidates = [lot for lot in lots if any(kw.lower() in lot["reagent_name"].lower() for kw in keywords)]
    if not candidates:
        candidates = lots

    if require_expired_on:
        expired = [lot for lot in candidates if date.fromisoformat(lot["expiry_date"]) < require_expired_on]
        if expired:
            return expired[0]

    if require_valid_on:
        valid = [lot for lot in candidates if date.fromisoformat(lot["manufacture_date"]) <= require_valid_on <= date.fromisoformat(lot["expiry_date"])]
        if valid:
            return valid[0]
        for lot in lots:
            if date.fromisoformat(lot["manufacture_date"]) <= require_valid_on <= date.fromisoformat(lot["expiry_date"]):
                return lot

    return candidates[0]


def generate_experiments(
    config: Dict[str, Any],
    sops: List[Dict[str, Any]],
    instruments: List[Dict[str, Any]],
    lots: List[Dict[str, Any]],
    samples: List[Dict[str, Any]],
    rng: Optional[random.Random] = None,
) -> List[Dict[str, Any]]:
    """Generate 800 deterministic experiment records spanning the 9 required scenario families."""
    if rng is None:
        rng = random.Random(config.get("seed", 42))

    total_experiments = config.get("experiments", 800)
    target_review_proportion = config.get("target_review_scenario_proportion", 0.25)
    total_review = int(round(total_experiments * target_review_proportion))
    total_valid = total_experiments - total_review

    # 8 review scenario families
    review_families = [
        "Calibration expiry",
        "Incorrect SOP version",
        "Expired reagent lot",
        "Sample holding-time violation",
        "Measurement outside SOP limits",
        "Unit conversion",
        "Missing evidence",
        "Conflicting evidence",
    ]

    # Distribute review experiments evenly across the 8 review families
    counts_per_family = {}
    base_per_review = total_review // len(review_families)
    remainder = total_review % len(review_families)
    for i, fam in enumerate(review_families):
        counts_per_family[fam] = base_per_review + (1 if i < remainder else 0)
    counts_per_family["Valid experiments"] = total_valid

    # Helper indices for lookup
    active_clauses = [c for c in sops if c["superseded_date"] is None]
    superseded_clauses = [c for c in sops if c["superseded_date"] is not None]

    raw_experiments: List[Dict[str, Any]] = []

    # -------------------------------------------------------------
    # 1. Calibration expiry (25 experiments)
    # -------------------------------------------------------------
    for i in range(counts_per_family["Calibration expiry"]):
        clause = active_clauses[i % len(active_clauses)]
        sample = samples[i % len(samples)]
        inst = [inst for inst in instruments if inst["calibration_status"] == "EXPIRED"][i % 10]
        cal_dt = date.fromisoformat(inst["calibration_date"])
        exp_dt = cal_dt + timedelta(days=inst["validity_days"])
        # Set run date strictly after calibration expiry
        run_d = exp_dt + timedelta(days=rng.randint(15, 60))
        sample_col = datetime(run_d.year, run_d.month, run_d.day, 8, 0, 0)
        ana_dt = sample_col + timedelta(hours=min(sample["max_holding_hours"] - 2, 4))
        lot = _find_matching_lot(clause, lots, require_valid_on=run_d)

        # Compliant measurement within limits
        min_v = clause["minimum_value"]
        max_v = clause["maximum_value"]
        val = round(min_v + (max_v - min_v) * rng.uniform(0.2, 0.8), clause["measurement_precision"])
        unc = round(max(val * 0.01, 0.01), clause["measurement_precision"])

        raw_experiments.append({
            "scenario_family": "Calibration expiry",
            "run_date": _iso_date(run_d),
            "collected_at": sample["collected_at"],
            "analyzed_at": _iso_datetime(ana_dt),
            "sop_id": clause["sop_id"],
            "sop_version": clause["sop_version"],
            "clause_id": clause["clause_id"],
            "instrument_id": inst["instrument_id"],
            "lot_id": lot["lot_id"],
            "sample_id": sample["sample_id"],
            "measured_value": val,
            "measurement_unit": clause["canonical_unit"],
            "measurement_uncertainty": unc,
        })

    # -------------------------------------------------------------
    # 2. Incorrect SOP version (25 experiments)
    # -------------------------------------------------------------
    for i in range(counts_per_family["Incorrect SOP version"]):
        # Pick superseded clause
        clause = superseded_clauses[i % len(superseded_clauses)]
        sample = samples[(i + 25) % len(samples)]
        sup_d = date.fromisoformat(clause["superseded_date"])

        # Run date is strictly AFTER the clause was superseded
        run_d = sup_d + timedelta(days=rng.randint(15, 60))
        sample_col = datetime(run_d.year, run_d.month, run_d.day, 8, 0, 0)
        ana_dt = sample_col + timedelta(hours=4)

        inst = _find_matching_instrument(clause, instruments, require_calibrated_on=run_d)
        lot = _find_matching_lot(clause, lots, require_valid_on=run_d)

        min_v = clause["minimum_value"]
        max_v = clause["maximum_value"]
        val = round(min_v + (max_v - min_v) * rng.uniform(0.2, 0.8), clause["measurement_precision"])
        unc = round(max(val * 0.01, 0.01), clause["measurement_precision"])

        raw_experiments.append({
            "scenario_family": "Incorrect SOP version",
            "run_date": _iso_date(run_d),
            "collected_at": _iso_datetime(sample_col),
            "analyzed_at": _iso_datetime(ana_dt),
            "sop_id": clause["sop_id"],
            "sop_version": clause["sop_version"],
            "clause_id": clause["clause_id"],
            "instrument_id": inst["instrument_id"],
            "lot_id": lot["lot_id"],
            "sample_id": sample["sample_id"],
            "measured_value": val,
            "measurement_unit": clause["canonical_unit"],
            "measurement_uncertainty": unc,
        })

    # -------------------------------------------------------------
    # 3. Expired reagent lot (25 experiments)
    # -------------------------------------------------------------
    for i in range(counts_per_family["Expired reagent lot"]):
        clause = active_clauses[(i + 5) % len(active_clauses)]
        sample = samples[(i + 50) % len(samples)]

        # Find expired lot
        expired_lot = [lot for lot in lots if date.fromisoformat(lot["expiry_date"]) < date(2025, 5, 1)][i % 10]
        lot_exp_d = date.fromisoformat(expired_lot["expiry_date"])

        # Run date is AFTER lot expiry
        run_d = lot_exp_d + timedelta(days=rng.randint(10, 40))
        sample_col = datetime(run_d.year, run_d.month, run_d.day, 8, 30, 0)
        ana_dt = sample_col + timedelta(hours=3)

        inst = _find_matching_instrument(clause, instruments, require_calibrated_on=run_d)

        min_v = clause["minimum_value"]
        max_v = clause["maximum_value"]
        val = round(min_v + (max_v - min_v) * rng.uniform(0.2, 0.8), clause["measurement_precision"])
        unc = round(max(val * 0.01, 0.01), clause["measurement_precision"])

        raw_experiments.append({
            "scenario_family": "Expired reagent lot",
            "run_date": _iso_date(run_d),
            "collected_at": _iso_datetime(sample_col),
            "analyzed_at": _iso_datetime(ana_dt),
            "sop_id": clause["sop_id"],
            "sop_version": clause["sop_version"],
            "clause_id": clause["clause_id"],
            "instrument_id": inst["instrument_id"],
            "lot_id": expired_lot["lot_id"],
            "sample_id": sample["sample_id"],
            "measured_value": val,
            "measurement_unit": clause["canonical_unit"],
            "measurement_uncertainty": unc,
        })

    # -------------------------------------------------------------
    # 4. Sample holding-time violation (25 experiments)
    # -------------------------------------------------------------
    for i in range(counts_per_family["Sample holding-time violation"]):
        clause = active_clauses[(i + 10) % len(active_clauses)]
        sample = samples[(i + 75) % len(samples)]
        max_h = sample["max_holding_hours"]

        sample_col = datetime.strptime(sample["collected_at"], "%Y-%m-%dT%H:%M:%SZ")
        # Exceed holding hours by 12 to 48 hours
        excess_hours = max_h + rng.randint(12, 48)
        ana_dt = sample_col + timedelta(hours=excess_hours)
        run_d = ana_dt.date()

        inst = _find_matching_instrument(clause, instruments, require_calibrated_on=run_d)
        lot = _find_matching_lot(clause, lots, require_valid_on=run_d)

        min_v = clause["minimum_value"]
        max_v = clause["maximum_value"]
        val = round(min_v + (max_v - min_v) * rng.uniform(0.2, 0.8), clause["measurement_precision"])
        unc = round(max(val * 0.01, 0.01), clause["measurement_precision"])

        raw_experiments.append({
            "scenario_family": "Sample holding-time violation",
            "run_date": _iso_date(run_d),
            "collected_at": sample["collected_at"],
            "analyzed_at": _iso_datetime(ana_dt),
            "sop_id": clause["sop_id"],
            "sop_version": clause["sop_version"],
            "clause_id": clause["clause_id"],
            "instrument_id": inst["instrument_id"],
            "lot_id": lot["lot_id"],
            "sample_id": sample["sample_id"],
            "measured_value": val,
            "measurement_unit": clause["canonical_unit"],
            "measurement_uncertainty": unc,
        })

    # -------------------------------------------------------------
    # 5. Measurement outside SOP limits (25 experiments)
    # -------------------------------------------------------------
    for i in range(counts_per_family["Measurement outside SOP limits"]):
        clause = active_clauses[(i + 15) % len(active_clauses)]
        sample = samples[(i + 100) % len(samples)]
        sample_col = datetime.strptime(sample["collected_at"], "%Y-%m-%dT%H:%M:%SZ")
        ana_dt = sample_col + timedelta(hours=4)
        run_d = ana_dt.date()

        inst = _find_matching_instrument(clause, instruments, require_calibrated_on=run_d)
        lot = _find_matching_lot(clause, lots, require_valid_on=run_d)

        min_v = clause["minimum_value"]
        max_v = clause["maximum_value"]
        span = max_v - min_v

        # 50% above max, 50% below min
        if i % 2 == 0:
            val = round(max_v + max(span * rng.uniform(0.15, 0.45), 0.5), clause["measurement_precision"])
        else:
            if min_v > 0.0:
                val = round(max(0.0, min_v - max(span * rng.uniform(0.15, 0.45), 0.5)), clause["measurement_precision"])
                if val >= min_v:
                    val = round(min_v - 0.5, clause["measurement_precision"])
            else:
                val = -round(max(span * rng.uniform(0.15, 0.45), 0.5), clause["measurement_precision"])

        unc = round(max(val * 0.01, 0.01), clause["measurement_precision"])

        raw_experiments.append({
            "scenario_family": "Measurement outside SOP limits",
            "run_date": _iso_date(run_d),
            "collected_at": sample["collected_at"],
            "analyzed_at": _iso_datetime(ana_dt),
            "sop_id": clause["sop_id"],
            "sop_version": clause["sop_version"],
            "clause_id": clause["clause_id"],
            "instrument_id": inst["instrument_id"],
            "lot_id": lot["lot_id"],
            "sample_id": sample["sample_id"],
            "measured_value": val,
            "measurement_unit": clause["canonical_unit"],
            "measurement_uncertainty": unc,
        })

    # -------------------------------------------------------------
    # 6. Unit conversion (25 experiments)
    # -------------------------------------------------------------
    # Use concentration clauses whose canonical unit is mg/L or g/L
    unit_clauses = [c for c in active_clauses if c["canonical_unit"] in ("mg/L", "g/L")]
    for i in range(counts_per_family["Unit conversion"]):
        clause = unit_clauses[i % len(unit_clauses)]
        sample = samples[(i + 120) % len(samples)]
        sample_col = datetime.strptime(sample["collected_at"], "%Y-%m-%dT%H:%M:%SZ")
        ana_dt = sample_col + timedelta(hours=3)
        run_d = ana_dt.date()

        inst = _find_matching_instrument(clause, instruments, require_calibrated_on=run_d)
        lot = _find_matching_lot(clause, lots, require_valid_on=run_d)

        min_v = clause["minimum_value"]
        max_v = clause["maximum_value"]
        nominal_canon = min_v + (max_v - min_v) * rng.uniform(0.3, 0.7)

        # Convert to alternate valid unit (g/L or µg/L when canonical is mg/L)
        if clause["canonical_unit"] == "mg/L":
            if i % 2 == 0:
                alt_unit = "g/L"
                val = round(nominal_canon / 1000.0, 4)
            else:
                alt_unit = "µg/L"
                val = round(nominal_canon * 1000.0, 1)
        else:  # canonical is g/L
            alt_unit = "mg/L"
            val = round(nominal_canon * 1000.0, 1)

        unc = round(max(val * 0.015, 0.001), 3)

        raw_experiments.append({
            "scenario_family": "Unit conversion",
            "run_date": _iso_date(run_d),
            "collected_at": sample["collected_at"],
            "analyzed_at": _iso_datetime(ana_dt),
            "sop_id": clause["sop_id"],
            "sop_version": clause["sop_version"],
            "clause_id": clause["clause_id"],
            "instrument_id": inst["instrument_id"],
            "lot_id": lot["lot_id"],
            "sample_id": sample["sample_id"],
            "measured_value": val,
            "measurement_unit": alt_unit,
            "measurement_uncertainty": unc,
        })

    # -------------------------------------------------------------
    # 7. Missing evidence (25 experiments)
    # -------------------------------------------------------------
    for i in range(counts_per_family["Missing evidence"]):
        clause = active_clauses[(i + 2) % len(active_clauses)]
        sample = samples[(i + 10) % len(samples)]
        sample_col = datetime.strptime(sample["collected_at"], "%Y-%m-%dT%H:%M:%SZ")
        ana_dt = sample_col + timedelta(hours=3)
        run_d = ana_dt.date()

        inst = _find_matching_instrument(clause, instruments, require_calibrated_on=run_d)
        lot = _find_matching_lot(clause, lots, require_valid_on=run_d)

        inst_id = inst["instrument_id"]
        lot_id = lot["lot_id"]
        sample_id = sample["sample_id"]

        # Intentionally omit one key piece of evidence
        mod = i % 3
        if mod == 0:
            inst_id = None
        elif mod == 1:
            lot_id = None
        else:
            sample_id = None

        min_v = clause["minimum_value"]
        max_v = clause["maximum_value"]
        val = round(min_v + (max_v - min_v) * rng.uniform(0.2, 0.8), clause["measurement_precision"])
        unc = round(max(val * 0.01, 0.01), clause["measurement_precision"])

        raw_experiments.append({
            "scenario_family": "Missing evidence",
            "run_date": _iso_date(run_d),
            "collected_at": sample["collected_at"],
            "analyzed_at": _iso_datetime(ana_dt),
            "sop_id": clause["sop_id"],
            "sop_version": clause["sop_version"],
            "clause_id": clause["clause_id"],
            "instrument_id": inst_id,
            "lot_id": lot_id,
            "sample_id": sample_id,
            "measured_value": val,
            "measurement_unit": clause["canonical_unit"],
            "measurement_uncertainty": unc,
        })

    # -------------------------------------------------------------
    # 8. Conflicting evidence (25 experiments)
    # -------------------------------------------------------------
    for i in range(counts_per_family["Conflicting evidence"]):
        clause = active_clauses[(i + 7) % len(active_clauses)]
        sample = samples[(i + 35) % len(samples)]
        sample_col = datetime.strptime(sample["collected_at"], "%Y-%m-%dT%H:%M:%SZ")
        ana_dt = sample_col + timedelta(hours=4)
        run_d = ana_dt.date()

        inst = _find_matching_instrument(clause, instruments, require_calibrated_on=run_d)
        lot = _find_matching_lot(clause, lots, require_valid_on=run_d)

        sop_id_val = clause["sop_id"]
        clause_id_val = clause["clause_id"]
        inst_id_val = inst["instrument_id"]
        col_at_val = sample["collected_at"]
        ana_at_val = _iso_datetime(ana_dt)

        conflict_type = i % 3
        if conflict_type == 0:
            # Timestamp paradox: analyzed_at precedes collected_at
            ana_at_val = _iso_datetime(sample_col - timedelta(hours=3))
        elif conflict_type == 1:
            # Instrument mismatch: measurement performed on incompatible instrument type
            incompatibles = [inst_rec for inst_rec in instruments if inst_rec["instrument_type"] not in PARAMETER_INSTRUMENT_MAP.get(clause["parameter"], [])]
            if incompatibles:
                inst_id_val = incompatibles[0]["instrument_id"]
        else:
            # Clause/SOP mismatch: clause_id from SOP-005 paired with SOP-001
            other_clause = [c for c in active_clauses if c["sop_id"] != clause["sop_id"]][0]
            clause_id_val = other_clause["clause_id"]

        min_v = clause["minimum_value"]
        max_v = clause["maximum_value"]
        val = round(min_v + (max_v - min_v) * rng.uniform(0.2, 0.8), clause["measurement_precision"])
        unc = round(max(val * 0.01, 0.01), clause["measurement_precision"])

        raw_experiments.append({
            "scenario_family": "Conflicting evidence",
            "run_date": _iso_date(run_d),
            "collected_at": col_at_val,
            "analyzed_at": ana_at_val,
            "sop_id": sop_id_val,
            "sop_version": clause["sop_version"],
            "clause_id": clause_id_val,
            "instrument_id": inst_id_val,
            "lot_id": lot["lot_id"],
            "sample_id": sample["sample_id"],
            "measured_value": val,
            "measurement_unit": clause["canonical_unit"],
            "measurement_uncertainty": unc,
        })

    # -------------------------------------------------------------
    # 9. Valid experiments (600 experiments)
    # -------------------------------------------------------------
    for i in range(counts_per_family["Valid experiments"]):
        sample = samples[i % len(samples)]
        sample_col = datetime.strptime(sample["collected_at"], "%Y-%m-%dT%H:%M:%SZ")

        # Holding time is strictly compliant
        hold_time = min(sample["max_holding_hours"] - 2, 4 + (i % 16))
        ana_dt = sample_col + timedelta(hours=max(1, hold_time))
        run_d = ana_dt.date()

        # Find applicable SOP clause for run_d
        applicable_clauses = [
            c for c in sops
            if date.fromisoformat(c["effective_date"]) <= run_d
            and (c["superseded_date"] is None or run_d < date.fromisoformat(c["superseded_date"]))
            and not (c["sop_id"] == "SOP-003" and date(2025, 5, 15) <= run_d <= date(2025, 5, 31))
        ]
        clause = applicable_clauses[i % len(applicable_clauses)]

        inst = _find_matching_instrument(clause, instruments, require_calibrated_on=run_d)
        lot = _find_matching_lot(clause, lots, require_valid_on=run_d)

        min_v = clause["minimum_value"]
        max_v = clause["maximum_value"]
        # Measurement strictly within SOP limits
        val = round(min_v + (max_v - min_v) * rng.uniform(0.25, 0.75), clause["measurement_precision"])
        unc = round(max(val * 0.012, 0.01), clause["measurement_precision"])

        raw_experiments.append({
            "scenario_family": "Valid experiments",
            "run_date": _iso_date(run_d),
            "collected_at": sample["collected_at"],
            "analyzed_at": _iso_datetime(ana_dt),
            "sop_id": clause["sop_id"],
            "sop_version": clause["sop_version"],
            "clause_id": clause["clause_id"],
            "instrument_id": inst["instrument_id"],
            "lot_id": lot["lot_id"],
            "sample_id": sample["sample_id"],
            "measured_value": val,
            "measurement_unit": clause["canonical_unit"],
            "measurement_uncertainty": unc,
        })

    # Deterministic chronological sort and stable experiment ID assignment
    raw_experiments.sort(key=lambda r: (r["run_date"], r["analyzed_at"], r["scenario_family"], r["clause_id"]))

    final_experiments = []
    for idx, exp in enumerate(raw_experiments):
        exp_record = {"experiment_id": f"EXP-{idx+1:04d}", **exp}
        final_experiments.append(exp_record)

    return final_experiments


def generate_all(
    config: Optional[Dict[str, Any]] = None,
    config_path: str = "config/simulator_config.json",
    output_dir: str = "data/raw",
) -> Dict[str, Any]:
    """Execute full dataset generation pipeline and return metadata."""
    if config is None:
        config = load_config(config_path)

    seed = config.get("seed", 42)
    rng = random.Random(seed)

    sop_count = config.get("sop_clauses", 40)
    inst_count = config.get("instruments", 25)
    lot_count = config.get("lots", 40)
    sample_count = config.get("samples", 150)

    # 1. Generate individual datasets deterministically
    sops = generate_sops(sop_count, rng)
    instruments = generate_instruments(inst_count, rng)
    lots = generate_lots(lot_count, rng)
    samples = generate_samples(sample_count, rng)
    experiments = generate_experiments(config, sops, instruments, lots, samples, rng)

    # 2. Output filepaths
    os.makedirs(output_dir, exist_ok=True)
    paths = {
        "sops": os.path.join(output_dir, "sops_v1.jsonl"),
        "instruments": os.path.join(output_dir, "instruments_v1.jsonl"),
        "lots": os.path.join(output_dir, "lots_v1.jsonl"),
        "samples": os.path.join(output_dir, "samples_v1.jsonl"),
        "experiments": os.path.join(output_dir, "experiments_v1.jsonl"),
        "runs_csv": os.path.join(output_dir, "runs_v1.csv"),
    }

    # 3. Save files
    save_jsonl(sops, paths["sops"])
    save_jsonl(instruments, paths["instruments"])
    save_jsonl(lots, paths["lots"])
    save_jsonl(samples, paths["samples"])
    save_jsonl(experiments, paths["experiments"])
    save_csv(experiments, paths["runs_csv"], EXPERIMENT_FIELDNAMES)

    # 4. Scenario family breakdown
    scenario_counts: Dict[str, int] = {}
    for exp in experiments:
        fam = exp["scenario_family"]
        scenario_counts[fam] = scenario_counts.get(fam, 0) + 1

    total_exp = len(experiments)
    review_exp = total_exp - scenario_counts.get("Valid experiments", 0)
    review_prop = round(review_exp / total_exp, 4) if total_exp > 0 else 0.0

    # 5. Content hashes
    hashes = compute_dataset_hashes(paths)

    metadata = {
        "seed": seed,
        "configuration": config,
        "generator_version": GENERATOR_VERSION,
        "record_counts": {
            "sops": len(sops),
            "instruments": len(instruments),
            "lots": len(lots),
            "samples": len(samples),
            "experiments": len(experiments),
            "runs_csv": len(experiments),
        },
        "scenario_family_counts": scenario_counts,
        "review_scenario_proportion": review_prop,
        "content_hashes": hashes,
    }

    metadata_path = os.path.join(output_dir, "metadata.json")
    import json
    with open(metadata_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    return metadata

