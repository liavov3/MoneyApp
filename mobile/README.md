# MoneySaver — Mobile (Expo / React Native)

First slice: **App foundation + read-only Home Dashboard** (Hebrew RTL, dark
premium). Renders real data from `GET /api/v1/home` (+ `GET /api/v1/categories`
for Hebrew category labels). Quick Add, editing, and recurring-template screens
are intentionally **not** built yet — the "הוספת הוצאה" button is a placeholder.

## Run

### Expo Go compatibility

The app uses **Expo SDK 57**. Use an Expo Go installation that supports SDK 57.
For a physical phone, connect it to the computer's Wi-Fi, set
`EXPO_PUBLIC_API_URL` to the computer's LAN address on port 8000, and start the
backend from `backend/` with
`.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000`.
Then run `npm start` from `mobile/` and scan the QR code. The backend health
endpoint is `/api/v1/health`.

After changing SDK versions, restart Expo with `npx expo start --clear` and
reopen the project in Expo Go so the old bundle is not reused.

```bash
cd mobile
npm install
# point the app at your running backend:
cp .env.example .env   # then edit EXPO_PUBLIC_API_URL
npm start              # open in Expo Go (press a / i, or scan the QR)
```

- **Backend URL** — set `EXPO_PUBLIC_API_URL` in `.env`. Simulator on the same
  machine: `http://localhost:8000`. Physical device / Android emulator: your
  machine's LAN IP (e.g. `http://192.168.1.20:8000`).
- **Auth token** — the backend uses a static dev bearer token. On first launch
  the app shows a token gate; paste the token once and it is kept in the device
  SecureStore. It is never committed or logged. A `401` clears it and returns to
  the gate.

## Checks

```bash
npm run typecheck   # tsc --noEmit
```

## Layout

```
mobile/
  App.tsx                     # RTL setup + gate/home routing
  src/
    api.ts                    # fetch client + SecureStore token
    types.ts                  # GET /home + /categories shapes (no invented fields)
    format.ts                 # agorot -> ₪, date helpers
    theme.ts                  # dark-premium tokens
    components/ui.tsx         # Card / Button / AppText / Loading
    screens/HomeScreen.tsx    # the dashboard (actual vs planned separated)
    screens/TokenGateScreen.tsx
```
