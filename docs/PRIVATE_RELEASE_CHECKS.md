# Private web release checks — 2026-09-13

Scope: PRIVATE_AUTH_V0_0_2 and the free same-origin web deployment.

Completed locally:

- Focused backend authentication/category/migration suite: 35 passed, zero skipped.
- Full backend suite: 328 passed, zero skipped, including financial ownership
  regressions, in 1030.67 seconds.
- Mobile TypeScript check passed; 42 mobile tests passed, zero skipped.
- Expo web, iOS and Android production exports succeeded. Native exports are
  bundle checks, not signed native installations or real-device tests.
- Alembic upgrade completed and Alembic check found no schema drift.
- Browser at 390 × 844: opening login, rejected password, successful login,
  remembered session after refresh, protected save with exact agorot, settings,
  logout and signed-out refresh passed using an isolated synthetic owner.
- No browser application warnings/errors were observed in that verification.
- Installation manifest and four icon assets are present in the web export.
- Known local database credentials and dev token matched no deployable source
  or web build files. Web output contains no source maps.
- Existing configured owner ID matches the previous local principal. The owner
  created the private login personally; creation was verified without reading
  or printing the password.

Completed on Render:

- Release `8ae914fe09febfb6109480df4237035f5671556e` was published to the existing
  repository with the owner's explicit approval and deployed successfully.
- Live app: <https://moneysaver-private.onrender.com>.
- Render confirms Docker / Free, Frankfurt, automatic deployment off. The
  initial cloud build and startup succeeded in 1 minute 38 seconds.
- The approved database credential was imported into Render's secret settings;
  the temporary local import file was removed afterward.
- Ten hosted checks passed: app, health, manifest and iPhone icon return 200;
  signed-out transactions/session return 401; secret/repository/docs paths return
  404; signed-out logout returns 204. Checked responses have no-store, HSTS and CSP.
- The logout cookie policy has Secure, HttpOnly, SameSite=Strict, the __Host-
  prefix, and no Domain. Actual successful-login cookie inspection remains pending.
- The hosted browser displays the username/password screen with no observed
  application errors or warnings. No access-code prompt is present.

Pending external checks:

- Existing-owner login, records, refresh and logout in the hosted app; the owner
  has been asked to verify their login without sharing credentials in chat.
- Neon account billing-plan confirmation; no new database or paid Render service
  was created. Render Free itself was verified in the deployment dashboard.
- Native SecureStore persistence and actual iPhone Safari/Home Screen behavior.
- A local Docker container build could not be run because Docker's engine did
  not become available; the actual Render container build/start succeeded.

No financial API payloads, financial schema, signs, aggregates, or recurring
behavior were revised. The previously documented capped Home income/net totals
and offline-sync limitations remain outside this authentication release.
