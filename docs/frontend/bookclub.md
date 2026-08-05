# frontend — Book Club Manager

## `bookclub.html` / `bookclub.js` (406 / 1,514 lines)

The app. Single `state` object (top of `bookclub.js`) holds: `user`,
`clubs`/`club` (selected club), `view` (current tab — meetings/books/
members/etc), and per-entity lists (`members`, `books`, `meetings`,
`roster`, `questions`, `templates`, `participation`) plus UI-only fields
(search queries per tab, `participationSort`, `transitSelectedMemberId`).
Talks to `/bookclub/*` (club-scoped CRUD, ~19 distinct call sites for
members/books/meetings/roster/templates/questions/emails/giveaway) and
`/bookclub/clubs/*` (club switching). See `docs/backend/bookclub.md` for the
endpoint groups.

## `public-club.html` / `public-club.js` (1 / 15 lines, minified)

Public read-only club page rendered at `/clubs/{slug}`. No `state` object —
a single IIFE fetches `GET /api/public/clubs/{slug}` and renders the club
name/description, book shelf, and next meeting directly into the DOM. Uses
`platform.css`, not `bookclub.css`.

## Gotchas

- `bookclub.js`'s `state.view` drives which tab is rendered — most render
  functions branch on it rather than the page having separate routes.
- `public-club.js` is genuinely minified (not just short) — if it needs a
  real edit, consider whether to de-minify it first rather than hand-editing
  packed code.
