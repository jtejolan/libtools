import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from accounts import login_throttle
from database import Base
from dependencies import get_db
from main import app, bookclub_public_app


class FacilitatorRoutesTests(unittest.TestCase):
    """Covers /facilitator/* — the thin route layer that lets an owner-role
    ParticipantAccount call the same crud.py functions the staff /bookclub
    routes use (see docs/backend/bookclub.md)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(cls.engine)
        cls.sessions = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)

        def override_get_db():
            db: Session = cls.sessions()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        bookclub_public_app.dependency_overrides[get_db] = override_get_db

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        bookclub_public_app.dependency_overrides.clear()
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def setUp(self) -> None:
        login_throttle.reset()
        with self.engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
        self.client = TestClient(app, base_url="http://bookclub.libtools.app")
        created = self.client.post(
            "/participant/clubs",
            json={
                "club_name": "Mystery Lovers Club",
                "facilitator_name": "Alex Facilitator",
                "facilitator_email": "alex@example.com",
                "password": "facilitator-pw-1",
                "confirm_password": "facilitator-pw-1",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)

    def tearDown(self) -> None:
        self.client.close()
        login_throttle.reset()

    def create_book(self, title="The Silent Patient") -> dict:
        response = self.client.post(
            "/facilitator/books",
            json={"title": title, "author": "Alex Michaelides"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_member_participant_cannot_access_facilitator_routes(self) -> None:
        self.client.post("/participant/auth/logout")
        register = self.client.post(
            "/participant/auth/register",
            json={
                "club_slug": "mystery-lovers-club",
                "name": "Reader One",
                "email": "reader@example.com",
                "password": "reader-password-1",
                "confirm_password": "reader-password-1",
            },
        )
        self.assertEqual(register.status_code, 201, register.text)
        response = self.client.get("/facilitator/books")
        self.assertEqual(response.status_code, 403, response.text)

    def test_signed_out_visitor_cannot_access_facilitator_routes(self) -> None:
        self.client.post("/participant/auth/logout")
        response = self.client.get("/facilitator/books")
        self.assertEqual(response.status_code, 401, response.text)

    def test_book_crud(self) -> None:
        book = self.create_book()
        self.assertEqual(book["title"], "The Silent Patient")

        listed = self.client.get("/facilitator/books")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)

        updated = self.client.patch(f"/facilitator/books/{book['id']}", json={"is_past_selection": True})
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertTrue(updated.json()["is_past_selection"])

        deleted = self.client.delete(f"/facilitator/books/{book['id']}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/facilitator/books").json(), [])

    def test_meeting_requires_existing_book(self) -> None:
        response = self.client.post(
            "/facilitator/meetings",
            json={"meeting_date": "2026-09-01", "book_id": 999},
        )
        self.assertEqual(response.status_code, 404, response.text)

    def test_meeting_crud(self) -> None:
        book = self.create_book()
        created = self.client.post(
            "/facilitator/meetings",
            json={"meeting_date": "2026-09-01", "book_id": book["id"], "location": "Community room"},
        )
        self.assertEqual(created.status_code, 201, created.text)
        meeting = created.json()
        self.assertEqual(meeting["book"]["title"], "The Silent Patient")

        updated = self.client.patch(f"/facilitator/meetings/{meeting['id']}", json={"status": "completed"})
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["status"], "completed")

        deleted = self.client.delete(f"/facilitator/meetings/{meeting['id']}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/facilitator/meetings").json(), [])

    def test_deleting_book_in_use_by_a_meeting_is_blocked(self) -> None:
        book = self.create_book()
        self.client.post("/facilitator/meetings", json={"meeting_date": "2026-09-01", "book_id": book["id"]})
        response = self.client.delete(f"/facilitator/books/{book['id']}")
        self.assertEqual(response.status_code, 409, response.text)

    def test_template_crud(self) -> None:
        # Confirms self-serve clubs start with zero templates — no
        # library-specific DEFAULT_TEMPLATES seeded (see
        # docs/backend/bookclub.md).
        self.assertEqual(self.client.get("/facilitator/templates").json(), [])

        created = self.client.post(
            "/facilitator/templates",
            json={
                "key": "meeting_reminder",
                "name": "Meeting reminder",
                "kind": "email",
                "subject": "See you at {{meeting_date}}!",
                "body": "Hi {{first_name}}, don't forget our meeting on {{meeting_date}}.",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)

        duplicate = self.client.post(
            "/facilitator/templates",
            json={
                "key": "meeting_reminder",
                "name": "Duplicate",
                "kind": "email",
                "subject": "x",
                "body": "x",
            },
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.text)

        updated = self.client.patch("/facilitator/templates/meeting_reminder", json={"name": "Updated reminder"})
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["name"], "Updated reminder")

    def test_facilitator_only_sees_their_own_clubs_books(self) -> None:
        self.create_book(title="Club One's Book")
        self.client.post("/participant/auth/logout")

        other_club = self.client.post(
            "/participant/clubs",
            json={
                "club_name": "Sci-Fi Explorers",
                "facilitator_name": "Sam Two",
                "facilitator_email": "sam@example.com",
                "password": "facilitator-pw-2",
                "confirm_password": "facilitator-pw-2",
            },
        )
        self.assertEqual(other_club.status_code, 201, other_club.text)
        books = self.client.get("/facilitator/books").json()
        self.assertEqual(books, [])


if __name__ == "__main__":
    unittest.main()
