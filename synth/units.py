"""Robust unit conversion and measurement uncertainty evaluation for VAULT.

Canonical unit: mg/L
Supported conversions:
- 1 g/L = 1000 mg/L
- 1 mg/L = 1 mg/L
- 1000 µg/L = 1 mg/L (1 µg/L = 0.001 mg/L)

Uses Python Decimal for all conversions and boundary-sensitive comparisons.
Avoids float arithmetic for boundary-sensitive calculations.
"""

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Set, Tuple, Union

# Primary canonical unit for mass concentration
CANONICAL_UNIT = "mg/L"

# Supported mass concentration units and aliases
SUPPORTED_CONCENTRATION_UNITS: Set[str] = {
    "g/L",
    "mg/L",
    "µg/L",
    "μg/L",  # Greek small letter mu (U+03BC)
    "ug/L",  # ASCII fallback
}

# Linear conversion factors to canonical unit (mg/L) using Decimal
# 1 g/L = 1000 mg/L
# 1 mg/L = 1 mg/L
# 1000 µg/L = 1 mg/L
CONVERSION_FACTORS_DECIMAL: Dict[str, Decimal] = {
    "g/L": Decimal("1000"),
    "mg/L": Decimal("1"),
    "µg/L": Decimal("0.001"),
    "μg/L": Decimal("0.001"),
    "ug/L": Decimal("0.001"),
}

# Legacy support constants for backward-compatibility with other domains
CANONICAL_UNITS: Set[str] = {
    "mg/L",
    "g/L",
    "µg/L",
    "pH",
    "µS/cm",
    "mS/cm",
    "NTU",
    "AU",
    "%",
    "°C",
}

MASS_CONCENTRATION_TO_MG_PER_L = {
    "mg/L": 1.0,
    "g/L": 1000.0,
    "µg/L": 0.001,
}

DECIMAL_MASS_CONCENTRATION_TO_MG_PER_L = {
    "mg/L": Decimal("1.0"),
    "g/L": Decimal("1000.0"),
    "µg/L": Decimal("0.001"),
}

CONDUCTIVITY_TO_US_PER_CM = {
    "µS/cm": 1.0,
    "mS/cm": 1000.0,
}

DECIMAL_CONDUCTIVITY_TO_US_PER_CM = {
    "µS/cm": Decimal("1.0"),
    "mS/cm": Decimal("1000.0"),
}

# Standard reason codes for measurement validation
REASON_MEASUREMENT_OUT_OF_RANGE = "MEASUREMENT_OUT_OF_RANGE"
REASON_UNCERTAINTY_CROSSES_BOUNDARY = "UNCERTAINTY_CROSSES_BOUNDARY"
REASON_UNCERTAINTY_BOUNDARY_OVERLAP = "UNCERTAINTY_CROSSES_BOUNDARY"
REASON_UNSUPPORTED_UNIT = "UNSUPPORTED_UNIT"
REASON_MISSING_REQUIRED_EVIDENCE = "MISSING_REQUIRED_EVIDENCE"


def is_supported_unit(unit: Optional[str]) -> bool:
    """Return True if unit is one of the supported mass concentration units."""
    if not unit or not isinstance(unit, str):
        return False
    return unit.strip() in SUPPORTED_CONCENTRATION_UNITS


def to_decimal(val: Any) -> Optional[Decimal]:
    """Convert value to Decimal cleanly without float representation errors."""
    if val is None:
        return None
    if isinstance(val, Decimal):
        return val
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return None


def convert_to_canonical(
    value: Union[Decimal, float, int, str],
    unit: str,
) -> Optional[Decimal]:
    """Convert value from given unit to canonical unit (mg/L) using Decimal.

    Conversions:
    - 1 g/L = 1000 mg/L
    - 1 mg/L = 1 mg/L
    - 1000 µg/L = 1 mg/L

    Returns None if unit is unsupported or value cannot be parsed.
    """
    d_val = to_decimal(value)
    if d_val is None or not is_supported_unit(unit):
        return None

    unit_clean = unit.strip()
    factor = CONVERSION_FACTORS_DECIMAL[unit_clean]
    return d_val * factor


def are_units_compatible(unit_from: str, unit_to: str) -> bool:
    """Check whether two units can be converted between each other."""
    if unit_from == unit_to:
        return True
    if is_supported_unit(unit_from) and is_supported_unit(unit_to):
        return True
    if unit_from in CONDUCTIVITY_TO_US_PER_CM and unit_to in CONDUCTIVITY_TO_US_PER_CM:
        return True
    return False


def convert_value(value: float, unit_from: str, unit_to: str) -> Optional[float]:
    """Convert numerical measurement from unit_from to unit_to (float fallback)."""
    if unit_from == unit_to:
        return value

    if is_supported_unit(unit_from) and is_supported_unit(unit_to):
        d_val = to_decimal(value)
        if d_val is None:
            return None
        canon = convert_to_canonical(d_val, unit_from)
        if canon is None:
            return None
        target_factor = CONVERSION_FACTORS_DECIMAL[unit_to.strip()]
        return float(canon / target_factor)

    if unit_from in CONDUCTIVITY_TO_US_PER_CM and unit_to in CONDUCTIVITY_TO_US_PER_CM:
        base_us = value * CONDUCTIVITY_TO_US_PER_CM[unit_from]
        return base_us / CONDUCTIVITY_TO_US_PER_CM[unit_to]

    return None


def convert_value_decimal(value: Decimal, unit_from: str, unit_to: str) -> Optional[Decimal]:
    """Convert Decimal numerical measurement from unit_from to unit_to."""
    if unit_from == unit_to:
        return value

    if is_supported_unit(unit_from) and is_supported_unit(unit_to):
        canon = convert_to_canonical(value, unit_from)
        if canon is None:
            return None
        target_factor = CONVERSION_FACTORS_DECIMAL[unit_to.strip()]
        return canon / target_factor

    if (
        unit_from in DECIMAL_CONDUCTIVITY_TO_US_PER_CM
        and unit_to in DECIMAL_CONDUCTIVITY_TO_US_PER_CM
    ):
        base_us = value * DECIMAL_CONDUCTIVITY_TO_US_PER_CM[unit_from]
        return base_us / DECIMAL_CONDUCTIVITY_TO_US_PER_CM[unit_to]

    return None


def compare_measurement(
    measured_value: Any,
    measurement_unit: Optional[str],
    measurement_uncertainty: Any = Decimal("0"),
    minimum_value: Any = None,
    maximum_value: Any = None,
    canonical_unit: str = CANONICAL_UNIT,
) -> Dict[str, Any]:
    """Compare a measured value and its uncertainty interval against SOP specification limits.

    Calculate:
    lower_bound = normalized_value - normalized_uncertainty
    upper_bound = normalized_value + normalized_uncertainty

    Cases evaluated:
    - Case 1 (Clearly within range):
      Entire uncertainty interval is within SOP limits (sop_min <= lower_bound and upper_bound <= sop_max) -> pass
    - Case 2 (Clearly outside range):
      Entire uncertainty interval is outside SOP limits (upper_bound < sop_min or lower_bound > sop_max) -> fail
    - Case 3 (Boundary uncertainty):
      Interval overlaps or crosses an SOP boundary -> needs_review
    - Case 4 (Unsupported unit):
      Unit is unknown or unsupported -> needs_review

    Returns a comprehensive dictionary with exact Decimals and required output fields.
    """
    d_val = to_decimal(measured_value)
    d_unc = to_decimal(measurement_uncertainty) if measurement_uncertainty is not None else Decimal("0")
    sop_min = to_decimal(minimum_value)
    sop_max = to_decimal(maximum_value)

    # Missing evidence check
    if d_val is None:
        return {
            "original_value": None,
            "original_unit": measurement_unit,
            "normalized_value": None,
            "canonical_unit": canonical_unit,
            "normalized_uncertainty": None,
            "lower_bound": None,
            "upper_bound": None,
            "sop_minimum": sop_min,
            "sop_maximum": sop_max,
            "status": "needs_review",
            "reason_code": REASON_MISSING_REQUIRED_EVIDENCE,
            "details": "Missing or unparseable measured value.",
        }

    if not measurement_unit:
        return {
            "original_value": d_val,
            "original_unit": None,
            "normalized_value": None,
            "canonical_unit": canonical_unit,
            "normalized_uncertainty": None,
            "lower_bound": None,
            "upper_bound": None,
            "sop_minimum": sop_min,
            "sop_maximum": sop_max,
            "status": "needs_review",
            "reason_code": REASON_MISSING_REQUIRED_EVIDENCE,
            "details": "Missing measurement unit.",
        }

    if sop_min is None or sop_max is None:
        return {
            "original_value": d_val,
            "original_unit": measurement_unit,
            "normalized_value": None,
            "canonical_unit": canonical_unit,
            "normalized_uncertainty": None,
            "lower_bound": None,
            "upper_bound": None,
            "sop_minimum": sop_min,
            "sop_maximum": sop_max,
            "status": "needs_review",
            "reason_code": REASON_MISSING_REQUIRED_EVIDENCE,
            "details": "Missing SOP minimum or maximum specification limit.",
        }

    # Case 4: Unsupported unit check
    unit_str = str(measurement_unit).strip()
    canon_str = str(canonical_unit).strip()

    if canon_str == CANONICAL_UNIT:
        if not is_supported_unit(unit_str):
            return {
                "original_value": d_val,
                "original_unit": unit_str,
                "normalized_value": None,
                "canonical_unit": canon_str,
                "normalized_uncertainty": None,
                "lower_bound": None,
                "upper_bound": None,
                "sop_minimum": sop_min,
                "sop_maximum": sop_max,
                "status": "needs_review",
                "reason_code": REASON_UNSUPPORTED_UNIT,
                "details": f"Measurement unit '{unit_str}' is unsupported for canonical unit '{canon_str}'.",
            }
        factor = CONVERSION_FACTORS_DECIMAL[unit_str]
        normalized_value = d_val * factor
        normalized_uncertainty = d_unc * factor
    else:
        # Support other domain units when measurement unit matches canonical unit
        if unit_str != canon_str:
            if not are_units_compatible(unit_str, canon_str):
                return {
                    "original_value": d_val,
                    "original_unit": unit_str,
                    "normalized_value": None,
                    "canonical_unit": canon_str,
                    "normalized_uncertainty": None,
                    "lower_bound": None,
                    "upper_bound": None,
                    "sop_minimum": sop_min,
                    "sop_maximum": sop_max,
                    "status": "needs_review",
                    "reason_code": REASON_UNSUPPORTED_UNIT,
                    "details": f"Measurement unit '{unit_str}' is incompatible with canonical unit '{canon_str}'.",
                }
            norm = convert_value_decimal(d_val, unit_str, canon_str)
            norm_unc = convert_value_decimal(d_unc, unit_str, canon_str)
            normalized_value = norm if norm is not None else d_val
            normalized_uncertainty = norm_unc if norm_unc is not None else d_unc
        else:
            normalized_value = d_val
            normalized_uncertainty = d_unc

    # Ensure uncertainty is non-negative
    if normalized_uncertainty < Decimal("0"):
        return {
            "original_value": d_val,
            "original_unit": unit_str,
            "normalized_value": normalized_value,
            "canonical_unit": canon_str,
            "normalized_uncertainty": normalized_uncertainty,
            "lower_bound": None,
            "upper_bound": None,
            "sop_minimum": sop_min,
            "sop_maximum": sop_max,
            "status": "needs_review",
            "reason_code": REASON_MISSING_REQUIRED_EVIDENCE,
            "details": f"Measurement uncertainty cannot be negative: {normalized_uncertainty}.",
        }

    # Calculate uncertainty bounds
    lower_bound = normalized_value - normalized_uncertainty
    upper_bound = normalized_value + normalized_uncertainty

    # Compare interval with SOP permitted range [sop_min, sop_max]
    # Case 1 – Clearly within range: entire interval is within SOP limits
    if sop_min <= lower_bound and upper_bound <= sop_max:
        return {
            "original_value": d_val,
            "original_unit": unit_str,
            "normalized_value": normalized_value,
            "canonical_unit": canon_str,
            "normalized_uncertainty": normalized_uncertainty,
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
            "sop_minimum": sop_min,
            "sop_maximum": sop_max,
            "status": "pass",
            "reason_code": None,
            "details": (
                f"Entire uncertainty interval [{lower_bound}, {upper_bound}] {canon_str} "
                f"is within SOP limits [{sop_min}, {sop_max}] {canon_str}."
            ),
        }

    # Case 2 – Clearly outside range: entire interval is outside SOP limits
    if upper_bound < sop_min or lower_bound > sop_max:
        return {
            "original_value": d_val,
            "original_unit": unit_str,
            "normalized_value": normalized_value,
            "canonical_unit": canon_str,
            "normalized_uncertainty": normalized_uncertainty,
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
            "sop_minimum": sop_min,
            "sop_maximum": sop_max,
            "status": "fail",
            "reason_code": REASON_MEASUREMENT_OUT_OF_RANGE,
            "details": (
                f"Entire uncertainty interval [{lower_bound}, {upper_bound}] {canon_str} "
                f"is outside SOP limits [{sop_min}, {sop_max}] {canon_str}."
            ),
        }

    # Case 3 – Boundary uncertainty: interval overlaps or crosses an SOP boundary
    return {
        "original_value": d_val,
        "original_unit": unit_str,
        "normalized_value": normalized_value,
        "canonical_unit": canon_str,
        "normalized_uncertainty": normalized_uncertainty,
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
        "sop_minimum": sop_min,
        "sop_maximum": sop_max,
        "status": "needs_review",
        "reason_code": REASON_UNCERTAINTY_CROSSES_BOUNDARY,
        "details": (
            f"Uncertainty interval [{lower_bound}, {upper_bound}] {canon_str} "
            f"overlaps or crosses SOP specification boundary [{sop_min}, {sop_max}] {canon_str}."
        ),
    }


# Backwards compatibility alias
evaluate_measurement_uncertainty = compare_measurement
