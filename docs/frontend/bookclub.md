# frontend — Book Club Manager

## `bookclub.html` / `bookclub.js` (433 / 2,181 lines)

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
meeting when nothing is scheduled) via the Book Club Manager logo
(`#open-next-meeting`, calls `openDefaultMeeting()` + `chooseDefaultMeeting()`).
The sidebar **Meetings** nav item (`data-view="meetings"`) is a separate,
plain browse-all entry point — it opens the calendar-style overview
(`renderMeetings()`, upcoming/past sections with the next meeting visually
promoted), it does **not** jump to the current meeting. There is no
"view all meetings" button on the session page — the nav item is the only way
back to the overview from inside a session.

The session workspace has previous/next navigation, meeting discussion notes,
meeting-specific participant notes, and a live post-meeting recap. A roster
member gets a distinct "✦ First meeting" badge (`.status-pill.first-session-badge`,
computed client-side from `state.participation`) when the meeting being
viewed is their first-ever attended session — roster only, not the Members
grid. Don't confuse this with `.status-pill.new-badge`, which despite its
name means "welcome email pending," not "new member." Day-of mode
temporarily removes the broader application chrome and summary cards so
attendance, notes, and the giveaway remain in focus.

Roster entries render as `.roster-member-card` articles (`renderRoster()`,
`#roster-table` — an `id` left over from when this was a `<table>`, now a
plain grid `<div>`). The whole card is the attendance toggle: a delegated
click/keydown listener on `#roster-table` calls `saveParticipation(id,
{attended})` for any click that doesn't land on `[data-roster-menu]` (the
per-card kebab `<details>`) or `[data-open-followup]` (the email badges,
kept directly on the card). Toggling flips `.is-attended` optimistically
before the request resolves so the transition plays immediately; the
following `renderMeetingView()` re-render then settles it into the real
state. **Add note**/**Send a book**/**Remove member** live in the kebab
menu now — there's no more standalone "Send a book" button or attendance
checkbox. Removing a member is immediate, no `window.confirm`.

**Status is mostly computed, not chosen.** `effectiveMeetingStatus(meeting)`
returns `"completed"` if that's the stored status, `"in_progress"` if `now`
falls within the meeting's `starts_at`/`ends_at` window (server-computed,
null if `meeting_time` doesn't parse), else `"planned"` — there's no status
dropdown anymore, just a live badge (`#meeting-status-badge`, refreshed by a
60s `setInterval` so it flips to "In progress" without a reload) and a
`#toggle-completed` button that PATCHes `status` between `"planned"`/
`"completed"` only. `"in_progress"` and `"cancelled"` are gone as stored
values — see `docs/backend/bookclub.md` for the migration that normalized
old rows.

The giveaway is a heading-row action button (`#open-giveaway-dialog`, "Draw a
Name", in `.session-mode-controls` next to "Send Reminder" — styled the same
way, both `.reminder-trigger`) rather than a page panel — clicking it opens
`#giveaway-dialog`, plays a spin animation (`.giveaway-orbit.drawing`,
`drawWinner()`, at least 5s — an artificial `setTimeout` on top of the actual
`POST /bookclub/meetings/{id}/giveaway/draw`, since the request alone is too
fast to read) then reveals the winner. `renderGiveaway()` still targets
`#giveaway-content` by id, just relocated into the dialog.

**Archive view**: `#toggle-archive-view` in `.session-mode-controls` PATCHes
`archived_at` and switches to a second, read-only summary layout
(`#meeting-archive-view`, `renderArchiveView()`) that becomes the *default*
view for that meeting going forward — `state.viewingEdit` (session-local,
reset whenever `loadSelectedMeeting()` runs) decides which of
`#meeting-archive-view`/`#meeting-edit-view` is shown, defaulting to the
archive view whenever `meeting.archived_at` is set. "Edit session"
(`#edit-session`, in the archive view's own header) flips back to the normal
workspace without touching the flag; "Unarchive" (`#unarchive-meeting`,
in edit view, hidden unless archived) clears it. This is a **live view**, not
a frozen snapshot — `renderArchiveView()` reads the same `state.roster`/
`sessionRecap()` data as the edit view, so an edit made after archiving shows
up immediately next time the archive view renders. `sessionRecap()` was
extended (not forked) with `notAttended`/`newMembers` name lists for this.

Adding/editing a meeting picks the book via a type-to-search autocomplete
(`#meeting-book-search`/`#meeting-book-results`, `renderBookSearchResults()`)
instead of a `<select>` — same pattern as `renderMemberSearchResults()`
(roster-add search), writing into a hidden `book_id` input. A duration
`<select>` (30 min–3 hr presets, default 90) sits next to the free-text
start-time input — together these drive the backend's computed
`starts_at`/`ends_at` that the status badge above depends on. Both
`destination_branch` inputs (member dialog, send-a-book composer) have a
shared `<datalist id="branch-suggestions">` fed by `renderBranchSuggestions()`
from distinct branches already on file — no backend endpoint for this.

**Club settings** is the final sidebar item and is a full page (not a
dialog), merging the club-identity form (name/description/organizer/video
call link/public toggle) with the "Email & label templates" editor that used
to be its own separate "Templates" nav item — there is no standalone
Templates page anymore.

Members and participation share one card-based community view. Each member
card shows a prominent, copyable email (`.copy-email-button`, clipboard copy
via a `data-copy-email` click-delegate branch) alongside attendance and pages
read; the history dialog lists attended books only and summarizes books,
pages, and giveaway wins. Pending welcome/arrival email badges appear both
there and on meeting roster cards.

Communication actions live on the session instead of a separate Messages page.
Roster prompts (`openFollowupDialog()`) open a dialog with four distinct
actions: **Copy address** (bare email, `data-copy-email`), **Copy email
text** (composed To/Subject/Body via a `.../preview` fetch,
`data-copy-registrant-email`), **Mark as sent** (records the sent-timestamp
without emailing, `data-mark-registrant-sent` → `.../mark-sent`, for when
staff send manually), and **Send email** (real in-app send,
`data-send-registrant-email` → `.../send`). **Send a book** creates and
prints the transit label from the roster, then marks the member as awaiting
arrival. The "Send Reminder" trigger (`#open-reminder-dialog`, in the
session command bar) opens address-copy, email-copy, and send actions for
the whole roster.

The transit label's `@media print` rule (`bookclub.css`, in the print
section near the end of the file) is sized for an 80mm thermal receipt
printer (`@page { size: 80mm auto; margin: 0 }`, monospace font, no
borders/columns) rather than a full letter/A4 sheet — it's only ever
printed one at a time from "Send a book" via `window.print()`
(`printTransitLabel()`), never as a batch of multiple labels per page.

## `public-club.html` / `public-club.js` (1 / 15 lines, minified)

Public read-only club page rendered at `/clubs/{slug}`. No `state` object —
a single IIFE fetches `GET /api/public/clubs/{slug}` and renders the club
name/description, book shelf, and next meeting directly into the DOM. Uses
`platform.css`, not `bookclub.css`.

## `bookclub.libtools.app` pages

Served by `bookclub_public_app` (see `docs/architecture.md`), not the
primary app — separate pages from everything above, styled with
`platform.css` for visual consistency but functionally independent.

- **`bookclub-landing.html` / `.js`** — subdomain root. "Start a club" goes
  to `/create` — entirely in-subdomain, since facilitators are
  `ParticipantAccount`s now, not `LibtoolsUser`s (see
  `docs/backend/bookclub.md`); "Find your club" is a slug search that
  navigates to `/clubs/{slug}`.
- **`bookclub-account.html` / `.js`** — one shared shell for both the
  facilitator create-club flow and participant
  join/login/forgot-password/verify-email/reset-password, keyed by URL path
  the same way `account.html`/`account.js` handles the equivalent staff
  flows. `/create` (create a club + its owner account together, no slug —
  there's no club yet), `/clubs/{slug}/join`, `/clubs/{slug}/login`, and
  `/clubs/{slug}/forgot-password` read the slug from the URL path (no club
  picker); `/verify-email` and `/reset-password` don't need one since a
  token alone identifies the participant.
- **`bookclub-participant.html` / `.js`** — logged-in participant dashboard
  at `/dashboard`, shared by both plain participants and facilitators
  (`role="owner"`). Currently a shell (welcome message, email-verification
  nudge, logout) — rating/voting UI and a facilitator-only "manage your
  club" console entry point land in later phases.

## Gotchas

- `bookclub.js`'s `state.view` drives which tab is rendered — most render
  functions branch on it rather than the page having separate routes.
- `public-club.js` is genuinely minified (not just short) — if it needs a
  real edit, consider whether to de-minify it first rather than hand-editing
  packed code.
- `public-club.html`/`.js` is shared: it's served both at
  `libtools.app/clubs/{slug}` (primary app) and
  `bookclub.libtools.app/clubs/{slug}` (`bookclub_public_app`) — one file,
  two hosts.
