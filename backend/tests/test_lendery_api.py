import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from lendery.availability import AvailabilityResult
from lendery.routes import get_db
from main import app


class LenderyAvailabilityApiTests(unittest.TestCase):
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

    def create_linked_item(self, barcode: str = "LENDERY-1") -> dict:
        response = self.client.post(
            "/lendery/items",
            json={
                "name": "Carpet cleaner",
                "barcode": barcode,
                "library_url": (
                    "https://vaughanpl.bibliocommons.com/"
                    "v2/record/S130C603511"
                ),
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.json()

    @patch("lendery.availability.check_availability")
    def test_item_detail_refreshes_availability(self, check) -> None:
        check.return_value = AvailabilityResult(
            status="available",
            available_copies=1,
            total_copies_at_branch=2,
        )
        created = self.create_linked_item()

        response = self.client.get(
            f"/lendery/items/{created['id']}"
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["availability_status"], "available")
        self.assertEqual(body["available_copies"], 1)
        self.assertEqual(body["total_copies_at_branch"], 2)
        self.assertIsNotNone(body["availability_checked_at"])

    @patch("lendery.availability.check_availability")
    def test_in_and_out_filters_use_saved_status(self, check) -> None:
        created_in = self.create_linked_item("IN-1")
        check.return_value = AvailabilityResult("available", 1, 1)
        self.client.get(f"/lendery/items/{created_in['id']}")

        created_out = self.create_linked_item("OUT-1")
        check.return_value = AvailabilityResult("unavailable", 0, 1)
        self.client.get(f"/lendery/items/{created_out['id']}")

        in_items = self.client.get(
            "/lendery/items?availability=in"
        ).json()
        out_items = self.client.get(
            "/lendery/items?availability=out"
        ).json()

        self.assertEqual(
            [entry["barcode"] for entry in in_items],
            ["IN-1"],
        )
        self.assertEqual(
            [entry["barcode"] for entry in out_items],
            ["OUT-1"],
        )


if __name__ == "__main__":
    unittest.main()
