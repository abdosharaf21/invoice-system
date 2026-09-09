"""Value normalization for imported accounting rows.

Raw cells from a parsed file are translated into their canonical typed
values here. Normalization is deliberately strict about *bad* data
(garbage never becomes a silently wrong number) but forgiving about
*formatting* (commas, currency symbols, date layouts and Excel serial
dates are all accepted).

Money is handled exclusively with :class:`decimal.Decimal` so cents are
never corrupted by floating point arithmetic.
"""

import re
import uuid as uuidlib
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from backend.modules.imports.contract import CONTRACT, REQUIRED_FIELDS
from backend.modules.imports.errors import (
    E_INVALID_DATE,
    E_INVALID_ENUM,
    E_INVALID_MONEY,
    E_INVALID_QUANTITY,
    E_INVALID_UUID,
    E_MISSING_FIELD,
    ImportErrorInfo,
)

_MONEY_QUANTIZE = Decimal("0.01")
_QUANTITY_QUANTIZE = Decimal("0.0001")

_CURRENCY_TOKEN = re.compile(r"(ج\.?م|egp|usd|eur|درهم|£|€|\$)", re.IGNORECASE)
_EXCEL_SERIAL_BASE = date(1899, 12, 30)
_EXCEL_MIN_SERIAL = 20000
_EXCEL_MAX_SERIAL = 80000

_NON_NUMERIC = re.compile(r"[^0-9.]")

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%d.%m.%Y",
)


def normalize_uuid(value: Any) -> Optional[str]:
    """Return a canonical lower-case dashed UUID or None if invalid."""
    text = str(value or "").strip()
    if not text:
        return None
    cleaned = text.lower().replace("{", "").replace("}", "").replace("\u2011", "-")
    try:
        parsed = uuidlib.UUID(cleaned)
    except (ValueError, AttributeError):
        return None
    return str(parsed)


def _clean_money_text(value: str) -> str:
    text = _CURRENCY_TOKEN.sub("", value)
    text = text.strip()
    if not text:
        return ""

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    elif text.startswith("-"):
        negative = True
        text = text.lstrip("-")

    has_dot = "." in text
    has_comma = "," in text
    if has_dot and has_comma:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif has_comma:
        after = text[text.rfind(",") + 1:]
        if len(after) in (1, 2) and after.isdigit():
            text = text.replace(",", ".")
        else:
            text = text.replace(",", "")

    text = _NON_NUMERIC.sub("", text)
    return f"-{text}" if text and negative else text


def parse_money(value: Any) -> Optional[Decimal]:
    """Parse a money value to a 2-place Decimal, or None when invalid."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        return value.quantize(_MONEY_QUANTIZE, rounding=ROUND_HALF_UP)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return Decimal(str(value)).quantize(_MONEY_QUANTIZE, rounding=ROUND_HALF_UP)

    text = _clean_money_text(str(value))
    if not text:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    return number.quantize(_MONEY_QUANTIZE, rounding=ROUND_HALF_UP)


def parse_quantity(value: Any) -> Optional[Decimal]:
    """Parse a quantity value to a 4-place Decimal, or None when invalid."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        return value.quantize(_QUANTITY_QUANTIZE, rounding=ROUND_HALF_UP)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return Decimal(str(value)).quantize(_QUANTITY_QUANTIZE, rounding=ROUND_HALF_UP)

    text = _clean_money_text(str(value))
    if not text:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    return number.quantize(_QUANTITY_QUANTIZE, rounding=ROUND_HALF_UP)


def _parse_excel_serial_number(value: Any) -> Optional[date]:
    if isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        serial = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if _EXCEL_MIN_SERIAL <= serial <= _EXCEL_MAX_SERIAL and serial.is_integer():
        return _EXCEL_SERIAL_BASE + timedelta(days=int(serial))
    return None


def _parse_date_value(value: Any) -> Optional[date]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    serial_date = _parse_excel_serial_number(value)
    if serial_date:
        return serial_date

    text = str(value).strip()
    if not text:
        return None
    if len(text) <= 5:
        serial_date = _parse_excel_serial_number(text)
        if serial_date:
            return serial_date

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    parts = re.split(r"[-/.]", text)
    if len(parts) == 3:
        try:
            year = int(parts[2])
            first = int(parts[0])
            second = int(parts[1])
            if second <= 12 and first > 12:
                return date(year, first, second)
        except ValueError:
            pass

    return None


def _parse_enum(value: Any, allowed) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().lower().replace(" ", "_")
    if text in allowed:
        return text
    return None


def _parse_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_row(
    row_number: int,
    values: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[ImportErrorInfo]]:
    """Normalize one parsed row into typed canonical values.

    Args:
        row_number: 1-based file row number (for error reporting).
        values: Mapping of canonical field name to a raw cell value.
            Values that are ``None`` or blank are treated as absent.

    Returns:
        A ``(normalized, errors)`` tuple. ``normalized`` contains the
        canonical fields that could be converted; fields that failed are
        absent. ``errors`` holds a structured ImportErrorInfo per problem.
    """
    normalized: Dict[str, Any] = {}
    errors: List[ImportErrorInfo] = []

    for field_name in REQUIRED_FIELDS:
        if field_name not in values:
            errors.append(ImportErrorInfo(
                row_number=row_number,
                field=field_name,
                error_code=E_MISSING_FIELD,
                message=f"Missing required column '{field_name}'.",
            ))

    for field_name, spec in CONTRACT.items():
        raw = values.get(field_name)
        missing = raw is None or str(raw).strip() == ""

        if spec.kind == "string":
            parsed = _parse_string(raw)
            if missing and spec.required:
                errors.append(ImportErrorInfo(
                    row_number=row_number,
                    field=field_name,
                    error_code=E_MISSING_FIELD,
                    message=f"Missing required field '{field_name}'.",
                ))
            elif parsed is not None:
                normalized[field_name] = parsed
            elif spec.default is not None:
                normalized[field_name] = spec.default

        elif spec.kind == "uuid":
            if missing:
                continue
            parsed = normalize_uuid(raw)
            if parsed is None:
                errors.append(ImportErrorInfo(
                    row_number=row_number,
                    field=field_name,
                    error_code=E_INVALID_UUID,
                    message=f"'{raw}' is not a valid UUID.",
                ))
            else:
                normalized[field_name] = parsed

        elif spec.kind == "date":
            if missing:
                if spec.required:
                    errors.append(ImportErrorInfo(
                        row_number=row_number,
                        field=field_name,
                        error_code=E_MISSING_FIELD,
                        message=f"Missing required field '{field_name}'.",
                    ))
                continue
            parsed = _parse_date_value(raw)
            if parsed is None:
                errors.append(ImportErrorInfo(
                    row_number=row_number,
                    field=field_name,
                    error_code=E_INVALID_DATE,
                    message=f"'{raw}' is not a valid date (expected YYYY-MM-DD).",
                ))
            else:
                normalized[field_name] = parsed

        elif spec.kind == "money":
            if missing:
                if spec.required:
                    errors.append(ImportErrorInfo(
                        row_number=row_number,
                        field=field_name,
                        error_code=E_MISSING_FIELD,
                        message=f"Missing required field '{field_name}'.",
                    ))
                elif spec.default is not None:
                    normalized[field_name] = spec.default
                continue
            parsed = parse_money(raw)
            if parsed is None:
                errors.append(ImportErrorInfo(
                    row_number=row_number,
                    field=field_name,
                    error_code=E_INVALID_MONEY,
                    message=f"'{raw}' is not a valid monetary amount.",
                ))
            else:
                normalized[field_name] = parsed

        elif spec.kind == "quantity":
            if missing:
                if spec.required:
                    errors.append(ImportErrorInfo(
                        row_number=row_number,
                        field=field_name,
                        error_code=E_MISSING_FIELD,
                        message=f"Missing required field '{field_name}'.",
                    ))
                elif spec.default is not None:
                    normalized[field_name] = spec.default
                continue
            parsed = parse_quantity(raw)
            if parsed is None:
                errors.append(ImportErrorInfo(
                    row_number=row_number,
                    field=field_name,
                    error_code=E_INVALID_QUANTITY,
                    message=f"'{raw}' is not a valid quantity.",
                ))
            else:
                normalized[field_name] = parsed

        elif spec.kind == "enum":
            if missing:
                if spec.required:
                    errors.append(ImportErrorInfo(
                        row_number=row_number,
                        field=field_name,
                        error_code=E_MISSING_FIELD,
                        message=f"Missing required field '{field_name}'.",
                    ))
                elif spec.default is not None:
                    normalized[field_name] = spec.default
                continue
            parsed = _parse_enum(raw, spec.allowed)
            if parsed is None:
                errors.append(ImportErrorInfo(
                    row_number=row_number,
                    field=field_name,
                    error_code=E_INVALID_ENUM,
                    message=(
                        f"'{raw}' is not a valid {field_name}. "
                        f"Expected one of: {', '.join(sorted(spec.allowed))}."
                    ),
                ))
            else:
                normalized[field_name] = parsed

    return normalized, errors