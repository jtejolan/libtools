# Dependency map

## Internal: cross-package imports

```
accounts  <──  bookclub   (bookclub/access.py, bookclub/club_routes.py import accounts.auth.CurrentUser)
accounts  <──  lendery    (lendery/routes.py imports accounts.auth.require_lendery_view/manage)
bookclub  <──  lendery    (lendery/routes.py + lendery/catalogue.py import bookclub.catalogue)

accounts  ──>  bookclub   (accounts/bootstrap.py imports bookclub.models — BOOTSTRAP-TIME ONLY,
                            seeding club access at startup; not a general accounts→bookclub
                            dependency, does not create a cycle)
```

So `accounts` is the common dependency root that `bookclub` and `lendery` both
build on; `bookclub` is additionally a dependency of `lendery` (catalogue
scraping reuse). `bookclub` and `lendery` never import from each other's
`routes.py`/`crud.py`/`models.py` — only `lendery` reaches into
`bookclub.catalogue`.

Every package (plus `main.py`) may depend on the shared top-level modules in
`backend/app/`: `database.py`, `dependencies.py`, `security.py`,
`email_delivery.py`. See `docs/backend/shared.md`.

## External dependencies (`backend/requirements.txt`)

| Package | Version | Used for |
|---|---|---|
| `fastapi` | 0.139.0 | Web framework, routing, dependency injection |
| `sqlalchemy` | 2.0.51 | ORM — all `models.py` files |
| `alembic` | 1.16.1 | Schema migrations, run on startup via `main.py`'s lifespan |
| `psycopg[binary]` | >=3.2,<4 | Postgres driver (Railway deploys via `DATABASE_URL`) |
| `pydantic` | 2.13.4 | Request/response schema validation (`schemas.py` files) |
| `httpx` | 0.28.1 | Dual role: FastAPI's test client dependency, AND scraping BiblioCommons catalogue pages in `lendery/catalogue.py` and `bookclub/catalogue.py` |
| `pillow` | >=11.3,<12 | Component photo processing/resizing (`lendery/component_images.py`) |
| `pillow-heif` | >=1.1,<2 | iPhone HEIC/HEIF photo support, paired with pillow |
| `python-multipart` | >=0.0.20,<1 | File upload form parsing (component photo uploads) |
| `itsdangerous` | >=2.2,<3 | Signs the session cookie (`SessionMiddleware`) |
| `python-dotenv` | (unpinned) | Loads `backend/.env` in `database.py` |
| `uvicorn` | (unpinned) | ASGI server, run by `backend/start.sh` |

See also `docs/code-index.md` for where each package's files live.
