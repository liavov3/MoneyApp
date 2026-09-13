# MoneySaver mobile

Expo SDK 57 / React Native, with Hebrew copy, RTL layouts and a dark theme.

## Available flows

- The opening screen signs in to a private owner account with username/password.
  Native sessions use Expo SecureStore; web sessions use an HttpOnly cookie that
  survives refresh. The password is never persisted by app code. There is no
  public registration and no access-code prompt.
- Home shows actual spending and recurring projections separately, category
  totals, recent transactions, and monthly goals.
- Quick Add records expenses, income, or refunds. Amount is required; merchant,
  category, and date support quick entry with recent merchants and suggestions.
- History supports cursor pagination, category/uncategorized filters, and an
  all-months view. Failed page loads retain the entries already displayed.
- Transaction editing preserves untouched fields, refund categories and types,
  and negative adjustments. The current API cannot change negative adjustment
  amounts; the editor explains this instead of reversing their sign.
- A transaction's merchant can be changed or cleared without renaming the
  merchant on other transactions or silently changing the category.
- Failed category loads offer a retry that keeps the current entry draft.
  Switching months ignores delayed responses for previously selected months.
- Quick Add returns to the app with a saved-entry card offering another entry,
  edit, or undo. Same-day duplicate-looking entries and amounts at or above
  10,000 show advisory notes after saving. Confirming a large amount or dismissing
  the card keeps the entry; undo removes
  only the new entry. A lost undo response stays visible and can be retried for
  that same entry without resubmitting the expense.
- After saving a categorized merchant, Quick Add can offer to remember that
  category for future entries. Remember requires an explicit tap; Not now leaves
  the saved transaction alone. Repeated Other expenses first offer a better
  category, applied to this saved entry and future suggestions only. Earlier
  transactions are never recategorized by this flow. Generic payees and merchants
  with an active exact rule do not trigger the offer. Failed confirmations remain
  retryable without resubmitting the expense or automatically repeating a write.
- Recurring commitments can be created, edited, deactivated, and deleted.
  Editing unrelated details preserves the existing expected date.
- Expense, income, and savings goals support defaults and month overrides.

## Run locally

Run the backend from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Run mobile commands from `mobile/`:

```powershell
npm install
npm start
```

Use an Expo Go version supporting SDK 57. On a phone, use the computer's LAN
address for `EXPO_PUBLIC_API_URL` and connect to the same network. Configure local
values in ignored `mobile/.env`; restart Expo after changing them. The health
endpoint is `/api/v1/health`.

Set only `EXPO_PUBLIC_API_URL` in native mobile configuration. Provision a
username/password through the local backend setup page (see
[private deployment](../docs/PRIVATE_DEPLOYMENT.md)). The old
`EXPO_PUBLIC_API_TOKEN` setting is ignored and can be removed. Public servers
must use HTTPS; local development can use HTTP on localhost, loopback, or a
private LAN IPv4 address. URLs containing credentials, query strings, or fragments
are rejected.

Settings signs out by revoking the server session before removing the stored
connection and closing financial screens. Failed logout stays visible and
retryable. An expired session covers screens and open sheets until sign-in;
drafts remain in memory, and writes are never automatically retried. Native
credential persistence still needs real-device verification. Remembered sessions
expire after 30 days; resetting the password revokes all sessions immediately.

For web, run `npm run build:web`, set `WEB_DIST_DIR` on the backend to the
absolute `mobile/dist` path, and open the backend address. Web always uses the
same origin for API calls. The manifest and Apple touch icon support Add to Home
Screen. There is no service worker, offline data cache or offline write queue.
The Docker build serves this export and FastAPI together. Native Expo requests
do not need browser CORS configuration.

## Verification

```powershell
npm run typecheck
npm test
npx expo export --platform ios --platform android
```

The regression tests run the actual TypeScript money/edit helpers, shared
category and session stores, and API client through Node's test runner. They do
not replace device testing. Browser previews can exercise shared screens;
native keyboard, safe-area, accessibility,
and RTL behavior still need a phone or simulator.

## Known work in progress

Home income/net totals and related goal progress still use a capped transaction
page. Complete server aggregates require the proposed frozen-contract revision.
Offline synchronization and text search are also proposed, not implemented.
