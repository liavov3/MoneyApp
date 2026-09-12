# MoneyApp quality improvements

Requested: September 13, 2026. Preserve the current app in Git, fix discovered
errors, and implement useful improvements to the manual-first product.

## Checkpoint

Existing work saved and pushed as `4e65acd` on `main` before new implementation.

## Confirmed issues and planned work

- Home derives income/net and savings-goal progress from the first 100 rows.
  Replace these with complete, server-calculated totals.
- Home also labels every positive transaction as income, including refunds and
  positive adjustments. Keep these types distinct in the proposed aggregates;
  the net of recorded transactions is not a verified savings or bank balance.
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

- Resolved in the runtime-credential slice: `mobile/src/api.ts` previously read
  `EXPO_PUBLIC_API_TOKEN`, contrary to API section 3 and `backend/app/config.py`.
  The access code is now entered at runtime and saved using Expo SecureStore on
  native devices. The public-token setting is ignored. Distribution still needs
  native persistence/modal verification and appropriate server security; this
  remains the existing single-user personal-server model.
- Resolved in the current slice: API contract section 9 permits merchant edits,
  but the implementation previously ignored them. The backend now resolves an
  owned merchant id or merchant text using Quick Add's existing identity ladder;
  the transaction editor and mobile request types expose the documented edit.
  The frozen contract and schema files were not changed.
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

## Merchant editing and recovery slice

- PATCH merchant edits affect only the selected transaction. An explicitly
  supplied `merchant_id` wins over text, including null to clear the association.
  When only non-null `merchant_input` is supplied, the server resolves or creates
  the merchant using the existing trusted matching rules. Supplied input updates
  the private raw-input field; null clears that field without changing an omitted
  merchant association. Omitted fields remain unchanged. No category rule is
  created, and the public response still excludes raw input.
- The editor sends only an intentional merchant change. Clearing the field
  sends `merchant_id: null`; editing another field leaves merchant identity alone.
- Concurrent amount/type edits lock the transaction while computing its new
  signed amount, preserving a consistent final type and amount.
- Category fetches are shared across mounted screens. A failed load offers an
  explicit retry; recovery updates all consumers and preserves the entry draft.
- Home ignores superseded month requests, including their errors and loading
  state. This does not resolve the separate capped income/net aggregate issue.
- Malformed non-ASCII bearer bytes return unauthorized instead of raising a
  comparison error. This does not replace the development-token setup.

Verification for this slice:

- Targeted transaction PATCH tests: 25 passed, database connected.
- Malformed bearer tests: 5 passed.
- Mobile regressions: 14 passed, zero skipped; TypeScript passed.
- Production web, iOS, and Android exports passed.
- Synthetic browser/API checks: merchant replacement and clearing preserved
  amount, type, category, date, note, and creation time. Category recovery restored
  all 14 choices while retaining a typed 12.34 amount. After switching back to
  September, a delayed August response did not overwrite September's exact
  12524-agorot actual spending or its separately displayed 5000-agorot projection.
- Full backend suite: 273 passed, zero skipped, database connected (724.94 s).
- The temporary browser preview was closed and its synthetic user/data removed.
- Native phone/simulator interaction checks remain unavailable in this run.

## Runtime credential slice

- Restores API section 3's existing rule that the bearer token must not be
  embedded in a mobile bundle. A masked connection form validates the code
  through the existing authenticated categories endpoint before saving it.
- Native credentials use Expo SecureStore with `WHEN_UNLOCKED_THIS_DEVICE_ONLY`,
  bound to the configured server URL. Web previews keep credentials in memory
  only. HTTPS is required outside localhost, loopback, and private LAN IPv4
  development addresses. URLs carrying credentials, queries, or fragments fail
  validation. The endpoint address remains non-secret build configuration.
- Explicit disconnection clears credentials, cached categories, and mounted
  financial screens. Erase failures are visible and retryable. Unauthorized
  responses cover all screens and sheets, showing one reconnection form on the
  topmost surface while keeping unsaved forms mounted underneath.
- Late responses cannot populate a new session or expire its replacement code.
  A write response crossing a session change remains ambiguous unless the server
  explicitly rejected authentication. No write is automatically retried.
- Backend auth, resource routes, ownership, payloads, database/schema, and frozen
  contract documents remain unchanged. Registration, token refresh/revocation
  endpoints, and biometric app locking are not introduced.
- Documentation follows Expo's [environment-variable guidance](https://docs.expo.dev/guides/environment-variables/)
  and [SecureStore behavior](https://docs.expo.dev/versions/latest/sdk/securestore/).

Verification:

- 29 mobile regressions passed, zero skipped: missing credentials, failed
  verification, secure-storage failures/retries, server binding, concurrent
  connection/removal, expiration, stale reads/401s, and ambiguous writes.
- TypeScript and production web/iOS/Android exports passed. A legacy public-token
  canary and its variable name were absent from all 44 exported files.
- Browser/API: incorrect code kept the app gated; a valid code opened Home.
  Expiration during Quick Add hid financial data and preserved a typed 43.21
  draft. Reconnection did not create a transaction; one explicit retry saved
  exactly -4321 agorot, raising actual spending from 12524 to 16845 agorot.
  Forgetting the connection returned to an empty, masked connection form.
- Refreshing an authenticated browser preview discarded its temporary code and
  returned to the empty connection form. No browser application errors remained.
- Full backend suite: 273 passed, zero skipped, database connected (727.81 s).
- The temporary preview was closed and its synthetic user/data removed.
- Real-device persistence, native modals, keyboard, and accessibility testing
  remain unavailable in this run.

## Verification and completion

Run the full database-connected backend suite for financial/cross-layer changes,
focused mobile regressions, TypeScript checks, and production mobile bundles.
Exercise changed UI flows in an available runtime. Verify exact amounts, refunds,
adjustments, ownership, month boundaries, more than 100 rows, request races,
duplicate/retry behavior, empty/error states, and Hebrew RTL. Record unavailable
checks honestly. Commit/push verified slices and check remote equality.

This document tracks intended work; it is not proof of completion.
