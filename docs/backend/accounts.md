# accounts/

One `LibtoolsUser` table shared across every Libtools product (Lendery, Book
Club Manager, Storytime Studio). Owns session/auth, platform-admin user
management, and per-tool permission grants.

## Models (`accounts/models.py`, 76 lines)

| Model | Table | Purpose |
|---|---|---|
| `LibtoolsUser` | `libtools_users` | Account: credentials, role, `session_version` (bump invalidates all sessions), `quick_actions` |
| `ToolAccess` | `libtools_tool_access` | Per-user grant of an assignable permission, e.g. `lendery_manage`, `lendery_view` |
| `AccountToken` | `libtools_account_tokens` | Hashed, expiring token for email-verification/password-reset flows |

No `crud.py` in this package — DB operations live inline in `routes.py` and
`bootstrap.py`.

## Routes (`accounts/routes.py`, 546 lines)

| Router | Prefix | Endpoints | Purpose |
|---|---|---|---|
| `router` | `/auth` | 13 | register, login, logout, `/me`, dashboard summary, quick-actions, password change, recovery (request/confirm), email verification (request/confirm), password reset (request/confirm) |
| `admin_router` | `/api/admin/users` | 5 | list/create/patch users, admin-triggered password reset, admin-triggered recovery-code reset |

## Other modules

- `auth.py` — session resolution and dependency guards: `CurrentUser`,
  `get_current_user`, `require_platform_admin`, `require_lendery_view`,
  `require_lendery_manage`. Other packages build their own access checks on
  top of these (see `docs/dependency-map.md`).
- `bootstrap.py` — on startup, seeds/repairs platform accounts from
  `LIBTOOLS_ADMIN_NAME`/`LIBTOOLS_ADMIN_PASSWORD`, seeds club access, and
  migrates legacy lendery-only accounts.
- `account_tokens.py` — issues/validates hashed `AccountToken` rows.
- `email_delivery.py` — accounts-specific HTML email templates (verification,
  reset, password-changed), built on the shared `backend/app/email_delivery.py`.
- `login_throttle.py` — in-memory per-process brute-force lockout: 5 failed
  attempts / 15-minute window locks the username for 15 minutes.

## Gotchas

- `ToolAccess` only gates *assignable* permissions like `lendery_manage`/
  `lendery_view`. Book Club Manager and Storytime Studio are **not** gated
  this way — every signed-in account has access to them.
- Bumping `session_version` on a user invalidates all of that user's existing
  sessions (used on password reset/deactivation) — the session cookie stores
  `libtools_session_version` and is checked against the DB value on each
  request.
- `login_throttle.py` state is **in-memory, per-process**: it resets on every
  restart/redeploy, and on a multi-replica Postgres deployment each replica
  throttles independently (best-effort, not a hard guarantee). SQLite
  deployments are single-replica so this is exact there.
- Passwords are hashed with **scrypt** (`backend/app/security.py`), not
  bcrypt/argon2 — don't swap libraries without a reason (see
  `docs/coding-guidelines.md`).
- Email is required for new accounts (`RegistrationRequest`/`UserCreate` in
  `schemas.py`), enforced at the Pydantic/frontend level only — the
  `libtools_users.email` column itself stays nullable so pre-existing
  accounts created before this requirement (e.g. the bootstrap admin) don't
  break.

## Where to look for X

| Task | Files to touch |
|---|---|
| Add a new assignable tool permission | `accounts/models.py` (no change needed — `tool_key` is a free string), wherever the tool checks access (e.g. `accounts/auth.py` for a new `require_<tool>` guard), the consuming package's `routes.py` |
| Change login lockout thresholds | `accounts/login_throttle.py` (`MAX_ATTEMPTS`, `WINDOW_SECONDS`, `LOCKOUT_SECONDS`) |
| Add a new admin-user-management endpoint | `accounts/routes.py` (`admin_router` section), `accounts/schemas.py` |
| Change what invalidates a session | `accounts/models.py` (`session_version`), wherever it's bumped in `routes.py` |
