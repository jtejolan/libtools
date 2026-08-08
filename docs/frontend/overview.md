# frontend/ — overview

No framework, no bundler. Each page is a standalone `<name>.html` +
`<name>.js` file that manages its own DOM and a plain-object `state`, served
directly as static files by FastAPI (`main.py` mounts `/static` to
`frontend/` and serves fixed page routes — see `docs/architecture.md`).

`frontend/src/` and `frontend/public/` exist but are **empty** — not part of
the active build. `frontend/package.json` is **not a file** — it's an empty
directory, a filesystem oddity; there is no npm project here, don't try to
`npm install`.

## Shared files

| File | Lines | Purpose |
|---|---|---|
| `dom-utils.js` | 8 | `escapeHtml()` — the only shared JS helper, included via `<script defer>` on 9 of the 10 app pages (all except `index.html`) |
| `platform.css` | 268 | Shared chrome/layout across `account`, `admin-accounts`, `admin-users`, `dashboard`, `check`, `public-club`, `bookclub-landing`, `bookclub-account`, `bookclub-participant` |
| `quotes.js` | 614 | Static book-quote content data (not logic), used by `index.html` and `dashboard.html` only |

There is **no shared `api.js`** — every page duplicates its own
`request()`/`requestJson()` fetch wrapper. This is an intentional,
consistent convention — see `docs/coding-guidelines.md`.

## Page inventory

| Page pair | Lines (html+js+css) | Purpose | Detail in |
|---|---|---|---|
| `index.html`/`home.js` | 207+131 | Public marketing homepage | `docs/frontend/accounts.md` |
| `dashboard.html`/`dashboard.js` | 6+402 | Post-login landing page, tool grid | `docs/frontend/accounts.md` |
| `account.html`/`account.js` | 162+284 | Login/register/password-reset/recovery/settings | `docs/frontend/accounts.md` |
| `admin-accounts.html`/`.js` | 70+178 | Platform-admin account management (canonical) | `docs/frontend/accounts.md` |
| `admin-users.html`/`.js` | 2+12 | Minified legacy duplicate — don't edit | `docs/frontend/accounts.md` |
| `bookclub.html`/`bookclub.js` | 406+1514 | Book Club Manager app | `docs/frontend/bookclub.md` |
| `public-club.html`/`.js` | 1+15 | Public read-only club page (minified) | `docs/frontend/bookclub.md` |
| `lendery.html`/`lendery.js` | 466+2458 | Lendery inventory app (largest JS file in repo) | `docs/frontend/lendery.md` |
| `lendery-export.html`/`.js` | 89+256 | Configurable CSV export UI | `docs/frontend/lendery.md` |
| `check.html`/`check.js` | 23+154 | Public barcode quick-check, no auth | `docs/frontend/lendery.md` |

Full file-by-file line counts: `docs/code-index.md`.
