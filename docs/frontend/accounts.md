# frontend — accounts area

Five thin page-pairs bundled into one doc since none individually clears
~400 lines. Unlike `lendery.js`/`bookclub.js`, none of these hold a single
big `state` object — each uses a handful of top-level `let`/`const`
variables (e.g. `admin-accounts.js`: `let users = []`, `let query = ""`).

## `index.html` / `home.js` (207 / 131 lines)

Public marketing homepage. Calls `GET /auth/me` (adjusts the header CTA if
already logged in) and `GET /api/public/stats` (item/club counts). Also
drives a rotating book-quote widget from `quotes.js`. Uses its own
`styles.css` (1015 lines), not `platform.css`.

## `dashboard.html` / `dashboard.js` (6 / 429 lines)

Post-login landing page — tool grid, quick actions, per-tool summary cards
(e.g. Lendery needs-attention count, next Book Club meeting countdown).
Calls `/auth/quick-actions`, `/auth/logout`, `/auth/me`,
`/auth/dashboard-summary`.

`isBookclubOnlyFacilitator(user, tools)` special-cases self-serve book club
leads: a signed-in account with no `admin` role, no `lendery_manage` tool
access, but at least one club in `user.clubs` gets a stripped-down
dashboard — one enlarged `.dash-card-solo` Book Club Manager card plus the
quote card, skipping the Lendery card and quick actions entirely (and their
init functions, `initializeLenderyScan`/`initializeQuickActionsEditor`, are
never called for that case). This is computed purely client-side from
fields `/auth/me` already returns — no backend change. These accounts are
still ordinary `LibtoolsUser` rows (see `docs/backend/bookclub.md`'s
participant-accounts section for the accounts that *are* fully separate);
this is a display simplification, not an access-control boundary — nothing
server-side prevents such an account from hitting `/lendery` directly, it's
just not surfaced on their dashboard.

## `account.html` / `account.js` (162 / 284 lines)

One page, several "cards" toggled by `showAuthCard(name)`: login, signup,
forgot-password, reset-password, verify-email, recovery-code. Also serves
signed-in "account settings" (password change, quick actions). Calls
`/auth/login`, `/auth/register`, `/auth/password-reset/*`, `/auth/recover`,
`/auth/password`, `/auth/recovery-code`, `/auth/verify-email` request/confirm,
`/auth/logout`, `/auth/me`.

## `admin-accounts.html` / `admin-accounts.js` (70 / 178 lines) — canonical

Platform-admin account management: list/search users, create, reset
password/recovery code, toggle tool access. Calls `/api/admin/users` and its
`/{id}/...` sub-routes, plus `/auth/logout`, `/auth/me`.

## `admin-users.html` / `admin-users.js` (2 / 12 lines) — LEGACY, DO NOT EDIT

A minified duplicate of the admin-accounts flow, hitting the same
`/api/admin/users*` endpoints. `main.py`'s `/admin/users` route redirects to
`/admin/accounts`, so this page pair is effectively dead in normal
navigation — treat `admin-accounts.*` as the only file to touch for this
feature area.

## Shared

All five use `platform.css` except `index.html` (own `styles.css`). See
`docs/frontend/overview.md` for shared JS/CSS files common across the whole
frontend.
