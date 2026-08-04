# Library Tools

A cozy home for practical library software. The FastAPI service serves the
project homepage at `/`, the Lendery inventory workspace at `/lendery`, the
interactive API documentation at `/docs`, and the Lendery endpoints below the
same `/lendery` namespace.

## Book Club Manager

The account-protected Book Club Manager workspace is available at `/bookclub`,
with its API under the same path. Every signed-in Libtools user can create and
switch between separate book clubs; every club keeps its members, books,
meetings, and templates isolated. Each club also has an optional read-only public page at
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

Add a Vaughan BiblioCommons record URL to an item's `library_url` field.
Adding or changing that link checks availability immediately, using only
copies at Pierre Berton Resource Library; copies at every other branch are
ignored. The saved status is one of `available`, `checked_out`, or
`unavailable`.

Filter saved statuses through the list API:

```text
GET /lendery/items?availability=in
GET /lendery/items?availability=out
GET /lendery/items?availability=unavailable
```

An availability failure keeps the previous status and records the failed check
instead of marking the item out.

When the inventory page opens, linked items that have never been checked or
were last checked more than 30 minutes ago refresh in the background. The page
also provides status filters and Available first / Unavailable first sorting.

## Lendery maintenance and repairs

Lendery editors can keep a private repair history for each inventory item.
Maintenance cases record the problem, an optional affected component, and a
status such as open, waiting for a part, in repair, or resolved. Timestamped
updates can record ordered, received, and installed parts together with cost,
quantity, vendor link, order number, notes, and the editor who made the entry.
Maintenance records and their API endpoints are not available to viewers.
`GET /lendery/maintenance` lists every open case across the whole inventory
(not just one item) so editors can triage from a single queue instead of
opening each item; items currently `unavailable` with no case yet also
surface there as a prompt to log one.

An item can also track whether it ships with a physical manual, independent
of its components. Editors can flag the manual missing from an item's return
checklist; flagging opens a maintenance case automatically so it appears in
the queue above, and "mark found" clears the flag.

Editors can explicitly mark an item unavailable with a reason, then return it
to circulation later. These collection states are separate from live catalogue
checkouts. Removing an item asks for a reason and moves it into the editor-only
Removed Items view. This is a soft deletion: components, notes, photos, and
repair history are retained and the item can be restored.

Lendery also keeps an append-only operational activity ledger. It records item
status changes, removals, missing and returned components, maintenance issues,
part orders, installations, and completed repairs. Item identity details are
snapshotted so this ledger remains available even if an editor permanently
deletes the inventory record.

The configurable export workspace is at `/lendery/export`. Editors can choose
inventory or item-history data, export all records or narrow the file to one
category or item, and select the exact CSV fields. The original
`GET /lendery/items/export.csv` endpoint remains available for compatibility.

## Libtools accounts

Personal Libtools accounts work across Book Club Manager, Storytime Studio, and
future tools. The account dashboard is at `/account`; platform administrators
manage users, tool access, password resets, and recovery codes at
`/admin/accounts`. Accounts use a required name, unique username, and password.
Because email is not required, every new account receives a saved recovery code
and can also use an administrator-assisted reset. People can create their own
account at `/signup`.
An optional email address is stored as unverified until its single-use,
24-hour verification link is completed. Verified addresses can request
single-use password-reset links that expire after one hour.

The account token and user-interface flows are implemented, but outbound email
delivery is intentionally left behind the adapter in
`backend/app/accounts/email_delivery.py` until a provider is configured.

On an upgrade from the old shared-login system, the existing Lendery
administrator becomes the first Libtools administrator and keeps the same
password. The former clerk credential is removed. Existing Book Club records
are assigned to a default Science Fiction Book Club owned by that
administrator.

Every personal account can browse Lendery inventory, refresh availability, and
operate item checklists, create book clubs, and use Storytime Studio when it is
released. Administrators can grant **Edit Lendery inventory** access from
`/admin/accounts` to staff who should also create, edit, and delete inventory
and components.

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

Lendery component photos are processed and stored on the same persistent
volume under `/data/uploads`. Back up both `/data/librarytools.db` and
`/data/uploads`; the database contains the photo references, while the image
files live in the uploads directory. For local development, uploads default to
`backend/uploads`. Set `LIBTOOLS_UPLOAD_DIR` to use a different location.

PostgreSQL is also supported. Add a Railway PostgreSQL service and set the web
service's `DATABASE_URL` to its connection URL. A PostgreSQL deployment starts
with an empty database; the local SQLite records are not imported automatically.
