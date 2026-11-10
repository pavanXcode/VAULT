"""Deterministic laboratory validation rules for VAULT.

Provides five deterministic verification functions:
1. validate_sop()
2. validate_calibration()
3. validate_lot()
4. validate_holding_time()
5. validate_measurement()
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Set, Union

from synth.units import (
    CANONICAL_UNIT,
    REASON_MEASUREMENT_OUT_OF_RANGE,
    REASON_UNCERTAINTY_BOUNDARY_OVERLAP,
    REASON_UNCERTAINTY_CROSSES_BOUNDARY,
    REASON_UNSUPPORTED_UNIT,
    are_units_compatible,
    compare_measurement,
    convert_value_decimal,
)

# Standard reason codes
REASON_SOP_VERSION_INVALID = "SOP_VERSION_INVALID"
REASON_SOP_VERSION_CONFLICT = "SOP_VERSION_CONFLICT"
REASON_CALIBRATION_EXPIRED = "CALIBRATION_EXPIRED"
REASON_LOT_EXPIRED = "LOT_EXPIRED"
REASON_HOLDING_TIME_EXCEEDED = "HOLDING_TIME_EXCEEDED"
REASON_MEASUREMENT_OUT_OF_RANGE = "MEASUREMENT_OUT_OF_RANGE"
REASON_MISSING_REQUIRED_EVIDENCE = "MISSING_REQUIRED_EVIDENCE"
REASON_UNSUPPORTED_UNIT = "UNSUPPORTED_UNIT"
REASON_INVALID_TIMESTAMP_ORDER = "INVALID_TIMESTAMP_ORDER"


def _format_result(
    status: str,
    reason_code: Optional[str],
    details: str,
    source_ids: Optional[List[str]] = None,
    calculated_values: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return a consistent dictionary conforming to VAULT rule specification."""
    return {
        "status": status,
        "reason_code": reason_code,
        "details": details,
        "source_ids": source_ids if source_ids is not None else [],
        "calculated_values": calculated_values if calculated_values is not None else {},
    }


def _parse_date(val: Any) -> Optional[date]:
    """Parse date from date, datetime, or ISO string."""
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        val_clean = val.strip()
        if not val_clean:
            return None
        if "T" in val_clean:
            val_clean = val_clean.split("T")[0]
        try:
            return date.fromisoformat(val_clean)
        except ValueError:
            return None
    return None


def _parse_datetime(val: Any) -> Optional[datetime]:
    """Parse datetime from datetime or ISO string."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        val_clean = val.strip()
        if not val_clean:
            return None
        # Handle trailing Z for UTC
        if val_clean.endswith("Z"):
            val_clean = val_clean[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(val_clean)
        except ValueError:
            # Fallback for plain dates
            try:
                d = date.fromisoformat(val_clean)
                return datetime(d.year, d.month, d.day, 0, 0, 0)
            except ValueError:
                return None
    return None


# =============================================================================
# Rule 1: SOP Version Validation
# =============================================================================
def validate_sop(
    experiment: Optional[Dict[str, Any]] = None,
    sops: Optional[Union[List[Dict[str, Any]], Dict[str, Any]]] = None,
    *,
    sop_id: Optional[str] = None,
    sop_version: Optional[str] = None,
    run_date: Optional[Union[str, date, datetime]] = None,
    clause_id: Optional[str] = None,
    effective_date: Optional[Union[str, date]] = None,
    superseded_date: Optional[Union[str, date]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Validate whether an SOP version is applicable on the experiment run date.

    Conditions:
    - effective_date <= run_date
    - run_date < superseded_date (if superseded_date is null, treated as open-ended)
    - Detect overlapping or conflicting applicable SOP versions
    - Missing SOP evidence returns needs_review
    """
    if experiment:
        sop_id = sop_id or experiment.get("sop_id")
        sop_version = sop_version or experiment.get("sop_version")
        run_date = run_date or experiment.get("run_date")
        clause_id = clause_id or experiment.get("clause_id")

    source_ids: List[str] = []
    if sop_id:
        source_ids.append(str(sop_id))
    if clause_id and clause_id not in source_ids:
        source_ids.append(str(clause_id))

    # Missing evidence check
    if not sop_id:
        return _format_result(
            status="needs_review",
            reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
            details="Missing SOP identifier (sop_id is null or empty).",
            source_ids=source_ids,
        )

    if sop_version is None or str(sop_version).strip() == "":
        return _format_result(
            status="needs_review",
            reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
            details="Missing SOP version (sop_version is null or empty).",
            source_ids=source_ids,
            calculated_values={"sop_id": sop_id},
        )

    run_dt = _parse_date(run_date)
    if run_dt is None:
        return _format_result(
            status="needs_review",
            reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
            details="Missing or unparseable experiment run date.",
            source_ids=source_ids,
            calculated_values={"sop_id": sop_id, "sop_version": str(sop_version)},
        )

    sop_version_str = str(sop_version).strip()

    # Case A: sops catalog provided
    if sops is not None:
        sop_list = sops if isinstance(sops, list) else [sops]
        matching_records = [r for r in sop_list if r.get("sop_id") == sop_id]

        if not matching_records:
            return _format_result(
                status="needs_review",
                reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
                details=f"No SOP catalog records found for sop_id '{sop_id}'.",
                source_ids=source_ids,
                calculated_values={"sop_id": sop_id, "sop_version": sop_version_str},
            )

        # Aggregate versions and their clauses
        versions_info: Dict[str, Dict[str, Any]] = {}
        for rec in matching_records:
            v_key = str(rec.get("sop_version", "")).strip()
            if not v_key:
                continue
            if v_key not in versions_info:
                versions_info[v_key] = {
                    "effective_date": _parse_date(rec.get("effective_date")),
                    "superseded_date": _parse_date(rec.get("superseded_date")),
                    "clauses": set(),
                }
            c_id = rec.get("clause_id")
            if c_id:
                versions_info[v_key]["clauses"].add(str(c_id))

        if not versions_info:
            return _format_result(
                status="needs_review",
                reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
                details=f"No version definitions available for sop_id '{sop_id}'.",
                source_ids=source_ids,
            )

        # Find applicable versions on run_dt
        applicable_versions: List[str] = []
        for v_name, v_data in versions_info.items():
            eff = v_data["effective_date"]
            sup = v_data["superseded_date"]
            if eff is not None and eff <= run_dt:
                if sup is None or run_dt < sup:
                    applicable_versions.append(v_name)

        # Detect overlapping / conflicting applicable SOP versions
        if len(set(applicable_versions)) > 1:
            return _format_result(
                status="needs_review",
                reason_code=REASON_SOP_VERSION_CONFLICT,
                details=(
                    f"Overlapping or conflicting applicable SOP versions detected on {run_dt.isoformat()}: "
                    f"{sorted(list(set(applicable_versions)))}."
                ),
                source_ids=source_ids,
                calculated_values={
                    "sop_id": sop_id,
                    "run_date": run_dt.isoformat(),
                    "applicable_versions": sorted(list(set(applicable_versions))),
                    "specified_version": sop_version_str,
                },
            )

        if not applicable_versions:
            # No version is applicable on run_date
            return _format_result(
                status="fail",
                reason_code=REASON_SOP_VERSION_INVALID,
                details=(
                    f"No active SOP version exists for '{sop_id}' on run date {run_dt.isoformat()}."
                ),
                source_ids=source_ids,
                calculated_values={
                    "sop_id": sop_id,
                    "run_date": run_dt.isoformat(),
                    "specified_version": sop_version_str,
                },
            )

        active_version = applicable_versions[0]
        if sop_version_str != active_version:
            return _format_result(
                status="fail",
                reason_code=REASON_SOP_VERSION_INVALID,
                details=(
                    f"Specified SOP version '{sop_version_str}' is invalid on run date {run_dt.isoformat()}. "
                    f"Active applicable version is '{active_version}'."
                ),
                source_ids=source_ids,
                calculated_values={
                    "sop_id": sop_id,
                    "run_date": run_dt.isoformat(),
                    "specified_version": sop_version_str,
                    "active_version": active_version,
                },
            )

        # Check clause existence if clause_id is specified
        if clause_id:
            clause_set = versions_info[active_version]["clauses"]
            if clause_set and clause_id not in clause_set:
                return _format_result(
                    status="fail",
                    reason_code=REASON_SOP_VERSION_INVALID,
                    details=f"Clause '{clause_id}' does not exist in SOP '{sop_id}' version '{active_version}'.",
                    source_ids=source_ids,
                    calculated_values={
                        "sop_id": sop_id,
                        "sop_version": active_version,
                        "clause_id": clause_id,
                    },
                )

        eff_date = versions_info[active_version]["effective_date"]
        sup_date = versions_info[active_version]["superseded_date"]
        return _format_result(
            status="pass",
            reason_code=None,
            details=f"SOP version '{sop_version_str}' is valid and applicable on {run_dt.isoformat()}.",
            source_ids=source_ids,
            calculated_values={
                "sop_id": sop_id,
                "sop_version": sop_version_str,
                "run_date": run_dt.isoformat(),
                "effective_date": eff_date.isoformat() if eff_date else None,
                "superseded_date": sup_date.isoformat() if sup_date else None,
            },
        )

    # Case B: Standalone version with explicit effective/superseded dates
    eff_dt = _parse_date(effective_date)
    sup_dt = _parse_date(superseded_date)

    if eff_dt is None:
        return _format_result(
            status="needs_review",
            reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
            details="Missing SOP effective_date.",
            source_ids=source_ids,
        )

    # Condition: effective_date <= run_date and (superseded_date is null or run_date < superseded_date)
    if run_dt < eff_dt:
        return _format_result(
            status="fail",
            reason_code=REASON_SOP_VERSION_INVALID,
            details=f"Run date {run_dt.isoformat()} precedes SOP effective date {eff_dt.isoformat()}.",
            source_ids=source_ids,
            calculated_values={
                "run_date": run_dt.isoformat(),
                "effective_date": eff_dt.isoformat(),
                "superseded_date": sup_dt.isoformat() if sup_dt else None,
            },
        )

    if sup_dt is not None and run_dt >= sup_dt:
        return _format_result(
            status="fail",
            reason_code=REASON_SOP_VERSION_INVALID,
            details=f"SOP version was superseded on {sup_dt.isoformat()}, before run date {run_dt.isoformat()}.",
            source_ids=source_ids,
            calculated_values={
                "run_date": run_dt.isoformat(),
                "effective_date": eff_dt.isoformat(),
                "superseded_date": sup_dt.isoformat(),
            },
        )

    return _format_result(
        status="pass",
        reason_code=None,
        details=f"SOP version '{sop_version_str}' is valid on {run_dt.isoformat()}.",
        source_ids=source_ids,
        calculated_values={
            "sop_id": sop_id,
            "sop_version": sop_version_str,
            "run_date": run_dt.isoformat(),
            "effective_date": eff_dt.isoformat(),
            "superseded_date": sup_dt.isoformat() if sup_dt else None,
        },
    )


# =============================================================================
# Rule 2: Instrument Calibration Validation
# =============================================================================
def validate_calibration(
    experiment: Optional[Dict[str, Any]] = None,
    instruments: Optional[Union[List[Dict[str, Any]], Dict[str, Any]]] = None,
    *,
    instrument_id: Optional[str] = None,
    calibration_date: Optional[Union[str, date, datetime]] = None,
    validity_days: Optional[int] = None,
    run_date: Optional[Union[str, date, datetime]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Validate instrument calibration on experiment run date.

    Validity condition:
    calibration_date <= run_date <= calibration_date + validity_days (inclusive final day)

    Expired or invalid calibration returns fail.
    Missing required calibration evidence returns needs_review.
    """
    if experiment:
        instrument_id = instrument_id or experiment.get("instrument_id")
        run_date = run_date or experiment.get("run_date") or experiment.get("analyzed_at")

    source_ids: List[str] = [str(instrument_id)] if instrument_id else []

    if not instrument_id:
        return _format_result(
            status="needs_review",
            reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
            details="Missing instrument identifier (instrument_id is null or empty).",
            source_ids=source_ids,
        )

    # Lookup in instruments catalog if provided
    if instruments is not None:
        inst_list = instruments if isinstance(instruments, list) else [instruments]
        matching = [i for i in inst_list if i.get("instrument_id") == instrument_id]
        if not matching:
            return _format_result(
                status="needs_review",
                reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
                details=f"Instrument '{instrument_id}' not found in instruments catalog.",
                source_ids=source_ids,
            )
        inst_record = matching[0]
        if calibration_date is None:
            calibration_date = inst_record.get("calibration_date")
        if validity_days is None:
            validity_days = inst_record.get("validity_days")

    cal_dt = _parse_date(calibration_date)
    run_dt = _parse_date(run_date)

    if cal_dt is None:
        return _format_result(
            status="needs_review",
            reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
            details="Missing or unparseable calibration date.",
            source_ids=source_ids,
        )

    if validity_days is None:
        return _format_result(
            status="needs_review",
            reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
            details="Missing calibration validity days.",
            source_ids=source_ids,
        )

    try:
        val_days_int = int(validity_days)
    except (ValueError, TypeError):
        return _format_result(
            status="needs_review",
            reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
            details=f"Invalid calibration validity days: '{validity_days}'.",
            source_ids=source_ids,
        )

    if run_dt is None:
        return _format_result(
            status="needs_review",
            reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
            details="Missing or unparseable run date.",
            source_ids=source_ids,
        )

    from datetime import timedelta
    expiry_dt = cal_dt + timedelta(days=val_days_int)
    days_remaining = (expiry_dt - run_dt).days

    calculated_values = {
        "instrument_id": instrument_id,
        "calibration_date": cal_dt.isoformat(),
        "validity_days": val_days_int,
        "expiration_date": expiry_dt.isoformat(),
        "run_date": run_dt.isoformat(),
        "days_remaining": days_remaining,
    }

    if run_dt < cal_dt:
        return _format_result(
            status="fail",
            reason_code=REASON_CALIBRATION_EXPIRED,
            details=f"Run date {run_dt.isoformat()} precedes instrument calibration date {cal_dt.isoformat()}.",
            source_ids=source_ids,
            calculated_values=calculated_values,
        )

    if run_dt > expiry_dt:
        return _format_result(
            status="fail",
            reason_code=REASON_CALIBRATION_EXPIRED,
            details=(
                f"Instrument calibration expired on {expiry_dt.isoformat()} "
                f"({val_days_int} days validity). Run date was {run_dt.isoformat()}."
            ),
            source_ids=source_ids,
            calculated_values=calculated_values,
        )

    return _format_result(
        status="pass",
        reason_code=None,
        details=f"Instrument calibration is valid through {expiry_dt.isoformat()} (inclusive).",
        source_ids=source_ids,
        calculated_values=calculated_values,
    )


# =============================================================================
# Rule 3: Reagent Lot Validation
# =============================================================================
def validate_lot(
    experiment: Optional[Dict[str, Any]] = None,
    lots: Optional[Union[List[Dict[str, Any]], Dict[str, Any]]] = None,
    *,
    lot_id: Optional[str] = None,
    manufacture_date: Optional[Union[str, date, datetime]] = None,
    expiry_date: Optional[Union[str, date, datetime]] = None,
    run_date: Optional[Union[str, date, datetime]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Validate reagent lot against experiment run date.

    A lot is valid when:
    manufacture_date <= run_date <= expiry_date

    An expired lot returns fail.
    Missing lot evidence returns needs_review.
    """
    if experiment:
        lot_id = lot_id or experiment.get("lot_id")
        run_date = run_date or experiment.get("run_date") or experiment.get("analyzed_at")

    source_ids: List[str] = [str(lot_id)] if lot_id else []

    if not lot_id:
        return _format_result(
            status="needs_review",
            reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
            details="Missing reagent lot identifier (lot_id is null or empty).",
            source_ids=source_ids,
        )

    if lots is not None:
        lot_list = lots if isinstance(lots, list) else [lots]
        matching = [l for l in lot_list if l.get("lot_id") == lot_id]
        if not matching:
            return _format_result(
                status="needs_review",
                reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
                details=f"Reagent lot '{lot_id}' not found in lots catalog.",
                source_ids=source_ids,
            )
        lot_record = matching[0]
        if manufacture_date is None:
            manufacture_date = lot_record.get("manufacture_date")
        if expiry_date is None:
            expiry_date = lot_record.get("expiry_date")

    mfg_dt = _parse_date(manufacture_date)
    exp_dt = _parse_date(expiry_date)
    run_dt = _parse_date(run_date)

    if mfg_dt is None:
        return _format_result(
            status="needs_review",
            reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
            details="Missing or unparseable lot manufacture date.",
            source_ids=source_ids,
        )

    if exp_dt is None:
        return _format_result(
            status="needs_review",
            reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
            details="Missing or unparseable lot expiry date.",
            source_ids=source_ids,
        )

    if run_dt is None:
        return _format_result(
            status="needs_review",
            reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
            details="Missing or unparseable experiment run date.",
            source_ids=source_ids,
        )

    days_to_expiry = (exp_dt - run_dt).days
    calculated_values = {
        "lot_id": lot_id,
        "manufacture_date": mfg_dt.isoformat(),
        "expiry_date": exp_dt.isoformat(),
        "run_date": run_dt.isoformat(),
        "days_to_expiry": days_to_expiry,
    }

    if run_dt < mfg_dt:
        return _format_result(
            status="fail",
            reason_code=REASON_LOT_EXPIRED,
            details=f"Run date {run_dt.isoformat()} precedes reagent lot manufacture date {mfg_dt.isoformat()}.",
            source_ids=source_ids,
            calculated_values=calculated_values,
        )

    if run_dt > exp_dt:
        return _format_result(
            status="fail",
            reason_code=REASON_LOT_EXPIRED,
            details=f"Reagent lot expired on {exp_dt.isoformat()}. Run date was {run_dt.isoformat()}.",
            source_ids=source_ids,
            calculated_values=calculated_values,
        )

    return _format_result(
        status="pass",
        reason_code=None,
        details=f"Reagent lot is valid through {exp_dt.isoformat()}.",
        source_ids=source_ids,
        calculated_values=calculated_values,
    )


# =============================================================================
# Rule 4: Sample Holding-Time Validation
# =============================================================================
def validate_holding_time(
    experiment: Optional[Dict[str, Any]] = None,
    samples: Optional[Union[List[Dict[str, Any]], Dict[str, Any]]] = None,
    *,
    sample_id: Optional[str] = None,
    collected_at: Optional[Union[str, datetime]] = None,
    analyzed_at: Optional[Union[str, datetime]] = None,
    max_holding_hours: Optional[Union[int, float, Decimal]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Validate sample holding time between collection and analysis.

    The sample passes when:
    analyzed_at - collected_at <= max_holding_hours

    Missing timestamps, invalid timestamp order, or missing limits return needs_review.
    """
    if experiment:
        sample_id = sample_id or experiment.get("sample_id")
        collected_at = collected_at or experiment.get("collected_at")
        analyzed_at = analyzed_at or experiment.get("analyzed_at")

    source_ids: List[str] = [str(sample_id)] if sample_id else []

    if samples is not None and sample_id:
        sample_list = samples if isinstance(samples, list) else [samples]
        matching = [s for s in sample_list if s.get("sample_id") == sample_id]
        if not matching:
            return _format_result(
                status="needs_review",
                reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
                details=f"Sample '{sample_id}' not found in samples catalog.",
                source_ids=source_ids,
            )
        sample_rec = matching[0]
        if collected_at is None:
            collected_at = sample_rec.get("collected_at")
        if max_holding_hours is None:
            max_holding_hours = sample_rec.get("max_holding_hours")

    if not sample_id and collected_at is None and analyzed_at is None:
        return _format_result(
            status="needs_review",
            reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
            details="Missing sample identification and timestamps.",
            source_ids=source_ids,
        )

    col_dt = _parse_datetime(collected_at)
    ana_dt = _parse_datetime(analyzed_at)

    if col_dt is None:
        return _format_result(
            status="needs_review",
            reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
            details="Missing or unparseable collection timestamp (collected_at).",
            source_ids=source_ids,
        )

    if ana_dt is None:
        return _format_result(
            status="needs_review",
            reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
            details="Missing or unparseable analysis timestamp (analyzed_at).",
            source_ids=source_ids,
        )

    if max_holding_hours is None:
        return _format_result(
            status="needs_review",
            reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
            details="Missing maximum holding hours threshold (max_holding_hours).",
            source_ids=source_ids,
        )

    try:
        max_h_dec = Decimal(str(max_holding_hours))
        if max_h_dec <= 0:
            return _format_result(
                status="needs_review",
                reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
                details=f"Invalid non-positive holding time limit: {max_holding_hours}.",
                source_ids=source_ids,
            )
    except (InvalidOperation, ValueError, TypeError):
        return _format_result(
            status="needs_review",
            reason_code=REASON_MISSING_REQUIRED_EVIDENCE,
            details=f"Unparseable holding time limit: '{max_holding_hours}'.",
            source_ids=source_ids,
        )

    # Invalid timestamp order: analysis before collection
    if ana_dt < col_dt:
        elapsed_sec = (ana_dt - col_dt).total_seconds()
        elapsed_h = elapsed_sec / 3600.0
        return _format_result(
            status="needs_review",
            reason_code=REASON_INVALID_TIMESTAMP_ORDER,
            details=(
                f"Invalid timestamp order: analyzed_at ({ana_dt.isoformat()}) "
                f"precedes collected_at ({col_dt.isoformat()})."
            ),
            source_ids=source_ids,
            calculated_values={
                "collected_at": col_dt.isoformat(),
                "analyzed_at": ana_dt.isoformat(),
                "elapsed_hours": round(elapsed_h, 4),
                "max_holding_hours": float(max_h_dec),
            },
        )

    elapsed_seconds = Decimal(str((ana_dt - col_dt).total_seconds()))
    elapsed_hours = elapsed_seconds / Decimal("3600")
    margin_hours = max_h_dec - elapsed_hours

    calculated_values = {
        "collected_at": col_dt.isoformat(),
        "analyzed_at": ana_dt.isoformat(),
        "elapsed_hours": round(float(elapsed_hours), 4),
        "max_holding_hours": float(max_h_dec),
        "margin_hours": round(float(margin_hours), 4),
    }

    if elapsed_hours > max_h_dec:
        return _format_result(
            status="fail",
            reason_code=REASON_HOLDING_TIME_EXCEEDED,
            details=(
                f"Sample holding time exceeded: {float(elapsed_hours):.2f} hours elapsed "
                f"exceeds maximum limit of {float(max_h_dec):.2f} hours."
            ),
            source_ids=source_ids,
            calculated_values=calculated_values,
        )

    return _format_result(
        status="pass",
        reason_code=None,
        details=(
            f"Sample analyzed within holding time: {float(elapsed_hours):.2f} hours <= "
            f"{float(max_h_dec):.2f} hours limit."
        ),
        source_ids=source_ids,
        calculated_values=calculated_values,
    )


# =============================================================================
# Rule 5: Measurement Validation
# =============================================================================
def validate_measurement(
    experiment: Optional[Dict[str, Any]] = None,
    clause: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
    *,
    measured_value: Optional[Union[int, float, Decimal, str]] = None,
    measurement_unit: Optional[str] = None,
    measurement_uncertainty: Optional[Union[int, float, Decimal, str]] = None,
    minimum_value: Optional[Union[int, float, Decimal, str]] = None,
    maximum_value: Optional[Union[int, float, Decimal, str]] = None,
    canonical_unit: Optional[str] = None,
    clause_id: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Validate numerical measurement and its uncertainty interval against SOP specification limits.

    Integrates with synth/units.py robust unit conversion and measurement comparison.
    Uses Decimal arithmetic for boundary-sensitive calculations.
    """
    if experiment:
        if measured_value is None:
            measured_value = experiment.get("measured_value")
        if measurement_unit is None:
            measurement_unit = experiment.get("measurement_unit")
        if measurement_uncertainty is None:
            measurement_uncertainty = experiment.get("measurement_uncertainty")
        if clause_id is None:
            clause_id = experiment.get("clause_id")

    source_ids: List[str] = [str(clause_id)] if clause_id else []

    if clause is not None:
        clause_dict = None
        if isinstance(clause, list):
            if clause_id:
                matching = [c for c in clause if c.get("clause_id") == clause_id]
                if matching:
                    clause_dict = matching[0]
            elif clause:
                clause_dict = clause[0]
        elif isinstance(clause, dict):
            clause_dict = clause

        if clause_dict:
            if minimum_value is None:
                minimum_value = clause_dict.get("minimum_value")
            if maximum_value is None:
                maximum_value = clause_dict.get("maximum_value")
            if canonical_unit is None:
                canonical_unit = clause_dict.get("canonical_unit")

    # Delegate comparison and interval math to synth/units.py
    target_canonical = canonical_unit or CANONICAL_UNIT
    comp = compare_measurement(
        measured_value=measured_value,
        measurement_unit=measurement_unit,
        measurement_uncertainty=measurement_uncertainty,
        minimum_value=minimum_value,
        maximum_value=maximum_value,
        canonical_unit=target_canonical,
    )

    # Prepare backward-compatible calculated_values dictionary
    norm_val = comp.get("normalized_value")
    norm_unc = comp.get("normalized_uncertainty")
    orig_val = comp.get("original_value")
    sop_min = comp.get("sop_minimum")
    sop_max = comp.get("sop_maximum")
    lower_b = comp.get("lower_bound")
    upper_b = comp.get("upper_bound")

    calculated_values: Dict[str, Any] = {
        "original_value": float(orig_val) if orig_val is not None else None,
        "original_unit": comp.get("original_unit"),
        "raw_value": float(orig_val) if orig_val is not None else None,
        "raw_unit": comp.get("original_unit"),
        "normalized_value": float(norm_val) if norm_val is not None else None,
        "canonical_unit": comp.get("canonical_unit"),
        "normalized_uncertainty": float(norm_unc) if norm_unc is not None else None,
        "lower_bound": float(lower_b) if lower_b is not None else None,
        "upper_bound": float(upper_b) if upper_b is not None else None,
        "sop_minimum": float(sop_min) if sop_min is not None else None,
        "sop_maximum": float(sop_max) if sop_max is not None else None,
        "minimum_value": float(sop_min) if sop_min is not None else None,
        "maximum_value": float(sop_max) if sop_max is not None else None,
        "in_specification": (comp.get("status") == "pass"),
    }
    if norm_val is not None and sop_min is not None:
        calculated_values["margin_to_min"] = float(norm_val - sop_min)
    if norm_val is not None and sop_max is not None:
        calculated_values["margin_to_max"] = float(sop_max - norm_val)

    # Return top-level fields required by Task 4 plus common format
    return {
        "status": comp["status"],
        "reason_code": comp["reason_code"],
        "details": comp["details"],
        "source_ids": source_ids,
        "original_value": orig_val,
        "original_unit": comp.get("original_unit"),
        "normalized_value": norm_val,
        "canonical_unit": comp.get("canonical_unit"),
        "normalized_uncertainty": norm_unc,
        "lower_bound": lower_b,
        "upper_bound": upper_b,
        "sop_minimum": sop_min,
        "sop_maximum": sop_max,
        "calculated_values": calculated_values,
    }

