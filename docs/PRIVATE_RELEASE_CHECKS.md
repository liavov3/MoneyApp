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
- Existing configured owner ID matches the previous local principal. The first
  owner login is intentionally left for the owner to create in the local setup
  page; no password is chosen or printed by the assistant.

Pending external checks:

- Render build/start, live HTTPS cookie flags, hosted access restrictions,
  provider free-plan confirmation, and existing-owner login on the live app.
- Native SecureStore persistence and actual iPhone Safari/Home Screen behavior.
- A local Docker container build could not be run because Docker's engine did
  not become available. The intended hosting container must pass Render's build
  and startup checks before deployment can be declared complete.

No financial API payloads, financial schema, signs, aggregates, or recurring
behavior were revised. The previously documented capped Home income/net totals
and offline-sync limitations remain outside this authentication release.
