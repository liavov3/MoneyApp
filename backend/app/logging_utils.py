"""Privacy-safe logging utility.

The default-and-only sanctioned log shape carries IDs, counts, and enum names —
NEVER merchant text, amounts, notes, raw input, correction content, emails,
tokens, or any PII (DATABASE_SCHEMA §11; API_CONTRACT §4/§15; QA-10-*).

`log_event` is the single entry point so the safe pattern is the default. It
accepts ONLY an allow-list of safe keys; any other keyword is dropped (and a
generic warning is emitted) rather than risking a content leak.

Duration is always emitted as a coarse BUCKET, never a precise timing tied to
content (QA-10-09).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Final

_LOGGER_NAME: Final = "money_app"

# Keys that are safe to log. Anything outside this set is refused.
_ALLOWED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "request_id",
        "endpoint",
        "method",
        "status",
        "duration_bucket",
        "validation_error_code",
        "confidence_level",
        "match_type",
        "rule_source",
        "transaction_type",
        "source",
        "cadence",
        "row_count",
        "count",
        # Opaque uuid identifiers only (never email/token).
        "user_id",
        "transaction_id",
        "merchant_id",
        "alias_id",
        "category_id",
        "rule_id",
        "template_id",
        # Presence booleans (e.g. whether a name exists) — never the value.
        "name_present",
        "db_reachable",
        "event",
    }
)


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)


def configure_logging(level: str = "INFO") -> None:
    """Configure the app logger once, with a plain structured formatter."""
    logger = get_logger()
    if logger.handlers:  # idempotent
        logger.setLevel(level.upper())
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(level.upper())
    logger.propagate = False


def duration_bucket(seconds: float) -> str:
    """Coarse duration bucket: '<2s' | '2-5s' | '>5s' (QA-10-09)."""
    if seconds < 2.0:
        return "<2s"
    if seconds <= 5.0:
        return "2-5s"
    return ">5s"


def log_event(event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    """Emit one privacy-safe structured log line.

    Only allow-listed keys are serialized. Unknown keys are dropped to prevent
    accidental PII leakage; their presence triggers a generic warning that
    names the offending KEY only (never its value).
    """
    logger = get_logger()
    safe: dict[str, Any] = {"event": event}
    rejected: list[str] = []
    for key, value in fields.items():
        if key in _ALLOWED_KEYS:
            safe[key] = value
        else:
            rejected.append(key)
    if rejected:
        logger.warning("dropped_unsafe_log_keys keys=%s", json.dumps(sorted(rejected)))
    logger.log(level, json.dumps(safe, ensure_ascii=True, sort_keys=True))
