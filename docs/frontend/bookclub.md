# frontend — Book Club Manager

## `bookclub.html` / `bookclub.js` (457 / 2,298 lines)

The app. Single `state` object (top of `bookclub.js`) holds: `user`,
`clubs`/`club` (selected club), `view` (current tab — meetings/books/
members/etc), and per-entity lists (`members`, `books`, `meetings`,
`roster`, `templates`, `participation`) plus UI-only fields
(search queries for the larger collections, `memberSort`/`bookSort`, day-of mode, and
unsaved discussion-note state).
Talks to `/bookclub/*` (club-scoped CRUD call sites for
members/books/meetings/roster/templates/emails/giveaway) and
`/bookclub/clubs/*` (club switching). See `docs/backend/bookclub.md` for the
endpoint groups.

The Books view includes a client-computed collection snapshot: catalogue/page
totals, reading-length and genre bar charts, a read/upcoming/unscheduled shelf
ring, and the publication-year span. Its sort menu supports title, author,
page-count, and publication-date ordering; books missing the selected numeric
or date field are kept at the end in either direction.

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
  (`role="owner"`). A welcome message, email-verification nudge, logout,
  and — for owners only — a "Manage your club" card linking to `/manage`.
  A "Vote on the next book" section (`#voting-content`) shows the current
  round's approved candidates with a vote button (highlights
  `my_vote_candidate_id`), a "propose another book" `<select>` built from
  books not already candidates, and — for the participant's own
  not-yet-approved proposals only — a small "awaiting facilitator approval"
  note; other participants' pending/rejected proposals aren't shown at all.
  While the round is open, `vote_count` comes back `null` from the API
  (hidden) so no tally renders; once `status: "closed"`, results render
  with counts and a 🏆 next to the winning book. Below that, a "Rate what
  you've read" section (`#ratings-list`, `.rating-card`/`.star-row`/
  `.star-button` in `platform.css`) lists every book in the club with a
  clickable 1-5 star widget and an optional review textarea; ratings are an
  upsert (`PUT /participant/books/{id}/rating`) — resubmitting updates your
  existing rating rather than adding a second one. Other participants'
  ratings/reviews are visible too, collapsed behind a `<details>` ("N other
  reviews"), not just an aggregate average — fetched per-book
  (`GET .../ratings`), N+1 requests, acceptable at club-catalogue scale.
  The club's book list (`/participant/books`) is fetched once into
  `participantState.books` and reused by both the ratings section and the
  voting "propose" dropdown, rather than fetched twice. A separate "Vote on
  the next meeting date" section (`#date-poll-content`) follows the same
  hidden-tally-while-open / 🏆-on-close pattern as book voting, but has no
  "propose a date" form at all — date options are facilitator-only (see
  `docs/backend/bookclub.md`'s "two separate systems" gotcha), so there's
  nothing for a participant to propose.
- **`bookclub-manage.html` / `.js`** — the facilitator console at `/manage`,
  redirects non-owners back to `/dashboard`. A single tabbed page (Books /
  Meetings / Voting / Meeting date / Templates, `.manage-tab`/
  `.manage-dialog` in `platform.css`), not a `bookclub.js`-style multi-view
  SPA — deliberately smaller, since it only needs the generic CRUD
  `facilitator_routes.py` exposes (no member-roster/transit-label/giveaway
  UI, none of that applies to self-serve clubs). Books support the same
  BiblioCommons catalogue-import flow as the staff tool
  (`POST /facilitator/books/import`). The Voting tab: "Start a poll" opens
  `#start-voting-dialog` with a checkbox per club book (facilitator-proposed
  candidates auto-approve); once open, pending (participant-proposed)
  candidates get inline Approve/Reject buttons, vote counts are always
  visible (unlike the participant view), and "Add another candidate"
  appends more books to the same open round without needing a new poll.
  The Meeting date tab is the same shape but simpler — `#start-date-poll-dialog`
  has three plain `<input type=date>` fields (2 optional) instead of a book
  checklist, since there's no approval queue to render. On the Templates
  tab, `kind === "email"` templates get a "Send to participants" button
  (`POST /facilitator/broadcast`) alongside Edit — a `confirm()` dialog
  first (same pattern as delete actions elsewhere in this file), then a
  toast reporting `sent_count`/`recipient_count`, or — since
  `RESEND_API_KEY` is commonly unset in dev — "Email delivery isn't
  connected yet — would have reached N participants" when
  `delivery_configured` is `false`. A second toast surfaces
  `missing_variables` if the template had unfilled `{{placeholders}}`.
- **`bookclub-unsubscribe.html` / `.js`** — the public page at `/unsubscribe?token=…`
  linked from every broadcast email. Loading the page does *not* unsubscribe
  anyone — it shows a "Confirm unsubscribe" button the visitor must click,
  specifically so an email client's link-prefetching/security-scanning
  can't trigger a real unsubscribe just by fetching the URL. Works with no
  login at all (`POST /participant/unsubscribe` takes only the token).
  Re-visiting an already-used link renders "Already unsubscribed" rather
  than erroring, since the underlying token isn't single-use (see
  `docs/backend/bookclub.md`'s gotcha on why).

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
