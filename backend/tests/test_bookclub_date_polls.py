import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from accounts import login_throttle
from database import Base
from dependencies import get_db
from main import app, bookclub_public_app


class DatePollRoutesTests(unittest.TestCase):
    """Covers meeting-date polling — a deliberately independent system
    from book voting (test_bookclub_voting.py), per docs/backend/bookclub.md."""

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

    def open_poll(self, option_dates=None) -> dict:
        response = self.facilitator.post(
            "/bookclub/community/date-poll",
            json={"option_dates": option_dates or ["2026-09-01", "2026-09-08"]},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_only_facilitator_can_open_a_poll(self) -> None:
        response = self.reader_a.post("/bookclub/community/date-poll", json={"option_dates": ["2026-09-01"]})
        self.assertEqual(response.status_code, 404, response.text)

    def test_cannot_open_a_second_poll_while_one_is_open(self) -> None:
        self.open_poll()
        response = self.facilitator.post("/bookclub/community/date-poll", json={"option_dates": ["2026-09-15"]})
        self.assertEqual(response.status_code, 409, response.text)

    def test_participant_can_view_and_vote(self) -> None:
        poll = self.open_poll()
        option_id = poll["options"][0]["id"]
        response = self.reader_a.put("/participant/date-poll/vote", json={"option_id": option_id})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["my_vote_option_id"], option_id)
        self.assertEqual(response.json()["my_vote_option_ids"], [option_id])

    def test_participant_can_select_multiple_dates(self) -> None:
        poll = self.open_poll()
        option_ids = [option["id"] for option in poll["options"]]
        response = self.reader_a.put(
            "/participant/date-poll/vote", json={"option_ids": option_ids}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["my_vote_option_ids"], option_ids)

        facilitator_view = self.facilitator.get("/bookclub/community/date-poll").json()
        self.assertTrue(all(option["vote_count"] == 1 for option in facilitator_view["options"]))

    def test_participant_can_replace_or_clear_date_choices(self) -> None:
        poll = self.open_poll()
        first, second = poll["options"][0]["id"], poll["options"][1]["id"]
        self.reader_a.put(
            "/participant/date-poll/vote", json={"option_ids": [first, second]}
        )
        response = self.reader_a.put(
            "/participant/date-poll/vote", json={"option_ids": [second]}
        )
        self.assertEqual(response.json()["my_vote_option_ids"], [second])

        response = self.reader_a.put("/participant/date-poll/vote", json={"option_ids": []})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["my_vote_option_ids"], [])

    def test_vote_counts_hidden_from_participants_while_open(self) -> None:
        poll = self.open_poll()
        option_id = poll["options"][0]["id"]
        self.reader_a.put("/participant/date-poll/vote", json={"option_id": option_id})
        response = self.reader_b.get("/participant/date-poll")
        self.assertTrue(all(o["vote_count"] is None for o in response.json()["options"]))

    def test_vote_counts_always_visible_to_facilitator(self) -> None:
        poll = self.open_poll()
        option_id = poll["options"][0]["id"]
        self.reader_a.put("/participant/date-poll/vote", json={"option_id": option_id})
        response = self.facilitator.get("/bookclub/community/date-poll")
        matching = [o for o in response.json()["options"] if o["id"] == option_id][0]
        self.assertEqual(matching["vote_count"], 1)

    def test_facilitator_can_add_another_option_to_open_poll(self) -> None:
        self.open_poll(option_dates=["2026-09-01"])
        response = self.facilitator.post(
            "/bookclub/community/date-poll/options", json={"option_date": "2026-09-22"}
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(len(response.json()["options"]), 2)

    def test_closing_picks_the_most_voted_date_as_winner(self) -> None:
        poll = self.open_poll()
        first, second = poll["options"][0]["id"], poll["options"][1]["id"]
        self.reader_a.put("/participant/date-poll/vote", json={"option_id": second})
        self.reader_b.put("/participant/date-poll/vote", json={"option_id": second})
        onlooker = self.register_reader("onlooker@example.com")
        onlooker.put("/participant/date-poll/vote", json={"option_id": first})

        response = self.facilitator.post("/bookclub/community/date-poll/close")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "closed")
        self.assertEqual(body["winning_date"], poll["options"][1]["option_date"])
        onlooker.close()

    def test_cannot_vote_after_poll_is_closed(self) -> None:
        poll = self.open_poll()
        option_id = poll["options"][0]["id"]
        self.facilitator.post("/bookclub/community/date-poll/close")
        response = self.reader_a.put("/participant/date-poll/vote", json={"option_id": option_id})
        self.assertEqual(response.status_code, 404, response.text)

    def test_results_visible_to_participants_once_closed(self) -> None:
        poll = self.open_poll()
        option_id = poll["options"][0]["id"]
        self.reader_a.put("/participant/date-poll/vote", json={"option_id": option_id})
        self.facilitator.post("/bookclub/community/date-poll/close")
        response = self.reader_b.get("/participant/date-poll")
        matching = [o for o in response.json()["options"] if o["id"] == option_id][0]
        self.assertEqual(matching["vote_count"], 1)

    def test_facilitator_can_open_a_new_poll_after_closing(self) -> None:
        self.open_poll()
        self.facilitator.post("/bookclub/community/date-poll/close")
        response = self.facilitator.post("/bookclub/community/date-poll", json={"option_dates": ["2026-10-01"]})
        self.assertEqual(response.status_code, 201, response.text)

    def test_book_voting_and_date_polling_are_independent(self) -> None:
        # Opening a book-voting round doesn't block or interact with an
        # open date poll, and vice versa — confirms the "two separate
        # systems" design choice actually holds at the API level.
        book = self.facilitator.post(
            "/bookclub/community/books", json={"title": "Dune", "author": "Frank Herbert"}
        ).json()
        self.facilitator.post("/bookclub/community/voting-round", json={"candidate_book_ids": [book["id"]]})
        response = self.facilitator.post("/bookclub/community/date-poll", json={"option_dates": ["2026-09-01"]})
        self.assertEqual(response.status_code, 201, response.text)


if __name__ == "__main__":
    unittest.main()
