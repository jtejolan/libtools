# bookclub/

Multi-tenant book club manager. Every club-owned table is scoped by
`club_id`, and uniqueness constraints (email, ISBN, template key) are scoped
**per club**, not global. Available to every signed-in Libtools account
(not gated by `ToolAccess` — see `docs/backend/accounts.md`).

## Models (`bookclub/models.py`, 454 lines)

| Model | Table | Purpose |
|---|---|---|
| `BookClub` | `book_clubs` | A club: name, slug, `public` flag, organizer info, `club_type` (`"library"` default / `"self_serve"` — descriptive/filtering only, see below, not itself an access-control check) |
| `BookClubAccess` | `book_club_access` | User-to-club grant (`role`, e.g. owner) |
| `BookClubMember` | `bookclub_members` | A club's member roster; unique per `(club_id, email)`; carries delivery details plus transit-label/email timestamps |
| `BookClubBook` | `bookclub_books` | A book the club has read/will read; unique per `(club_id, isbn)`; can be flagged as an undated past selection |
| `BookClubMeeting` | `bookclub_meetings` | A dated session tied to one book, with `meeting_duration_minutes`, an `archived_at` display-mode flag, and discussion notes; `book_title`/`book_author` are denormalized copies kept in sync on write. `starts_at`/`ends_at` are computed `@property`s (not columns), from `bookclub/scheduling.py` |
| `BookClubParticipation` | `bookclub_participation` | Member roster for one meeting (`attended` flag plus session-only participant note); unique per `(meeting_id, member_id)` |
| `BookClubTemplate` | `bookclub_templates` | Editable email template; unique per `(club_id, key)` |
| `BookClubDiscussionQuestion` | `bookclub_discussion_questions` | Legacy ordered questions retained for API compatibility; migration `e93f1a6b2c47` copies existing text into meeting discussion notes |
| `BookClubRating` | `bookclub_ratings` | A participant's 1-5 rating (DB `CheckConstraint`) + optional review of a book; unique per `(book_id, participant_id)`, editable (upsert, not append). FK to `ParticipantAccount` is a plain string FK (`bookclub_participant_accounts.id`), not an ORM `relationship()` — `crud.py` joins in the participant's name explicitly instead, since that model lives in `participant_models.py` and there's no existing precedent in this package for a cross-module `relationship()`. |
| `BookClubVotingRound` | `bookclub_voting_rounds` | A "what should we read next" poll; `status` `"open"`/`"closed"` only (simplified from an originally-planned draft/open/closed — see gotcha below), `winning_book_id` set on close. One open round per club at a time, enforced in `crud.py` (app-level, not a DB constraint). |
| `BookClubBookCandidate` | `bookclub_book_candidates` | A book nominated for a round; unique per `(voting_round_id, book_id)`. `status` `"pending"`/`"approved"`/`"rejected"` — facilitator-proposed candidates auto-approve, participant-proposed ones need `POST /facilitator/candidates/{id}/approve`. Has a normal in-module `book` relationship (unlike `BookClubRating`'s participant FK, this one doesn't cross into `participant_models.py`). |
| `BookClubVote` | `bookclub_votes` | One participant's vote for a candidate; unique per `(voting_round_id, participant_id)` — casting a second vote updates the existing row rather than adding one. |
| `BookClubDatePoll` | `bookclub_date_polls` | A "when should we meet next" poll — a **deliberately independent system** from `BookClubVotingRound`/`BookClubBookCandidate`/`BookClubVote` above, not a shared generalized poll (explicit product choice). Same open/closed shape, `winning_date` set on close, one open poll per club at a time (app-level, same as voting rounds). |
| `BookClubDatePollOption` | `bookclub_date_poll_options` | A candidate date; unique per `(poll_id, option_date)`. **Facilitator-only** — no participant-proposal path, so unlike `BookClubBookCandidate` there's no `status`/approval queue at all. |
| `BookClubDatePollVote` | `bookclub_date_poll_votes` | One participant's vote for a date option; unique per `(poll_id, participant_id)`. |

## Participant accounts (`bookclub.libtools.app`)

A second, separate account system for club **participants** (readers) and
**facilitators** (leads), not to be confused with staff
`LibtoolsUser`/`BookClubAccess` accounts. Lives in `bookclub/participant_*.py`
and is only reachable from the `bookclub_public_app` sub-app (see
`docs/architecture.md`) — none of it is mounted on the primary `libtools.app`
app.

**Facilitators are `ParticipantAccount`s too, not a third account system.**
Whoever creates a club via `POST /participant/clubs` gets a `ParticipantAccount`
with `role="owner"` on it (single owner in v1) — same table, same session
machinery, same login flow as an ordinary reader, just a `role` check away
from facilitator permissions. This was a deliberate pivot: an earlier version
of this feature made self-serve facilitators ordinary `LibtoolsUser`s who
managed their club from the staff `/bookclub` tool; that was reversed so a
self-serve facilitator never touches `libtools.app`, not even technically.
Library-run clubs (staff-provisioned, `LibtoolsUser`/`BookClubAccess`,
managed from the staff tool) are completely unaffected by any of this.

| Model | Table | Purpose |
|---|---|---|
| `ParticipantAccount` | `bookclub_participant_accounts` | A reader's or facilitator's login for one club; unique per `(club_id, email)` — the same person joining two clubs gets two rows. Email is required and must be verified. `role` is `"member"` (default) or `"owner"` (the facilitator). `unsubscribed_at` excludes them from facilitator broadcast emails (see below) — doesn't affect transactional email (verify/reset) or their ability to use the club. |
| `ParticipantAccountToken` | `bookclub_participant_account_tokens` | Hashed/expiring email-verification and password-reset tokens, parallel to `accounts.AccountToken` but never shared with it. |

| Router | Prefix | File | Endpoints | Purpose |
|---|---|---|---|---|
| `router` | `/participant/auth` | `participant_routes.py` | 8 | register/login/logout/me, email verification, password reset — all scoped by `club_slug` in the request body (a participant's identity is club-specific, so most requests need to say which club) |
| `club_router` | `/participant/clubs` | `participant_routes.py` | 1 | `POST ""` — creates a `BookClub` (`club_type="self_serve"`) and its owner `ParticipantAccount` together, in one transaction; mirrors `club_routes.py`'s slug-collision retry. Rate-limited like registration. |
| `router` | `/facilitator` | `facilitator_routes.py` | 26 | Book CRUD (incl. catalogue import), meeting CRUD, template CRUD, voting-round management (open/close, add/approve/reject candidates), date-poll management (open/close, add option), and `POST /broadcast` — thin wrappers calling the *same* `crud.py` functions `routes.py` uses, gated by `require_facilitator` instead of `require_selected_club`. No member-roster, onboarding/arrival-email, reminder-broadcast, giveaway, or transit-label endpoints — none of that applies to self-serve clubs. |
| `router` | `/participant/books` | `rating_routes.py` | 4 | `GET ""` (list club's books), `GET/PUT/DELETE "/{book_id}/rating(s)"` — any signed-in participant (member *or* owner) can browse and rate; gated by `CurrentParticipantClub`, not `require_facilitator`. |
| `router` | `/participant/voting-round` | `voting_routes.py` | 4 | `GET ""` (current round), `POST /candidates` (propose), `PUT/DELETE /vote` — any participant can view/propose/vote; `build_round_response()` here is imported by `facilitator_routes.py` too, so both sides render the exact same shape. |
| `router` | `/participant/date-poll` | `date_poll_routes.py` | 3 | `GET ""` (current poll), `PUT/DELETE /vote` — no propose endpoint (facilitator-only options); `build_poll_response()` here is imported by `facilitator_routes.py`, mirroring `voting_routes.py`'s pattern. |
| `router` | `/participant/unsubscribe` | `unsubscribe_routes.py` | 1 | `POST ""` — **deliberately public**, no `CurrentParticipant` dependency at all; authenticated only by the signed token in the request body, since it must work from a cold email client with no session. |

**Admin visibility** (`admin_routes.py`, mounted on the primary `app`, *not*
`bookclub_public_app` — it's a `LibtoolsUser`-admin feature reachable from
`libtools.app`, not a participant/facilitator one): `GET
/api/admin/bookclub/self-serve-clubs`, gated by `accounts.auth.
require_platform_admin`, lists `club_type="self_serve"` clubs (name, slug,
facilitator name/email, participant count, created date) via
`crud.list_self_serve_clubs`. Read-only, no management actions — self-serve
clubs never get a `BookClubAccess` row, so this is the *only* place an admin
can see they exist at all (support/abuse triage). `created_at` on the
response is the owner `ParticipantAccount`'s `created_at`, not a column on
`BookClub` itself — `BookClub` has no `created_at` column, and since the
owner row is created in the same transaction as the club
(`participant_routes.py`'s `create_club`), it's an accurate proxy without a
migration. Frontend: `admin-bookclub.html`/`.js` at `/admin/bookclub`,
linked from `admin-accounts.html` and the dashboard's admin account menu.

**Facilitator broadcast email** (`POST /facilitator/broadcast`, body
`{template_key, variables}`) reuses the existing `BookClubTemplate`/
`crud.render_template` machinery (the same one `routes.py`'s reminder
endpoints use for `BookClubMember`), pointed at
`crud.list_broadcastable_participants` instead — active, non-unsubscribed
`ParticipantAccount`s for the club. `club_name` is auto-injected into the
template variables so facilitators don't have to pass it themselves. Unlike
`bookclub/email_delivery.send_reminder_batch`'s member reminders (one BCC'd
send to everyone), broadcasts to participants send **one email per
recipient** via `participant_email_delivery.send_broadcast_email` — this is
required, not incidental: each email needs its own working, no-login-required
unsubscribe link (`bookclub/participant_unsubscribe.py` signs a token with
`itsdangerous`, reusing `LIBTOOLS_SESSION_SECRET` with a distinct salt), and
a single BCC send can't embed a different link per recipient.
`BroadcastEmailResponse.recipient_count` is the audience size regardless of
delivery success — kept separate from `sent_count` specifically so it
doesn't misleadingly read `0` in dev/test where `RESEND_API_KEY` isn't set
(this was a real bug caught during testing, see gotcha below).

`participant_auth.py`'s `require_participant_club`/`CurrentParticipantClub`
is the same `db.info["bookclub_id"]`-setting pattern as `require_facilitator`,
just without the owner-only check — `require_facilitator`
(`facilitator_auth.py`) now layers its role check on top of
`CurrentParticipantClub` rather than duplicating the club-resolution logic.

Other participant-only modules: `participant_auth.py` (session dependency
`CurrentParticipant`, mirrors `accounts/auth.py`), `participant_tokens.py`
(mirrors `accounts/account_tokens.py`), `participant_email_delivery.py`
(plain-text sends, mirrors `bookclub/email_delivery.py`, plus
`send_broadcast_email`), `participant_unsubscribe.py` (signs/verifies the
unsubscribe token — see below), `participant_session.py` (see gotcha below
— this is **not** a copy for duplication's sake, it fixes a real
cookie-collision bug), `facilitator_auth.py` (`require_facilitator`/
`CurrentFacilitator` — checks `role == "owner"` then sets
`db.info["bookclub_id"]`/`["bookclub"]` exactly like `access.py`'s
`require_selected_club` does for staff, so facilitator routes can call the
*same* `crud.py` functions `routes.py` uses, just via a different auth path).

## Routes

| Router | Prefix | File | Endpoints | Purpose |
|---|---|---|---|---|
| `router` | `/bookclub/clubs` | `club_routes.py` | 5 | Club CRUD, select-into-session, list accessible clubs |
| `public_router` | `/api/public/clubs` | `club_routes.py` | 1 | `GET /{slug}` — public read-only club page |
| `router` | `/bookclub` | `routes.py` | 44 | Members, books (incl. catalogue import), meetings, roster/participation, onboarding/arrival email preview/send/**mark-sent** and reminder preview/send, giveaway draw, templates, transit labels, discussion questions — whole router requires `require_selected_club` |

## Other modules

- `access.py` — `slugify()`, `accessible_club_statement()` (admins see all
  clubs, others only clubs they have `BookClubAccess` to),
  `require_bookclub_tool` (blocks users with `must_change_password` set),
  `require_selected_club` (reads `bookclub_id` from the session, 409s if
  none selected, 403s if the user can't access it — exported as the
  `SelectedClub` dependency type).
- `catalogue.py` — scrapes Vaughan PL (BiblioCommons) pages to autofill book
  metadata (title/author/ISBN/cover/etc). `lendery/catalogue.py` does the
  same kind of scraping for item metadata but is a **separate, unshared**
  implementation — a markup/parsing fix here does not automatically apply
  there. See `docs/backend/lendery.md`.
- `scheduling.py` (34 lines) — `parse_meeting_time()` (free-text, 5 known
  formats) and `meeting_datetime_range()`. Lives outside both `models.py`
  and `crud.py` so each can import it without a circular dependency;
  `models.py`'s `starts_at`/`ends_at` properties and `crud.py`'s
  `build_calendar_link()` both use it.
- `crud.py` (1,492 lines) — DB operations for every model above, including
  ratings (`get_book_ratings`/`get_own_rating`/`upsert_rating`/`delete_rating`),
  book voting (`open_voting_round`/`add_candidate`/`set_candidate_status`/
  `cast_vote`/`close_voting_round`/etc), date polling (the
  `*_date_poll`/`*_date_option`/`*_date_vote` functions — a parallel,
  independent set, not shared with the voting functions above), broadcast
  email (`list_broadcastable_participants`, `mark_participant_unsubscribed`),
  and `list_self_serve_clubs` (admin visibility — deliberately not scoped by
  `db.info["bookclub_id"]`, since it spans every self-serve club rather than
  one selected club).
- `admin_routes.py` (37 lines) — the admin-only self-serve-club visibility
  router, see above.
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
  named organizer) — meaningless, confusing content for a self-serve club.
  `POST /participant/clubs` deliberately doesn't call it at creation time,
  but that alone isn't enough: `crud.list_templates`/`get_template` (and
  therefore `update_template`, which calls `get_template`) *unconditionally*
  call `ensure_default_templates` as a side effect on every read — this was
  a real bug during Phase 3 testing, where simply calling
  `GET /facilitator/templates` silently seeded all six library defaults
  (mentioning "Josh"/"PBRL") into a self-serve club. Fixed by making
  `ensure_default_templates` itself check `club.club_type` and no-op for
  anything but `"library"` — self-serve clubs genuinely start with zero
  templates now, regardless of which template function is called first.
- **Book voting simplified from the original draft/open/closed design to
  just open/closed.** Once facilitators became `ParticipantAccount`s
  (`role="owner"`) instead of a separate `LibtoolsUser`-based flow, there
  was no longer a reason for `BookClubBookCandidate` to carry two different
  proposer-type FKs, and no strong need for a prep-only "draft" stage before
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
  (`GET /facilitator/voting-round` passes `show_counts=True`
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
| Change catalogue import parsing | `bookclub/catalogue.py` — remember `lendery/catalogue.py` does its own separate scraping and won't pick up the fix |
| Change how meeting time/duration is parsed or computed | `bookclub/scheduling.py` (used by both `models.py` and `crud.py`) |
| Add a manual "mark as sent" action for a new email type | `bookclub/crud.py` (mirror `mark_onboarding_email_sent`), `routes.py` (mirror the `.../mark-sent` route) |
| Expose an existing `crud.py` capability to self-serve facilitators | `bookclub/facilitator_routes.py` (add a thin wrapper calling the same `crud.py` function `routes.py` uses — see the reuse pattern this file already follows) |
| Add an admin-only view over self-serve clubs | `bookclub/admin_routes.py` (mounted on the primary `app`, gated by `require_platform_admin`), `crud.list_self_serve_clubs`, `schemas.SelfServeClubSummary`, `frontend/admin-bookclub.html`/`.js` |
