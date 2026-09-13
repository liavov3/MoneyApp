# MoneySaver mobile

Expo SDK 57 / React Native, with Hebrew copy, RTL layouts and a dark theme.

## Available flows

- The connection screen validates an access code against the personal server.
  Native builds save it in Expo SecureStore, bound to the configured server URL.
  Web previews retain it in memory only, until refresh or close.
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

Set only `EXPO_PUBLIC_API_URL` in mobile configuration. Enter the server's
`DEV_BEARER_TOKEN` value in the masked connection screen on first launch; never
put it in a public environment variable. The old `EXPO_PUBLIC_API_TOKEN` setting
is ignored and can be removed from local mobile configuration. Public servers
must use HTTPS; local development can use HTTP on localhost, loopback, or a
private LAN IPv4 address. URLs containing credentials, query strings, or fragments
are rejected.

Settings can forget the connection, removing the stored access code and closing
financial screens. This does not delete saved server transactions. If an access
code expires, the app covers every screen and open sheet until reconnection to
the same configured personal server; entered fields remain in memory and writes
are never automatically retried. Secure-storage read/write/erase failures remain
visible and recoverable. Forgetting the connection closes unsaved forms.

This remains the contract's single-user personal-server authentication model.
There is no account registration, server token refresh/revocation endpoint, or
biometric app lock. Native credential persistence and modal behavior still need
real-device verification before distribution.

Web preview dependencies are installed. `npm run web` starts the web client;
serve the API on the same origin or configure an appropriate development proxy.
Native Expo requests do not need browser CORS configuration.

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
