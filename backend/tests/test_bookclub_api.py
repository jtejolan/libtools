import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from accounts.models import LibtoolsUser
from bookclub.models import BookClub, BookClubAccess, BookClubMeeting, BookClubRating
from bookclub.participant_models import ParticipantAccount
from lendery.routes import get_db
from main import app
from security import hash_password


class BookClubApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(cls.engine)
        cls.sessions = sessionmaker(
            bind=cls.engine,
            autoflush=False,
            expire_on_commit=False,
        )

        def override_get_db():
            db: Session = cls.sessions()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def setUp(self) -> None:
        with self.engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
        with self.sessions() as db:
            user = LibtoolsUser(
                name="Admin",
                username="admin",
                password_hash=hash_password("admin-password"),
                role="admin",
            )
            club = BookClub(
                name="Science Fiction Book Club",
                slug="science-fiction-book-club",
                organizer_name="Josh",
                organizer_branch="PBRL",
            )
            db.add_all([user, club])
            db.flush()
            db.add(
                BookClubAccess(club_id=club.id, user_id=user.id, role="owner")
            )
            db.commit()
        response = self.client.post(
            "/auth/login",
            json={"username": "admin", "password": "admin-password"},
        )
        self.assertEqual(response.status_code, 200)
        selected = self.client.post("/bookclub/clubs/1/select")
        self.assertEqual(selected.status_code, 200, selected.text)

    def create_member(self, name: str, email: str) -> dict:
        response = self.client.post(
            "/bookclub/members",
            json={
                "name": name,
                "email": email,
                "joined_on": "2026-08-01",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def create_book(self, title: str = "The Left Hand of Darkness") -> dict:
        response = self.client.post(
            "/bookclub/books",
            json={
                "title": title,
                "author": "Ursula K. Le Guin",
                "description": "A science-fiction novel.",
                "publication_date": "1969-03-01",
                "publisher": "Ace Books",
                "page_count": 304,
                "genres": "Science fiction, speculative fiction",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def create_meeting(self) -> dict:
        book = self.create_book()
        response = self.client.post(
            "/bookclub/meetings",
            json={
                "meeting_date": "2026-09-10",
                "meeting_time": "7:00 PM",
                "location": "PBRL",
                "book_id": book["id"],
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_homepage_links_to_bookclub_api(self) -> None:
        with TestClient(app) as visitor:
            homepage = visitor.get("/")
            self.assertEqual(homepage.status_code, 200)
            self.assertIn('href="/bookclub"', homepage.text)
            self.assertIn("Available now", homepage.text)
            self.assertIn('id="home-account-link"', homepage.text)
            self.assertIn('/static/home.js?v=7', homepage.text)
            self.assertIn('id="home-account-link" href="/login"', homepage.text)
            self.assertIn('/static/styles.css?v=23', homepage.text)
            self.assertEqual(
                homepage.headers["cache-control"],
                "private, no-store",
            )

        entrypoint = self.client.get("/bookclub")
        self.assertEqual(entrypoint.status_code, 200)
        self.assertIn("Book Club Manager", entrypoint.text)
        self.assertIn('/static/bookclub.js?v=46', entrypoint.text)
        self.assertIn('/static/bookclub.css?v=47', entrypoint.text)
        self.assertNotIn('data-view="messages"', entrypoint.text)
        self.assertIn('id="open-reminder-dialog"', entrypoint.text)
        self.assertIn('id="send-book-dialog"', entrypoint.text)
        self.assertIn('id="followup-dialog"', entrypoint.text)
        self.assertIn('id="member-access-filter"', entrypoint.text)
        self.assertIn('href="/signup">Create an account</a>', entrypoint.text)
        self.assertEqual(entrypoint.headers["cache-control"], "no-store")

        community = self.client.get("/bookclub/community")
        self.assertEqual(community.status_code, 200)
        self.assertIn('aria-label="Book Club Manager navigation"', community.text)
        self.assertIn('href="/bookclub?action=view-meetings"', community.text)
        self.assertIn('href="/bookclub?action=view-books"', community.text)
        self.assertIn('href="/bookclub?action=view-members"', community.text)
        self.assertIn('aria-current="page">', community.text)
        self.assertIn('/static/bookclub.css?v=37', community.text)
        self.assertIn('/static/bookclub-manage.css?v=5', community.text)
        self.assertIn('/static/bookclub-manage.js?v=14', community.text)
        self.assertIn('id="invite-readers"', community.text)
        self.assertEqual(community.headers["cache-control"], "no-store")

    @patch("bookclub.catalogue.search_catalogue_books")
    def test_searches_google_books(self, search_books) -> None:
        search_books.return_value = [
            {
                "external_id": "abc123",
                "title": "Project Hail Mary",
                "author": "Andy Weir",
                "cover_image_url": "https://books.google.com/thumb.jpg",
                "description": "A lone astronaut must save Earth.",
                "publication_date": "2021-01-01",
                "isbn": "9780593135204",
                "publisher": "Ballantine Books",
                "page_count": 476,
                "genres": "Science fiction",
                "series": None,
                "catalogue_url": "https://books.google.com/books?id=abc123",
            }
        ]

        response = self.client.post(
            "/bookclub/books/search",
            json={"query": "Project Hail Mary Andy Weir"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        results = response.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Project Hail Mary")
        self.assertEqual(results[0]["page_count"], 476)
        search_books.assert_called_once_with("Project Hail Mary Andy Weir")

    @patch("bookclub.catalogue.search_catalogue_books")
    def test_reports_catalogue_search_errors(self, search_books) -> None:
        from bookclub.catalogue import CatalogueImportError

        search_books.side_effect = CatalogueImportError(
            "Enter a title or author to search."
        )
        response = self.client.post(
            "/bookclub/books/search",
            json={"query": "   "},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"],
            "Enter a title or author to search.",
        )

    def test_books_are_reusable_and_protected_while_in_use(self) -> None:
        book = self.create_book("A Wizard of Earthsea")
        updated = self.client.patch(
            f"/bookclub/books/{book['id']}",
            json={
                "cover_image_url": "https://example.com/earthsea.jpg",
                "discussion_notes": "Talk about balance and responsibility.",
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(
            updated.json()["discussion_notes"],
            "Talk about balance and responsibility.",
        )

        meeting = self.client.post(
            "/bookclub/meetings",
            json={
                "meeting_date": "2026-10-08",
                "book_id": book["id"],
            },
        )
        self.assertEqual(meeting.status_code, 201, meeting.text)
        self.assertEqual(meeting.json()["book"]["id"], book["id"])

        in_use = self.client.delete(f"/bookclub/books/{book['id']}")
        self.assertEqual(in_use.status_code, 409)

        deleted_meeting = self.client.delete(
            f"/bookclub/meetings/{meeting.json()['id']}"
        )
        self.assertEqual(deleted_meeting.status_code, 204)
        deleted_book = self.client.delete(f"/bookclub/books/{book['id']}")
        self.assertEqual(deleted_book.status_code, 204)

    def test_book_insights_combine_meetings_attendance_and_reader_reviews(self) -> None:
        book = self.create_book("The Dispossessed")
        meeting = self.client.post(
            "/bookclub/meetings",
            json={
                "meeting_date": "2026-08-08",
                "meeting_time": "7:00 PM",
                "location": "PBRL",
                "book_id": book["id"],
            },
        ).json()
        member = self.create_member("Alex Reader", "alex-reader@example.com")
        attended = self.client.put(
            f"/bookclub/meetings/{meeting['id']}/members/{member['id']}",
            json={"attended": True},
        )
        self.assertEqual(attended.status_code, 200, attended.text)
        updated_meeting = self.client.patch(
            f"/bookclub/meetings/{meeting['id']}",
            json={
                "status": "completed",
                "discussion_notes": "The group debated freedom and responsibility.",
            },
        )
        self.assertEqual(updated_meeting.status_code, 200, updated_meeting.text)

        with self.sessions() as db:
            participant = ParticipantAccount(
                name="Jamie Reviewer",
                email="jamie-reviewer@example.com",
                password_hash=hash_password("participant-password"),
            )
            db.add(participant)
            db.flush()
            db.add(
                BookClubRating(
                    club_id=1,
                    book_id=book["id"],
                    participant_id=participant.id,
                    rating=5,
                    review_text="Ambitious and beautifully argued.",
                )
            )
            db.commit()

        response = self.client.get(f"/bookclub/books/{book['id']}/insights")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["average_rating"], 5)
        self.assertEqual(body["rating_count"], 1)
        self.assertEqual(body["ratings"][0]["participant_name"], "Jamie Reviewer")
        self.assertEqual(body["meetings"][0]["attendance_count"], 1)
        self.assertEqual(body["meetings"][0]["roster_count"], 1)
        self.assertEqual(body["meetings"][0]["pages_read"], 304)
        self.assertEqual(body["total_attendance"], 1)
        self.assertEqual(body["reading_impact_pages"], 304)
        self.assertIn("freedom", body["meetings"][0]["discussion_notes"])

    def test_roster_is_built_manually_and_tracks_attendance_and_giveaway(self) -> None:
        alex = self.create_member("Alex Reader", "ALEX@example.com")
        blair = self.create_member("Blair Reader", "blair@example.com")
        meeting = self.create_meeting()

        # Meetings start with an empty roster now — no auto-add of active members.
        empty_roster = self.client.get(f"/bookclub/meetings/{meeting['id']}/roster")
        self.assertEqual(empty_roster.status_code, 200)
        self.assertEqual(empty_roster.json(), [])

        added_alex = self.client.put(
            f"/bookclub/meetings/{meeting['id']}/members/{alex['id']}", json={}
        )
        self.assertEqual(added_alex.status_code, 200, added_alex.text)
        added_blair = self.client.put(
            f"/bookclub/meetings/{meeting['id']}/members/{blair['id']}", json={}
        )
        self.assertEqual(added_blair.status_code, 200, added_blair.text)

        roster = self.client.get(f"/bookclub/meetings/{meeting['id']}/roster")
        self.assertEqual(len(roster.json()), 2)

        alex_update = self.client.put(
            f"/bookclub/meetings/{meeting['id']}/members/{alex['id']}",
            json={"attended": True},
        )
        self.assertEqual(alex_update.status_code, 200, alex_update.text)

        with patch("bookclub.crud.secrets.choice", return_value=None) as choose:
            choose.side_effect = lambda entries: entries[0]
            winner = self.client.post(
                f"/bookclub/meetings/{meeting['id']}/giveaway/draw"
            )
        self.assertEqual(winner.status_code, 200, winner.text)
        self.assertEqual(winner.json()["member"]["id"], alex["id"])

        saved = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/giveaway/draw"
        )
        self.assertEqual(saved.json(), winner.json())

        history = self.client.get(
            f"/bookclub/members/{alex['id']}/history"
        )
        self.assertEqual(history.status_code, 200)
        self.assertTrue(history.json()[0]["attended"])

        removed = self.client.delete(
            f"/bookclub/meetings/{meeting['id']}/members/{blair['id']}"
        )
        self.assertEqual(removed.status_code, 204)
        roster_after_removal = self.client.get(f"/bookclub/meetings/{meeting['id']}/roster")
        self.assertEqual(
            [entry["member_id"] for entry in roster_after_removal.json()], [alex["id"]]
        )

        missing_removal = self.client.delete(
            f"/bookclub/meetings/{meeting['id']}/members/{blair['id']}"
        )
        self.assertEqual(missing_removal.status_code, 404)

        deleted_member = self.client.delete(f"/bookclub/members/{alex['id']}")
        self.assertEqual(deleted_member.status_code, 204)
        self.assertEqual(
            self.client.get(f"/bookclub/meetings/{meeting['id']}/roster").json(),
            [],
        )
        self.assertIsNone(
            self.client.get(f"/bookclub/meetings/{meeting['id']}").json()[
                "giveaway_winner_member_id"
            ]
        )
        self.assertEqual(
            self.client.delete(f"/bookclub/members/{alex['id']}").status_code,
            404,
        )

    def test_member_transfer_requires_destination_branch(self) -> None:
        missing_branch = self.client.post(
            "/bookclub/members",
            json={
                "name": "No Branch",
                "email": "no-branch@example.com",
                "joined_on": "2026-08-01",
                "is_new_registrant": True,
                "delivery_method": "transfer",
            },
        )
        self.assertEqual(missing_branch.status_code, 422)

        member = self.client.post(
            "/bookclub/members",
            json={
                "name": "Has Branch",
                "email": "has-branch@example.com",
                "joined_on": "2026-08-01",
                "is_new_registrant": True,
                "delivery_method": "transfer",
                "destination_branch": "Maple Library",
            },
        ).json()
        self.assertEqual(member["destination_branch"], "Maple Library")

        # Switching away from transfer clears the stored destination branch.
        updated = self.client.patch(
            f"/bookclub/members/{member['id']}", json={"delivery_method": "none"}
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertIsNone(updated.json()["destination_branch"])

    def test_templates_are_editable_renderable_and_restorable(self) -> None:
        templates = self.client.get("/bookclub/templates")
        self.assertEqual(templates.status_code, 200)
        self.assertEqual(len(templates.json()), 6)

        updated = self.client.patch(
            "/bookclub/templates/monthly_reminder",
            json={
                "subject": "Next: {{book_title}}",
                "body": "Hello {{first_name}} — see you {{meeting_date}}.",
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)

        preview = self.client.post(
            "/bookclub/templates/monthly_reminder/render",
            json={
                "variables": {
                    "first_name": "Alex",
                    "book_title": "Dune",
                }
            },
        )
        self.assertEqual(preview.json()["subject"], "Next: Dune")
        self.assertEqual(preview.json()["missing_variables"], ["meeting_date"])
        self.assertIn("{{meeting_date}}", preview.json()["body"])

        restored = self.client.post(
            "/bookclub/templates/monthly_reminder/restore"
        )
        self.assertEqual(restored.status_code, 200)
        self.assertIn("Sci-Fi Book Club reminder", restored.json()["subject"])

    def test_transit_label_renders_for_any_member(self) -> None:
        alex = self.create_member("Alex Reader", "alex@example.com")

        response = self.client.post(
            "/bookclub/transit-labels/render",
            json={"member_id": alex["id"], "destination_branch": "Maple Library"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("Alex Reader", response.json()["body"])
        self.assertIn("Maple Library", response.json()["body"])
        self.assertIn("Josh at PBRL", response.json()["body"])
        self.assertEqual(response.json()["missing_variables"], [])
        self.assertIsNone(
            self.client.get(f"/bookclub/members/{alex['id']}").json()[
                "transit_label_printed_at"
            ]
        )

        printed = self.client.post(
            "/bookclub/transit-labels/print",
            json={"member_id": alex["id"], "destination_branch": "Maple Library"},
        )
        self.assertEqual(printed.status_code, 200, printed.text)
        updated_member = self.client.get(f"/bookclub/members/{alex['id']}").json()
        self.assertIsNotNone(updated_member["transit_label_printed_at"])
        self.assertEqual(updated_member["delivery_method"], "transfer")
        self.assertEqual(updated_member["destination_branch"], "Maple Library")

        missing_member = self.client.post(
            "/bookclub/transit-labels/render",
            json={"member_id": 999999, "destination_branch": "Maple Library"},
        )
        self.assertEqual(missing_member.status_code, 404)

    def test_questions_start_blank_and_can_be_managed_manually(self) -> None:
        meeting = self.create_meeting()
        saved = self.client.get(
            f"/bookclub/meetings/{meeting['id']}/questions"
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json(), [])

        created = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/questions",
            json={"text": "What surprised the group most?"},
        )
        self.assertEqual(created.status_code, 201, created.text)

        question_id = created.json()["id"]
        edited = self.client.patch(
            f"/bookclub/questions/{question_id}",
            json={"text": "Which idea stayed with the group?"},
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(
            edited.json()["text"],
            "Which idea stayed with the group?",
        )

        deleted = self.client.delete(
            f"/bookclub/questions/{question_id}"
        )
        self.assertEqual(deleted.status_code, 204)
        empty_again = self.client.get(
            f"/bookclub/meetings/{meeting['id']}/questions"
        )
        self.assertEqual(empty_again.json(), [])

    def test_session_workspace_tracks_status_discussion_and_participant_notes(self) -> None:
        meeting = self.create_meeting()
        self.assertEqual(meeting["status"], "planned")
        self.assertIsNone(meeting["discussion_notes"])

        updated = self.client.patch(
            f"/bookclub/meetings/{meeting['id']}",
            json={
                "discussion_notes": "The group focused on memory and identity.",
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["status"], "planned")
        self.assertIn("memory and identity", updated.json()["discussion_notes"])

        # "in_progress" is a computed display state, not a settable value —
        # only "planned"/"completed" are valid to PATCH directly.
        in_progress_rejected = self.client.patch(
            f"/bookclub/meetings/{meeting['id']}",
            json={"status": "in_progress"},
        )
        self.assertEqual(in_progress_rejected.status_code, 422)

        member = self.create_member("Alex Reader", "alex-session@example.com")
        participation = self.client.put(
            f"/bookclub/meetings/{meeting['id']}/members/{member['id']}",
            json={"attended": True, "notes": "Joining by Zoom."},
        )
        self.assertEqual(participation.status_code, 200, participation.text)
        self.assertTrue(participation.json()["attended"])
        self.assertEqual(participation.json()["notes"], "Joining by Zoom.")

        completed = self.client.patch(
            f"/bookclub/meetings/{meeting['id']}",
            json={"status": "completed"},
        )
        self.assertEqual(completed.status_code, 200, completed.text)
        self.assertEqual(completed.json()["status"], "completed")

        invalid = self.client.patch(
            f"/bookclub/meetings/{meeting['id']}",
            json={"status": "maybe"},
        )
        self.assertEqual(invalid.status_code, 422)

        cancelled_rejected = self.client.patch(
            f"/bookclub/meetings/{meeting['id']}",
            json={"status": "cancelled"},
        )
        self.assertEqual(cancelled_rejected.status_code, 422)

    def test_meeting_duration_and_computed_time_range(self) -> None:
        book = self.create_book()
        parseable = self.client.post(
            "/bookclub/meetings",
            json={
                "meeting_date": "2026-09-10",
                "meeting_time": "7:00 PM",
                "meeting_duration_minutes": 60,
                "book_id": book["id"],
            },
        ).json()
        self.assertEqual(parseable["meeting_duration_minutes"], 60)
        self.assertEqual(parseable["starts_at"], "2026-09-10T19:00:00")
        self.assertEqual(parseable["ends_at"], "2026-09-10T20:00:00")

        default_duration = self.client.post(
            "/bookclub/meetings",
            json={"meeting_date": "2026-09-11", "book_id": book["id"]},
        ).json()
        self.assertEqual(default_duration["meeting_duration_minutes"], 90)

        unparseable = self.client.post(
            "/bookclub/meetings",
            json={
                "meeting_date": "2026-09-12",
                "meeting_time": "sometime in the evening",
                "book_id": book["id"],
            },
        ).json()
        self.assertIsNone(unparseable["starts_at"])
        self.assertIsNone(unparseable["ends_at"])

        too_short = self.client.post(
            "/bookclub/meetings",
            json={
                "meeting_date": "2026-09-13",
                "meeting_duration_minutes": 5,
                "book_id": book["id"],
            },
        )
        self.assertEqual(too_short.status_code, 422)

        updated_duration = self.client.patch(
            f"/bookclub/meetings/{parseable['id']}",
            json={"meeting_duration_minutes": 120},
        )
        self.assertEqual(updated_duration.status_code, 200, updated_duration.text)
        self.assertEqual(updated_duration.json()["ends_at"], "2026-09-10T21:00:00")

    def test_archived_at_can_be_set_and_cleared(self) -> None:
        meeting = self.create_meeting()
        self.assertIsNone(meeting["archived_at"])

        archived = self.client.patch(
            f"/bookclub/meetings/{meeting['id']}",
            json={"archived_at": "2026-09-11T12:00:00Z"},
        )
        self.assertEqual(archived.status_code, 200, archived.text)
        self.assertIsNotNone(archived.json()["archived_at"])

        unarchived = self.client.patch(
            f"/bookclub/meetings/{meeting['id']}",
            json={"archived_at": None},
        )
        self.assertEqual(unarchived.status_code, 200, unarchived.text)
        self.assertIsNone(unarchived.json()["archived_at"])

    def test_import_previous_attendees_copies_attended_members_only(self) -> None:
        attended_member = self.create_member("Attended Reader", "attended@example.com")
        absent_member = self.create_member("Absent Reader", "absent@example.com")
        book = self.create_book()
        previous_meeting = self.client.post(
            "/bookclub/meetings",
            json={"meeting_date": "2026-08-10", "book_id": book["id"]},
        ).json()
        current_meeting = self.client.post(
            "/bookclub/meetings",
            json={"meeting_date": "2026-09-10", "book_id": book["id"]},
        ).json()
        self.client.put(
            f"/bookclub/meetings/{previous_meeting['id']}/members/{attended_member['id']}",
            json={"attended": True},
        )
        self.client.put(
            f"/bookclub/meetings/{previous_meeting['id']}/members/{absent_member['id']}",
            json={"attended": False},
        )

        imported = self.client.post(
            f"/bookclub/meetings/{current_meeting['id']}/roster/import-previous"
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertEqual(
            {entry["member_id"] for entry in imported.json()}, {attended_member["id"]}
        )
        self.assertFalse(imported.json()[0]["attended"])

    def test_import_previous_attendees_skips_members_already_on_roster(self) -> None:
        attended_member = self.create_member("Attended Reader", "attended2@example.com")
        book = self.create_book()
        previous_meeting = self.client.post(
            "/bookclub/meetings",
            json={"meeting_date": "2026-08-10", "book_id": book["id"]},
        ).json()
        current_meeting = self.client.post(
            "/bookclub/meetings",
            json={"meeting_date": "2026-09-10", "book_id": book["id"]},
        ).json()
        self.client.put(
            f"/bookclub/meetings/{previous_meeting['id']}/members/{attended_member['id']}",
            json={"attended": True},
        )
        # Already checked in for the current meeting before importing.
        self.client.put(
            f"/bookclub/meetings/{current_meeting['id']}/members/{attended_member['id']}",
            json={"attended": True},
        )

        imported = self.client.post(
            f"/bookclub/meetings/{current_meeting['id']}/roster/import-previous"
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertEqual(len(imported.json()), 1)
        self.assertTrue(imported.json()[0]["attended"])

    def test_import_previous_attendees_404s_without_a_previous_meeting(self) -> None:
        meeting = self.create_meeting()
        response = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/roster/import-previous"
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn("no previous meeting", response.json()["detail"].lower())

    def test_import_previous_attendees_404s_for_unknown_meeting(self) -> None:
        response = self.client.post(
            "/bookclub/meetings/999999/roster/import-previous"
        )
        self.assertEqual(response.status_code, 404)

    def test_legacy_invalid_status_value_does_not_500_on_read(self) -> None:
        # A "cancelled"/"in_progress" row from before status was narrowed to
        # planned/completed (e.g. a dev DB snapshot committed pre-migration)
        # must still be readable — status is read-only output here, so it
        # shouldn't be able to break the whole list response.
        meeting = self.create_meeting()
        with self.sessions() as db:
            db.query(BookClubMeeting).filter(
                BookClubMeeting.id == meeting["id"]
            ).update({"status": "in_progress"})
            db.commit()

        listed = self.client.get("/bookclub/meetings")
        self.assertEqual(listed.status_code, 200, listed.text)
        matching = next(
            entry for entry in listed.json() if entry["id"] == meeting["id"]
        )
        self.assertEqual(matching["status"], "in_progress")

        patched = self.client.patch(
            f"/bookclub/meetings/{meeting['id']}",
            json={"notes": "still readable"},
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertEqual(patched.json()["status"], "in_progress")

    def test_onboarding_email_preview_and_send_track_sent_state(self) -> None:
        meeting = self.create_meeting()
        member = self.client.post(
            "/bookclub/members",
            json={
                "name": "New Registrant",
                "email": "new-registrant@example.com",
                "joined_on": "2026-08-01",
                "is_new_registrant": True,
                "delivery_method": "pickup",
            },
        ).json()
        self.assertEqual(member["delivery_method"], "pickup")
        self.assertIsNone(member["onboarding_email_sent_at"])
        self.client.put(
            f"/bookclub/meetings/{meeting['id']}/members/{member['id']}", json={}
        )

        preview = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/members/{member['id']}/onboarding-email/preview"
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertIn("held for pickup", preview.json()["body"])

        first_send = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/members/{member['id']}/onboarding-email/send"
        )
        self.assertEqual(first_send.status_code, 200, first_send.text)
        self.assertFalse(first_send.json()["sent"])  # Resend isn't configured in tests
        self.assertFalse(first_send.json()["already_sent_before"])

        updated_member = self.client.get(f"/bookclub/members/{member['id']}").json()
        self.assertIsNotNone(updated_member["onboarding_email_sent_at"])

        summary = self.client.get("/bookclub/members/participation-summary").json()
        member_row = next(row for row in summary if row["member"]["id"] == member["id"])
        self.assertIsNotNone(member_row["last_contacted_at"])

        second_send = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/members/{member['id']}/onboarding-email/send"
        )
        self.assertTrue(second_send.json()["already_sent_before"])

        not_on_roster = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/members/999999/onboarding-email/send"
        )
        self.assertEqual(not_on_roster.status_code, 404)

    def test_arrival_email_preview_and_send_only_for_transfer_registrants(self) -> None:
        meeting = self.create_meeting()
        transfer_member = self.client.post(
            "/bookclub/members",
            json={
                "name": "Transfer Registrant",
                "email": "transfer-registrant@example.com",
                "joined_on": "2026-08-01",
                "is_new_registrant": True,
                "delivery_method": "transfer",
                "destination_branch": "Maple Library",
            },
        ).json()
        self.client.put(
            f"/bookclub/meetings/{meeting['id']}/members/{transfer_member['id']}",
            json={},
        )

        preview = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/members/{transfer_member['id']}/arrival-email/preview"
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertIn("Maple Library", preview.json()["body"])
        self.assertIn("ready for pickup", preview.json()["body"])

        send = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/members/{transfer_member['id']}/arrival-email/send"
        )
        self.assertEqual(send.status_code, 200, send.text)
        self.assertFalse(send.json()["sent"])  # Resend isn't configured in tests
        self.assertFalse(send.json()["already_sent_before"])

        updated_member = self.client.get(f"/bookclub/members/{transfer_member['id']}").json()
        self.assertIsNotNone(updated_member["arrival_email_sent_at"])

        second_send = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/members/{transfer_member['id']}/arrival-email/send"
        )
        self.assertTrue(second_send.json()["already_sent_before"])

    def test_mark_sent_records_timestamp_without_calling_send(self) -> None:
        meeting = self.create_meeting()
        member = self.client.post(
            "/bookclub/members",
            json={
                "name": "Manual Sender",
                "email": "manual-sender@example.com",
                "joined_on": "2026-08-01",
                "is_new_registrant": True,
                "delivery_method": "pickup",
            },
        ).json()
        self.client.put(
            f"/bookclub/meetings/{meeting['id']}/members/{member['id']}", json={}
        )
        self.assertIsNone(member["onboarding_email_sent_at"])
        self.assertIsNone(member["arrival_email_sent_at"])

        onboarding_marked = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/members/{member['id']}/onboarding-email/mark-sent"
        )
        self.assertEqual(onboarding_marked.status_code, 200, onboarding_marked.text)
        self.assertTrue(onboarding_marked.json()["sent"])
        self.assertFalse(onboarding_marked.json()["already_sent_before"])

        arrival_marked = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/members/{member['id']}/arrival-email/mark-sent"
        )
        self.assertEqual(arrival_marked.status_code, 200, arrival_marked.text)
        self.assertFalse(arrival_marked.json()["already_sent_before"])

        updated_member = self.client.get(f"/bookclub/members/{member['id']}").json()
        self.assertIsNotNone(updated_member["onboarding_email_sent_at"])
        self.assertIsNotNone(updated_member["arrival_email_sent_at"])

        marked_again = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/members/{member['id']}/onboarding-email/mark-sent"
        )
        self.assertTrue(marked_again.json()["already_sent_before"])

        not_on_roster = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/members/999999/onboarding-email/mark-sent"
        )
        self.assertEqual(not_on_roster.status_code, 404)

    def test_reminder_send_updates_meeting_and_member_state(self) -> None:
        alex = self.create_member("Alex Reader", "alex-batch@example.com")
        casey = self.client.post(
            "/bookclub/members",
            json={
                "name": "Casey New",
                "email": "casey-batch@example.com",
                "joined_on": "2026-08-01",
                "is_new_registrant": True,
            },
        ).json()
        meeting = self.create_meeting()
        self.client.put(f"/bookclub/meetings/{meeting['id']}/members/{alex['id']}", json={})
        self.client.put(f"/bookclub/meetings/{meeting['id']}/members/{casey['id']}", json={})

        preview = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/reminder/preview"
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertIn(meeting["book"]["title"], preview.json()["subject"])
        self.assertIn(meeting["book"]["title"], preview.json()["body"])
        self.assertIn("Hi everyone", preview.json()["body"])
        self.assertEqual(preview.json()["missing_variables"], [])

        send = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/reminder/send",
            json={"member_ids": [alex["id"], casey["id"]]},
        )
        self.assertEqual(send.status_code, 200, send.text)
        self.assertFalse(send.json()["sent"])  # Resend isn't configured in tests
        self.assertEqual(send.json()["recipient_count"], 2)
        self.assertFalse(send.json()["already_sent_before"])

        updated_meeting = self.client.get(f"/bookclub/meetings/{meeting['id']}").json()
        self.assertIsNotNone(updated_meeting["reminder_sent_at"])

        updated_alex = self.client.get(f"/bookclub/members/{alex['id']}").json()
        self.assertIsNotNone(updated_alex["last_reminder_sent_at"])

        second_send = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/reminder/send",
            json={"member_ids": [alex["id"]]},
        )
        self.assertTrue(second_send.json()["already_sent_before"])

        invalid_send = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/reminder/send",
            json={"member_ids": [999999]},
        )
        self.assertEqual(invalid_send.status_code, 422)

    def test_reminder_mark_sent_records_timestamp_without_calling_send(self) -> None:
        alex = self.create_member("Alex Reader", "alex-marksent@example.com")
        meeting = self.create_meeting()
        self.client.put(f"/bookclub/meetings/{meeting['id']}/members/{alex['id']}", json={})
        self.assertIsNone(meeting["reminder_sent_at"])

        marked = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/reminder/mark-sent"
        )
        self.assertEqual(marked.status_code, 200, marked.text)
        self.assertTrue(marked.json()["sent"])
        self.assertEqual(marked.json()["recipient_count"], 1)
        self.assertFalse(marked.json()["already_sent_before"])

        updated_meeting = self.client.get(f"/bookclub/meetings/{meeting['id']}").json()
        self.assertIsNotNone(updated_meeting["reminder_sent_at"])
        updated_alex = self.client.get(f"/bookclub/members/{alex['id']}").json()
        self.assertIsNotNone(updated_alex["last_reminder_sent_at"])

        marked_again = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/reminder/mark-sent"
        )
        self.assertTrue(marked_again.json()["already_sent_before"])

        missing_meeting = self.client.post(
            "/bookclub/meetings/999999/reminder/mark-sent"
        )
        self.assertEqual(missing_meeting.status_code, 404)

    def test_participation_summary_aggregates_across_meetings(self) -> None:
        alex = self.create_member("Alex Reader", "alex-summary@example.com")

        def make_meeting(meeting_date: str, title: str) -> dict:
            book = self.create_book(title)
            response = self.client.post(
                "/bookclub/meetings",
                json={"meeting_date": meeting_date, "book_id": book["id"]},
            )
            self.assertEqual(response.status_code, 201, response.text)
            return response.json()

        meeting1 = make_meeting("2026-01-10", "January Book")
        meeting2 = make_meeting("2026-02-10", "February Book")
        meeting3 = make_meeting("2026-03-10", "March Book")

        self.client.put(
            f"/bookclub/meetings/{meeting1['id']}/members/{alex['id']}",
            json={"attended": True},
        )
        self.client.put(
            f"/bookclub/meetings/{meeting2['id']}/members/{alex['id']}",
            json={"attended": True},
        )
        # Added to meeting3's roster too, but left at the "not attended" default.
        self.client.put(
            f"/bookclub/meetings/{meeting3['id']}/members/{alex['id']}", json={}
        )

        with patch("bookclub.crud.secrets.choice", side_effect=lambda entries: entries[0]):
            winner = self.client.post(f"/bookclub/meetings/{meeting2['id']}/giveaway/draw")
        self.assertEqual(winner.status_code, 200, winner.text)
        self.assertEqual(winner.json()["member"]["id"], alex["id"])

        casey = self.client.post(
            "/bookclub/members",
            json={
                "name": "Casey NoHistory",
                "email": "casey-summary@example.com",
                "joined_on": "2026-04-01",
            },
        )
        self.assertEqual(casey.status_code, 201, casey.text)
        casey = casey.json()

        summary = self.client.get("/bookclub/members/participation-summary")
        self.assertEqual(summary.status_code, 200, summary.text)
        rows = {row["member"]["id"]: row for row in summary.json()}

        alex_row = rows[alex["id"]]
        self.assertEqual(alex_row["meetings_total"], 3)
        self.assertEqual(alex_row["attended_count"], 2)
        self.assertEqual(alex_row["giveaways_won"], 1)
        self.assertEqual(alex_row["pages_read"], 608)
        self.assertEqual(alex_row["last_attended_date"], "2026-02-10")
        self.assertEqual(alex_row["meetings_since_last_attended"], 1)
        self.assertIsNone(alex_row["last_contacted_at"])

        casey_row = rows[casey["id"]]
        self.assertEqual(casey_row["meetings_total"], 0)
        self.assertEqual(casey_row["attended_count"], 0)
        self.assertEqual(casey_row["giveaways_won"], 0)
        self.assertEqual(casey_row["pages_read"], 0)
        self.assertIsNone(casey_row["last_attended_date"])
        self.assertEqual(casey_row["meetings_since_last_attended"], 0)

    def test_club_settings_support_video_call_url(self) -> None:
        updated = self.client.patch(
            "/bookclub/clubs/1",
            json={"video_call_url": "https://zoom.us/j/123456"},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["video_call_url"], "https://zoom.us/j/123456")

        fetched = self.client.get("/bookclub/clubs/selected").json()
        self.assertEqual(fetched["video_call_url"], "https://zoom.us/j/123456")

    def test_public_club_page_lists_past_books_as_shelf(self) -> None:
        def make_meeting(meeting_date: str, title: str) -> dict:
            book = self.create_book(title)
            response = self.client.post(
                "/bookclub/meetings",
                json={"meeting_date": meeting_date, "book_id": book["id"]},
            )
            self.assertEqual(response.status_code, 201, response.text)
            return response.json()

        make_meeting("2020-01-10", "Past Book")
        make_meeting("2999-01-10", "Upcoming Book")
        # There's no "cancelled" status — a meeting the club no longer wants
        # showing up is just deleted instead.
        deleted = make_meeting("2099-01-10", "Deleted Book")
        deleted_response = self.client.delete(
            f"/bookclub/meetings/{deleted['id']}"
        )
        self.assertEqual(deleted_response.status_code, 204, deleted_response.text)
        undated_past = self.create_book("Undated Past Book")
        marked = self.client.patch(
            f"/bookclub/books/{undated_past['id']}",
            json={"is_past_selection": True},
        )
        self.assertEqual(marked.status_code, 200, marked.text)
        self.assertTrue(marked.json()["is_past_selection"])

        page = self.client.get("/api/public/clubs/science-fiction-book-club")
        self.assertEqual(page.status_code, 200, page.text)
        body = page.json()
        self.assertEqual(body["upcoming_meeting"]["book"]["title"], "Upcoming Book")
        self.assertEqual(body["enrollment_policy"], "open")
        self.assertIn("calendar.google.com", body["upcoming_meeting"]["google_calendar_url"])
        calendar = self.client.get(body["upcoming_meeting"]["ics_calendar_url"])
        self.assertEqual(calendar.status_code, 200, calendar.text)
        self.assertTrue(calendar.headers["content-type"].startswith("text/calendar"))
        self.assertIn("SUMMARY:Book club: Upcoming Book", calendar.text)
        self.assertIn('filename="science-fiction-book-club-book-club.ics"', calendar.headers["content-disposition"])
        self.assertEqual(len(body["shelf"]), 2)
        self.assertEqual(
            {book["title"] for book in body["shelf"]},
            {"Past Book", "Undated Past Book"},
        )
        undated = next(
            book for book in body["shelf"] if book["title"] == "Undated Past Book"
        )
        self.assertIsNone(undated["meeting_date"])

        self.client.patch("/bookclub/clubs/1", json={"public": False})
        hidden = self.client.get("/api/public/clubs/science-fiction-book-club")
        self.assertEqual(hidden.status_code, 404)

    def test_enrollment_policy_is_separate_from_public_page_visibility(self) -> None:
        updated = self.client.patch(
            "/bookclub/clubs/1",
            json={"public": True, "enrollment_policy": "invite_only"},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertTrue(updated.json()["public"])
        self.assertEqual(updated.json()["enrollment_policy"], "invite_only")
        public = self.client.get("/api/public/clubs/science-fiction-book-club")
        self.assertEqual(public.status_code, 200, public.text)
        self.assertEqual(public.json()["enrollment_policy"], "invite_only")


class BuildCalendarLinkTests(unittest.TestCase):
    def test_parses_common_time_formats_and_builds_dated_link(self) -> None:
        from datetime import date
        from types import SimpleNamespace
        from urllib.parse import parse_qs, urlparse

        from bookclub import crud

        meeting = SimpleNamespace(
            meeting_date=date(2026, 9, 10),
            meeting_time="7:00 PM",
            meeting_duration_minutes=120,
            location="Pierre Berton Resource Library",
            notes=None,
            book=SimpleNamespace(title="Project Hail Mary"),
        )
        link = crud.build_calendar_link(meeting, "https://zoom.us/j/123456")
        params = parse_qs(urlparse(link).query)
        self.assertEqual(params["dates"][0], "20260910T190000/20260910T210000")
        self.assertEqual(params["location"][0], "Pierre Berton Resource Library")
        self.assertIn("https://zoom.us/j/123456", params["details"][0])

    def test_unparseable_time_falls_back_to_all_day(self) -> None:
        from datetime import date
        from types import SimpleNamespace
        from urllib.parse import parse_qs, urlparse

        from bookclub import crud

        meeting = SimpleNamespace(
            meeting_date=date(2026, 9, 10),
            meeting_time="sometime in the evening",
            meeting_duration_minutes=90,
            location=None,
            notes=None,
            book=SimpleNamespace(title="Project Hail Mary"),
        )
        link = crud.build_calendar_link(meeting, None)
        params = parse_qs(urlparse(link).query)
        self.assertEqual(params["dates"][0], "20260910/20260911")
        self.assertNotIn("location", params)
        self.assertNotIn("details", params)


if __name__ == "__main__":
    unittest.main()
