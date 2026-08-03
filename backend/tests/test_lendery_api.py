import os
import tempfile
import unittest
from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, migrate_existing_database
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
        with patch(
            "lendery.availability.check_availability",
            return_value=AvailabilityResult("available", 1, 1),
        ):
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
    def test_creating_a_linked_item_checks_availability_immediately(
        self, check
    ) -> None:
        check.return_value = AvailabilityResult("checked_out", 0, 1)

        response = self.client.post(
            "/lendery/items",
            json={
                "name": "Carpet cleaner",
                "barcode": "IMMEDIATE-1",
                "library_url": (
                    "https://vaughanpl.bibliocommons.com/"
                    "v2/record/S130C603511"
                ),
            },
        )

        self.assertEqual(response.status_code, 201, response.text)
        created = response.json()
        self.assertEqual(created["availability_status"], "checked_out")
        self.assertEqual(created["available_copies"], 0)
        self.assertIsNotNone(created["availability_checked_at"])
        check.assert_called_once()

    @patch("lendery.availability.check_availability")
    def test_changing_the_library_url_checks_availability_immediately(
        self, check
    ) -> None:
        check.return_value = AvailabilityResult("available", 1, 1)
        created = self.create_linked_item()
        check.reset_mock()

        check.return_value = AvailabilityResult("not_held", 0, 0)
        response = self.client.patch(
            f"/lendery/items/{created['id']}",
            json={
                "library_url": (
                    "https://vaughanpl.bibliocommons.com/"
                    "v2/record/S130C999999"
                ),
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["availability_status"], "not_held")
        check.assert_called_once()

    @patch("lendery.catalogue.fetch_catalogue_item")
    def test_imports_item_details_from_vaughan_catalogue(self, fetch_item) -> None:
        fetch_item.return_value = {
            "name": "ThermoMaven 3000FT Smart Wireless Meat Thermometer",
            "description": "Monitor food from up to 3000 feet away.",
            "image_url": (
                "https://www.vaughanpl.info/img/catalogue/lendery/MeatThermo.jpg"
            ),
            "manual_url": (
                "https://www.vaughanpl.info/files/catalogue/"
                "ThermoMaven_X2_User_Manual_1.0.pdf"
            ),
            "library_url": (
                "https://vaughanpl.bibliocommons.com/v2/record/S130C772570"
            ),
        }
        response = self.client.post(
            "/lendery/items/import",
            json={
                "library_url": (
                    "https://vaughanpl.bibliocommons.com/v2/record/S130C772570"
                )
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json()["name"],
            "ThermoMaven 3000FT Smart Wireless Meat Thermometer",
        )
        self.assertTrue(response.json()["manual_url"].endswith(".pdf"))
        fetch_item.assert_called_once_with(
            "https://vaughanpl.bibliocommons.com/v2/record/S130C772570"
        )

    def test_lendery_page_uses_current_autofill_assets(self) -> None:
        response = self.client.get("/lendery")
        self.assertEqual(response.status_code, 200)
        self.assertIn('/static/lendery.js?v=31', response.text)
        self.assertIn('/static/lendery.css?v=31', response.text)
        self.assertIn('<option value="alphabetical">Alphabetical</option>', response.text)
        self.assertIn('value="recently-active">Most recently used', response.text)
        self.assertIn('value="recently-added">Recently added', response.text)
        self.assertIn('class="dashboard-link" href="/dashboard"', response.text)
        self.assertIn('class="mobile-return-top" href="#lendery-top"', response.text)

    def test_removed_item_is_preserved_and_can_be_restored(self) -> None:
        item = self.create_linked_item("REMOVAL-1")

        missing_reason = self.client.post(
            f"/lendery/items/{item['id']}/remove",
            json={"reason": "   "},
        )
        self.assertEqual(missing_reason.status_code, 422, missing_reason.text)

        removed = self.client.post(
            f"/lendery/items/{item['id']}/remove",
            json={"reason": "Motor cannot be repaired"},
        )
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertEqual(self.client.get("/lendery/items").json(), [])

        removed_items = self.client.get(
            "/lendery/items?lifecycle=removed"
        ).json()
        self.assertEqual(len(removed_items), 1)
        self.assertEqual(removed_items[0]["id"], item["id"])
        self.assertEqual(
            removed_items[0]["lifecycle_note"], "Motor cannot be repaired"
        )

        restored = self.client.post(f"/lendery/items/{item['id']}/restore")
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()["lifecycle_status"], "active")
        self.assertEqual(len(self.client.get("/lendery/items").json()), 1)

    def test_component_activity_updates_item_activity_time(self) -> None:
        item = self.create_linked_item("ACTIVITY-1")

        component = self.client.post(
            f"/lendery/items/{item['id']}/components",
            json={"name": "Charging cable", "quantity": 1},
        )
        refreshed = self.client.get(f"/lendery/items/{item['id']}")

        self.assertEqual(component.status_code, 201, component.text)
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        self.assertNotEqual(refreshed.json()["updated_at"], item["updated_at"])

    def test_lifecycle_filters_keep_removed_items_out_of_inventory(self) -> None:
        active = self.create_linked_item("ACTIVE-1")
        removed = self.create_linked_item("REMOVED-1")
        self.client.post(
            f"/lendery/items/{removed['id']}/remove",
            json={"reason": "Withdrawn from the collection"},
        )

        inventory = self.client.get("/lendery/items").json()
        removed_items = self.client.get(
            "/lendery/items?lifecycle=removed"
        ).json()
        all_items = self.client.get("/lendery/items?lifecycle=all").json()

        self.assertEqual([entry["id"] for entry in inventory], [active["id"]])
        self.assertEqual([entry["id"] for entry in removed_items], [removed["id"]])
        self.assertEqual(len(all_items), 2)

    def test_existing_sqlite_items_receive_lifecycle_columns(self) -> None:
        legacy_engine = create_engine("sqlite://", poolclass=StaticPool)
        try:
            with legacy_engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE lendery_items ("
                        "id INTEGER PRIMARY KEY, name VARCHAR(200) NOT NULL, "
                        "lifecycle_status VARCHAR(20) NOT NULL)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO lendery_items "
                        "(id, name, lifecycle_status) "
                        "VALUES (1, 'Legacy drill', 'retired')"
                    )
                )

            with patch("database.engine", legacy_engine):
                migrate_existing_database()

            columns = {
                column["name"]
                for column in inspect(legacy_engine).get_columns(
                    "lendery_items"
                )
            }
            self.assertIn("lifecycle_status", columns)
            self.assertIn("lifecycle_changed_at", columns)
            with legacy_engine.connect() as connection:
                row = connection.execute(
                    text(
                        "SELECT lifecycle_status, lifecycle_changed_at "
                        "FROM lendery_items WHERE id = 1"
                    )
                ).one()
            self.assertEqual(row.lifecycle_status, "active")
            self.assertIsNotNone(row.lifecycle_changed_at)
        finally:
            legacy_engine.dispose()

    def test_only_removed_items_can_be_permanently_deleted(self) -> None:
        item = self.create_linked_item("DELETE-FOREVER-1")
        component = self.client.post(
            f"/lendery/items/{item['id']}/components",
            json={"name": "Power cord", "quantity": 1},
        ).json()
        self.client.post(
            f"/lendery/components/{component['id']}/image",
            files={
                "image": ("cord.png", self.sample_png(100, 100), "image/png")
            },
        )
        image_path = component_image_path(component["id"])
        self.assertTrue(image_path.exists())

        rejected = self.client.delete(
            f"/lendery/items/{item['id']}/permanent"
        )
        self.assertEqual(rejected.status_code, 409, rejected.text)

        self.client.post(
            f"/lendery/items/{item['id']}/remove",
            json={"reason": "Duplicate record"},
        )
        deleted = self.client.delete(
            f"/lendery/items/{item['id']}/permanent"
        )

        self.assertEqual(deleted.status_code, 204, deleted.text)
        self.assertEqual(
            self.client.get(f"/lendery/items/{item['id']}").status_code,
            404,
        )
        self.assertFalse(image_path.exists())

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

    def test_export_csv_lists_inventory_and_requires_manage_access(self) -> None:
        self.create_linked_item("EXPORT-1")

        response = self.client.get("/lendery/items/export.csv")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.headers["content-type"].startswith("text/csv")
        )
        rows = response.text.splitlines()
        self.assertIn("barcode", rows[0])
        self.assertTrue(any("EXPORT-1" in row for row in rows[1:]))

    def test_physical_manual_inclusion_and_missing_flag_are_tracked(self) -> None:
        response = self.client.post(
            "/lendery/items",
            json={
                "name": "Telescope",
                "barcode": "MANUAL-1",
                "physical_manual_included": True,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        created = response.json()
        self.assertTrue(created["physical_manual_included"])
        self.assertFalse(created["physical_manual_missing"])

        default_response = self.client.post(
            "/lendery/items",
            json={"name": "Sewing kit", "barcode": "MANUAL-2"},
        )
        self.assertEqual(default_response.status_code, 201, default_response.text)
        self.assertFalse(default_response.json()["physical_manual_included"])

        flagged = self.client.patch(
            f"/lendery/items/{created['id']}",
            json={"physical_manual_missing": True},
        )
        self.assertEqual(flagged.status_code, 200, flagged.text)
        self.assertTrue(flagged.json()["physical_manual_missing"])

        unflagged = self.client.patch(
            f"/lendery/items/{created['id']}",
            json={"physical_manual_missing": False},
        )
        self.assertEqual(unflagged.status_code, 200, unflagged.text)
        self.assertFalse(unflagged.json()["physical_manual_missing"])

        csv_rows = self.client.get(
            "/lendery/items/export.csv"
        ).text.splitlines()
        self.assertIn("physical_manual_included", csv_rows[0])
        self.assertTrue(
            any("MANUAL-1" in row and "True" in row for row in csv_rows[1:])
        )

        with self.sessions() as db:
            viewer = LibtoolsUser(
                username="viewer",
                password_hash=hash_password("viewer-password"),
                role="user",
            )
            db.add(viewer)
            db.commit()

        viewer_client = TestClient(app)
        login = viewer_client.post(
            "/auth/login",
            json={"username": "viewer", "password": "viewer-password"},
        )
        self.assertEqual(login.status_code, 200)
        forbidden = viewer_client.get("/lendery/items/export.csv")
        self.assertEqual(forbidden.status_code, 403)
        viewer_client.close()

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
