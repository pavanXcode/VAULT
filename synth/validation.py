"""Comprehensive dataset validation routines for VAULT.

Validates:
- JSONL and CSV syntax
- Required fields across all datasets
- Unique identifiers
- Valid ISO dates and timestamps
- Foreign key relationships (strict for Valid experiments, categorized for review scenarios)
- SOP version consistency
- Supported units
- Measurement values and uncertainty
- Ground-truth ledger completeness and schema
- Verdict and reason-code consistency
- Abstention consistency
- Evidence references
"""

import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from synth.units import CANONICAL_UNITS, SUPPORTED_CONCENTRATION_UNITS
from synth.utils import read_csv, read_jsonl

# All recognized measurement units in VAULT
ALL_RECOGNIZED_UNITS: Set[str] = CANONICAL_UNITS | SUPPORTED_CONCENTRATION_UNITS | {"ug/L", "μg/L"}

# Expected schemas for raw datasets
SOP_REQUIRED_FIELDS = {
    "sop_id",
    "clause_id",
    "sop_version",
    "effective_date",
    "superseded_date",
    "parameter",
    "minimum_value",
    "maximum_value",
    "canonical_unit",
    "measurement_precision",
}

INSTRUMENT_REQUIRED_FIELDS = {
    "instrument_id",
    "instrument_type",
    "calibration_date",
    "validity_days",
    "calibration_status",
}

LOT_REQUIRED_FIELDS = {
    "lot_id",
    "reagent_name",
    "manufacture_date",
    "expiry_date",
}

SAMPLE_REQUIRED_FIELDS = {
    "sample_id",
    "collected_at",
    "max_holding_hours",
    "sample_type",
}

EXPERIMENT_REQUIRED_FIELDS = {
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
}

LEDGER_REQUIRED_FIELDS = {
    "experiment_id",
    "scenario_family",
    "verdict",
    "reason_codes",
    "abstain",
    "checks",
    "evidence",
    "measurement",
}

LEDGER_REQUIRED_CHECKS = {
    "sop",
    "calibration",
    "lot",
    "holding_time",
    "measurement",
}


def _is_valid_iso_date(val: Any) -> bool:
    """Return True if val is a valid ISO date string YYYY-MM-DD."""
    if not isinstance(val, str):
        return False
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", val.strip()):
        return False
    try:
        date.fromisoformat(val.strip())
        return True
    except ValueError:
        return False


def _is_valid_iso_datetime(val: Any) -> bool:
    """Return True if val is a valid ISO datetime string."""
    if not isinstance(val, str):
        return False
    val_clean = val.strip()
    if val_clean.endswith("Z"):
        val_clean = val_clean[:-1] + "+00:00"
    try:
        datetime.fromisoformat(val_clean)
        return True
    except ValueError:
        return False


def validate_jsonl_syntax(filepath: str) -> Dict[str, Any]:
    """Validate JSONL file readability and syntax of each line."""
    result: Dict[str, Any] = {
        "filepath": filepath,
        "valid": True,
        "line_count": 0,
        "errors": [],
    }
    if not os.path.exists(filepath):
        result["valid"] = False
        result["errors"].append(f"File not found: {filepath}")
        return result

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f, start=1):
                line_str = line.strip()
                if not line_str:
                    continue
                result["line_count"] += 1
                try:
                    json.loads(line_str)
                except json.JSONDecodeError as jde:
                    result["valid"] = False
                    result["errors"].append(f"Line {idx}: JSONDecodeError - {str(jde)}")
    except Exception as exc:
        result["valid"] = False
        result["errors"].append(f"Unable to read file: {str(exc)}")

    return result


def validate_csv_syntax(filepath: str) -> Dict[str, Any]:
    """Validate CSV file readability and row consistency."""
    result: Dict[str, Any] = {
        "filepath": filepath,
        "valid": True,
        "row_count": 0,
        "headers": [],
        "errors": [],
    }
    if not os.path.exists(filepath):
        result["valid"] = False
        result["errors"].append(f"File not found: {filepath}")
        return result

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader, None)
            if headers is None:
                result["valid"] = False
                result["errors"].append("CSV is empty or missing header line.")
                return result
            result["headers"] = headers
            header_len = len(headers)
            for idx, row in enumerate(reader, start=2):
                result["row_count"] += 1
                if len(row) != header_len:
                    result["valid"] = False
                    result["errors"].append(
                        f"Line {idx}: row length {len(row)} does not match header length {header_len}."
                    )
    except Exception as exc:
        result["valid"] = False
        result["errors"].append(f"Unable to read CSV file: {str(exc)}")

    return result


def validate_sops_dataset(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate SOPs dataset fields, uniqueness, dates, and limits."""
    result: Dict[str, Any] = {"dataset": "sops", "valid": True, "record_count": len(records), "errors": [], "warnings": []}
    clause_ids: Set[str] = set()

    for idx, rec in enumerate(records):
        missing = SOP_REQUIRED_FIELDS - set(rec.keys())
        if missing:
            result["valid"] = False
            result["errors"].append(f"Record {idx} ({rec.get('clause_id')}): missing required fields: {sorted(list(missing))}")

        cid = rec.get("clause_id")
        if not cid:
            result["valid"] = False
            result["errors"].append(f"Record {idx}: empty or null clause_id.")
        elif cid in clause_ids:
            result["valid"] = False
            result["errors"].append(f"Record {idx}: duplicate clause_id '{cid}'.")
        else:
            clause_ids.add(cid)

        eff = rec.get("effective_date")
        if not _is_valid_iso_date(eff):
            result["valid"] = False
            result["errors"].append(f"Record {idx} ({cid}): invalid effective_date '{eff}'.")

        sup = rec.get("superseded_date")
        if sup is not None and not _is_valid_iso_date(sup):
            result["valid"] = False
            result["errors"].append(f"Record {idx} ({cid}): invalid superseded_date '{sup}'.")

        if eff and sup and _is_valid_iso_date(eff) and _is_valid_iso_date(sup):
            if date.fromisoformat(eff) > date.fromisoformat(sup):
                result["valid"] = False
                result["errors"].append(f"Record {idx} ({cid}): effective_date '{eff}' is after superseded_date '{sup}'.")

        min_val = rec.get("minimum_value")
        max_val = rec.get("maximum_value")
        if min_val is not None and max_val is not None:
            if float(min_val) > float(max_val):
                result["valid"] = False
                result["errors"].append(f"Record {idx} ({cid}): minimum_value ({min_val}) > maximum_value ({max_val}).")

        prec = rec.get("measurement_precision")
        if prec is not None and (not isinstance(prec, int) or prec < 0):
            result["valid"] = False
            result["errors"].append(f"Record {idx} ({cid}): invalid measurement_precision '{prec}'.")

        unit = rec.get("canonical_unit")
        if unit not in ALL_RECOGNIZED_UNITS:
            result["warnings"].append(f"Record {idx} ({cid}): canonical_unit '{unit}' not in standard unit list.")

    return result


def validate_instruments_dataset(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate instruments dataset fields, uniqueness, dates, and validity days."""
    result: Dict[str, Any] = {"dataset": "instruments", "valid": True, "record_count": len(records), "errors": [], "warnings": []}
    inst_ids: Set[str] = set()

    for idx, rec in enumerate(records):
        missing = INSTRUMENT_REQUIRED_FIELDS - set(rec.keys())
        if missing:
            result["valid"] = False
            result["errors"].append(f"Record {idx} ({rec.get('instrument_id')}): missing required fields: {sorted(list(missing))}")

        iid = rec.get("instrument_id")
        if not iid:
            result["valid"] = False
            result["errors"].append(f"Record {idx}: empty or null instrument_id.")
        elif iid in inst_ids:
            result["valid"] = False
            result["errors"].append(f"Record {idx}: duplicate instrument_id '{iid}'.")
        else:
            inst_ids.add(iid)

        cal_date = rec.get("calibration_date")
        if not _is_valid_iso_date(cal_date):
            result["valid"] = False
            result["errors"].append(f"Record {idx} ({iid}): invalid calibration_date '{cal_date}'.")

        vdays = rec.get("validity_days")
        if vdays is None or not isinstance(vdays, int) or vdays <= 0:
            result["valid"] = False
            result["errors"].append(f"Record {idx} ({iid}): invalid validity_days '{vdays}'.")

        cstatus = rec.get("calibration_status")
        if cstatus not in ("VALID", "CALIBRATED", "EXPIRED", "PENDING"):
            result["warnings"].append(f"Record {idx} ({iid}): unexpected calibration_status '{cstatus}'.")

    return result


def validate_lots_dataset(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate reagent lots dataset fields, uniqueness, dates."""
    result: Dict[str, Any] = {"dataset": "lots", "valid": True, "record_count": len(records), "errors": [], "warnings": []}
    lot_ids: Set[str] = set()

    for idx, rec in enumerate(records):
        missing = LOT_REQUIRED_FIELDS - set(rec.keys())
        if missing:
            result["valid"] = False
            result["errors"].append(f"Record {idx} ({rec.get('lot_id')}): missing required fields: {sorted(list(missing))}")

        lid = rec.get("lot_id")
        if not lid:
            result["valid"] = False
            result["errors"].append(f"Record {idx}: empty or null lot_id.")
        elif lid in lot_ids:
            result["valid"] = False
            result["errors"].append(f"Record {idx}: duplicate lot_id '{lid}'.")
        else:
            lot_ids.add(lid)

        mfg = rec.get("manufacture_date")
        exp = rec.get("expiry_date")
        if not _is_valid_iso_date(mfg):
            result["valid"] = False
            result["errors"].append(f"Record {idx} ({lid}): invalid manufacture_date '{mfg}'.")
        if not _is_valid_iso_date(exp):
            result["valid"] = False
            result["errors"].append(f"Record {idx} ({lid}): invalid expiry_date '{exp}'.")

        if mfg and exp and _is_valid_iso_date(mfg) and _is_valid_iso_date(exp):
            if date.fromisoformat(mfg) > date.fromisoformat(exp):
                result["valid"] = False
                result["errors"].append(f"Record {idx} ({lid}): manufacture_date '{mfg}' > expiry_date '{exp}'.")

    return result


def validate_samples_dataset(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate samples dataset fields, uniqueness, timestamps, holding hours."""
    result: Dict[str, Any] = {"dataset": "samples", "valid": True, "record_count": len(records), "errors": [], "warnings": []}
    sample_ids: Set[str] = set()

    for idx, rec in enumerate(records):
        missing = SAMPLE_REQUIRED_FIELDS - set(rec.keys())
        if missing:
            result["valid"] = False
            result["errors"].append(f"Record {idx} ({rec.get('sample_id')}): missing required fields: {sorted(list(missing))}")

        sid = rec.get("sample_id")
        if not sid:
            result["valid"] = False
            result["errors"].append(f"Record {idx}: empty or null sample_id.")
        elif sid in sample_ids:
            result["valid"] = False
            result["errors"].append(f"Record {idx}: duplicate sample_id '{sid}'.")
        else:
            sample_ids.add(sid)

        col = rec.get("collected_at")
        if not _is_valid_iso_datetime(col):
            result["valid"] = False
            result["errors"].append(f"Record {idx} ({sid}): invalid collected_at timestamp '{col}'.")

        max_h = rec.get("max_holding_hours")
        if max_h is None or not (isinstance(max_h, (int, float))) or max_h <= 0:
            result["valid"] = False
            result["errors"].append(f"Record {idx} ({sid}): invalid max_holding_hours '{max_h}'.")

    return result


def validate_experiments_dataset(
    experiments: List[Dict[str, Any]],
    sops: List[Dict[str, Any]],
    instruments: List[Dict[str, Any]],
    lots: List[Dict[str, Any]],
    samples: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Validate experiments dataset fields, uniqueness, timestamps, units, measurements, and foreign keys."""
    result: Dict[str, Any] = {
        "dataset": "experiments",
        "valid": True,
        "record_count": len(experiments),
        "errors": [],
        "warnings": [],
        "foreign_key_summary": {
            "valid_experiments_violations": 0,
            "intentional_missing_ids": 0,
            "intentional_mismatched_ids": 0,
        },
    }

    # Build reference catalogs
    clause_catalog = {s["clause_id"]: s for s in sops if s.get("clause_id")}
    sop_clause_map: Dict[Tuple[str, str], Set[str]] = {}
    for s in sops:
        key = (s.get("sop_id", ""), s.get("sop_version", ""))
        sop_clause_map.setdefault(key, set()).add(s.get("clause_id", ""))

    inst_catalog = {i["instrument_id"] for i in instruments if i.get("instrument_id")}
    lot_catalog = {l["lot_id"] for l in lots if l.get("lot_id")}
    sample_catalog = {s["sample_id"] for s in samples if s.get("sample_id")}

    exp_ids: Set[str] = set()

    for idx, exp in enumerate(experiments):
        eid = exp.get("experiment_id")
        fam = exp.get("scenario_family", "")

        # Required fields
        missing = EXPERIMENT_REQUIRED_FIELDS - set(exp.keys())
        if missing:
            result["valid"] = False
            result["errors"].append(f"Experiment {idx} ({eid}): missing required fields: {sorted(list(missing))}")

        # Unique experiment_id
        if not eid:
            result["valid"] = False
            result["errors"].append(f"Experiment {idx}: empty or null experiment_id.")
        elif eid in exp_ids:
            result["valid"] = False
            result["errors"].append(f"Experiment {idx}: duplicate experiment_id '{eid}'.")
        else:
            exp_ids.add(eid)

        # Valid dates / timestamps
        run_d = exp.get("run_date")
        if not _is_valid_iso_date(run_d):
            result["valid"] = False
            result["errors"].append(f"Experiment {eid}: invalid run_date '{run_d}'.")

        col_at = exp.get("collected_at")
        if col_at is not None and not _is_valid_iso_datetime(col_at):
            result["valid"] = False
            result["errors"].append(f"Experiment {eid}: invalid collected_at '{col_at}'.")

        ana_at = exp.get("analyzed_at")
        if ana_at is not None and not _is_valid_iso_datetime(ana_at):
            result["valid"] = False
            result["errors"].append(f"Experiment {eid}: invalid analyzed_at '{ana_at}'.")

        # Supported units
        unit = exp.get("measurement_unit")
        if unit not in ALL_RECOGNIZED_UNITS:
            result["warnings"].append(f"Experiment {eid}: unit '{unit}' is outside recognized laboratory units.")

        # Measurement values & uncertainty
        val = exp.get("measured_value")
        if val is not None and not isinstance(val, (int, float, Decimal)):
            result["valid"] = False
            result["errors"].append(f"Experiment {eid}: non-numeric measured_value '{val}'.")

        unc = exp.get("measurement_uncertainty")
        if unc is not None:
            if not isinstance(unc, (int, float, Decimal)) or unc < 0:
                result["valid"] = False
                result["errors"].append(f"Experiment {eid}: invalid or negative measurement_uncertainty '{unc}'.")

        # Foreign Key & Referential Integrity
        cid = exp.get("clause_id")
        iid = exp.get("instrument_id")
        lid = exp.get("lot_id")
        sid = exp.get("sample_id")
        sop_id = exp.get("sop_id")
        sop_ver = exp.get("sop_version")

        is_valid_family = (fam == "Valid experiments")

        # For Valid experiments: strict referential integrity
        if is_valid_family:
            if not cid or cid not in clause_catalog:
                result["valid"] = False
                result["foreign_key_summary"]["valid_experiments_violations"] += 1
                result["errors"].append(f"Valid experiment {eid}: clause_id '{cid}' not found in SOPs catalog.")
            if not iid or iid not in inst_catalog:
                result["valid"] = False
                result["foreign_key_summary"]["valid_experiments_violations"] += 1
                result["errors"].append(f"Valid experiment {eid}: instrument_id '{iid}' not found in instruments catalog.")
            if not lid or lid not in lot_catalog:
                result["valid"] = False
                result["foreign_key_summary"]["valid_experiments_violations"] += 1
                result["errors"].append(f"Valid experiment {eid}: lot_id '{lid}' not found in lots catalog.")
            if not sid or sid not in sample_catalog:
                result["valid"] = False
                result["foreign_key_summary"]["valid_experiments_violations"] += 1
                result["errors"].append(f"Valid experiment {eid}: sample_id '{sid}' not found in samples catalog.")

            # SOP clause version consistency for valid experiments
            if cid and sop_id and sop_ver:
                allowed_clauses = sop_clause_map.get((sop_id, sop_ver), set())
                if cid not in allowed_clauses:
                    result["valid"] = False
                    result["foreign_key_summary"]["valid_experiments_violations"] += 1
                    result["errors"].append(
                        f"Valid experiment {eid}: clause_id '{cid}' does not belong to SOP '{sop_id}' version '{sop_ver}'."
                    )
        else:
            # For review scenarios: track intentional missing or mismatched foreign keys
            if iid is None or lid is None or sid is None or cid is None:
                result["foreign_key_summary"]["intentional_missing_ids"] += 1
            if (iid and iid not in inst_catalog) or (lid and lid not in lot_catalog) or (sid and sid not in sample_catalog) or (cid and cid not in clause_catalog):
                result["foreign_key_summary"]["intentional_mismatched_ids"] += 1

    return result


def validate_ground_truth_ledger(
    ledger_records: List[Dict[str, Any]],
    experiments: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Validate ground-truth ledger completeness, schema, verdict policy, abstention, and evidence references."""
    result: Dict[str, Any] = {
        "dataset": "ground_truth_ledger",
        "valid": True,
        "record_count": len(ledger_records),
        "errors": [],
        "warnings": [],
        "verdict_counts": {"valid": 0, "invalid": 0, "needs_review": 0},
    }

    exp_map = {e["experiment_id"]: e for e in experiments if e.get("experiment_id")}
    total_exps = len(experiments)

    if len(ledger_records) != total_exps:
        result["valid"] = False
        result["errors"].append(
            f"Ledger record count ({len(ledger_records)}) does not equal raw experiments count ({total_exps})."
        )

    ledger_ids: Set[str] = set()

    for idx, rec in enumerate(ledger_records):
        eid = rec.get("experiment_id")

        # Required fields
        missing = LEDGER_REQUIRED_FIELDS - set(rec.keys())
        if missing:
            result["valid"] = False
            result["errors"].append(f"Ledger record {idx} ({eid}): missing required fields: {sorted(list(missing))}")

        # Unique experiment_id
        if not eid:
            result["valid"] = False
            result["errors"].append(f"Ledger record {idx}: empty or null experiment_id.")
            continue
        elif eid in ledger_ids:
            result["valid"] = False
            result["errors"].append(f"Ledger record {idx}: duplicate experiment_id '{eid}'.")
        else:
            ledger_ids.add(eid)

        if eid not in exp_map:
            result["valid"] = False
            result["errors"].append(f"Ledger record {eid} does not exist in raw experiments dataset.")
            continue

        raw_exp = exp_map[eid]

        # Scenario family match
        if rec.get("scenario_family") != raw_exp.get("scenario_family"):
            result["valid"] = False
            result["errors"].append(
                f"Ledger {eid}: scenario_family '{rec.get('scenario_family')}' != raw '{raw_exp.get('scenario_family')}'."
            )

        # Checks validation
        checks = rec.get("checks", {})
        if not isinstance(checks, dict):
            result["valid"] = False
            result["errors"].append(f"Ledger {eid}: 'checks' must be a dictionary.")
            continue

        missing_checks = LEDGER_REQUIRED_CHECKS - set(checks.keys())
        if missing_checks:
            result["valid"] = False
            result["errors"].append(f"Ledger {eid}: missing required checks: {sorted(list(missing_checks))}")

        # Verify statuses and reason codes across the 5 checks
        check_statuses: List[str] = []
        collected_reason_codes: List[str] = []

        for cname in ("sop", "calibration", "lot", "holding_time", "measurement"):
            cdata = checks.get(cname, {})
            if not isinstance(cdata, dict):
                result["valid"] = False
                result["errors"].append(f"Ledger {eid}: check '{cname}' is not a dictionary.")
                continue

            st = cdata.get("status")
            if st not in ("pass", "fail", "needs_review"):
                result["valid"] = False
                result["errors"].append(f"Ledger {eid}: check '{cname}' has invalid status '{st}'.")
            else:
                check_statuses.append(st)

            rc = cdata.get("reason_code")
            if rc:
                collected_reason_codes.append(rc)

        # Verdict Policy Check
        verdict = rec.get("verdict")
        if verdict not in ("valid", "invalid", "needs_review"):
            result["valid"] = False
            result["errors"].append(f"Ledger {eid}: invalid verdict '{verdict}'.")
        else:
            result["verdict_counts"][verdict] += 1

        has_needs_review = any(s == "needs_review" for s in check_statuses)
        has_fail = any(s == "fail" for s in check_statuses)

        if has_needs_review:
            expected_verdict = "needs_review"
            expected_abstain = True
        elif has_fail:
            expected_verdict = "invalid"
            expected_abstain = False
        else:
            expected_verdict = "valid"
            expected_abstain = False

        if verdict != expected_verdict:
            result["valid"] = False
            result["errors"].append(
                f"Ledger {eid}: verdict policy violation! Expected '{expected_verdict}', got '{verdict}'."
            )

        # Abstention Consistency
        abstain = rec.get("abstain")
        if abstain != expected_abstain:
            result["valid"] = False
            result["errors"].append(
                f"Ledger {eid}: abstention violation! Expected abstain={expected_abstain}, got abstain={abstain}."
            )

        # Reason Codes Consistency
        record_reason_codes = rec.get("reason_codes", [])
        if not isinstance(record_reason_codes, list):
            result["valid"] = False
            result["errors"].append(f"Ledger {eid}: reason_codes must be a list.")
        else:
            # Check that reason codes match check-level non-null reason codes
            if sorted(record_reason_codes) != sorted(collected_reason_codes):
                result["valid"] = False
                result["errors"].append(
                    f"Ledger {eid}: reason_codes mismatch. Record: {record_reason_codes}, Checks: {collected_reason_codes}."
                )

        # Evidence references check
        evidence = rec.get("evidence", [])
        if not isinstance(evidence, list) or len(evidence) == 0:
            result["valid"] = False
            result["errors"].append(f"Ledger {eid}: evidence must be a non-empty list of references.")
        else:
            for ev in evidence:
                if not isinstance(ev, dict) or "evidence_type" not in ev:
                    result["valid"] = False
                    result["errors"].append(f"Ledger {eid}: evidence item missing 'evidence_type': {ev}.")

        # Measurement sub-dict check
        meas = rec.get("measurement", {})
        if not isinstance(meas, dict):
            result["valid"] = False
            result["errors"].append(f"Ledger {eid}: 'measurement' must be a dictionary.")
        else:
            meas_status = meas.get("status")
            if meas_status != checks.get("measurement", {}).get("status"):
                result["valid"] = False
                result["errors"].append(
                    f"Ledger {eid}: measurement.status '{meas_status}' != checks.measurement.status '{checks.get('measurement', {}).get('status')}'."
                )

    return result


def validate_summary_report(summary_path: str, ledger_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate data/reports/ground_truth_summary.json against ground-truth ledger records."""
    result: Dict[str, Any] = {"report": "ground_truth_summary", "valid": True, "errors": [], "warnings": []}

    if not os.path.exists(summary_path):
        result["valid"] = False
        result["errors"].append(f"Summary report file not found: {summary_path}")
        return result

    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)
    except Exception as exc:
        result["valid"] = False
        result["errors"].append(f"Unable to parse summary JSON: {str(exc)}")
        return result

    total_ledger = len(ledger_records)
    reported_total = summary.get("total_experiments")
    if reported_total != total_ledger:
        result["valid"] = False
        result["errors"].append(f"Summary total_experiments ({reported_total}) != ledger count ({total_ledger}).")

    unprocessed = summary.get("unprocessed_experiments", -1)
    if unprocessed != 0:
        result["valid"] = False
        result["errors"].append(f"Summary unprocessed_experiments ({unprocessed}) is not 0.")

    actual_valid = sum(1 for r in ledger_records if r.get("verdict") == "valid")
    actual_invalid = sum(1 for r in ledger_records if r.get("verdict") == "invalid")
    actual_nr = sum(1 for r in ledger_records if r.get("verdict") == "needs_review")

    if summary.get("valid_count") != actual_valid:
        result["valid"] = False
        result["errors"].append(f"Summary valid_count ({summary.get('valid_count')}) != actual ({actual_valid}).")

    if summary.get("invalid_count") != actual_invalid:
        result["valid"] = False
        result["errors"].append(f"Summary invalid_count ({summary.get('invalid_count')}) != actual ({actual_invalid}).")

    if summary.get("needs_review_count") != actual_nr:
        result["valid"] = False
        result["errors"].append(f"Summary needs_review_count ({summary.get('needs_review_count')}) != actual ({actual_nr}).")

    return result


def run_full_validation(
    raw_dir: str = "data/raw",
    ledger_path: str = "data/ground_truth/ground_truth_ledger.jsonl",
    summary_path: str = "data/reports/ground_truth_summary.json",
) -> Dict[str, Any]:
    """Execute complete validation suite across all raw data files, ledger, and summary."""
    overall_valid = True
    section_results: Dict[str, Any] = {}

    # 1. Syntax validations
    files_to_check = {
        "sops_jsonl": os.path.join(raw_dir, "sops_v1.jsonl"),
        "instruments_jsonl": os.path.join(raw_dir, "instruments_v1.jsonl"),
        "lots_jsonl": os.path.join(raw_dir, "lots_v1.jsonl"),
        "samples_jsonl": os.path.join(raw_dir, "samples_v1.jsonl"),
        "experiments_jsonl": os.path.join(raw_dir, "experiments_v1.jsonl"),
        "ledger_jsonl": ledger_path,
        "runs_csv": os.path.join(raw_dir, "runs_v1.csv"),
    }

    syntax_results = {}
    for key, fpath in files_to_check.items():
        if fpath.endswith(".csv"):
            res = validate_csv_syntax(fpath)
        else:
            res = validate_jsonl_syntax(fpath)
        syntax_results[key] = res
        if not res["valid"]:
            overall_valid = False

    section_results["syntax"] = syntax_results

    # 2. Load data for content checks
    sops = read_jsonl(files_to_check["sops_jsonl"]) if os.path.exists(files_to_check["sops_jsonl"]) else []
    insts = read_jsonl(files_to_check["instruments_jsonl"]) if os.path.exists(files_to_check["instruments_jsonl"]) else []
    lots = read_jsonl(files_to_check["lots_jsonl"]) if os.path.exists(files_to_check["lots_jsonl"]) else []
    samples = read_jsonl(files_to_check["samples_jsonl"]) if os.path.exists(files_to_check["samples_jsonl"]) else []
    experiments = read_jsonl(files_to_check["experiments_jsonl"]) if os.path.exists(files_to_check["experiments_jsonl"]) else []
    ledger = read_jsonl(ledger_path) if os.path.exists(ledger_path) else []

    # 3. Catalog validations
    sops_val = validate_sops_dataset(sops)
    insts_val = validate_instruments_dataset(insts)
    lots_val = validate_lots_dataset(lots)
    samples_val = validate_samples_dataset(samples)
    experiments_val = validate_experiments_dataset(experiments, sops, insts, lots, samples)

    for v in (sops_val, insts_val, lots_val, samples_val, experiments_val):
        if not v["valid"]:
            overall_valid = False

    section_results["catalogs"] = {
        "sops": sops_val,
        "instruments": insts_val,
        "lots": lots_val,
        "samples": samples_val,
        "experiments": experiments_val,
    }

    # 4. Ledger validation
    ledger_val = validate_ground_truth_ledger(ledger, experiments)
    if not ledger_val["valid"]:
        overall_valid = False
    section_results["ledger"] = ledger_val

    # 5. Summary validation
    summary_val = validate_summary_report(summary_path, ledger)
    if not summary_val["valid"]:
        overall_valid = False
    section_results["summary"] = summary_val

    # Aggregate counts
    total_errors = 0
    total_warnings = 0
    for sec_name, sec_data in section_results.items():
        if isinstance(sec_data, dict):
            for sub_name, sub_data in sec_data.items():
                if isinstance(sub_data, dict):
                    total_errors += len(sub_data.get("errors", []))
                    total_warnings += len(sub_data.get("warnings", []))

    return {
        "overall_valid": overall_valid,
        "total_errors": total_errors,
        "total_warnings": total_warnings,
        "section_results": section_results,
    }
