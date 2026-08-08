# frontend — Lendery

## `lendery.html` / `lendery.js` (466 / 2,458 lines) + `lendery.css` (3,280 lines)

The app — largest JS and CSS files in the repo. `state` (top of `lendery.js`)
holds: `user`, `items`, search/filter/sort UI fields (`query`, `category`,
`availabilityFilter`, `inventorySort`), `selectedId` (open item drawer),
`checkedComponents`/`physicalManualChecked` (return-checklist session state,
not persisted server-side), `maintenanceByItem`/`activityByItem` (Maps keyed
by item id), `refreshingIds`/`refreshPromises` (availability refresh
in-flight tracking), `maintenanceQueue`, `inventoryView`, and item
suggestion inbox fields. Talks to `/lendery/*` (~20 call sites) — see
`docs/backend/lendery.md` for the endpoint groups. Also renders the
"Needs attention" dashboard (open maintenance cases, unresolved unavailable
items, missing-component reports).

## `lendery-export.html` / `lendery-export.js` (89 / 256 lines) + `.css` (350 lines)

Configurable inventory/history CSV export UI, served at `/lendery/export`.
Small `state = { options: null, type: "inventory" }` — `options` is the
field-configuration payload fetched from `GET /lendery/export/options`.
Downloads via `/lendery/export/{type}.csv`.

## `check.html` / `check.js` (23 / 154 lines) + `.css` (70 lines)

Public, no-auth barcode "Quick Check" lookup tool (`robots noindex`). Served
both at the main app's public router and as the landing page of the separate
`lendery.libtools.app` subdomain ASGI app — see `docs/architecture.md`.
Small `state = { components: [], checked: new Set() }` for a return
checklist. Calls only `GET /api/public/lendery/items/barcode/{barcode}`.

## Gotchas

- The return-checklist state (`checkedComponents`, `physicalManualChecked`
  in `lendery.js`; `checked` in `check.js`) is **client-side only, per
  session** — it is not sent to or persisted by the backend. Don't confuse
  it with the server-side missing-report flags (`Component.missing_reported_at`,
  `LenderyItem.physical_manual_missing`/`checkin_card_missing`).
- Flagging the physical manual or check-in card missing also opens a
  `MaintenanceCase` via a follow-up POST from the frontend (not the backend
  PATCH itself) — that's how those flags surface in the "Needs attention"
  dashboard. See `docs/backend/lendery.md`.
- `renderItems()` reconciles `#inventory-grid`'s existing `article.item-card`
  DOM nodes by `data-item-id` (`reconcileGrid`) instead of replacing
  `innerHTML` wholesale — it patches a card in place only when its
  `cardSignature()` changed, and only brand-new cards get the `is-new` class
  that triggers the CSS phase-in animation. This was added because a full
  rebuild on every availability refresh (up to ~120 rebuilds across a ~60-item
  page load) made the whole grid visibly flash. `scheduleRender()`
  (microtask-coalesced `renderAll()`) is used instead of calling
  `renderItems()`/`renderAll()` directly from availability-refresh code paths,
  so several near-simultaneous refreshes settle into one render pass. Don't
  reintroduce a raw `grid.innerHTML = ...` rebuild in the item-card path
  without re-checking this.
