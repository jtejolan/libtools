# Code index

Flat file-level lookup: every source file, its rough size, and where to read
more. Use this to find *which* file is relevant before opening any source.
For what a file's symbols/routes/models actually do, follow the "Detail in"
column into the package doc.

Columns: **Path** (repo-relative) · **Lines** (`wc -l`, ballpark — not
guaranteed exact) · **Purpose** (one clause) · **Detail in**.

## backend/app/ (top level, shared)

| Path | Lines | Purpose | Detail in |
|---|---|---|---|
| `backend/app/main.py` | 268 | App wiring: lifespan/migrations, middleware, router mounts, static frontend, SPA page routes, second ASGI app for public subdomain | `docs/backend/shared.md`, `docs/architecture.md` |
| `backend/app/database.py` | 64 | Engine/session setup, SQLite default + Postgres URL rewrite | `docs/backend/shared.md` |
| `backend/app/dependencies.py` | 18 | `DatabaseSession`/`get_db` FastAPI dependency | `docs/backend/shared.md` |
| `backend/app/security.py` | 40 | Password hashing (scrypt) | `docs/backend/shared.md` |
| `backend/app/email_delivery.py` | 80 | Low-level email transport, wrapped by per-package senders | `docs/backend/shared.md` |
| `backend/app/models.py` | 0 | EMPTY — vestigial, ignore, do not use | — |

## backend/app/accounts/

| Path | Lines | Purpose | Detail in |
|---|---|---|---|
| `backend/app/accounts/__init__.py` | 1 | Package marker | — |
| `backend/app/accounts/models.py` | 76 | `LibtoolsUser`, `ToolAccess`, `AccountToken` | `docs/backend/accounts.md` |
| `backend/app/accounts/schemas.py` | 228 | Pydantic request/response schemas | `docs/backend/accounts.md` |
| `backend/app/accounts/routes.py` | 546 | `/auth/*` + `/api/admin/users` endpoints — no separate `crud.py`, DB ops live inline here and in `bootstrap.py` | `docs/backend/accounts.md` |
| `backend/app/accounts/auth.py` | 220 | Session resolution, `CurrentUser`, role/tool guards | `docs/backend/accounts.md` |
| `backend/app/accounts/bootstrap.py` | 91 | Seeds/repairs platform accounts + club access on startup | `docs/backend/accounts.md` |
| `backend/app/accounts/account_tokens.py` | 91 | Hashed expiring tokens for verify-email/password-reset | `docs/backend/accounts.md` |
| `backend/app/accounts/email_delivery.py` | 187 | Accounts-specific email templates | `docs/backend/accounts.md` |
| `backend/app/accounts/login_throttle.py` | 58 | In-memory brute-force lockout for `/auth/login` | `docs/backend/accounts.md` |

## backend/app/bookclub/

| Path | Lines | Purpose | Detail in |
|---|---|---|---|
| `backend/app/bookclub/models.py` | 245 | Club/member/book/meeting/participation/template/question models | `docs/backend/bookclub.md` |
| `backend/app/bookclub/schemas.py` | 408 | Pydantic schemas incl. `PublicXResponse` subset types | `docs/backend/bookclub.md` |
| `backend/app/bookclub/crud.py` | 1017 | DB ops for all bookclub entities | `docs/backend/bookclub.md` |
| `backend/app/bookclub/routes.py` | 581 | Members/books/meetings/roster/emails/giveaway/templates/questions (40 endpoints) | `docs/backend/bookclub.md` |
| `backend/app/bookclub/club_routes.py` | 199 | Club CRUD/switching + public `/api/public/clubs/{slug}` | `docs/backend/bookclub.md` |
| `backend/app/bookclub/access.py` | 57 | `require_selected_club`, club-scoping dependencies | `docs/backend/bookclub.md` |
| `backend/app/bookclub/catalogue.py` | 200 | Scrapes Vaughan PL (BiblioCommons) for book metadata | `docs/backend/bookclub.md` |
| `backend/app/bookclub/email_delivery.py` | 26 | Thin bookclub email wrapper | `docs/backend/bookclub.md` |

## backend/app/lendery/

| Path | Lines | Purpose | Detail in |
|---|---|---|---|
| `backend/app/lendery/models.py` | 291 | Item/ItemActivity/Component/MaintenanceCase/MaintenanceEvent/ItemSuggestion | `docs/backend/lendery.md` |
| `backend/app/lendery/schemas.py` | 625 | Pydantic schemas incl. `PublicLenderyItemResponse`, export field configs | `docs/backend/lendery.md` |
| `backend/app/lendery/crud.py` | 1227 | DB ops for all lendery entities — largest file in the repo | `docs/backend/lendery.md` |
| `backend/app/lendery/routes.py` | 895 | Items/components/maintenance/suggestions (~40 endpoints) + public barcode lookup | `docs/backend/lendery.md` |
| `backend/app/lendery/availability.py` | 235 | Live copy-availability check via Vaughan PL BiblioCommons gateway | `docs/backend/lendery.md` |
| `backend/app/lendery/catalogue.py` | 66 | Item metadata autofill scraping — NOT shared code with `bookclub/catalogue.py` | `docs/backend/lendery.md` |
| `backend/app/lendery/component_images.py` | 73 | Upload normalization incl. iPhone HEIC/HEIF, resolves `LIBTOOLS_UPLOAD_DIR` | `docs/backend/lendery.md` |

## backend/tests/

| Path | Lines | Purpose | Detail in |
|---|---|---|---|
| `backend/tests/test_accounts.py` | 870 | Accounts API tests | `docs/backend/accounts.md` |
| `backend/tests/test_auth.py` | 411 | Session/auth guard tests | `docs/backend/accounts.md` |
| `backend/tests/test_availability.py` | 337 | Lendery availability-check tests | `docs/backend/lendery.md` |
| `backend/tests/test_bookclub_api.py` | 784 | Bookclub API tests | `docs/backend/bookclub.md` |
| `backend/tests/test_catalogue_import.py` | 87 | Bookclub catalogue-scraping tests | `docs/backend/bookclub.md` |
| `backend/tests/test_lendery_api.py` | 962 | Lendery API tests | `docs/backend/lendery.md` |
| `backend/tests/test_lendery_catalogue.py` | 99 | Lendery catalogue-scraping tests | `docs/backend/lendery.md` |
| `backend/tests/test_session_secret.py` | 27 | `LIBTOOLS_SESSION_SECRET` startup-check tests | `docs/backend/shared.md` |

Run with `PYTHONPATH=app .venv/bin/python -m unittest discover -s tests -v`
from `backend/` — see root `CLAUDE.md` for full commands.

## backend/ (config, not app code)

| Path | Purpose | Detail in |
|---|---|---|
| `backend/alembic.ini` | Alembic config | `docs/backend/shared.md` |
| `backend/alembic/env.py` | Migration environment, points at `Base.metadata`/`DATABASE_URL` | `docs/backend/shared.md` |
| `backend/alembic/versions/*.py` (5 files) | Migration scripts, head is `d7e3b91c4a20` | `docs/backend/shared.md` |
| `backend/requirements.txt` | Python dependencies | `docs/dependency-map.md` |
| `backend/start.sh` | Production entrypoint (Railway volume seeding + uvicorn) | `docs/architecture.md` |
| `backend/librarytools.db` | Committed dev/seed SQLite database | `docs/backend/shared.md` |
| `backend/.env` | Local environment variables (not committed content, gitignored secrets) | — |

## frontend/ (top level)

| Path | Lines | Purpose | Detail in |
|---|---|---|---|
| `frontend/index.html` / `home.js` | 207 / 131 | Public marketing homepage | `docs/frontend/accounts.md` |
| `frontend/dashboard.html` / `dashboard.js` | 6 / 402 | Post-login landing page, tool grid | `docs/frontend/accounts.md` |
| `frontend/account.html` / `account.js` | 162 / 284 | Login/register/password-reset/recovery/settings | `docs/frontend/accounts.md` |
| `frontend/admin-accounts.html` / `admin-accounts.js` | 70 / 178 | Platform-admin account management (canonical) | `docs/frontend/accounts.md` |
| `frontend/admin-users.html` / `admin-users.js` | 2 / 12 | Minified LEGACY duplicate of admin-accounts — don't edit | `docs/frontend/accounts.md` |
| `frontend/bookclub.html` / `bookclub.js` | 397 / 1850 | Book Club Manager app | `docs/frontend/bookclub.md` |
| `frontend/public-club.html` / `public-club.js` | 1 / 15 | Public read-only club page (minified) | `docs/frontend/bookclub.md` |
| `frontend/lendery.html` / `lendery.js` | 466 / 2458 | Lendery inventory app — largest JS file in repo | `docs/frontend/lendery.md` |
| `frontend/lendery-export.html` / `lendery-export.js` | 89 / 256 | Configurable CSV export UI at `/lendery/export` | `docs/frontend/lendery.md` |
| `frontend/check.html` / `check.js` | 23 / 154 | Public barcode quick-check (no auth) | `docs/frontend/lendery.md` |
| `frontend/dom-utils.js` | 8 | Shared `escapeHtml()` helper, used on 9 of 10 app pages | `docs/frontend/overview.md` |
| `frontend/quotes.js` | 614 | Static book-quote content data (not logic), used by index/dashboard | `docs/frontend/overview.md` |
| `frontend/styles.css` | 1015 | `index.html`-only stylesheet | `docs/frontend/accounts.md` |
| `frontend/platform.css` | 258 | Shared chrome across 6 pages | `docs/frontend/overview.md` |
| `frontend/bookclub.css` | 529 | Bookclub app styles | `docs/frontend/bookclub.md` |
| `frontend/lendery.css` | 3280 | Lendery app styles — largest CSS file in repo | `docs/frontend/lendery.md` |
| `frontend/lendery-export.css` | 350 | Lendery export UI styles | `docs/frontend/lendery.md` |
| `frontend/check.css` | 70 | Quick-check page styles | `docs/frontend/lendery.md` |

## frontend/ (other)

| Path | Purpose | Detail in |
|---|---|---|
| `frontend/assets/` (35 files) | Logo/icon images for Lendery, Book Club, Storytime, Library Tools | — |
| `frontend/src/`, `frontend/public/` | Empty, unused — not part of the active build | `docs/frontend/overview.md` |
| `frontend/package.json` | NOT a file — empty directory, filesystem oddity, ignore | `docs/frontend/overview.md` |
