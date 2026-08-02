# Library Tools

A cozy home for practical library software. The FastAPI service serves the
project homepage at `/`, the Lendery inventory workspace at `/lendery`, the
interactive API documentation at `/docs`, and the Lendery endpoints below the
same `/lendery` namespace.

## Book Club Manager

The account-protected Book Club Manager workspace is available at `/bookclub`,
with its API under the same path. A Libtools user can create and switch between
separate book clubs; every club keeps its members, books, meetings, and
templates isolated. Each club also has an optional read-only public page at
`/clubs/{slug}`. The manager keeps Eventbrite out of the recurring-member
workflow and provides:

- a master member list with join dates and active status;
- a reusable book collection with covers, descriptions, publication details,
  catalogue links, and book-club notes;
- meeting rosters with per-book checkout, branch transfer, and attendance data;
- attendance history and a saved random giveaway winner for each meeting;
- editable onboarding, reminder, and transit-label templates;
- personalized email and printable transit-label previews; and
- an optional blank space for manually added discussion questions.

Creating a meeting adds all active members to its roster. Use
`POST /bookclub/meetings/{meeting_id}/roster/sync` to add active members who
joined later. Existing meetings are automatically linked to book records when
the updated application first starts. Email delivery is intentionally left to
the client or a future
mail-provider integration; the API returns recipient lists and fully rendered,
personalized previews without sending anything unexpectedly.

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

## Libtools accounts

Personal Libtools accounts work across Book Club Manager, Storytime Studio, and
future tools. The account dashboard is at `/account`; platform administrators
manage users, tool access, password resets, and recovery codes at
`/admin/users`. Accounts use a unique name and password. Because email is not
required, recovery uses a saved, one-time recovery code or an administrator
reset.

On an upgrade from the old shared-login system, the existing Lendery
administrator becomes the first Libtools administrator and keeps the same
password. The former clerk credential is removed. Existing Book Club records
are assigned to a default Science Fiction Book Club owned by that
administrator.

Lendery access is assigned to personal accounts. A **Viewer** can browse
inventory, refresh availability, and operate item checklists. A **Manager** can
also create, edit, and delete inventory and components.

## Run locally

Set the first Libtools administrator and a persistent session secret before a
brand-new installation starts:

```sh
cd backend/app
export LIBTOOLS_ADMIN_NAME="admin"
export LIBTOOLS_ADMIN_PASSWORD="choose-a-long-admin-password"
export LIBTOOLS_SESSION_SECRET="choose-a-long-random-value"
uvicorn main:app --reload
```

Passwords must be at least ten characters. The initial account variables only
create the first administrator; later password changes are not overwritten when
the service restarts. `LIBTOOLS_SESSION_SECRET` is optional, but setting it
keeps existing logins valid across restarts.

## Deploy to Railway

The repository includes a production Dockerfile and Railway health-check
configuration. To preserve the existing SQLite inventory:

1. Create a Railway project from this GitHub repository.
2. Attach a volume to the web service with the mount path `/data`.
3. Deploy the service.
4. Add `LIBTOOLS_ADMIN_NAME`, `LIBTOOLS_ADMIN_PASSWORD`, and a long random
   `LIBTOOLS_SESSION_SECRET` under the service variables.
5. Under **Settings → Networking**, generate a public domain.

On the first start, the current `backend/librarytools.db` is copied into the
empty volume. Later deploys reuse the volume database and do not overwrite it.
Keep the service at one replica while it uses SQLite.

PostgreSQL is also supported. Add a Railway PostgreSQL service and set the web
service's `DATABASE_URL` to its connection URL. A PostgreSQL deployment starts
with an empty database; the local SQLite records are not imported automatically.
