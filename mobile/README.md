# MoneySaver mobile

Expo SDK 57 / React Native, with Hebrew copy, RTL layouts and a dark theme.

## Available flows

- Home shows actual spending and recurring projections separately, category
  totals, recent transactions, and monthly goals.
- Quick Add records expenses, income, or refunds. Amount is required; merchant,
  category, and date support quick entry with recent merchants and suggestions.
- History supports cursor pagination, category/uncategorized filters, and an
  all-months view. Failed page loads retain the entries already displayed.
- Transaction editing preserves untouched fields, refund categories and types,
  and negative adjustments. The current API cannot change negative adjustment
  amounts; the editor explains this instead of reversing their sign.
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

The current development client uses `EXPO_PUBLIC_API_TOKEN` from local config.
It has no sign-in screen. Expo public variables become part of the client bundle;
this existing development setup is not suitable for distributing real credentials.
See `docs/QUALITY_IMPROVEMENTS.md` for the tracked auth-contract disagreement.

Web preview dependencies are installed. `npm run web` starts the web client;
serve the API on the same origin or configure an appropriate development proxy.
Native Expo requests do not need browser CORS configuration.

## Verification

```powershell
npm run typecheck
npm test
npx expo export --platform ios --platform android
```

The regression tests run the actual pure TypeScript money/edit helpers and API
client through Node's test runner. They do not replace device testing. Browser
previews can exercise shared screens; native keyboard, safe-area, accessibility,
and RTL behavior still need a phone or simulator.

## Known work in progress

Home income/net totals and related goal progress still use a capped transaction
page. Complete server aggregates require the proposed frozen-contract revision.
Offline synchronization and text search are also proposed, not implemented.
