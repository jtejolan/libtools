# frontend — Book Club Manager

## `bookclub.html` / `bookclub.js` (397 / 1,850 lines)

The app. Single `state` object (top of `bookclub.js`) holds: `user`,
`clubs`/`club` (selected club), `view` (current tab — meetings/books/
members/etc), and per-entity lists (`members`, `books`, `meetings`,
`roster`, `templates`, `participation`) plus UI-only fields
(search queries for the larger collections, `memberSort`, day-of mode, and
unsaved discussion-note state).
Talks to `/bookclub/*` (club-scoped CRUD call sites for
members/books/meetings/roster/templates/emails/giveaway) and
`/bookclub/clubs/*` (club switching). See `docs/backend/bookclub.md` for the
endpoint groups.

Opening a club lands on its nearest upcoming meeting (or the most recent past
meeting when nothing is scheduled). The **All meetings** view is a separate
calendar-style overview divided into upcoming and past sections, with the next
meeting visually promoted.

The Book Club Manager logo returns to that default upcoming session. The
session workspace has previous/next navigation, persisted lifecycle status,
meeting discussion notes, meeting-specific participant notes, and a live
post-meeting recap. Day-of mode temporarily removes the broader application
chrome and summary cards so attendance, notes, and the giveaway remain in
focus. Club settings is the final item in the Manage menu; the former Library
Tools sidebar group has been removed.

Members and participation share one card-based community view. Each member
shows attendance and pages read; the history dialog lists attended books only
and summarizes books, pages, and giveaway wins. Pending welcome/arrival email
badges appear both there and on meeting roster cards.

Communication actions live on the session instead of a separate Messages page.
Roster prompts open a focused welcome or arrival-follow-up dialog for that
member. **Send a book** creates and prints the transit label from the roster,
then marks the member as awaiting arrival. The monthly-reminder button in the
session controls opens address-copy, email-copy, and send actions for the whole
roster.

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
