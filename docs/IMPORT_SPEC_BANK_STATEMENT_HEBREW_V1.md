# Money App — Import Spec: Israeli Bank Statement Export (v0.0.1)

Source file analyzed: `report__2025-12-05__2026-06-13.xlsx`  
Generated from structure only. Sensitive names/account details are intentionally excluded.

## 1. File type

- Format: `.xlsx`
- Workbook sheets: one sheet, `Sheet1`
- Used range: `A1:I60` in the provided sample
- Statement type: bank current account / checking account movements, not credit-card itemized transactions

## 2. Layout

Rows before the header contain report metadata:

- Row 1: blank
- Row 2: report title
- Row 3: account + export timestamp metadata
- Row 4: account type metadata
- Row 5: report date range metadata
- Row 6: actual table header
- Row 7 onward: transaction rows

The importer should detect the header row by looking for the Hebrew column names, not by assuming row 6 forever.

## 3. Raw columns

| Excel column | Hebrew header | Meaning | Required | Notes |
|---|---|---|---|---|
| A | empty | unused | no | Ignore |
| B | יתרה | Balance after transaction | no | Can be blank in some rows. Do not require it. |
| C | תאריך ערך | Value date | yes | Format: `DD/MM/YYYY` |
| D | זכות | Credit amount | yes, but see placeholder logic | Incoming money / positive signed amount |
| E | חובה | Debit amount | yes, but see placeholder logic | Outgoing money / negative signed amount |
| F | תיאור | Description | yes | Raw counterparty/operation description |
| G | אסמכתא | Reference | recommended | Useful for deduplication |
| H | סוג פעולה | Operation type | recommended | Bank operation code |
| I | תאריך | Posted/transaction date | yes | Format: `DD/MM/YYYY` |

## 4. Amount parsing rule

In the provided export, the unused side of the credit/debit pair appears as `15`.
For example:

- Credit transaction: credit column has a real amount, debit column is `15`
- Debit transaction: debit column has a real amount, credit column is `15`

Do **not** blindly hardcode `15` forever. Implement a file-profile detector:

1. For the current file, inspect columns `זכות` and `חובה`.
2. If one side is `15` in nearly every row where the other side has a non-15 amount, treat `15` as the empty-side placeholder for this file profile.
3. If both sides are non-empty/non-placeholder, mark the row as ambiguous and require review.
4. If the real transaction amount is exactly `15`, use a fallback:
   - balance delta if available,
   - operation type,
   - or manual review.

Canonical normalized amount:

- `amount_minor` is signed integer minor units.
- Credit / incoming = positive.
- Debit / outgoing = negative.
- Store `direction` as `credit` or `debit`.
- Store `currency` as `ILS` unless the file explicitly includes another currency.

Examples:

- Credit 500.00 NIS → `amount_minor = 50000`, `direction = credit`
- Debit 149.00 NIS → `amount_minor = -14900`, `direction = debit`

## 5. Date parsing

- Parse both `תאריך` and `תאריך ערך` as `DD/MM/YYYY`.
- Store dates as date-only values.
- Use UTC timestamps only for imported-at / created-at metadata.
- Prefer `תאריך` as `posted_date`.
- Store `תאריך ערך` as `value_date`.

## 6. Normalized transaction fields

Recommended normalized transaction object:

```json
{
  "source": "bank_statement_import",
  "account_id": "...",
  "import_batch_id": "...",
  "posted_date": "YYYY-MM-DD",
  "value_date": "YYYY-MM-DD",
  "amount_minor": -14900,
  "currency": "ILS",
  "direction": "debit",
  "raw_description": "...",
  "normalized_counterparty": "...",
  "reference": "...",
  "operation_type": "...",
  "balance_after_minor": 221459,
  "category_id": "...",
  "dedup_hash": "..."
}
```

## 7. Deduplication

Build `dedup_hash` from stable normalized values:

```text
user_id
account_id
posted_date
value_date
amount_minor
normalized_description
reference
operation_type
```

Do not use the row number in the hash.

Normalize before hashing:

- Trim whitespace
- Collapse repeated spaces
- Normalize Hebrew quotes and punctuation when practical
- Remove invisible characters
- Keep digits in reference/operation type

## 8. Category strategy for this file type

This file is a bank account statement. It usually does **not** contain the true final merchant for card purchases.
For example, it may show a monthly credit-card payment rather than each restaurant/store purchase.

Therefore, use bank-statement categories such as:

- Income
- Incoming transfer
- Outgoing transfer
- Credit card payment
- Loan payment
- Interest / bank fee
- Cash deposit / cash withdrawal
- Other bank movement

Do not classify a credit-card bill as normal spending like Restaurants, Shopping, Groceries, etc.
When credit-card itemized files are imported later, mark the bank-level credit-card payment as `transfer_or_card_settlement` / excluded from spending totals to avoid double-counting.

## 9. Merchant / counterparty normalization

For bank statements, the better term is `counterparty` or `payee`, not always `merchant`.

Normalization v1:

1. Trim whitespace.
2. Collapse repeated spaces.
3. Remove account/reference suffixes where clearly operational.
4. Map known credit-card settlement descriptions to a canonical counterparty:
   - Isracard-style settlement → `Credit Card Statement Payment`
   - Max/other card settlement → `Credit Card Statement Payment`
5. Map loan repayment descriptions to `Loan Payment`.
6. Keep the raw description unchanged in `raw_description`.

## 10. Import preview requirements

After parsing, show:

- Total rows parsed
- Imported transactions count
- Duplicates skipped
- Ambiguous rows needing review
- Uncategorized rows
- Detected file profile: `bank_statement_hebrew_v1`
- Date range detected
- Credit/debit totals, but only in the local UI, not logs

## 11. Logging and privacy

Never log:

- Raw account metadata
- Full raw descriptions
- Amounts tied to identity
- Full file contents
- Full filenames if they contain PII

Safe logs:

- import_batch_id
- row_count
- duplicate_count
- ambiguous_count
- file_profile
- success/failure status

## 12. v0.0.1 implications

This file is sufficient for building:

- Excel import pipeline
- Header detection
- Column mapping
- Date/amount parsing
- Bank-statement transaction persistence
- Basic cash-flow dashboard
- Credit/debit totals
- Bank-level categories
- Category correction rules

This file is **not sufficient** for building accurate consumer spending categories like restaurants, groceries, shopping, transport, etc. For that, an itemized credit-card export is needed later.
