import unittest
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from accounts.models import LibtoolsUser
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

    def test_reader_preview_requires_a_verified_facilitator_email(self) -> None:
        response = self.manager.post("/bookclub/community/reader-preview")
        self.assertEqual(response.status_code, 409, response.text)

    def _verify_manager_email(self) -> None:
        with self.sessions() as db:
            user = db.scalar(select(LibtoolsUser).where(LibtoolsUser.username == "alex"))
            user.email_verified_at = datetime.now(timezone.utc)
            db.commit()

    def test_facilitator_can_preview_as_a_reader_without_signing_in_again(self) -> None:
        self._verify_manager_email()
        response = self.manager.post("/bookclub/community/reader-preview")
        self.assertEqual(response.status_code, 200, response.text)
        preview_url = response.json()["url"]
        self.assertTrue(
            preview_url.startswith("https://bookclub.libtools.app/participant/auth/preview-login?")
        )
        parsed = urlsplit(preview_url)
        path_and_query = f"{parsed.path}?{parsed.query}"

        reader = TestClient(app, base_url="http://bookclub.libtools.app")
        try:
            redirect = reader.get(path_and_query, follow_redirects=False)
            self.assertEqual(redirect.status_code, 303, redirect.text)
            self.assertEqual(redirect.headers["location"], "/dashboard")

            # The redirect's session cookie should already be a signed-in
            # reader session - no separate participant login required.
            library = reader.get("/participant/books/library")
            self.assertEqual(library.status_code, 200, library.text)
        finally:
            reader.close()

    def test_reader_preview_token_cannot_be_reused(self) -> None:
        self._verify_manager_email()
        preview_url = self.manager.post("/bookclub/community/reader-preview").json()["url"]
        parsed = urlsplit(preview_url)
        path_and_query = f"{parsed.path}?{parsed.query}"

        first = TestClient(app, base_url="http://bookclub.libtools.app")
        second = TestClient(app, base_url="http://bookclub.libtools.app")
        try:
            first_redirect = first.get(path_and_query, follow_redirects=False)
            self.assertEqual(first_redirect.status_code, 303, first_redirect.text)
            second_redirect = second.get(path_and_query, follow_redirects=False)
            self.assertEqual(second_redirect.status_code, 303, second_redirect.text)
            self.assertEqual(second_redirect.headers["location"], "/")
            self.assertEqual(second.get("/participant/books/library").status_code, 401)
        finally:
            first.close()
            second.close()


if __name__ == "__main__":
    unittest.main()
