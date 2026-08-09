# bookclub/

Multi-tenant book club manager. Every club-owned table is scoped by
`club_id`, and uniqueness constraints (email, ISBN, template key) are scoped
**per club**, not global. Available to every signed-in Libtools account
(not gated by `ToolAccess` — see `docs/backend/accounts.md`).

## Models (`bookclub/models.py`, 454 lines)

| Model | Table | Purpose |
|---|---|---|
| `BookClub` | `book_clubs` | A club: name, slug, `public` page flag, independent `enrollment_policy` (`open`/`invite_only`/`closed`), organizer info, and `club_type` (`library`/`private`, presentation/defaults only) |
| `BookClubAccess` | `book_club_access` | User-to-club grant (`role`, e.g. owner) |
| `BookClubMember` | `bookclub_members` | A club's member roster; unique per `(club_id, email)`; carries delivery details plus transit-label/email timestamps |
| `BookClubBook` | `bookclub_books` | A book the club has read/will read; unique per `(club_id, isbn)`; can be flagged as an undated past selection |
| `BookClubMeeting` | `bookclub_meetings` | A dated session tied to one book, with `meeting_duration_minutes`, an `archived_at` display-mode flag, and discussion notes; `book_title`/`book_author` are denormalized copies kept in sync on write. `starts_at`/`ends_at` are computed `@property`s (not columns), from `bookclub/scheduling.py` |
| `BookClubParticipation` | `bookclub_participation` | Member roster for one meeting (`attended`, participant-set `rsvp_status`, and a session-only note); unique per `(meeting_id, member_id)`. RSVP and attendance intentionally share this record. |
| `BookClubAnnouncement` | `bookclub_announcements` | Community announcement scoped to one club, with title/body, timestamps, and optional pinned priority. |
| `BookClubReadingProgress` | `bookclub_reading_progress` | Optional private reading state (`not_started`/`reading`/`finished`) for one roster member and club book; no row means the participant chose not to track it. |
| `BookClubNotificationPreference` | `bookclub_notification_preferences` | Per-membership preferences for announcements, polls, meeting reminders, and future discussion replies. |
| `BookClubTemplate` | `bookclub_templates` | Editable email template; unique per `(club_id, key)` |
| `BookClubDiscussionQuestion` | `bookclub_discussion_questions` | Legacy ordered questions retained for API compatibility; migration `e93f1a6b2c47` copies existing text into meeting discussion notes |
| `BookClubRating` | `bookclub_ratings` | A participant's 1-5 rating (DB `CheckConstraint`) + optional review of a book; unique per `(book_id, participant_id)`, editable (upsert, not append). FK to `ParticipantAccount` is a plain string FK (`bookclub_participant_accounts.id`), not an ORM `relationship()` — `crud.py` joins in the participant's name explicitly instead, since that model lives in `participant_models.py` and there's no existing precedent in this package for a cross-module `relationship()`. |
| `BookClubVotingRound` | `bookclub_voting_rounds` | A "what should we read next" poll; `status` `"open"`/`"closed"` only (simplified from an originally-planned draft/open/closed — see gotcha below), `winning_book_id` set on close. One open round per club at a time, enforced in `crud.py` (app-level, not a DB constraint). |
| `BookClubBookCandidate` | `bookclub_book_candidates` | A book nominated for a round; manager-added candidates auto-approve, participant proposals require approval through `/bookclub/community/candidates/{id}/approve` |
| `BookClubVote` | `bookclub_votes` | One participant's vote for a candidate; unique per `(voting_round_id, participant_id)` — casting a second vote updates the existing row rather than adding one. |
| `BookClubDatePoll` | `bookclub_date_polls` | A "when should we meet next" poll — a **deliberately independent system** from `BookClubVotingRound`/`BookClubBookCandidate`/`BookClubVote` above, not a shared generalized poll (explicit product choice). Same open/closed shape, `winning_date` set on close, one open poll per club at a time (app-level, same as voting rounds). |
| `BookClubDatePollOption` | `bookclub_date_poll_options` | A candidate date; unique per `(poll_id, option_date)`. **Facilitator-only** — no participant-proposal path, so unlike `BookClubBookCandidate` there's no `status`/approval queue at all. |
| `BookClubDatePollVote` | `bookclub_date_poll_votes` | One participant's vote for a date option; unique per `(poll_id, participant_id)`. |

## Account and roster model

Every club—library-run or private—is created and managed by a regular
`LibtoolsUser` through `BookClubAccess` and the primary Book Club Manager.
`bookclub.libtools.app` is participant-only. Its `/create` and `/manage`
paths redirect to the corresponding `libtools.app` account/manager flows.

`BookClubMember` is the canonical roster record. It may have a nullable
`participant_account_id`; unlinked members still support attendance, email,
delivery, notes, and giveaways, while linked members can also use announcements,
RSVP, ratings, book voting, and date polling. For an `open` club, registration
or an existing participant account can create a new linked roster row. An
`invite_only` club requires the facilitator to preload the same email on the
roster; `closed` permits only already-linked accounts to sign in. Public-page
visibility is deliberately independent from all three enrollment modes.

`ParticipantAccount` is a global email/password identity, unique by email,
and can link to roster entries in multiple clubs. The participant session
stores both the global account ID and the currently entered roster member ID.
Unsubscribe state is per roster membership, not global, so leaving one club's
broadcasts does not silence another club.

The manager member directory gets its bulk, derived access state from
`GET /bookclub/members/community-access`: Community active, Verification
pending, Invitation not accepted, Account disabled, or Inactive member, plus
the per-membership announcement subscription flag. Facilitators can issue a
fresh verification email through `POST /bookclub/members/{member_id}/verification`;
the endpoint refuses unlinked, disabled, or already-verified accounts.

Community management routes live at `/bookclub/community/*` on the primary
app and use `require_selected_club`. Participant routes remain on the
subdomain at `/participant/*`. Manager-added poll candidates use a null
participant proposer and auto-approve; reader proposals enter the approval
queue.

`GET /bookclub/community/overview` is a read-only community-health aggregate:
active roster totals, linked/verified/pending account status, the next meeting's
RSVP counts, and pending participant book proposals. Activation is derived from
the canonical roster link and `ParticipantAccount.email_verified_at`; there is
no second activation table or community roster.

Announcements are managed at `/bookclub/community/announcements` and read at
`/participant/announcements`. The participant RSVP endpoints live under
`/participant/meetings/*`; saving one creates or updates the same participation
row staff later use to record attendance.

Participant community routes also expose optional reading progress, per-club
notification preferences, a personal activity aggregate, a Google Calendar
link, and an authenticated `.ics` meeting download. Activity is derived from
existing ratings, votes, proposals, attendance, and reading-progress records;
it is not a second append-only audit log.

The participant landing page also supports account-first navigation. A global
login verifies the participant once, claims any still-unlinked active roster
rows with the same email, and returns the account's public clubs. Authenticated
readers can list those clubs and switch the active `bookclub_member_id` stored
in the participant session without signing in again. Existing club-scoped
login URLs remain supported for invitations and password recovery. A reader
who signs into or explicitly joins a second `open` club receives another linked
roster membership without creating another global account.

Migration `7e4c2a1f9d30` removes obsolete test-only `self_serve` clubs and
participant identities, makes participant email global, and adds the roster
link and per-membership unsubscribe fields. No compatibility merge is
attempted because the removed data was explicitly non-production test data.
Migration `9b2f4d6a8c10` adds club announcements and nullable RSVP status.
Migration `b4d7f1a3c920` adds optional reading progress and notification preferences.
Migration `e8a1c4d72f60` adds the separate enrollment policy, defaulting existing
clubs to `open` for backward compatibility.

## Routes

| Router | Prefix | File | Endpoints | Purpose |
|---|---|---|---|---|
| `router` | `/bookclub/clubs` | `club_routes.py` | 5 | Club CRUD, select-into-session, list accessible clubs |
| `public_router` | `/api/public/clubs` | `club_routes.py` | 2 | `GET /{slug}` public club data plus public upcoming-meeting `.ics` download |
| `router` | `/participant/auth` | `participant_routes.py` | 12 | Global and club-scoped participant registration/login, enrollment-aware joining, club listing/selection, session, verification, and password reset |
| `router` | `/bookclub` | `routes.py` | 47 | Members (including bulk community-access state and verification resend), books (incl. Google Books search and read-only `/{book_id}/insights` aggregation), meetings, roster/participation, onboarding/arrival email preview/send/**mark-sent** and reminder preview/send, giveaway draw, templates, transit labels, discussion questions — whole router requires `require_selected_club` |
| `router` | `/bookclub/community` | `facilitator_routes.py` | — | Community overview, announcements, book/date polls, plus supporting scoped endpoints |
| `router` | `/participant` | `participant_community_routes.py` | — | Announcements, next meeting/RSVP/calendar, optional reading progress, notification preferences, and personal activity |

## Other modules

- `access.py` — `slugify()`, `accessible_club_statement()` (admins see all
  clubs, others only clubs they have `BookClubAccess` to),
  `require_bookclub_tool` (blocks users with `must_change_password` set),
  `require_selected_club` (reads `bookclub_id` from the session, 409s if
  none selected, 403s if the user can't access it — exported as the
  `SelectedClub` dependency type).
- `catalogue.py` — `search_catalogue_books(query)` searches the Google Books
  API (`GET https://www.googleapis.com/books/v1/volumes`, optional
  `GOOGLE_BOOKS_API_KEY` env var to raise the quota) to autofill book
  metadata (title/author/ISBN/cover/etc) for the "Fill book details" search
  in the book dialog. This module also still owns the Vaughan PL
  (BiblioCommons) HTTP-fetch/JSON-state-extraction primitives
  (`fetch_catalogue_page`, `parse_catalogue_state`, `clean_catalogue_text`,
  `CatalogueImportError`) — `lendery/catalogue.py` imports and reuses these
  for its own item-metadata scraping, even though its field-level parsing
  (`parse_catalogue_item`) is separate from this module's book-field
  parsing. Don't remove/rename these primitives without checking
  `lendery/catalogue.py`. See `docs/backend/lendery.md`.
- `facilitator_routes.py` also serves an authenticated, no-store SVG invitation
  QR code for the selected public club at `/bookclub/community/invite-qr.svg`.
  The encoded destination always uses the participant subdomain origin; private
  clubs receive `409` until their public page is enabled.
- `scheduling.py` (34 lines) — `parse_meeting_time()` (free-text, 5 known
  formats) and `meeting_datetime_range()`. Lives outside both `models.py`
  and `crud.py` so each can import it without a circular dependency;
  `models.py`'s `starts_at`/`ends_at` properties and `crud.py`'s
  `build_calendar_link()` both use it.
- `crud.py` (1,511 lines) — DB operations for every model above, including
  ratings (`get_book_ratings`/`get_own_rating`/`upsert_rating`/`delete_rating`),
  book voting (`open_voting_round`/`add_candidate`/`set_candidate_status`/
  `cast_vote`/`close_voting_round`/etc), date polling (the
  `*_date_poll`/`*_date_option`/`*_date_vote` functions — a parallel,
  independent set, not shared with the voting functions above), broadcast
  email (`list_broadcastable_participants`, `mark_participant_unsubscribed`),
- `GET /bookclub/books/{book_id}/insights` is the staff Books-page detail
  aggregate. It combines club-scoped meeting participation/discussion data
  with participant-account ratings, returning per-meeting attendance and
  reader-page impact without exposing participant email or authentication data.
- `email_delivery.py` (26 lines) — thin plain-text wrapper over the shared
  `backend/app/email_delivery.py`.

## Gotchas

- Most of `routes.py` depends on `SelectedClub` (from `require_selected_club`),
  **not** just `BookClubUser` — a request without a club selected in the
  session gets a 409, not a 401/403.
- Public read-only access lives in `club_routes.py`'s `public_router`, not
  in `routes.py` — don't look for it there. That same `public_router` is
  mounted on *both* the primary app (serving `/api/public/clubs/{slug}` at
  `libtools.app/clubs/{slug}`) and the `bookclub_public_app` sub-app (serving
  it at `bookclub.libtools.app/clubs/{slug}`) — one router, two hosts, see
  `docs/architecture.md`.
- Uniqueness is per-club everywhere: two different clubs can have members
  with the same email, books with the same ISBN, or templates with the same
  key. Only `BookClub.slug` is globally unique.
- `BookClubMeeting.book_title`/`book_author` are denormalized snapshots kept
  in sync with the linked `BookClubBook` on write, retained for
  backwards-compatible migrations — don't treat them as the source of truth,
  edit via the book relationship.
- Printing a transit label records `transit_label_printed_at`; the UI treats a
  later print than `arrival_email_sent_at` as a fresh arrival-confirmation task.
- Member deletion explicitly clears saved giveaway-winner references and
  participation rows before removing the member, so it is reliable even when
  SQLite foreign-key enforcement differs between environments.
- `accounts/bootstrap.py` imports `bookclub.models` to seed club access at
  startup — this is a one-way, bootstrap-time-only dependency (see
  `docs/dependency-map.md`), not a sign that `accounts` generally depends on
  `bookclub`.
- `BookClubMeeting.status` only has two valid *write* values:
  `"planned"`/`"completed"` (`Literal` in `MeetingBase`/`MeetingUpdate`).
  `"in_progress"` is **never stored** — it's a frontend-computed display
  state (now vs. `starts_at`/`ends_at`). `"cancelled"` doesn't exist at all —
  a meeting the club no longer wants is deleted, not cancelled. Migration
  `f06fece22726` (current head) normalizes any pre-existing
  `cancelled`/`in_progress` rows to `"planned"` — but that's a one-time
  UPDATE, not an enforced constraint, so a row can still end up with a
  stale/legacy status value outside dev flows the migration didn't run
  against (e.g. a `librarytools.db` snapshot committed from an
  earlier/parallel state — this bit us once). `MeetingResponse.status` is
  therefore deliberately widened back to plain `str` (not the `Literal`) so
  reading a bad legacy value reports it instead of 500ing the whole list —
  only writes stay strict.
- `archived_at` (same migration) is a plain settable field via the generic
  `PATCH /bookclub/meetings/{id}` — unlike the email-sent timestamps below,
  it's a display-mode toggle (which view a session opens to by default), not
  an audit trail, so it doesn't get a dedicated endpoint.
- **`bookclub_public_app` cannot use Starlette's stock `SessionMiddleware`.**
  It's nested inside the primary app's own router via `Host()`, not a truly
  separate ASGI mount, so it runs *inside* the primary app's own
  `SessionMiddleware` too. Starlette's `SessionMiddleware` unconditionally
  writes to `scope["session"]`; two nested instances (even with different
  cookie names) alias onto that same scope key, so the *last* one to run
  wins and its data gets serialized into *both* Set-Cookie headers —
  participant session data was observed leaking into the `libtools_session`
  cookie during Phase 2 testing. `participant_session.py`'s
  `ParticipantSessionMiddleware` is a near-copy of Starlette's
  implementation keyed on a private scope attribute instead — use
  `get_participant_session(request)` from that module, never
  `request.session`, anywhere in the participant code path. Any *future*
  subdomain sub-app that needs its own session state will need the same
  treatment, not Starlette's `SessionMiddleware` directly.
- **`crud.ensure_default_templates` is club-type-aware — it's the only place
  that guards this, not the call sites.** `DEFAULT_TEMPLATES` (`crud.py:16-...`)
  is hardcoded library-specific content (physical pickup/transfer copy, a
  named organizer) and is inappropriate for private clubs. The guard must
  remain inside `ensure_default_templates`, because template reads call it
  as a side effect. Private clubs start with no templates.
- **Book voting simplified from the original draft/open/closed design to
  just open/closed.** There is no prep-only "draft" stage before
  participants can see a round — a facilitator opens a round with an
  initial candidate list already chosen. If a "prepare candidates before
  announcing" workflow is wanted later, add the draft state back rather
  than assuming it's already there.
- **`vote_count.get(candidate.id)` vs `.get(candidate.id, 0)` — a real bug
  from Phase 4 testing.** `crud.vote_counts()` is a `GROUP BY`, so a
  candidate with zero votes is simply *absent* from the result dict, not
  present with value `0`. `CandidateResponse.vote_count` is `None` for two
  different reasons — "hidden because the round is open" and "not in the
  tally dict" — so a bare `.get()` silently produced `None` (rendered as
  "hidden") for a real zero-vote candidate once results were visible.
  `voting_routes.py`'s `build_round_response` uses `.get(candidate.id, 0)`
  specifically to keep those two meanings distinct — don't regress this if
  touching vote-count rendering.
- **Vote counts are hidden from participants while a round is open**
  (`CandidateResponse.vote_count` is `None`), to avoid an early visible
  tally influencing later votes — always visible to the facilitator
  (`GET /bookclub/community/voting-round` passes `show_counts=True`
  unconditionally) and to everyone once the round is `"closed"`.
- **Tie-breaking on close** (`crud.close_voting_round`) goes to whichever
  approved candidate was proposed first (lowest `id`), via
  `max(approved, key=lambda c: (counts.get(c.id, 0), -c.id))` — deterministic,
  not random. `crud.close_date_poll` uses the identical pattern for date
  options.
- **Book voting and meeting-date polling are two separate, un-shared
  systems by explicit product choice — don't try to unify them.** They look
  almost identical (open/closed round, propose/vote/close, hidden tally
  while open, same tie-break rule) and it's tempting to generalize into one
  "poll" abstraction, but date options are facilitator-only (no approval
  queue, no `status` column at all on `BookClubDatePollOption`) while book
  candidates have a real participant-proposal/approval workflow — the
  duplication is intentional so each can change shape independently later.
  `voting_routes.py`/`date_poll_routes.py` and their `build_*_response()`
  helpers are separate files for the same reason.
- **`BroadcastEmailResponse.recipient_count` vs `sent_count` — a real bug
  from Phase 6 testing.** The first draft only had one count, incremented
  when `participant_email_delivery.send_broadcast_email` returned `True` —
  in dev/test, where `RESEND_API_KEY` isn't set and every send legitimately
  returns `False`, that made a real 3-person audience read back as `0`
  recipients. `recipient_count` (audience size, from
  `crud.list_broadcastable_participants`) and `sent_count` (how many sends
  actually succeeded) are now tracked separately — don't collapse them back
  into one field.
- **`unsubscribe_token` is signed, not stored.** `participant_unsubscribe.py`
  computes `issue_unsubscribe_token(participant_id)` fresh at send time via
  `itsdangerous.URLSafeSerializer` — there's no per-participant token column
  or table (unlike `ParticipantAccountToken`, which is genuinely single-use
  by design for verify/reset). This is intentional: an unsubscribe link
  must stay valid and **idempotent** no matter how many times it's clicked
  (email clients sometimes prefetch/re-fetch links), which a
  consume-once token model actively works against.
- The onboarding/arrival-email `mark-sent` endpoints
  (`.../onboarding-email/mark-sent`, `.../arrival-email/mark-sent`) record
  the sent-timestamp **without** calling `email_delivery` — for staff who
  sent the email manually (e.g. copy-pasted the composed text) and want the
  pending-followup badge cleared. `MemberUpdate` deliberately does **not**
  expose `onboarding_email_sent_at`/`arrival_email_sent_at` — these two
  endpoints are the only way to set them outside of an actual send.

## Where to look for X

| Task | Files to touch |
|---|---|
| Add a new club-scoped entity | `bookclub/models.py` (remember `club_id` FK + per-club `UniqueConstraint`), `schemas.py`, `crud.py`, `routes.py` |
| Change what's visible on the public club page | `bookclub/club_routes.py` (`public_router`), `schemas.py` (`PublicClubResponse`) |
| Add a new email template kind | `bookclub/models.py` (`BookClubTemplate.kind`), `crud.py`, `routes.py`, `email_delivery.py` |
| Change book search field mapping | `bookclub/catalogue.py`'s `_parse_volume`/`_extract_isbn` (Google Books) |
| Change the shared BiblioCommons fetch/parse primitives | `bookclub/catalogue.py`'s `fetch_catalogue_page`/`parse_catalogue_state` — `lendery/catalogue.py` imports these directly, so a signature change affects both; its own field-level parsing (`parse_catalogue_item`) is separate and won't pick up book-field fixes |
| Change how meeting time/duration is parsed or computed | `bookclub/scheduling.py` (used by both `models.py` and `crud.py`) |
| Add a manual "mark as sent" action for a new email type | `bookclub/crud.py` (mirror `mark_onboarding_email_sent`), `routes.py` (mirror the `.../mark-sent` route) |
| Expose a community-management capability | `bookclub/facilitator_routes.py` under `/bookclub/community`, using regular selected-club authorization |
