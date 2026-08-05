# backend/app/ — shared top-level modules

Reference doc for the files every package (`accounts/`, `bookclub/`,
`lendery/`) can depend on. See `docs/architecture.md` for how they fit
together narratively; this file is the module → symbol lookup.

## `main.py` (268 lines)

App wiring only — no business logic. `lifespan()` runs Alembic migrations to
`head` (`_run_migrations()`) then seeds/repairs platform accounts
(`initialize_platform_accounts`) and removes legacy lendery-only accounts on
every startup. `docs_url`/`openapi_url` are disabled on app creation and
manually re-added at `/docs`/`/openapi.json`, gated behind
`Depends(require_platform_admin)`. `SessionMiddleware` uses cookie
`libtools_session`, 30-day max age, `same_site="lax"`; the session secret
comes from `LIBTOOLS_SESSION_SECRET` and the app refuses to start on Railway
without it. Mounts all package routers, mounts `/static` to `frontend/`,
serves fixed-HTML "SPA page" routes (`/dashboard`, `/lendery`, `/bookclub`,
`/login`, `/account`, `/clubs/{slug}`, etc.), and mounts a **second, separate
FastAPI app** (`lendery_public_app`) for the `lendery.libtools.app`
subdomain. See `docs/architecture.md` for why.

## `database.py` (64 lines)

`DATABASE_URL` env var, defaulting to
`sqlite:///{BACKEND_DIR}/librarytools.db`. Rewrites `postgres://` and
`postgresql://` prefixes to `postgresql+psycopg://` (psycopg3 driver, used on
Railway). Relative `sqlite:///./` paths get resolved against `BACKEND_DIR`.
`check_same_thread=False` is set only for SQLite. Exports `engine`,
`SessionLocal` (session factory, `expire_on_commit=False`), and `Base`
(shared `DeclarativeBase` all models inherit from).

## `dependencies.py` (18 lines)

`get_db()` — a generator yielding a `SessionLocal()` session and closing it
in `finally`. `DatabaseSession = Annotated[Session, Depends(get_db)]` — the
type every route handler in every package uses as its DB parameter.

## `security.py` (40 lines)

`hash_password(password) -> str` / `verify_password(password, encoded) -> bool`.
Uses **scrypt** (`hashlib.scrypt`, n=2^14, r=8, p=1), not bcrypt/argon2 —
don't swap without a reason. Encoded format is `scrypt$<salt>$<hash>`,
both base64url.

## `email_delivery.py` (80 lines)

Low-level email transport. Each package wraps this with its own templates:
`accounts/email_delivery.py`, `bookclub/email_delivery.py`.

## Gotchas

- `backend/app/models.py` exists but is **empty (0 lines)** — vestigial,
  ignore it. Each package has its own `models.py`.
- `lendery.libtools.app` is inserted at `app.router.routes[0]` (not
  appended) so host-based routing matches it before the generic any-host
  routes below would otherwise shadow it for the same paths — see
  `docs/architecture.md`.
- `backend/librarytools.db` is a **committed** dev/seed SQLite database. On
  Railway with SQLite, `backend/start.sh` copies it onto the attached volume
  on first boot only; Postgres deployments start empty (no import of local
  SQLite data).
