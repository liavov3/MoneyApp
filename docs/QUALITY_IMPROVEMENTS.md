# MoneyApp quality improvements

Requested: September 13, 2026. Preserve the current app in Git, fix discovered
errors, and implement useful improvements to the manual-first product.

## Checkpoint

Existing work saved and pushed as `4e65acd` on `main` before new implementation.

## Confirmed issues and planned work

- Home derives income/net and savings-goal progress from the first 100 rows.
  Replace these with complete, server-calculated totals.
- Transaction history ignores `next_cursor`. Implement complete paginated history,
  existing category/uncategorized filters, and explicit retry for page failures.
- Editing a refund clears its category, and sending an untouched negative
  adjustment as a positive magnitude can reverse its sign. Send only changed
  fields and retain the exact transaction type and unchanged signed adjustment
  amount. Changing a negative adjustment amount is unsupported by the current
  API and must fail with a clear message rather than reverse the sign.
- Editor saving state is retained across openings. Reset per record; ignore stale
  loads and prevent concurrent save/delete operations.
- Decimal validation accepts unsafe integer magnitudes. Reject imprecise input;
  display precise field errors from the API.
- Test connection, app connection, and migration connection can target different
  databases when TEST_DATABASE_URL is set. Align the test suite on one target.
- Settings and mobile README describe an older app. Update them to match the
  actual runtime and supported flows.

## Proposed contract revision (awaiting explicit approval)

The frozen API and schema remain unchanged until approval. Proposed additions:

1. Home: add `income_received_minor`, `refunds_received_minor`,
   `adjustments_net_minor`, and signed `recorded_net_minor`, from the complete
   selected month's owned manual, non-settlement transactions. Income is only
   `transaction_type=income`; refunds remain separate. For expenses, refunds,
   and adjustments, include consumer-spending categories or uncategorized rows;
   exclude bank-movement categories. Keep existing gross actual spend unchanged.
   `recorded_net_minor = income + refunds + adjustments - spent_so_far_minor`.
   This is the net of recorded activity, not a bank balance or verified savings.
   Recurring projections remain separate. Fetch one consistent database snapshot.
2. Transaction search: optional `query` (literal substring, at most 100 characters)
   and `transaction_type` filters on GET /transactions, composed with existing
   month/category filters and cursor pagination. Search merchant name/note only
   within the authenticated user's rows; never log the query.
3. Reliable offline entry: optional client-generated UUID `client_request_id` on
   Quick Add, unique per user, with stored original request identity and response.
   Retrying the identical request returns the original result; changing its
   payload returns a generic conflict. Persist pending entries securely on the
   device, show unsynced status, and remove them only after confirmed success.
   Deleting a saved transaction must not allow an old retry to recreate it.
   This requires a documented migration for durable idempotency receipts.

## Product sequence

Fix correctness and recovery first. Add full-history search/filtering and fast
refund entry, then offline capture once the idempotency contract is approved.
Add an understandable monthly review using authoritative server totals, plus
user-controlled export and privacy settings where supported. Keep Quick Add's
normal path short and keep all predictions explicitly separate from actuals.

## Additional contract disagreements found during inspection

- `mobile/src/api.ts` uses `EXPO_PUBLIC_API_TOKEN`, which becomes part of the
  distributed client bundle. API contract section 3 and `backend/app/config.py`
  explicitly say the dev bearer token must not be in a mobile bundle. A secure
  credential setup/session flow is required before distribution. The earlier
  README's SecureStore token-gate description did not match the implementation.
- API contract section 9 permits merchant edits, while `PatchRequest` and
  `_EDITABLE_FIELDS` in `backend/app/routers/transactions.py` omit them. Mobile
  deliberately renders the merchant read-only. Implement the documented merchant
  edit flow in a subsequent aligned slice; do not silently rewrite the contract.
- `backend/app/routers/monthly_goals.py` and migrations 0004/0005 implement
  defaults and month overrides for three goal types outside the frozen API/schema
  files. Reconcile this pre-existing extension as part of contract review.

## Verification evidence so far

- Checkpoint backend: 246 passed, zero skipped, connected to configured Postgres.
- Money/date boundary regressions: 14 passed.
- Full post-change backend suite: 260 passed, zero skipped, database connected.
- Mobile money/edit/API regressions: 10 passed, including stalled-response timeout
  and preventing automatic retries after ambiguous write failures.
- TypeScript and production web/iOS/Android exports passed.
- Synthetic browser preview: reached the oldest row in a 125-entry month;
  uncategorized filter showed its empty state; note-only refund edit verified
  through the API retained `refund`, `groceries`, and exactly 3350 agorot.
- Decimal-comma refund entry saved exactly 1234 agorot through the UI/API.
- Renaming a recurring commitment through the UI preserved its original date
  and signed amount of -5000 agorot.
- Compatible dependency updates removed the high-severity and browser-mapping
  findings. Eleven moderate findings remain in Expo's build-tool dependency
  chain; the suggested forced fixes change major SDK versions and were not used.

Final TypeScript checks and production web/iOS/Android exports passed after the
last changes. Native on-device interaction testing has not been performed.
The requested complete aggregate/search/offline contract revision is still
awaiting approval. The overall improvement goal is not complete.

## Verification and completion

Run the full database-connected backend suite for financial/cross-layer changes,
focused mobile regressions, TypeScript checks, and production mobile bundles.
Exercise changed UI flows in an available runtime. Verify exact amounts, refunds,
adjustments, ownership, month boundaries, more than 100 rows, request races,
duplicate/retry behavior, empty/error states, and Hebrew RTL. Record unavailable
checks honestly. Commit/push verified slices and check remote equality.

This document tracks intended work; it is not proof of completion.
