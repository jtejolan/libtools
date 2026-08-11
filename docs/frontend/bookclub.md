# frontend — Book Club Manager

## `bookclub.html` / `bookclub.js` (463 / 2,446 lines)

The app. Single `state` object (top of `bookclub.js`) holds: `user`,
`clubs`/`club` (selected club), `view` (current tab — meetings/books/
members/etc), and per-entity lists (`members`, `memberAccess`, `books`,
`meetings`, `roster`, `templates`, `participation`) plus UI-only fields
(search queries for the larger collections, `memberSort`/`memberAccessFilter`/`bookSort`,
`bookDisplay`, the open `bookDetailId`, day-of mode, and unsaved
discussion-note state).
Talks to `/bookclub/*` (club-scoped CRUD call sites for
members/books/meetings/roster/templates/emails/giveaway) and
`/bookclub/clubs/*` (club switching). See `docs/backend/bookclub.md` for the
endpoint groups.

The topbar club switcher (`#club-menu`) is a `<details>` dropdown listing the
user's other clubs plus a "+ Create a new book club" link to the standalone
`bookclub-new.html`/`.js` page at `/bookclub/new` (POSTs `/bookclub/clubs`,
selects it, then redirects to `/bookclub`). The `#club-dialog` modal still
exists but only for the ambiguous case where multiple clubs exist and none is
selected yet (or ad-hoc dashboard deep-links); it no longer contains the
create-club form.

The Books view includes a client-computed collection snapshot: catalogue/page
totals, reading-length and genre bar charts, a read/upcoming/unscheduled shelf
ring, and the publication-year span. Its sort menu supports title, author,
page-count, and publication-date ordering; books missing the selected numeric
or date field are kept at the end in either direction. `bookDisplay` drives
the accessible List/Compact toolbar toggle: list mode keeps the descriptive
horizontal record, while compact mode becomes a cover-forward responsive grid
without changing the card's detail, edit, or delete interactions.

Book cards are keyboard-accessible detail triggers (`data-open-book-detail`),
with Edit/Delete buttons remaining independent. `openBookDetail()` fetches the
staff-only `GET /bookclub/books/{id}/insights` aggregate and opens
`#book-detail-dialog`: full edition metadata and facilitator notes, meeting
discussion history, attendance, reader-page impact, participant ratings and
reviews, plus previous/next navigation in chronological club-book order.
Meeting rows jump into the existing session workspace rather than duplicating
its editing controls in the dialog.

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
name means "welcome email pending," not "new member." The **Run session**
button toggles the internal `dayOfMode`: it temporarily removes broader
application chrome and the recap, then lays out attendance beside a sticky
discussion-notes panel on desktop (stacked on mobile) so both remain usable
during the conversation. The old three-card meeting stats block is now a
compact `.session-summary-strip` inside the roster heading.

The post-meeting recap is progressively disclosed via
`#toggle-session-recap`. A newly opened planned meeting starts collapsed; it
automatically expands when attendance or discussion notes make the summary
useful, and completed meetings open it by default. Manual Show/Hide controls
remain available afterward.

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

Members and participation share one card-based directory. Its heading explains
that every participant belongs here while an online account remains optional.
Each member
card shows a prominent, copyable email (`.copy-email-button`, clipboard copy
via a `data-copy-email` click-delegate branch) alongside attendance and pages
read. Every card also has a plain-language **Community access** row: Community
active, Verification pending, No account, Account disabled, or
Inactive member. The directory can filter on the same states and flags when
announcements are off. Context actions copy the public invitation, resend email
verification, or reactivate an inactive roster member when that action applies;
history and edit remain available on every card. The history dialog lists
attended books only and summarizes books, pages, and giveaway wins. Pending
welcome/arrival email badges appear both there and on meeting roster cards.

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

## `public-club.html` / `public-club.js` / `public-club.css`

Responsive invitation destination rendered at `/clubs/{slug}`. It fetches
`GET /api/public/clubs/{slug}` and presents the club identity, organizer,
current book, and upcoming meeting with public `.ics`/Google Calendar actions in
one unified opening hero before a consolidated membership invitation and the
previous-book shelf. The compact
invitation pairs Join/sign-in actions with the participant features they unlock,
including conversation, reading progress, ratings and reviews, stats, and
club decisions. Its membership controls reflect the club's open/invitation-only/
closed enrollment policy. When a participant session is present, they change
from generic signup links to an account-aware open/join action and support
joining a second open club without another account.

## `bookclub.libtools.app` participant community

- `bookclub-landing.html` is the participant-first entry point. Its invitation
  tab accepts either a full `/clubs/{slug}` link or the slug as a short club
  code and verifies that the public club exists before navigating. Its sign-in
  tab authenticates the global participant identity and displays every linked
  public club through `GET /participant/auth/clubs`; choosing one updates the
  active roster membership before opening `/dashboard`. Returning signed-in
  readers see the same chooser automatically. “Start a club” remains a
  facilitator path to the regular Libtools signup/Book Club Manager flow.
- `public-club.html` is the club-specific step between an invitation and the
  account/dashboard experience; it exposes enrollment-aware Join, sign-in, and
  calendar actions on the subdomain.
- `bookclub-account.html` handles participant registration, login, recovery,
  and verification only; the old facilitator creation card is removed.
- `bookclub-participant.html` is a small routed participant portal with
  **Home**, **Books**, **My stats**, **Club stats**, and **Members** views.
  Home uses a conversational morning, afternoon, evening, or late-night greeting
  that includes the participant's name, and remains calm and current-book-first.
  A compact book hero leads directly into three visible workspaces:
  **Conversation**, **Ratings and Reviews**, and **Reading progress**. Conversation uses
  a compact horizontal activity ribbon above an orderly single-column thread feed,
  with visually nested replies, spoiler-aware posts, and reactions;
  the hero includes an immediately saved, keyboard-accessible clickable star
  rating with half-star precision. Its review shortcut opens a focused modal
  with the same star control and a written-review field; Ratings and Reviews is a
  read-only visual dashboard with a large aggregate score, rating-distribution
  bars, and an orderly member review feed;
  Reading progress includes optional sharing plus a live graphical calculator
  with a completion ring, page slider, exact-page entry, and automatic
  daily/weekly pace targets. Books is a dedicated club reading journey with a
  current/next chapter, shared-shelf milestones, and a connected cover-forward
  searchable/filterable history modeled on the facilitator collection. It also
  includes a frontend-only Google Books suggestion flow that previews the title
  destined for the facilitator queue without claiming to submit it before the
  backend is connected. Choosing a club title opens a stable query-routed
  book view; completed titles default to a participant-safe session recap with
  previous/next book navigation, aggregate attendance, reader-pages, and public
  discussion notes. The latest announcement expands automatically when its
  newest item is unread, can be marked read and minimized into a compact strip,
  and retains an unread-count badge plus minute/visibility refresh checks for
  new posts. Book/date votes stay in a collapsed **Open
  decisions** section until needed. The page also provides a club switcher,
  announcement archive with read state, calendar actions, a grouped searchable
  immediate/digest notification preferences, and an opt-in member directory
  whose responses never expose roster email or staff notes. My stats summarizes
  the signed-in reader's meetings, books, pages, ratings, genres, progress, and
  recent activity. Club stats is presented as **Our club story**: a community
  personality summary, favourite genres, book-length patterns, reader-favourite
  titles, shelf momentum, shared rating patterns, and a book-focused timeline of
  completed reads. It omits attendance reporting, leaderboards, and individual
  comparisons. It has no facilitator role or management link.
- `bookclub-manage.html` is now served from
  `libtools.app/bookclub/community`, authenticated by the regular Libtools
  session and selected club. It shares the Book Club Manager's green sidebar,
  account menu, responsive shell, and direct navigation to the Meetings, Books,
  Members, and Settings views. Its content focuses on community health/account
  activation, next-meeting RSVP counts, book/date polls, announcements, and a
  discussion moderation queue. A
  prominent **Invite readers** dialog supplies the canonical
  `bookclub.libtools.app/clubs/{slug}` link, copyable club code, downloadable
  QR code, and public-page preview. Private clubs see a settings prompt instead
  of unusable share controls.
  Books, meetings, roster details, and email templates stay on their dedicated
  manager pages.

## Gotchas

- `bookclub.js`'s `state.view` drives which tab is rendered — most render
  functions branch on it rather than the page having separate routes.
- `public-club.html`/`.js`/`.css` is shared: it's served both at
  `libtools.app/clubs/{slug}` (primary app) and
  `bookclub.libtools.app/clubs/{slug}` (`bookclub_public_app`) — one file,
  two hosts.
## Participant attendance history

Completed session cards on the participant book page let signed-in members self-report whether they attended. The report immediately contributes to personal and club statistics and is identified as self-reported in the facilitator roster. Facilitators can confirm the report or toggle the roster attendance to correct it; once a facilitator records attendance, that authoritative value remains in use even if the participant submits another report.

## Reader book suggestions

The participant Books page has a Google Books search and a persistent suggestion form. Selecting a result preserves its catalogue metadata and opens an optional comments field before submission. Suggestions are independent of formal voting rounds, appear in the facilitator Community page under Book suggestions, and can be added to the club library or dismissed. Accepted suggestions retain their review status and point to the newly created club book.
