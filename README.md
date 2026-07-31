# Library Tools

A cozy home for practical library software. The FastAPI service serves the
project homepage at `/`, the Lendery inventory workspace at `/lendery`, the
interactive API documentation at `/docs`, and the Lendery endpoints below the
same `/lendery` namespace.

## Pierre Berton availability

Add a Vaughan BiblioCommons record URL to an item's `library_url` field. Opening
that item refreshes its status using only copies at Pierre Berton Resource
Library; copies at every other branch are ignored. The saved status is one of
`available`, `checked_out`, `unavailable`, `not_held`, or `unknown`.

Filter saved statuses through the list API:

```text
GET /lendery/items?availability=in
GET /lendery/items?availability=out
GET /lendery/items?availability=unavailable
GET /lendery/items?availability=not_held
GET /lendery/items?availability=unknown
```

An availability failure keeps the previous status and records the failed check
instead of marking the item out.

When the inventory page opens, linked items that have never been checked or
were last checked more than 30 minutes ago refresh in the background. The page
also provides status filters and Available first / Unavailable first sorting.

## Run locally

Lendery has two fixed accounts: `admin` can change inventory and checklist
definitions, while `clerk` has read-only inventory access and can operate
checklists. Set their initial passwords before the first start:

```sh
cd backend/app
export LENDERY_ADMIN_PASSWORD="choose-an-admin-password"
export LENDERY_CLERK_PASSWORD="choose-a-clerk-password"
export LENDERY_SESSION_SECRET="choose-a-long-random-value"
uvicorn main:app --reload
```

Passwords must be at least eight characters. The initial password variables
only create missing accounts; later password changes made in Lendery are not
overwritten when the service restarts. `LENDERY_SESSION_SECRET` is optional,
but setting it keeps existing logins valid across restarts.

## Deploy to Railway

The repository includes a production Dockerfile and Railway health-check
configuration. To preserve the existing SQLite inventory:

1. Create a Railway project from this GitHub repository.
2. Attach a volume to the web service with the mount path `/data`.
3. Deploy the service.
4. Add `LENDERY_ADMIN_PASSWORD`, `LENDERY_CLERK_PASSWORD`, and a long random
   `LENDERY_SESSION_SECRET` under the service variables.
5. Under **Settings → Networking**, generate a public domain.

On the first start, the current `backend/librarytools.db` is copied into the
empty volume. Later deploys reuse the volume database and do not overwrite it.
Keep the service at one replica while it uses SQLite.

PostgreSQL is also supported. Add a Railway PostgreSQL service and set the web
service's `DATABASE_URL` to its connection URL. A PostgreSQL deployment starts
with an empty database; the local SQLite records are not imported automatically.
