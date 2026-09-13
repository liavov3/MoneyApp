# Private MoneySaver on iPhone — free hosting

## What is included

The repository contains an installable Expo web export, private username/password
login, same-origin HttpOnly cookie sessions, and a free Render Docker Blueprint.
The existing Neon database remains the source of truth. Deployment has no public
signup, analytics, advertising, third-party scripts, or client-side data cache.

This is a Home Screen web app, not an App Store binary. It needs internet.
Render's free server sleeps after 15 minutes idle and can take about a minute
to wake. Free hosting is subject to provider quotas; verify Render and Neon are
on free plans before deployment. A provider subdomain is sufficient.

## 1. Set up the private owner locally

From `backend/`, using the existing ignored `.env` database configuration:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.owner_setup
```

Open `http://127.0.0.1:8766` on this computer. Choose a username and a unique
password/passphrase of at least 15 characters. The helper is bound to loopback,
checks Host, Origin, and a per-process nonce, and only permits initial creation.
It stores an Argon2id hash, not the password. Stop the helper after completion.

`OWNER_USER_ID` must identify the existing owner whose transactions should remain
accessible. It defaults to the original seeded user; if local `DEV_USER_ID` was
customized, explicitly set `OWNER_USER_ID` to that same existing ID before setup
and on Render. Creating a new login does not move or rewrite financial records.

For recovery, run `python -m app.manage_auth --reset` locally. This replaces the
login and revokes all sessions. There is intentionally no public reset endpoint.
Never submit passwords or database connection strings in chat or commit them.

## 2. Deploy the free service

1. Sign in to Render and connect only the MoneyApp repository if GitHub access
   is needed. Keep the source repository's existing visibility.
2. Create a Blueprint using this repository's `render.yaml` on the reviewed
   commit. It specifies exactly one **Free** web service in Frankfurt, no paid
   disk, and no Render Postgres database.
3. Set `DATABASE_URL` in Render's secret environment to the same owner's Neon
   connection string. Do not set `DEV_BEARER_TOKEN`, passwords, or credentials
   in any `EXPO_PUBLIC_*` variable. Confirm `OWNER_USER_ID` matches local setup.
4. Deploy. The multi-stage Docker build excludes local secrets, builds the
   web app, installs the backend, and runs as a non-root user. Startup validates
   production configuration and applies migrations before accepting requests.
5. Render supplies `RENDER_EXTERNAL_HOSTNAME`; the server derives its allowed
   HTTPS origin from it. If using a custom domain, explicitly set `PUBLIC_ORIGIN`
   to that exact HTTPS origin. Use only one canonical browser origin.

Automatic deployment is off so an unreviewed push cannot replace the live app.
To update, choose a tested commit and deploy it manually. Do not run the test
suite against a live personal database; use a dedicated Neon test branch once
the app is in everyday use.

## 3. Verify before everyday use

- In a signed-out browser, `/api/v1/transactions` must return 401.
- Login succeeds only for the configured owner; no access code is requested.
- Refresh retains login; logout revokes the session and refresh stays signed out.
- The production cookie has Secure, HttpOnly, SameSite=Strict and no Domain.
- Save an intentional small test entry, confirm it, then delete that test entry.
- Check the API uses HTTPS and no requests go to a local computer address.
- Confirm your existing records are visible under the owner account.

In Safari: open the deployment URL, Share → Add to Home Screen → Open as Web App
→ Add. Sign in from the installed app if Safari and the Home Screen app have
separate storage on your iOS version. No Expo Go or running computer is needed.

## Privacy boundary

The login controls access to financial data. Sessions and API responses are not
stored in JavaScript-accessible persistent storage or service-worker caches.
The application logs only route templates, status codes, request IDs and coarse
timing. HTTPS protects traffic; the app has no third-party analytics.

This is not end-to-end encryption: Render runs the server and Neon stores the
database. Provider administrators and anyone with your hosting/database account
credentials may be able to access data. Provider-level logs and retention are
governed by those services. Protect both accounts and retain an appropriate
database backup outside this deployment; free-plan restore windows are limited.

References: [Render free services](https://render.com/docs/free),
[Render Blueprint reference](https://render.com/docs/blueprint-spec),
[Neon plans](https://neon.com/pricing),
[Apple Home Screen web apps](https://support.apple.com/en-mide/guide/iphone/iphea86e5236/ios).
