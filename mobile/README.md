# MoneySaver — Mobile (Expo / React Native)

First slice: **App foundation + read-only Home Dashboard** (Hebrew RTL, dark
premium). Renders real data from `GET /api/v1/home` (+ `GET /api/v1/categories`
for Hebrew category labels). Quick Add, editing, and recurring-template screens
are intentionally **not** built yet — the "הוספת הוצאה" button is a placeholder.

## Run

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
