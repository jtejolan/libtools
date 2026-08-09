import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from accounts import login_throttle
from database import Base
from dependencies import get_db
from main import app, bookclub_public_app


class VotingRoutesTests(unittest.TestCase):
    """Covers book voting: participant-facing propose/vote
    (voting_routes.py) and facilitator-facing open/approve/reject/close
    (facilitator_routes.py's voting endpoints)."""

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
        self.facilitator = TestClient(app, base_url="http://bookclub.libtools.app")
        created = self.facilitator.post(
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
        self.book_a = self.create_book("Dune")
        self.book_b = self.create_book("Foundation")
        self.book_c = self.create_book("The Martian")

        self.reader_a = self.register_reader("reader-a@example.com")
        self.reader_b = self.register_reader("reader-b@example.com")

    def create_book(self, title: str) -> int:
        response = self.facilitator.post(
            "/facilitator/books", json={"title": title, "author": "Someone"}
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

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

    def open_round(self, candidate_book_ids=None) -> dict:
        response = self.facilitator.post(
            "/facilitator/voting-round",
            json={"candidate_book_ids": candidate_book_ids or [self.book_a, self.book_b]},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_only_facilitator_can_open_a_round(self) -> None:
        response = self.reader_a.post(
            "/facilitator/voting-round", json={"candidate_book_ids": [self.book_a]}
        )
        self.assertEqual(response.status_code, 403, response.text)

    def test_cannot_open_a_second_round_while_one_is_open(self) -> None:
        self.open_round()
        response = self.facilitator.post(
            "/facilitator/voting-round", json={"candidate_book_ids": [self.book_c]}
        )
        self.assertEqual(response.status_code, 409, response.text)

    def test_facilitator_proposed_candidates_are_auto_approved(self) -> None:
        round_ = self.open_round()
        self.assertEqual(len(round_["candidates"]), 2)
        self.assertTrue(all(c["status"] == "approved" for c in round_["candidates"]))

    def test_participant_can_view_and_vote_for_approved_candidate(self) -> None:
        round_ = self.open_round()
        candidate_id = round_["candidates"][0]["id"]
        response = self.reader_a.put("/participant/voting-round/vote", json={"candidate_id": candidate_id})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["my_vote_candidate_id"], candidate_id)

    def test_vote_counts_hidden_from_participants_while_open(self) -> None:
        round_ = self.open_round()
        candidate_id = round_["candidates"][0]["id"]
        self.reader_a.put("/participant/voting-round/vote", json={"candidate_id": candidate_id})
        response = self.reader_b.get("/participant/voting-round")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(all(c["vote_count"] is None for c in response.json()["candidates"]))

    def test_vote_counts_always_visible_to_facilitator(self) -> None:
        round_ = self.open_round()
        candidate_id = round_["candidates"][0]["id"]
        self.reader_a.put("/participant/voting-round/vote", json={"candidate_id": candidate_id})
        response = self.facilitator.get("/facilitator/voting-round")
        self.assertEqual(response.status_code, 200, response.text)
        matching = [c for c in response.json()["candidates"] if c["id"] == candidate_id][0]
        self.assertEqual(matching["vote_count"], 1)

    def test_revoting_changes_the_vote_not_adds_a_second_one(self) -> None:
        round_ = self.open_round()
        first, second = round_["candidates"][0]["id"], round_["candidates"][1]["id"]
        self.reader_a.put("/participant/voting-round/vote", json={"candidate_id": first})
        self.reader_a.put("/participant/voting-round/vote", json={"candidate_id": second})
        results = self.facilitator.get("/facilitator/voting-round").json()
        counts = {c["id"]: c["vote_count"] for c in results["candidates"]}
        self.assertEqual(counts[first], 0)
        self.assertEqual(counts[second], 1)

    def test_member_proposed_candidate_requires_facilitator_approval(self) -> None:
        self.open_round(candidate_book_ids=[self.book_a])
        response = self.reader_a.post("/participant/voting-round/candidates", json={"book_id": self.book_c})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["status"], "pending")

        # A pending candidate can't be voted for yet.
        vote = self.reader_b.put(
            "/participant/voting-round/vote", json={"candidate_id": response.json()["id"]}
        )
        self.assertEqual(vote.status_code, 404, vote.text)

        approved = self.facilitator.post(f"/facilitator/candidates/{response.json()['id']}/approve")
        self.assertEqual(approved.status_code, 200, approved.text)
        vote_after_approval = self.reader_b.put(
            "/participant/voting-round/vote", json={"candidate_id": response.json()["id"]}
        )
        self.assertEqual(vote_after_approval.status_code, 200, vote_after_approval.text)

    def test_rejected_candidate_cannot_be_voted_for(self) -> None:
        self.open_round(candidate_book_ids=[self.book_a])
        proposed = self.reader_a.post(
            "/participant/voting-round/candidates", json={"book_id": self.book_c}
        ).json()
        self.facilitator.post(f"/facilitator/candidates/{proposed['id']}/reject")
        vote = self.reader_b.put("/participant/voting-round/vote", json={"candidate_id": proposed["id"]})
        self.assertEqual(vote.status_code, 404, vote.text)

    def test_closing_a_round_picks_the_most_voted_candidate_as_winner(self) -> None:
        round_ = self.open_round()
        first, second = round_["candidates"][0]["id"], round_["candidates"][1]["id"]
        self.reader_a.put("/participant/voting-round/vote", json={"candidate_id": second})
        self.reader_b.put("/participant/voting-round/vote", json={"candidate_id": second})
        onlooker = self.register_reader("onlooker@example.com")
        onlooker.put("/participant/voting-round/vote", json={"candidate_id": first})

        response = self.facilitator.post("/facilitator/voting-round/close")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "closed")
        self.assertEqual(body["winning_book"]["id"], self.book_b)
        onlooker.close()

    def test_results_and_vote_counts_visible_to_participants_once_closed(self) -> None:
        round_ = self.open_round()
        candidate_id = round_["candidates"][0]["id"]
        self.reader_a.put("/participant/voting-round/vote", json={"candidate_id": candidate_id})
        self.facilitator.post("/facilitator/voting-round/close")

        response = self.reader_b.get("/participant/voting-round")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "closed")
        matching = [c for c in body["candidates"] if c["id"] == candidate_id][0]
        self.assertEqual(matching["vote_count"], 1)

    def test_cannot_vote_after_round_is_closed(self) -> None:
        round_ = self.open_round()
        candidate_id = round_["candidates"][0]["id"]
        self.facilitator.post("/facilitator/voting-round/close")
        response = self.reader_a.put("/participant/voting-round/vote", json={"candidate_id": candidate_id})
        self.assertEqual(response.status_code, 404, response.text)

    def test_facilitator_can_open_a_new_round_after_closing_the_previous_one(self) -> None:
        self.open_round()
        self.facilitator.post("/facilitator/voting-round/close")
        response = self.facilitator.post(
            "/facilitator/voting-round", json={"candidate_book_ids": [self.book_c]}
        )
        self.assertEqual(response.status_code, 201, response.text)

    def test_voting_round_scoped_to_own_club(self) -> None:
        self.open_round()
        self.facilitator.post("/participant/auth/logout")
        other_club = self.facilitator.post(
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
        response = self.facilitator.get("/facilitator/voting-round")
        self.assertEqual(response.status_code, 404, response.text)


if __name__ == "__main__":
    unittest.main()
