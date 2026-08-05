# Architecture

Cross-package synthesis — how the pieces in `docs/backend/*.md` and
`docs/frontend/*.md` fit together. Each section ends with a pointer to the
doc that covers its detail; this file doesn't restate that detail.

## Request flow

A request carries a signed session cookie (`libtools_session`,
`itsdangerous`-signed via `SessionMiddleware`). Route handlers depend on
`CurrentUser`/`get_current_user` (`accounts/auth.py`) to resolve it into a
`LibtoolsUser`, then on package-specific guards layered on top:
`require_lendery_view`/`manage` (lendery), `require_selected_club`
(bookclub, also reads `bookclub_id` out of the session). Public endpoints
(`/api/public/*`) skip auth entirely and return narrow `PublicXResponse`
schemas. See `docs/backend/accounts.md`, `docs/coding-guidelines.md`.

## The two ASGI apps

`main.py` builds two separate FastAPI apps. The primary `app` serves the
whole product — all routers, the full static frontend, session-gated
`/docs`+`/openapi.json`. A second app, `lendery_public_app`, has **no auth
and no session middleware** and serves only `public_lendery_router` plus a
single landing page (`check.html`) — the Lendery "Quick Check" micro-site.
It's mounted onto the primary app via
`Host("lendery.libtools.app", app=lendery_public_app)`, and that mount is
**inserted at `app.router.routes[0]`** (not appended) so Starlette matches
it before the generic any-host routes below would otherwise shadow the same
paths for the public subdomain. This is the single most surprising thing in
`main.py` — everything else is fairly conventional FastAPI wiring. See
`docs/backend/shared.md`, `docs/frontend/lendery.md`.

## Auth & sessions

One `LibtoolsUser` table shared by every product. `ToolAccess` rows gate
assignable permissions (`lendery_view`/`lendery_manage`); Book Club Manager
and Storytime Studio have no such gate — any signed-in account can use them.
Bumping `session_version` invalidates all of a user's existing sessions.
Login is throttled in-memory (5 attempts / 15 min → 15 min lockout),
per-process. Detail: `docs/backend/accounts.md`.

## Multi-tenancy in Book Club

Every club-owned table carries `club_id`, and uniqueness constraints are
scoped per club, not global. `require_selected_club` reads the
session-selected `bookclub_id`, checks `BookClubAccess`, and most of
`bookclub/routes.py` depends on it (`SelectedClub`), not just an
authenticated `BookClubUser`. Detail: `docs/backend/bookclub.md`.

## Static frontend serving & SPA routes

There's no frontend build step. `main.py` mounts `/static` to the `frontend/`
directory and separately defines fixed routes (`/dashboard`, `/lendery`,
`/bookclub`, `/login`, `/account`, `/clubs/{slug}`, etc.) that each return a
specific HTML file via `FileResponse` — these aren't a router-driven SPA,
just one FastAPI route per page shell. The page's own JS then fetches data
client-side. Detail: `docs/frontend/overview.md`.

## Migrations

Schema changes are managed with Alembic (`backend/alembic/`); `main.py`'s
`lifespan` runs `alembic upgrade head` on every startup instead of
`Base.metadata.create_all`. Current head: `a4af3deaaa80`. Workflow for
adding a migration (autogenerate, then manual review — autogenerate misses
things like column renames/check constraints) is documented in the root
`CLAUDE.md`; don't duplicate it here.

## Deployment shape

Railway, from the root `Dockerfile` (installs `backend/requirements.txt`,
copies `backend/`+`frontend/`, runs `backend/start.sh`). SQLite deployments
need a Railway volume at `/data`, seeded from the committed
`backend/librarytools.db` on first boot, and must stay single-replica
(matches `login_throttle.py`'s in-memory-per-process limitation above).
Postgres is supported via `DATABASE_URL` and starts empty. Detail: root
`CLAUDE.md`'s Deployment section, `docs/backend/shared.md`.
