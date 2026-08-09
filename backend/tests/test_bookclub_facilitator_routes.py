import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from dependencies import get_db
from main import app, bookclub_public_app


class CommunityManagementRoutesTests(unittest.TestCase):
    """Community controls belong to Libtools-managed book clubs."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        cls.sessions = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(cls.engine)

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
        with self.engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
        self.manager = TestClient(app)
        registered = self.manager.post("/auth/register", json={
            "name": "Alex Facilitator", "username": "alex", "email": "alex@example.com",
            "password": "facilitator-password", "confirm_password": "facilitator-password",
        })
        self.assertEqual(registered.status_code, 201, registered.text)
        created = self.manager.post("/bookclub/clubs", json={"name": "Mystery Lovers Club"})
        self.assertEqual(created.status_code, 201, created.text)
        selected = self.manager.post(f"/bookclub/clubs/{created.json()['id']}/select")
        self.assertEqual(selected.status_code, 200, selected.text)

    def tearDown(self) -> None:
        self.manager.close()

    def test_participant_subdomain_has_no_facilitator_api(self) -> None:
        participant = TestClient(app, base_url="http://bookclub.libtools.app")
        try:
            response = participant.get("/facilitator/books")
            self.assertEqual(response.status_code, 404, response.text)
        finally:
            participant.close()

    def test_signed_out_user_cannot_manage_community(self) -> None:
        visitor = TestClient(app)
        try:
            response = visitor.get("/bookclub/community/books")
            self.assertEqual(response.status_code, 401, response.text)
        finally:
            visitor.close()

    def test_libtools_owner_can_manage_books_meetings_and_polls(self) -> None:
        book = self.manager.post(
            "/bookclub/community/books", json={"title": "Dune", "author": "Frank Herbert"}
        )
        self.assertEqual(book.status_code, 201, book.text)
        meeting = self.manager.post(
            "/bookclub/community/meetings",
            json={"meeting_date": "2026-09-01", "book_id": book.json()["id"]},
        )
        self.assertEqual(meeting.status_code, 201, meeting.text)
        poll = self.manager.post(
            "/bookclub/community/voting-round",
            json={"candidate_book_ids": [book.json()["id"]]},
        )
        self.assertEqual(poll.status_code, 201, poll.text)
        self.assertEqual(poll.json()["candidates"][0]["status"], "approved")


if __name__ == "__main__":
    unittest.main()
