import os
import tempfile
import unittest
from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from accounts.models import LibtoolsUser
from lendery.availability import AvailabilityResult
from lendery.component_images import component_image_path
from lendery.routes import get_db
from main import app
from security import hash_password


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
        self.upload_directory = tempfile.TemporaryDirectory()
        self.upload_environment = patch.dict(
            os.environ,
            {"LIBTOOLS_UPLOAD_DIR": self.upload_directory.name},
        )
        self.upload_environment.start()
        with self.engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
        with self.sessions() as db:
            user = LibtoolsUser(
                    username="admin",
                    password_hash=hash_password("admin-password"),
                    role="admin",
            )
            db.add(user)
            db.commit()
        response = self.client.post(
            "/auth/login",
            json={
                "username": "admin",
                "password": "admin-password",
            },
        )
        self.assertEqual(response.status_code, 200)

    def tearDown(self) -> None:
        self.upload_environment.stop()
        self.upload_directory.cleanup()

    @staticmethod
    def sample_png(width: int = 1800, height: int = 900) -> bytes:
        contents = BytesIO()
        Image.new("RGB", (width, height), (42, 112, 83)).save(
            contents,
            format="PNG",
        )
        return contents.getvalue()

    @staticmethod
    def sample_heif() -> bytes:
        contents = BytesIO()
        Image.new("RGB", (120, 80), (218, 170, 86)).save(
            contents,
            format="HEIF",
        )
        return contents.getvalue()

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
        self.assertEqual(body["availability_status_version"], 2)
        self.assertEqual(body["available_copies"], 1)
        self.assertEqual(body["total_copies_at_branch"], 2)
        self.assertIsNotNone(body["availability_checked_at"])

    @patch("lendery.availability.check_availability")
    def test_in_and_out_filters_use_saved_status(self, check) -> None:
        created_in = self.create_linked_item("IN-1")
        check.return_value = AvailabilityResult("available", 1, 1)
        self.client.get(f"/lendery/items/{created_in['id']}")

        created_out = self.create_linked_item("OUT-1")
        check.return_value = AvailabilityResult("checked_out", 0, 1)
        self.client.get(f"/lendery/items/{created_out['id']}")

        created_unavailable = self.create_linked_item("UNAVAILABLE-1")
        check.return_value = AvailabilityResult("unavailable", 0, 0)
        self.client.get(
            f"/lendery/items/{created_unavailable['id']}"
        )

        in_items = self.client.get(
            "/lendery/items?availability=in"
        ).json()
        out_items = self.client.get(
            "/lendery/items?availability=out"
        ).json()
        unavailable_items = self.client.get(
            "/lendery/items?availability=unavailable"
        ).json()

        self.assertEqual(
            [entry["barcode"] for entry in in_items],
            ["IN-1"],
        )
        self.assertEqual(
            [entry["barcode"] for entry in out_items],
            ["OUT-1"],
        )
        self.assertEqual(
            [entry["barcode"] for entry in unavailable_items],
            ["UNAVAILABLE-1"],
        )

    def test_component_photo_upload_is_processed_and_served(self) -> None:
        item = self.create_linked_item()
        component = self.client.post(
            f"/lendery/items/{item['id']}/components",
            json={"name": "Upholstery nozzle", "quantity": 1},
        ).json()

        uploaded = self.client.post(
            f"/lendery/components/{component['id']}/image",
            files={
                "image": ("nozzle.png", self.sample_png(), "image/png"),
            },
        )

        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        self.assertEqual(
            uploaded.json()["image_url"],
            f"/lendery/components/{component['id']}/image",
        )
        saved_path = component_image_path(component["id"])
        self.assertTrue(saved_path.is_file())
        with Image.open(saved_path) as processed:
            self.assertEqual(processed.format, "WEBP")
            self.assertEqual(processed.size, (1200, 600))

        served = self.client.get(uploaded.json()["image_url"])
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served.headers["content-type"], "image/webp")
        self.assertEqual(served.headers["cache-control"], "private, no-store")

    def test_invalid_component_photo_is_rejected(self) -> None:
        item = self.create_linked_item()
        component = self.client.post(
            f"/lendery/items/{item['id']}/components",
            json={"name": "Hose", "quantity": 1},
        ).json()

        response = self.client.post(
            f"/lendery/components/{component['id']}/image",
            files={"image": ("not-an-image.jpg", b"hello", "image/jpeg")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(component_image_path(component["id"]).exists())

    def test_iphone_heif_photo_is_supported(self) -> None:
        item = self.create_linked_item()
        component = self.client.post(
            f"/lendery/items/{item['id']}/components",
            json={"name": "Power cord", "quantity": 1},
        ).json()

        response = self.client.post(
            f"/lendery/components/{component['id']}/image",
            files={"image": ("cord.heic", self.sample_heif(), "image/heic")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        with Image.open(component_image_path(component["id"])) as processed:
            self.assertEqual(processed.format, "WEBP")

    def test_component_photo_is_removed_with_component(self) -> None:
        item = self.create_linked_item()
        component = self.client.post(
            f"/lendery/items/{item['id']}/components",
            json={"name": "Brush", "quantity": 1},
        ).json()
        self.client.post(
            f"/lendery/components/{component['id']}/image",
            files={"image": ("brush.png", self.sample_png(100, 100), "image/png")},
        )
        self.assertTrue(component_image_path(component["id"]).exists())

        deleted = self.client.delete(
            f"/lendery/components/{component['id']}"
        )

        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(component_image_path(component["id"]).exists())

    def test_removing_component_photo_clears_reference(self) -> None:
        item = self.create_linked_item()
        component = self.client.post(
            f"/lendery/items/{item['id']}/components",
            json={"name": "Crevice tool", "quantity": 1},
        ).json()
        self.client.post(
            f"/lendery/components/{component['id']}/image",
            files={"image": ("tool.png", self.sample_png(100, 100), "image/png")},
        )

        removed = self.client.delete(
            f"/lendery/components/{component['id']}/image"
        )
        refreshed = self.client.get(
            f"/lendery/components/{component['id']}"
        )

        self.assertEqual(removed.status_code, 204)
        self.assertIsNone(refreshed.json()["image_url"])
        self.assertFalse(component_image_path(component["id"]).exists())


if __name__ == "__main__":
    unittest.main()
