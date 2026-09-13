# Private installation and authentication v0.0.2

Authorized by the owner's request on 2026-09-13 to publish the personal app
privately, introduce login, and remove the access-code screen. This additive
revision supersedes only the local/dev authentication assumption in
API_CONTRACT_V0_0_1 §3 and its deferred authentication scope in §16. The frozen
financial API and schema files remain unchanged.

## End-to-end trace and scope

Previously: the connection screen accepted a static bearer token, native
SecureStore persisted it, web kept it in memory, and `require_principal`
compared it to server configuration before resolving `dev_user_id`. Every
resource route already filters by the server-resolved user. There was no
password account, revocable session, browser cookie, or hosted web build.

Now: an operator provisions exactly the configured owner's account locally.
The login form sends username/password over HTTPS; the server verifies an
Argon2id password hash and issues a random, revocable session. No public signup
or password-reset endpoint exists. Provisioning preserves the existing owner's
user ID and financial data. Resource payloads and ownership-as-404 are unchanged.

## API additions under /api/v1/auth

- `POST /login`: JSON `{username, password, client: "web" | "native"}`;
  extra fields rejected. Username: 3–80 ASCII letters/digits or `._@+-`,
  normalized to lowercase. Password: 1–128 characters on login; provisioning
  requires at least 15 characters. Neither password nor username is logged.
- Web success 200: `{authenticated: true, expires_at: <UTC timestamp>}`.
  The secret exists only in a host-only HttpOnly, SameSite=Strict cookie,
  Secure in production, Path=/, with 30-day absolute expiry. Browser JavaScript
  cannot read it. The production cookie name is `__Host-moneysaver_session`.
- Native success 200 additionally returns `access_token`. Native clients send
  it as a bearer token and keep it only in SecureStore. Native login requests
  with an Origin header are rejected (browser clients must use cookie mode).
- `GET /session`: authenticated 200 `{authenticated: true, expires_at}`;
  invalid, expired, revoked or missing sessions return the standard 401 envelope.
- `POST /logout`: idempotently revoke the presented session, clear its cookie,
  and return 204. A network failure must remain visible and retryable in the UI;
  it must never be reported as a completed server logout.
- Login is limited to five attempts per 60 seconds per configured owner, across
  processes and restarts. This intentionally uses no stored IP addresses or
  usernames. Excess requests return 429 `rate_limited` with `Retry-After: 60`.
- Browser login/logout and all cookie-authenticated writes require the exact
  configured Origin plus `X-MoneySaver-Client: web`. Cross-origin requests are
  refused with 403 `unsupported_operation`; no permissive CORS policy is added.
- All API responses use `Cache-Control: no-store`. No passwords, financial
  payloads or sessions are put in localStorage, IndexedDB, service-worker caches,
  source maps, logs, build variables, or repository files.
- Static dev bearer authentication is disabled by default, requires explicit
  `ALLOW_DEV_BEARER=true` in local/test mode, and is forbidden in production.

## Additive database schema (migration 0006_private_auth)

All timestamps are `timestamptz`; no financial tables or values are modified.

| Table | Columns and constraints |
| --- | --- |
| `private_accounts` | `user_id uuid` PK/FK users ON DELETE CASCADE; `username text` unique; `password_hash text`; `created_at`, `updated_at` default now() |
| `private_sessions` | `token_hash varchar(64)` PK, SHA-256 of a 256-bit random secret; `user_id uuid` FK private_accounts ON DELETE CASCADE; `created_at` default now(); `expires_at`; index `(user_id, expires_at)` |
| `private_login_windows` | `user_id uuid` PK/FK users ON DELETE CASCADE; `window_started_at`; `attempts smallint` CHECK attempts >= 0 |

Provisioning/reset is an explicit local operator action. It locks the owner's
account, changes the password hash, and revokes all existing sessions in the same
transaction. Login locks the same account while checking its password and
issuing a session, so a concurrent reset cannot leave an old-password session
alive. Expired sessions are cleaned up at login.

## Hosting and iPhone behavior

One free Render web service serves the Expo web export and FastAPI at the same
HTTPS origin. Neon retains the database; free plan eligibility/limits must be
checked in the owner's account. Only built static files are served, not the
repository. The app includes a web manifest and Apple touch icon. There is no
service worker or offline transaction queue in this revision. The existing
app still needs internet. Render free instances can take about a minute to
wake after 15 minutes idle; initial session restoration allows for that delay.

Privacy means authenticated access, safe session handling and no added analytics.
It is not end-to-end encryption: Render runs the server and Neon stores the
database. Someone with access to those accounts or their database credentials
can access the stored data. Keep those accounts protected and use strong,
unique credentials. Provider infrastructure logs are controlled by the providers.
