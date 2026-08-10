import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from accounts import login_throttle
from database import Base
from dependencies import get_db
from main import app, bookclub_public_app


class RatingRoutesTests(unittest.TestCase):
    """Covers /participant/books — book listing and rating, visible to
    every participant in the club (not just an aggregate), per
    docs/backend/bookclub.md."""

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
        self.facilitator = TestClient(app)
        registered = self.facilitator.post("/auth/register", json={
            "name": "Alex Facilitator", "username": "alex", "email": "alex@example.com",
            "password": "facilitator-pw-1", "confirm_password": "facilitator-pw-1",
        })
        self.assertEqual(registered.status_code, 201, registered.text)
        created = self.facilitator.post("/bookclub/clubs", json={"name": "Mystery Lovers Club"})
        self.assertEqual(created.status_code, 201, created.text)
        self.facilitator.post(f"/bookclub/clubs/{created.json()['id']}/select")
        book = self.facilitator.post(
            "/bookclub/community/books",
            json={"title": "The Silent Patient", "author": "Alex Michaelides"},
        )
        self.assertEqual(book.status_code, 201, book.text)
        self.book_id = book.json()["id"]

        self.reader_a = self.register_reader("reader-a@example.com")
        self.reader_b = self.register_reader("reader-b@example.com")

    def register_reader(self, email: str) -> TestClient:
        client = TestClient(app, base_url="http://bookclub.libtools.app")
        response = client.post(
            "/participant/auth/register",
            json={
                "club_slug": "mystery-lovers-club",
                "name": email.split("@")[0],
                "email": email,
                "password": "reader-password-1",
                "confirm_password": "reader-password-1",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return client

    def tearDown(self) -> None:
        self.facilitator.close()
        self.reader_a.close()
        self.reader_b.close()
        login_throttle.reset()

    def test_list_books_visible_to_any_participant(self) -> None:
        response = self.reader_a.get("/participant/books")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()[0]["title"], "The Silent Patient")

    def test_submit_and_view_rating(self) -> None:
        response = self.reader_a.put(
            f"/participant/books/{self.book_id}/rating",
            json={"rating": 5, "review_text": "Loved it"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["average"], 5)
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["ratings"][0]["participant_name"], "reader-a")

    def test_rating_accepts_half_star_increments_only(self) -> None:
        accepted = self.reader_a.put(
            f"/participant/books/{self.book_id}/rating",
            json={"rating": 4.5, "review_text": "Almost perfect"},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["ratings"][0]["rating"], 4.5)
        rejected = self.reader_a.put(
            f"/participant/books/{self.book_id}/rating", json={"rating": 4.2}
        )
        self.assertEqual(rejected.status_code, 422, rejected.text)

    def test_ratings_are_visible_to_other_participants_not_just_aggregate(self) -> None:
        self.reader_a.put(f"/participant/books/{self.book_id}/rating", json={"rating": 4})
        self.reader_b.put(f"/participant/books/{self.book_id}/rating", json={"rating": 2})

        # A third participant (never rated) can still see both named ratings.
        onlooker = self.register_reader("onlooker@example.com")
        response = onlooker.get(f"/participant/books/{self.book_id}/ratings")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["count"], 2)
        self.assertEqual(body["average"], 3)
        names = {entry["participant_name"] for entry in body["ratings"]}
        self.assertEqual(names, {"reader-a", "reader-b"})
        onlooker.close()

    def test_resubmitting_a_rating_updates_it_rather_than_duplicating(self) -> None:
        self.reader_a.put(f"/participant/books/{self.book_id}/rating", json={"rating": 2})
        response = self.reader_a.put(
            f"/participant/books/{self.book_id}/rating", json={"rating": 5, "review_text": "Changed my mind"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["ratings"][0]["rating"], 5)
        self.assertEqual(body["ratings"][0]["review_text"], "Changed my mind")

    def test_rating_out_of_range_is_rejected(self) -> None:
        response = self.reader_a.put(f"/participant/books/{self.book_id}/rating", json={"rating": 6})
        self.assertEqual(response.status_code, 422, response.text)

    def test_delete_rating(self) -> None:
        self.reader_a.put(f"/participant/books/{self.book_id}/rating", json={"rating": 3})
        deleted = self.reader_a.delete(f"/participant/books/{self.book_id}/rating")
        self.assertEqual(deleted.status_code, 204, deleted.text)
        response = self.reader_a.get(f"/participant/books/{self.book_id}/ratings")
        self.assertEqual(response.json()["count"], 0)
        self.assertIsNone(response.json()["average"])

    def test_rating_a_book_from_another_club_is_not_found(self) -> None:
        other_club = self.facilitator.post("/bookclub/clubs", json={"name": "Sci-Fi Explorers"})
        self.assertEqual(other_club.status_code, 201, other_club.text)
        self.facilitator.post(f"/bookclub/clubs/{other_club.json()['id']}/select")
        other_book = self.facilitator.post(
            "/bookclub/community/books", json={"title": "Dune", "author": "Frank Herbert"}
        )
        self.assertEqual(other_book.status_code, 201, other_book.text)

        response = self.reader_a.put(
            f"/participant/books/{other_book.json()['id']}/rating", json={"rating": 5}
        )
        self.assertEqual(response.status_code, 404, response.text)

    def test_libtools_manager_session_is_not_a_participant_session(self) -> None:
        response = self.facilitator.put(f"/participant/books/{self.book_id}/rating", json={"rating": 4})
        self.assertEqual(response.status_code, 404, response.text)


if __name__ == "__main__":
    unittest.main()
