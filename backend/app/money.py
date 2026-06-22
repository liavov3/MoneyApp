"""Money normalization at the API boundary (API_CONTRACT §14).

Decimal-only parsing of a major-unit amount (shekels) into signed integer
agorot (`amount_minor`). NEVER uses binary float math — JSON numbers are routed
through their string form before `Decimal`, so values like `33.555` keep their
exact 3-decimal shape and are rejected rather than silently rounded.

Rules (API_CONTRACT §14):
- at most 2 decimal places; more → `too_many_decimals` (never rounded);
- zero → `zero_amount`;
- negative input → `negative_amount` (the client always sends a magnitude;
  the sign is applied server-side from `transaction_type`);
- `expense` stores NEGATIVE agorot; `income`/`refund`/`adjustment` POSITIVE.

Raises `AppError("validation_error", field_errors=[...])` (HTTP 422) with a
generic, content-free message — the offending amount value is never echoed or
logged.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.errors import AppError

# transaction_type -> stored sign (schema §5 / API_CONTRACT §14).
_NEGATIVE_TYPES = {"expense"}

_MESSAGES = {
    "empty_amount": "Enter an amount.",
    "invalid_amount": "Enter a valid amount.",
    "negative_amount": "Enter a positive amount.",
    "too_many_decimals": "Amount can have at most 2 decimal places.",
    "zero_amount": "Enter an amount above 0.",
}


def _amount_error(code: str) -> AppError:
    return AppError(
        code="validation_error",
        field_errors=[
            {"field": "amount", "code": code, "message": _MESSAGES[code]}
        ],
    )


def _to_decimal(raw: object) -> Decimal:
    """Convert an accepted JSON value to Decimal via its string form (no float)."""
    if raw is None:
        raise _amount_error("empty_amount")
    # bool is an int subclass — reject it explicitly (True/False is not money).
    if isinstance(raw, bool):
        raise _amount_error("invalid_amount")
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            raise _amount_error("empty_amount")
    elif isinstance(raw, int):
        s = str(raw)
    elif isinstance(raw, float):
        # Route through repr so e.g. 33.50 -> "33.5" exactly (round-trip repr),
        # never the binary-float expansion.
        s = repr(raw)
    else:
        raise _amount_error("invalid_amount")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise _amount_error("invalid_amount") from None
    if not d.is_finite():
        raise _amount_error("invalid_amount")
    return d


def parse_amount_to_minor(raw: object, transaction_type: str = "expense") -> int:
    """Parse a major-unit amount into signed integer agorot.

    Order of checks mirrors API_CONTRACT §14: negative, then decimal places,
    then zero. Returns the signed `amount_minor` (expense negative).
    """
    d = _to_decimal(raw)

    if d < 0:
        raise _amount_error("negative_amount")
    if d.as_tuple().exponent < -2:
        raise _amount_error("too_many_decimals")
    if d == 0:
        raise _amount_error("zero_amount")

    # Exact: d has at most 2 decimal places, so d*100 is an integer.
    magnitude = int((d * 100).to_integral_value())
    sign = -1 if transaction_type in _NEGATIVE_TYPES else 1
    return sign * magnitude
