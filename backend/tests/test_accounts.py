import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from accounts.models import AccountToken, LibtoolsUser, ToolAccess
from accounts.bootstrap import initialize_platform_accounts
from accounts import login_throttle
from bookclub.models import BookClub, BookClubBook, BookClubMeeting
from database import Base
from dependencies import get_db
from lendery.models import Component, LenderyItem, MaintenanceCase
from main import app
from security import hash_password


class PlatformAccountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(cls.engine)
        cls.sessions = sessionmaker(
            bind=cls.engine, autoflush=False, expire_on_commit=False
        )

        def override_get_db():
            db: Session = cls.sessions()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def setUp(self) -> None:
        login_throttle.reset()
        with self.engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
        with self.sessions() as db:
            admin = LibtoolsUser(
                name="Admin",
                username="admin",
                password_hash=hash_password("admin-password"),
                role="admin",
            )
            db.add(admin)
            db.commit()
        self.admin = TestClient(app)
        response = self.admin.post(
            "/auth/login",
            json={"username": "admin", "password": "admin-password"},
        )
        self.assertEqual(response.status_code, 200)

    def tearDown(self) -> None:
        self.admin.close()

    def create_user(self, username: str) -> dict:
        response = self.admin.post(
            "/api/admin/users",
            json={
                "name": username,
                "username": username,
                "password": "starting-password",
                "confirm_password": "starting-password",
                "tools": [],
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_signed_in_homepage_redirects_to_dashboard(self) -> None:
        response = self.admin.get("/", follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/dashboard")
        self.assertEqual(response.headers["cache-control"], "private, no-store")

        public_homepage = self.admin.get("/home")
        self.assertEqual(public_homepage.status_code, 200)
        self.assertIn("Library Tools", public_homepage.text)

    def test_account_creation_login_and_offline_recovery(self) -> None:
        created = self.create_user("Taylor")
        self.assertTrue(created["recovery_code"])
        self.assertEqual(created["tools"], ["bookclub", "storytime"])

        user = TestClient(app)
        try:
            login = user.post(
                "/auth/login",
                json={"username": "taylor", "password": "starting-password"},
            )
            self.assertEqual(login.status_code, 200)
            user.post("/auth/logout")

            recovered = user.post(
                "/auth/recover",
                json={
                    "username": "Taylor",
                    "recovery_code": created["recovery_code"].lower(),
                    "password": "replacement-password",
                    "confirm_password": "replacement-password",
                },
            )
            self.assertEqual(recovered.status_code, 200, recovered.text)
            self.assertNotEqual(
                recovered.json()["recovery_code"], created["recovery_code"]
            )
            self.assertEqual(
                user.post(
                    "/auth/login",
                    json={
                        "username": "Taylor",
                        "password": "replacement-password",
                    },
                ).status_code,
                200,
            )
        finally:
            user.close()

    def test_public_registration_creates_a_session_and_one_recovery_code(self) -> None:
        client = TestClient(app)
        try:
            response = client.post(
                "/auth/register",
                json={
                    "name": "New Reader",
                    "username": "  New   Reader  ",
                    "email": "",
                    "password": "reader-password",
                    "confirm_password": "reader-password",
                },
            )
            self.assertEqual(response.status_code, 201, response.text)
            created = response.json()
            self.assertEqual(created["name"], "New Reader")
            self.assertEqual(created["username"], "New Reader")
            self.assertIsNone(created["email"])
            self.assertFalse(created["email_verified"])
            self.assertTrue(created["recovery_code"])
            self.assertEqual(client.get("/auth/me").status_code, 200)
            self.assertEqual(client.get("/lendery/items").status_code, 200)
            self.assertEqual(
                client.post(
                    "/auth/register",
                    json={
                        "name": "New Reader Duplicate",
                        "username": "new reader",
                        "password": "another-password",
                        "confirm_password": "another-password",
                    },
                ).status_code,
                409,
            )

            with self.sessions() as db:
                user = db.scalar(
                    select(LibtoolsUser).where(
                        LibtoolsUser.username == "New Reader"
                    )
                )
                self.assertIsNotNone(user.recovery_code_hash)
                self.assertNotIn(created["recovery_code"], user.recovery_code_hash)
        finally:
            client.close()

    def test_registration_with_email_creates_single_use_verification_link(self) -> None:
        client = TestClient(app)
        try:
            with patch(
                "accounts.routes.email_delivery.send_verification_email",
                return_value=True,
            ) as send_email:
                response = client.post(
                    "/auth/register",
                    json={
                        "name": "Email Reader",
                        "username": "Email Reader",
                        "email": " Reader@Example.COM ",
                        "password": "reader-password",
                        "confirm_password": "reader-password",
                    },
                )
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(response.json()["email"], "reader@example.com")
            self.assertFalse(response.json()["email_verified"])
            self.assertTrue(response.json()["email_verification_required"])
            self.assertTrue(response.json()["email_delivery_configured"])
            verification_url = send_email.call_args.kwargs["verification_url"]
            token = parse_qs(urlsplit(verification_url).query)["token"][0]

            verified = client.post("/auth/verify-email", json={"token": token})
            self.assertEqual(verified.status_code, 200, verified.text)
            self.assertTrue(verified.json()["email_verified"])
            self.assertEqual(
                client.post("/auth/verify-email", json={"token": token}).status_code,
                400,
            )

            duplicate = TestClient(app)
            try:
                duplicate_response = duplicate.post(
                    "/auth/register",
                    json={
                        "name": "Other Reader",
                        "username": "Other Reader",
                        "email": "READER@example.com",
                        "password": "reader-password",
                        "confirm_password": "reader-password",
                    },
                )
                self.assertEqual(duplicate_response.status_code, 409)
            finally:
                duplicate.close()
        finally:
            client.close()

    def test_verified_email_password_reset_is_private_expiring_and_single_use(self) -> None:
        client = TestClient(app)
        try:
            with patch(
                "accounts.routes.email_delivery.send_verification_email",
                return_value=True,
            ) as verification_email:
                registered = client.post(
                    "/auth/register",
                    json={
                        "name": "Reset Reader",
                        "username": "Reset Reader",
                        "email": "reset@example.com",
                        "password": "original-password",
                        "confirm_password": "original-password",
                    },
                )
            self.assertEqual(registered.status_code, 201, registered.text)
            verification_token = parse_qs(
                urlsplit(
                    verification_email.call_args.kwargs["verification_url"]
                ).query
            )["token"][0]
            self.assertEqual(
                client.post(
                    "/auth/verify-email", json={"token": verification_token}
                ).status_code,
                200,
            )

            with patch(
                "accounts.routes.email_delivery.send_password_reset_email",
                return_value=True,
            ) as reset_email:
                requested = client.post(
                    "/auth/password-reset/request",
                    json={"email": "RESET@example.com"},
                )
            self.assertEqual(requested.status_code, 200, requested.text)
            reset_token = parse_qs(
                urlsplit(reset_email.call_args.kwargs["reset_url"]).query
            )["token"][0]
            reset = client.post(
                "/auth/password-reset/confirm",
                json={
                    "token": reset_token,
                    "password": "replacement-password",
                    "confirm_password": "replacement-password",
                },
            )
            self.assertEqual(reset.status_code, 204, reset.text)
            self.assertEqual(client.get("/auth/me").status_code, 401)
            self.assertEqual(
                client.post(
                    "/auth/password-reset/confirm",
                    json={
                        "token": reset_token,
                        "password": "another-password",
                        "confirm_password": "another-password",
                    },
                ).status_code,
                400,
            )
            self.assertEqual(
                client.post(
                    "/auth/login",
                    json={
                        "username": "Reset Reader",
                        "password": "replacement-password",
                    },
                ).status_code,
                200,
            )
        finally:
            client.close()

    def test_password_reset_request_does_not_disclose_account_state(self) -> None:
        client = TestClient(app)
        try:
            with patch(
                "accounts.routes.email_delivery.send_password_reset_email"
            ) as send_email:
                missing = client.post(
                    "/auth/password-reset/request",
                    json={"email": "missing@example.com"},
                )
            self.assertEqual(missing.status_code, 200, missing.text)
            self.assertFalse(send_email.called)

            client.post(
                "/auth/register",
                json={
                    "name": "Unverified Reader",
                    "username": "Unverified Reader",
                    "email": "unverified@example.com",
                    "password": "reader-password",
                    "confirm_password": "reader-password",
                },
            )
            with patch(
                "accounts.routes.email_delivery.send_password_reset_email"
            ) as send_email:
                unverified = client.post(
                    "/auth/password-reset/request",
                    json={"email": "unverified@example.com"},
                )
            self.assertEqual(unverified.status_code, 200, unverified.text)
            self.assertEqual(unverified.json()["message"], missing.json()["message"])
            self.assertFalse(send_email.called)
        finally:
            client.close()

    def test_administrator_can_reset_a_self_registered_account(self) -> None:
        client = TestClient(app)
        try:
            registered = client.post(
                "/auth/register",
                json={
                    "name": "Assisted Reader",
                    "username": "Assisted Reader",
                    "password": "original-password",
                    "confirm_password": "original-password",
                },
            )
            self.assertEqual(registered.status_code, 201, registered.text)
            reset = self.admin.post(
                f"/api/admin/users/{registered.json()['id']}/password",
                json={
                    "password": "temporary-password",
                    "confirm_password": "temporary-password",
                },
            )
            self.assertEqual(reset.status_code, 200, reset.text)
            self.assertTrue(reset.json()["recovery_code"])
            self.assertEqual(client.get("/auth/me").status_code, 401)

            login = client.post(
                "/auth/login",
                json={
                    "username": "Assisted Reader",
                    "password": "temporary-password",
                },
            )
            self.assertEqual(login.status_code, 200, login.text)
            self.assertTrue(login.json()["must_change_password"])
            changed = client.put(
                "/auth/password",
                json={
                    "current_password": "temporary-password",
                    "password": "permanent-password",
                    "confirm_password": "permanent-password",
                },
            )
            self.assertEqual(changed.status_code, 204, changed.text)
            self.assertFalse(client.get("/auth/me").json()["must_change_password"])
        finally:
            client.close()

    def test_expired_email_token_is_rejected(self) -> None:
        client = TestClient(app)
        try:
            with patch(
                "accounts.routes.email_delivery.send_verification_email",
                return_value=True,
            ) as send_email:
                client.post(
                    "/auth/register",
                    json={
                        "name": "Expired Reader",
                        "username": "Expired Reader",
                        "email": "expired@example.com",
                        "password": "reader-password",
                        "confirm_password": "reader-password",
                    },
                )
            token = parse_qs(
                urlsplit(send_email.call_args.kwargs["verification_url"]).query
            )["token"][0]
            with self.sessions() as db:
                saved = db.scalar(
                    select(AccountToken).where(
                        AccountToken.purpose == "email_verification"
                    )
                )
                saved.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
                db.commit()
            self.assertEqual(
                client.post("/auth/verify-email", json={"token": token}).status_code,
                400,
            )
        finally:
            client.close()

    def test_account_pages_include_registration_and_reset_flows(self) -> None:
        for path in (
            "/login",
            "/signup",
            "/forgot-password",
            "/reset-password?token=placeholder",
            "/verify-email?token=placeholder",
        ):
            response = self.admin.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn("Create your account", response.text)
            self.assertIn("/static/account.js?v=11", response.text)

        admin_page = self.admin.get("/admin/accounts")
        self.assertEqual(admin_page.status_code, 200)
        self.assertIn("Account management", admin_page.text)
        self.assertIn('name="name"', admin_page.text)
        self.assertIn("available to every account", admin_page.text)
        self.assertNotIn('name="bookclub"', admin_page.text)
        self.assertNotIn('name="storytime"', admin_page.text)
        legacy_page = self.admin.get("/admin/users", follow_redirects=False)
        self.assertEqual(legacy_page.status_code, 302)
        self.assertEqual(legacy_page.headers["location"], "/admin/accounts")

    def test_registration_requires_a_name_separate_from_username(self) -> None:
        client = TestClient(app)
        try:
            missing = client.post(
                "/auth/register",
                json={
                    "username": "nameless-reader",
                    "password": "reader-password",
                    "confirm_password": "reader-password",
                },
            )
            self.assertEqual(missing.status_code, 422, missing.text)
        finally:
            client.close()

    def test_initial_admin_bootstrap_assigns_lendery_editing_once(self) -> None:
        with self.engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())

        with patch.dict(
            "os.environ",
            {
                "LIBTOOLS_ADMIN_NAME": "admin",
                "LIBTOOLS_ADMIN_PASSWORD": "bootstrap-password",
            },
        ):
            with self.sessions() as db:
                initialize_platform_accounts(db)
                admin = db.scalar(
                    select(LibtoolsUser).where(LibtoolsUser.username == "admin")
                )
                assigned_tools = list(
                    db.scalars(
                        select(ToolAccess.tool_key)
                        .where(ToolAccess.user_id == admin.id)
                        .order_by(ToolAccess.tool_key)
                    )
                )

        self.assertEqual(
            assigned_tools,
            ["lendery_manage"],
        )

    def test_lendery_view_is_default_and_edit_access_can_be_toggled(self) -> None:
        created = self.admin.post(
            "/api/admin/users",
            json={
                "name": "Inventory Viewer",
                "username": "Inventory Viewer",
                "password": "viewer-password",
                "confirm_password": "viewer-password",
                "tools": [],
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["tools"], ["bookclub", "storytime"])
        client = TestClient(app)
        try:
            self.assertEqual(
                client.post(
                    "/auth/login",
                    json={
                        "username": "Inventory Viewer",
                        "password": "viewer-password",
                    },
                ).status_code,
                200,
            )
            self.assertEqual(client.get("/lendery/items").status_code, 200)
            self.assertEqual(client.get("/auth/me").status_code, 200)
            self.assertEqual(
                client.post(
                    "/lendery/items",
                    json={"name": "Projector", "barcode": "P-1"},
                ).status_code,
                403,
            )

            enabled = self.admin.patch(
                f"/api/admin/users/{created.json()['id']}",
                json={"tools": ["lendery_manage"]},
            )
            self.assertEqual(enabled.status_code, 200, enabled.text)
            self.assertEqual(
                enabled.json()["tools"],
                ["bookclub", "lendery_manage", "storytime"],
            )
            self.assertEqual(
                client.post(
                    "/lendery/items",
                    json={"name": "Projector", "barcode": "P-2"},
                ).status_code,
                201,
            )

            disabled = self.admin.patch(
                f"/api/admin/users/{created.json()['id']}",
                json={"tools": []},
            )
            self.assertEqual(disabled.status_code, 200, disabled.text)
            self.assertEqual(client.get("/lendery/items").status_code, 200)
            self.assertEqual(
                client.post(
                    "/lendery/items",
                    json={"name": "Projector", "barcode": "P-3"},
                ).status_code,
                403,
            )
        finally:
            client.close()

    def test_updating_a_user_with_unchanged_tools_does_not_error(self) -> None:
        # The admin-accounts page always resends the current tool selection
        # alongside name/role edits, even when it hasn't changed - saving
        # must be idempotent rather than erroring on the second save.
        me = self.admin.get("/auth/me")
        user_id = me.json()["id"]

        first = self.admin.patch(
            f"/api/admin/users/{user_id}",
            json={"name": "Renamed Admin", "role": "admin", "tools": ["lendery_manage"]},
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["name"], "Renamed Admin")
        self.assertIn("lendery_manage", first.json()["tools"])

        second = self.admin.patch(
            f"/api/admin/users/{user_id}",
            json={"name": "Renamed Admin", "role": "admin", "tools": ["lendery_manage"]},
        )
        self.assertEqual(second.status_code, 200, second.text)
        self.assertIn("lendery_manage", second.json()["tools"])

    def test_dashboard_summary_combines_live_workspace_data(self) -> None:
        meeting_date = date.today() + timedelta(days=5)
        with self.sessions() as db:
            admin = db.scalar(
                select(LibtoolsUser).where(LibtoolsUser.username == "admin")
            )
            unavailable = LenderyItem(
                name="Unavailable projector",
                barcode="DASH-1",
                availability_status="unavailable",
            )
            missing_part = LenderyItem(
                name="Kit with missing part",
                barcode="DASH-2",
                availability_status="available",
            )
            checked_out = LenderyItem(
                name="Repair queue item",
                barcode="DASH-3",
                availability_status="checked_out",
            )
            removed = LenderyItem(
                name="Removed item",
                barcode="DASH-4",
                lifecycle_status="removed",
                availability_status="unavailable",
            )
            db.add_all([unavailable, missing_part, checked_out, removed])
            db.flush()
            db.add(
                Component(
                    item_id=missing_part.id,
                    name="Power cable",
                    missing_reported_at=datetime.now(timezone.utc),
                )
            )
            db.add(
                MaintenanceCase(
                    item_id=checked_out.id,
                    title="Replace cracked case",
                    status="open",
                    opened_by_user_id=admin.id,
                    opened_by_name=admin.username,
                )
            )
            club = BookClub(name="Tuesday Readers", slug="tuesday-readers")
            db.add(club)
            db.flush()
            book = BookClubBook(
                club_id=club.id,
                title="Kindred",
                author="Octavia E. Butler",
            )
            db.add(book)
            db.flush()
            db.add(
                BookClubMeeting(
                    club_id=club.id,
                    meeting_date=meeting_date,
                    meeting_time="7:00 PM",
                    location="Meeting Room A",
                    book_id=book.id,
                    book_title=book.title,
                    book_author=book.author,
                )
            )
            db.commit()

        response = self.admin.get("/auth/dashboard-summary")
        self.assertEqual(response.status_code, 200, response.text)
        summary = response.json()
        self.assertEqual(summary["lendery"]["total_items"], 3)
        self.assertEqual(summary["lendery"]["checked_out_items"], 1)
        self.assertEqual(summary["lendery"]["available_items"], 1)
        self.assertEqual(summary["lendery"]["attention_count"], 3)
        self.assertEqual(summary["bookclub"]["club_count"], 1)
        self.assertEqual(summary["bookclub"]["next_meeting"]["days_until"], 5)
        self.assertEqual(
            summary["bookclub"]["next_meeting"]["book_title"], "Kindred"
        )

    def test_dashboard_summary_hides_editor_attention_from_viewers(self) -> None:
        created = self.admin.post(
            "/api/admin/users",
            json={
                "name": "Dashboard Viewer",
                "username": "Dashboard Viewer",
                "password": "viewer-password",
                "confirm_password": "viewer-password",
                "tools": [],
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        viewer = TestClient(app)
        try:
            self.assertEqual(
                viewer.post(
                    "/auth/login",
                    json={
                        "username": "Dashboard Viewer",
                        "password": "viewer-password",
                    },
                ).status_code,
                200,
            )
            response = viewer.get("/auth/dashboard-summary")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIsNone(response.json()["lendery"]["attention_count"])
            self.assertTrue(response.json()["bookclub"]["has_access"])
        finally:
            viewer.close()

    def test_book_club_records_are_isolated_by_account(self) -> None:
        first = self.create_user("First Facilitator")
        second = self.create_user("Second Facilitator")
        clients = [TestClient(app), TestClient(app)]
        slugs = []
        try:
            for client, user in zip(clients, (first, second), strict=True):
                login = client.post(
                    "/auth/login",
                    json={
                        "username": user["username"],
                        "password": "starting-password",
                    },
                )
                self.assertEqual(login.status_code, 200)
                club = client.post(
                    "/bookclub/clubs",
                    json={"name": f"{user['username']} Club"},
                )
                self.assertEqual(club.status_code, 201, club.text)
                slugs.append(club.json()["slug"])
                selected = client.post(
                    f"/bookclub/clubs/{club.json()['id']}/select"
                )
                self.assertEqual(selected.status_code, 200)
                member = client.post(
                    "/bookclub/members",
                    json={
                        "name": "Shared Reader",
                        "email": "reader@example.com",
                        "joined_on": "2026-08-01",
                    },
                )
                self.assertEqual(member.status_code, 201, member.text)

            self.assertEqual(len(clients[0].get("/bookclub/members").json()), 1)
            self.assertEqual(len(clients[1].get("/bookclub/members").json()), 1)
            book = clients[0].post(
                "/bookclub/books",
                json={"title": "Kindred", "author": "Octavia E. Butler"},
            )
            self.assertEqual(book.status_code, 201, book.text)
            meeting = clients[0].post(
                "/bookclub/meetings",
                json={
                    "book_id": book.json()["id"],
                    "meeting_date": "2026-09-10",
                },
            )
            self.assertEqual(meeting.status_code, 201, meeting.text)
            public = clients[0].get(f"/api/public/clubs/{slugs[0]}")
            self.assertEqual(public.status_code, 200, public.text)
            self.assertEqual(
                public.json()["upcoming_meeting"]["book"]["title"], "Kindred"
            )
            forbidden = clients[0].post(
                f"/bookclub/clubs/{clients[1].get('/bookclub/clubs').json()[0]['id']}/select"
            )
            self.assertEqual(forbidden.status_code, 404)
        finally:
            for client in clients:
                client.close()


class LoginThrottleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(cls.engine)
        cls.sessions = sessionmaker(
            bind=cls.engine, autoflush=False, expire_on_commit=False
        )

        def override_get_db():
            db: Session = cls.sessions()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def setUp(self) -> None:
        login_throttle.reset()
        with self.engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
        with self.sessions() as db:
            db.add(
                LibtoolsUser(
                    name="Taylor",
                    username="taylor",
                    password_hash=hash_password("correct-password"),
                    role="user",
                )
            )
            db.commit()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        login_throttle.reset()

    def test_repeated_failed_logins_lock_out_the_account(self) -> None:
        for _ in range(login_throttle.MAX_ATTEMPTS):
            response = self.client.post(
                "/auth/login",
                json={"username": "taylor", "password": "wrong-password"},
            )
            self.assertEqual(response.status_code, 401)

        locked_out = self.client.post(
            "/auth/login",
            json={"username": "taylor", "password": "correct-password"},
        )
        self.assertEqual(locked_out.status_code, 429, locked_out.text)
        self.assertIn("Retry-After", locked_out.headers)

    def test_lockout_is_scoped_per_username(self) -> None:
        for _ in range(login_throttle.MAX_ATTEMPTS):
            self.client.post(
                "/auth/login",
                json={"username": "taylor", "password": "wrong-password"},
            )

        other_user = self.client.post(
            "/auth/login",
            json={"username": "someone-else", "password": "whatever"},
        )
        self.assertEqual(other_user.status_code, 401)

    def test_successful_login_clears_prior_failures(self) -> None:
        for _ in range(login_throttle.MAX_ATTEMPTS - 1):
            self.client.post(
                "/auth/login",
                json={"username": "taylor", "password": "wrong-password"},
            )

        success = self.client.post(
            "/auth/login",
            json={"username": "taylor", "password": "correct-password"},
        )
        self.assertEqual(success.status_code, 200, success.text)

        for _ in range(login_throttle.MAX_ATTEMPTS - 1):
            response = self.client.post(
                "/auth/login",
                json={"username": "taylor", "password": "wrong-password"},
            )
            self.assertEqual(response.status_code, 401)

        still_allowed = self.client.post(
            "/auth/login",
            json={"username": "taylor", "password": "correct-password"},
        )
        self.assertEqual(still_allowed.status_code, 200, still_allowed.text)

    def test_lockout_expires_after_the_window(self) -> None:
        with patch("accounts.login_throttle.time.monotonic") as fake_monotonic:
            fake_monotonic.return_value = 1_000.0
            for _ in range(login_throttle.MAX_ATTEMPTS):
                self.client.post(
                    "/auth/login",
                    json={"username": "taylor", "password": "wrong-password"},
                )
            locked_out = self.client.post(
                "/auth/login",
                json={"username": "taylor", "password": "correct-password"},
            )
            self.assertEqual(locked_out.status_code, 429)

            fake_monotonic.return_value = (
                1_000.0 + login_throttle.LOCKOUT_SECONDS + 1
            )
            unlocked = self.client.post(
                "/auth/login",
                json={"username": "taylor", "password": "correct-password"},
            )
        self.assertEqual(unlocked.status_code, 200, unlocked.text)


if __name__ == "__main__":
    unittest.main()
