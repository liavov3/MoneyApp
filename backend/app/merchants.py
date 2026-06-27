"""Merchant text normalization (MERCHANT_NORMALIZATION_SPEC §4).

One deterministic function turns a user-typed merchant string into the
`normalized_merchant_name` matching key — reused everywhere (match, dedup, and
later alias/autocomplete) so the same input always collapses to the same key.

v0.0.1 manual-first pipeline (spec §4): strip invisible/bidi chars → NFC →
trim + collapse whitespace → case-fold Latin (Hebrew has no case, untouched).
That yields same-script identity for `exact`/`normalized_exact` auto-link
(§7) — "Golda"/"golda"/"  GOLDA " → `golda`. It deliberately does NOT fold
across scripts (`golda` != `גולדה`) or do fuzzy/typo matching: the safe
direction is a separate merchant, never a silent over-merge (§5, §12).

# ponytail: punctuation/dash/quote canonicalization (spec §4 step 6) is
# deferred — omitting it only ever yields a *separate* merchant (the safe,
# anti-over-merge direction), never a wrong merge. Add it if real friction.

Privacy: raw input AND the normalized key are sensitive — NEVER log either (§14).
"""

from __future__ import annotations

import re
import unicodedata

# Invisible / zero-width / bidi control chars (spec §4 step 3) — common in
# copy-paste and RTL text; they would otherwise break exact equality.
_INVISIBLE = re.compile("[​‌‍‎‏‪-‮⁠﻿]")


def clean_raw(raw: str) -> str:
    """Verbatim-preserving hygiene (spec §4 steps 3-4): strip invisibles + NFC.

    Keeps the user's case and original spacing — this is what is stored as
    `transactions.raw_merchant_input` (audit source of truth).
    """
    return unicodedata.normalize("NFC", _INVISIBLE.sub("", raw))


def display_form(raw: str) -> str:
    """Human-facing name: cleaned + trimmed + whitespace-collapsed, case kept."""
    return " ".join(clean_raw(raw).split())


def normalize_merchant_name(raw: str) -> str:
    """The matching/dedup key (spec §4): display form, case-folded. May be ''."""
    return display_form(raw).casefold()


if __name__ == "__main__":
    assert normalize_merchant_name("Golda") == "golda"
    assert normalize_merchant_name("  GOLDA  ") == "golda"
    assert normalize_merchant_name("Wolt  Tel   Aviv") == "wolt tel aviv"
    assert normalize_merchant_name("golda‎") == "golda"            # bidi stripped
    assert normalize_merchant_name("גולדה") == "גולדה"                   # Hebrew preserved
    assert normalize_merchant_name("Golda") != normalize_merchant_name("גולדה")  # no cross-script
    assert normalize_merchant_name("Golda") != normalize_merchant_name("Goldaa")  # no fuzzy
    assert display_form("  Golda  ") == "Golda"                          # case preserved
    assert normalize_merchant_name("   ") == ""                          # blank
    print("ok")
