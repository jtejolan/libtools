import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from accounts.models import LibtoolsUser
from bookclub.models import BookClub, BookClubAccess
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
        self.assertIn('/static/bookclub.js?v=18', entrypoint.text)
        self.assertIn('/static/bookclub.css?v=18', entrypoint.text)
        self.assertIn('href="/signup">Create an account</a>', entrypoint.text)
        self.assertEqual(entrypoint.headers["cache-control"], "no-store")

    @patch("bookclub.catalogue.fetch_catalogue_book")
    def test_imports_a_vaughan_catalogue_book(self, fetch_book) -> None:
        fetch_book.return_value = {
            "title": "Project Hail Mary",
            "author": "Andy Weir",
            "cover_image_url": "https://www.syndetics.com/cover.jpg",
            "description": "A lone astronaut must save Earth.",
            "publication_date": "2021-01-01",
            "isbn": "9780593135204",
            "publisher": "Ballantine Books",
            "page_count": 476,
            "genres": "Science fiction, Astronauts — Fiction",
            "series": None,
            "catalogue_url": "https://vaughanpl.bibliocommons.com/v2/record/S130C532272",
        }

        response = self.client.post(
            "/bookclub/books/import",
            json={
                "catalogue_url": "https://vaughanpl.bibliocommons.com/v2/record/S130C532272"
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["title"], "Project Hail Mary")
        self.assertEqual(response.json()["page_count"], 476)
        fetch_book.assert_called_once_with(
            "https://vaughanpl.bibliocommons.com/v2/record/S130C532272"
        )

    @patch("bookclub.catalogue.fetch_catalogue_book")
    def test_reports_catalogue_import_errors(self, fetch_book) -> None:
        from bookclub.catalogue import CatalogueImportError

        fetch_book.side_effect = CatalogueImportError(
            "Enter a Vaughan Public Libraries catalogue record link."
        )
        response = self.client.post(
            "/bookclub/books/import",
            json={"catalogue_url": "https://example.com/not-a-book"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"],
            "Enter a Vaughan Public Libraries catalogue record link.",
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
        self.assertEqual(alex_row["last_attended_date"], "2026-02-10")
        self.assertEqual(alex_row["meetings_since_last_attended"], 1)
        self.assertIsNone(alex_row["last_contacted_at"])

        casey_row = rows[casey["id"]]
        self.assertEqual(casey_row["meetings_total"], 0)
        self.assertEqual(casey_row["attended_count"], 0)
        self.assertEqual(casey_row["giveaways_won"], 0)
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

        page = self.client.get("/api/public/clubs/science-fiction-book-club")
        self.assertEqual(page.status_code, 200, page.text)
        body = page.json()
        self.assertEqual(body["upcoming_meeting"]["book"]["title"], "Upcoming Book")
        self.assertEqual(len(body["shelf"]), 1)
        self.assertEqual(body["shelf"][0]["title"], "Past Book")

        self.client.patch("/bookclub/clubs/1", json={"public": False})
        hidden = self.client.get("/api/public/clubs/science-fiction-book-club")
        self.assertEqual(hidden.status_code, 404)


class BuildCalendarLinkTests(unittest.TestCase):
    def test_parses_common_time_formats_and_builds_dated_link(self) -> None:
        from datetime import date
        from types import SimpleNamespace
        from urllib.parse import parse_qs, urlparse

        from bookclub import crud

        meeting = SimpleNamespace(
            meeting_date=date(2026, 9, 10),
            meeting_time="7:00 PM",
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
