# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A FastAPI backend + vanilla-JS frontend serving several library tools from one
app: Lendery (lendable equipment inventory), Book Club Manager, and a shared
Libtools account system. See README.md for the full feature description of
each tool. There is no frontend build step — `frontend/*.js`/`*.html`/`*.css`
are served directly as static files.

## Commands

Run locally (from `backend/app`, with a venv active):
```sh
export LIBTOOLS_ADMIN_NAME="admin"
export LIBTOOLS_ADMIN_PASSWORD="choose-a-long-admin-password"
export LIBTOOLS_SESSION_SECRET="choose-a-long-random-value"
uvicorn main:app --reload
```
The admin env vars only matter on a brand-new database (no users yet).

Install deps: `pip install -r backend/requirements.txt` (there is a
`backend/.venv` already set up in this checkout).

Run tests — the test suite uses `unittest` (no pytest installed), and imports
modules as if `backend/app` were on the path (e.g. `from database import
Base`, not `from app.database import Base`). Run from `backend/`:
```sh
cd backend
PYTHONPATH=app .venv/bin/python -m unittest discover -s tests -v
```
Run a single test file/case:
```sh
PYTHONPATH=app .venv/bin/python -m unittest tests.test_lendery_api -v
PYTHONPATH=app .venv/bin/python -m unittest tests.test_lendery_api.LenderyAvailabilityApiTests.test_item_detail_refreshes_availability
```
There is no lint/format config in the repo (no ruff/flake8/eslint configs) —
don't invent one.

## Architecture

**Backend layout** (`backend/app/`): each product area is its own package
(`accounts/`, `bookclub/`, `lendery/`) with the same internal shape —
`models.py` (SQLAlchemy), `schemas.py` (Pydantic), `crud.py`, `routes.py`.
`main.py` wires up the FastAPI app, mounts each package's router, serves the
static frontend, and gates `/docs`/`/openapi.json` behind platform-admin auth
(Swagger UI is not public). `database.py` builds the engine (SQLite by
default at `backend/librarytools.db`, or Postgres via `DATABASE_URL`).
Schema changes are managed with Alembic (`backend/alembic/`, config at
`backend/alembic.ini`); `main.py`'s `lifespan` runs `alembic upgrade head`
on startup instead of `Base.metadata.create_all`. When adding a column or
table to a model, generate a revision from `backend/` with
`PYTHONPATH=app DATABASE_URL=... .venv/bin/alembic revision --autogenerate -m "..."`
against a database that already has the previous schema, then review the
generated file before committing it — autogenerate doesn't reliably detect
things like column renames or check constraints.

**Accounts & auth** (`accounts/`): one `LibtoolsUser` table shared across all
tools. Book Club Manager and Storytime Studio are available to every signed-in
account. `ToolAccess` rows are reserved for assignable permissions such as
`lendery_manage`, checked via `has_tool_access(db, user, tool_key)`. Session state is a signed cookie
(`SessionMiddleware`) storing `libtools_user_id` + `libtools_session_version`;
bumping a user's `session_version` invalidates all their existing sessions
(used on password reset/deactivation). `accounts/auth.py` defines the
FastAPI dependency helpers other packages build on:
`CurrentUser`/`get_current_user`, `require_platform_admin`,
`require_lendery_view`/`require_lendery_manage`. Passwords are hashed with
scrypt in `security.py` (not bcrypt/argon2 — don't swap libraries without a
reason).

**Book Club Manager** (`bookclub/`): multi-tenant — every club-owned table
(`bookclub_members`, `bookclub_books`, `bookclub_meetings`,
`bookclub_templates`) is scoped by `club_id`, and uniqueness constraints
(email, ISBN, template key) are scoped per-club, not global. `access.py`'s
`require_selected_club` reads the *currently selected* club out of the
session (`bookclub_id`) and enforces the user has `BookClubAccess` to it (or
is a platform admin); most `bookclub/routes.py` endpoints depend on
`SelectedClub`, not just `BookClubUser`. `club_routes.py` handles
club creation/switching plus the public read-only `/clubs/{slug}` page.
`catalogue.py` parses BiblioCommons book metadata for autofill.

**Lendery** (`lendery/`): inventory items can have `Component`s and
`MaintenanceCase`s (each case has ordered `MaintenanceEvent`s — the repair
history: ordered/received/installed parts, cost, vendor, notes).
`ItemActivity` is the append-only, exportable operational ledger. It snapshots
item identity fields so lifecycle, missing-component, order, and repair events
survive permanent deletion of the inventory record. The staff-controlled
`lifecycle_status` (`active`/`unavailable`/`removed`) is deliberately separate
from catalogue availability and must never log ordinary checkouts/returns.
The configurable inventory/history export UI is served at `/lendery/export`.
Maintenance data is edit-access-only, never exposed to viewers. Availability
checking (`availability.py`) calls Vaughan's BiblioCommons gateway for an
item's linked `library_url`, but only counts copies at Pierre Berton
Resource Library — copies elsewhere are ignored; a failed check preserves
the last known `availability_status` and records `availability_error`
instead of flipping the item to unavailable. `catalogue.py` does the same
BiblioCommons-scraping-based autofill as bookclub's, but for item fields
(name/description/manual link) instead of book metadata — the two catalogue
modules are not shared code, so keep parsing fixes in sync manually if
BiblioCommons' markup changes. `component_images.py` normalizes uploaded
photos (including iPhone HEIC/HEIF) before storing them under the upload
dir (`LIBTOOLS_UPLOAD_DIR`, default `backend/uploads`).

**Frontend**: no framework, no bundler. Each page is a standalone
`<name>.html` + `<name>.js` (e.g. `lendery.html`/`lendery.js`,
`bookclub.html`/`bookclub.js`) that manages its own DOM and a plain-object
`state`, and talks to the backend via `fetch`. `frontend/src` and
`frontend/public` exist but are currently empty — not part of the active
build.

## Deployment

Deploys to Railway from the root `Dockerfile` (installs `backend/requirements.txt`,
copies `backend/` + `frontend/`, runs `backend/start.sh`). SQLite deployments
require a Railway volume at `/data` (`start.sh` seeds it from the committed
`backend/librarytools.db` on first boot) and must stay at one replica.
Postgres is supported by setting `DATABASE_URL`; a Postgres deployment starts
empty (no import of the local SQLite data).
