# lendery/

Lendable equipment inventory tool. Largest package in the repo
(`crud.py` alone is 1,227 lines — the single biggest file). Requires
`ToolAccess` (`lendery_view`/`lendery_manage`) — see `docs/backend/accounts.md`.

## Models (`lendery/models.py`, 291 lines)

| Model | Table | Purpose |
|---|---|---|
| `LenderyItem` | `lendery_items` | Inventory item: catalogue/availability fields, `lifecycle_status` (active/unavailable/removed), `physical_manual_missing`, `checkin_card_missing` |
| `ItemActivity` | `lendery_item_activity` | Append-only operational ledger — snapshots item identity fields so history survives permanent item deletion |
| `Component` | `components` | Sub-part of an item; `optional` flag; missing-report state (`missing_reported_at`/`_by`/`_note`, `missing_ignored_at`/`_by`) |
| `MaintenanceCase` | `lendery_maintenance_cases` | A repair/issue case tied to an item (+ optional component) |
| `MaintenanceEvent` | `lendery_maintenance_events` | Ordered event within a case: ordered/received/installed parts, cost, vendor, notes, status changes |
| `ItemSuggestion` | `lendery_item_suggestions` | Public "suggest an item" inbox |

## Routes (`lendery/routes.py`, 895 lines)

| Router | Prefix | Endpoints | Purpose |
|---|---|---|---|
| `router` | `/lendery` | 39 | Suggestions CRUD, item CRUD/import/export(CSV)/barcode-lookup/availability-refresh (single + `POST /items/availability/refresh-batch`)/soft-delete-restore-permadelete, components CRUD + image upload + missing-report, maintenance queue/cases/events. Whole router requires `require_lendery_view`; individual write endpoints additionally require `require_lendery_manage`. |
| `public_router` | `/api/public/lendery` | 1 | `GET /items/barcode/{barcode}` — public barcode lookup, narrow `PublicLenderyItemResponse` |

## Other modules

- `availability.py` (235 lines) — checks live copy availability against
  Vaughan PL's BiblioCommons gateway for an item's `library_url`. Only
  counts copies at **Pierre Berton Resource Library** — copies elsewhere are
  ignored. A failed check preserves the last known `availability_status` and
  sets `availability_error` instead of flipping the item to unavailable.
  `routes.refresh_items_availability_batch` (`POST
  /items/availability/refresh-batch`) fans out `check_availability` calls
  for multiple items concurrently via `asyncio.to_thread` + a bounded
  semaphore (still the same sync `httpx.Client`, no `AsyncClient`), then
  applies+commits all results in one pass via
  `crud.apply_availability_results` — added so the frontend can refresh a
  page's worth of items (~60) in a handful of round trips/one DB commit
  instead of one request+commit per item.
- `catalogue.py` (66 lines) — item metadata (name/description/manual link)
  autofill, reusing `bookclub/catalogue.py`'s scraping helpers but with its
  own item-field mapping — **not shared code**, keep parsing fixes synced
  manually if BiblioCommons' markup changes.
- `component_images.py` (73 lines) — normalizes uploaded component photos
  (incl. iPhone HEIC/HEIF via pillow-heif) before storing under
  `LIBTOOLS_UPLOAD_DIR` (default `backend/uploads`).
- `crud.py` (1,227 lines) — DB operations for every model above, plus the
  configurable CSV export (`inventory_csv`/`items_csv`/`list_item_activity`).

## Gotchas

- Availability checking only counts **Pierre Berton Resource Library**
  copies — this is deliberate, not a bug, and is the single most surprising
  thing about `availability.py` if you're skimming it fresh.
- `ItemActivity` snapshots item identity fields (barcode/name/category) and
  keeps `original_item_id` even after `item_id` is nulled
  (`ondelete="SET NULL"`) — so activity/export history survives permanent
  deletion of the inventory record. Don't assume a null `item_id` means the
  row is orphaned/invalid.
- `lifecycle_status` (staff-controlled: active/unavailable/removed) is
  deliberately separate from catalogue `availability_status` and **must
  never** log ordinary checkouts/returns as activity — those two concepts
  are easy to conflate.
- `lendery/catalogue.py` does the same kind of BiblioCommons scraping as
  `bookclub/catalogue.py` but is a separate, unshared implementation for
  item fields instead of book fields.
- Maintenance data (`MaintenanceCase`/`MaintenanceEvent`) is edit-access-only,
  never exposed to viewers.
- The configurable inventory/history export UI is served at `/lendery/export`
  (frontend page) — see `docs/frontend/lendery.md`.

## Where to look for X

| Task | Files to touch |
|---|---|
| Add a new maintenance event type | `lendery/models.py` (`MaintenanceEvent`), `schemas.py`, `crud.py`, `routes.py` |
| Add a new item-level flag (like `checkin_card_missing`) | `lendery/models.py` (paired bool on `LenderyItem`), `schemas.py` (Update/Response schemas + export field keys), `crud.py` (`update_item` field loop + `ItemActivity` logging), `routes.py` usually unchanged (generic PATCH), plus an Alembic migration |
| Change what counts as "available" | `lendery/availability.py` |
| Add a new inventory export column | `lendery/schemas.py` (`INVENTORY_EXPORT_FIELD_KEYS`), `crud.py` (`INVENTORY_EXPORT_FIELDS` label + `_inventory_export_row`) |
| Fix catalogue autofill parsing | `lendery/catalogue.py` AND `bookclub/catalogue.py` if the underlying BiblioCommons markup changed — these are not shared |
