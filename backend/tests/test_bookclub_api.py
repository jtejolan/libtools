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
        self.assertIn('/static/bookclub.js?v=14', entrypoint.text)
        self.assertIn('/static/bookclub.css?v=16', entrypoint.text)
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

    def test_member_roster_filters_attendance_and_giveaway(self) -> None:
        alex = self.create_member("Alex Reader", "ALEX@example.com")
        blair = self.create_member("Blair Reader", "blair@example.com")
        meeting = self.create_meeting()

        roster = self.client.get(
            f"/bookclub/meetings/{meeting['id']}/roster"
        )
        self.assertEqual(roster.status_code, 200)
        self.assertEqual(len(roster.json()), 2)

        alex_update = self.client.put(
            f"/bookclub/meetings/{meeting['id']}/members/{alex['id']}",
            json={
                "delivery_method": "transfer",
                "destination_branch": "Maple Library",
                "book_checked_out": True,
                "attended": True,
            },
        )
        self.assertEqual(alex_update.status_code, 200, alex_update.text)
        self.client.put(
            f"/bookclub/meetings/{meeting['id']}/members/{blair['id']}",
            json={"delivery_method": "pickup", "attended": True},
        )

        received = self.client.get(
            f"/bookclub/meetings/{meeting['id']}/recipients?filter=checked_out"
        ).json()
        self.assertEqual([member["id"] for member in received], [alex["id"]])

        with patch("bookclub.crud.secrets.choice", return_value=None) as choose:
            choose.side_effect = lambda entries: entries[0]
            winner = self.client.post(
                f"/bookclub/meetings/{meeting['id']}/giveaway/draw"
            )
        self.assertEqual(winner.status_code, 200, winner.text)
        self.assertIn(winner.json()["member"]["id"], {alex["id"], blair["id"]})

        saved = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/giveaway/draw"
        )
        self.assertEqual(saved.json(), winner.json())

        history = self.client.get(
            f"/bookclub/members/{alex['id']}/history"
        )
        self.assertEqual(history.status_code, 200)
        self.assertTrue(history.json()[0]["attended"])
        self.assertTrue(history.json()[0]["book_checked_out"])

    def test_sync_adds_new_regular_to_existing_meeting(self) -> None:
        self.create_member("First Reader", "first@example.com")
        meeting = self.create_meeting()
        self.create_member("Later Reader", "later@example.com")

        response = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/roster/sync"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"added": 1, "total": 2})

    def test_templates_are_editable_renderable_and_restorable(self) -> None:
        templates = self.client.get("/bookclub/templates")
        self.assertEqual(templates.status_code, 200)
        self.assertEqual(len(templates.json()), 5)

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

    def test_transit_labels_render_in_a_batch(self) -> None:
        alex = self.create_member("Alex Reader", "alex@example.com")
        self.create_member("Local Reader", "local@example.com")
        meeting = self.create_meeting()
        self.client.put(
            f"/bookclub/meetings/{meeting['id']}/members/{alex['id']}",
            json={
                "delivery_method": "transfer",
                "destination_branch": "Maple Library",
            },
        )

        response = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/transit-labels/render",
            json={},
        )
        self.assertEqual(response.status_code, 200, response.text)
        labels = response.json()
        self.assertEqual(len(labels), 1)
        self.assertIn("Alex Reader", labels[0]["body"])
        self.assertIn("Maple Library", labels[0]["body"])
        self.assertIn("Josh at PBRL", labels[0]["body"])
        self.assertEqual(labels[0]["missing_variables"], [])

        previews = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/emails/preview",
            json={"email_type": "onboarding", "member_ids": [alex["id"]]},
        )
        self.assertEqual(previews.status_code, 200, previews.text)
        self.assertEqual(previews.json()[0]["template_key"], "onboarding_transfer")
        self.assertIn("Maple Library", previews.json()[0]["body"])
        self.assertEqual(previews.json()[0]["missing_variables"], [])

        empty_previews = self.client.post(
            f"/bookclub/meetings/{meeting['id']}/emails/preview",
            json={"email_type": "onboarding", "member_ids": []},
        )
        self.assertEqual(empty_previews.json(), [])

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


if __name__ == "__main__":
    unittest.main()
