import json
import os
import tempfile
import unittest

import app as tender_app


class MemberAccessControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_db_path = tender_app.DB_PATH
        cls.original_secret_key = tender_app.app.secret_key
        cls.original_codes = {
            env_name: os.environ.get(env_name)
            for env_name in tender_app.AUTH_CODE_ENV.values()
        }
        cls.access_codes = {
            "Developer": "test-developer-access-code-" + ("x" * 24),
            "Kamal Sir": "test-kamal-access-code-" + ("y" * 24),
            "Uday Sir": "test-uday-access-code-" + ("z" * 24),
        }
        for role, env_name in tender_app.AUTH_CODE_ENV.items():
            os.environ[env_name] = cls.access_codes[role]
        tender_app._configure_session_secret()
        cls.configured_secret_key = tender_app.app.secret_key

        cls.temp_dir = tempfile.TemporaryDirectory()
        tender_app.DB_PATH = os.path.join(cls.temp_dir.name, "test_tenders.db")
        tender_app.init_db()
        tender_app.app.config["TESTING"] = True

    @classmethod
    def tearDownClass(cls):
        tender_app.DB_PATH = cls.original_db_path
        tender_app.app.secret_key = cls.original_secret_key
        for env_name, value in cls.original_codes.items():
            if value is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = value
        cls.temp_dir.cleanup()

    def setUp(self):
        conn = tender_app.get_db()
        conn.execute("DELETE FROM pending_sync")
        conn.commit()
        conn.close()
        self.client = tender_app.app.test_client()

    def login(self, client, role):
        return client.post(
            "/api/auth/login",
            json={"access_code": self.access_codes[role]},
        )

    def test_pages_and_decision_apis_require_member_session(self):
        gate = self.client.get("/bid?tender=IND2708")
        self.assertIn(b"Checking saved access", gate.data)
        self.assertIn(b'id="login-form" style="display:none"', gate.data)
        self.assertIn(b"Enter your private access code", gate.data)
        self.assertIn(b"pageshow", gate.data)
        self.assertEqual(gate.headers["Cache-Control"], "no-store")
        self.assertIn(b"Member access code", self.client.get("/dontbid").data)
        self.assertEqual(
            self.client.get("/api/auth/status").get_json(),
            {"authenticated": False, "role": None},
        )
        self.assertEqual(
            self.client.post(
                "/api/submit_allocation",
                json={"tender_no": "IND2708"},
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.post(
                "/api/record_dontbid",
                json={"tender_no": "IND2708"},
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.post("/api/add_manufacturer", json={"name": "Example"}).status_code,
            401,
        )

    def test_each_private_code_authenticates_its_exact_member_role(self):
        for role in tender_app.AUTHORIZED_ROLES:
            client = tender_app.app.test_client()
            response = self.login(client, role)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["role"], role)
            self.assertEqual(
                client.get("/api/auth/status").get_json(),
                {"authenticated": True, "role": role},
            )
            page = client.get("/bid?tender=IND2708")
            self.assertEqual(page.status_code, 200)
            self.assertIn(role.encode(), page.data)
            self.assertIn(b"Fill blank manufacturer for selected items", page.data)
            self.assertIn(b"applyManufacturerToSelectedBlanks", page.data)
            self.assertIn(b"selected items already have manufacturers", page.data.lower())
            self.assertIn(b"Change an item individually", page.data)
            self.assertIn(b"manufacturer for every selected item", page.data)
            self.assertNotIn(b"if (sel && sel !== s)", page.data)

        cookie = response.headers.get("Set-Cookie", "")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertIn("Expires=", cookie)
        self.assertEqual(
            tender_app.app.permanent_session_lifetime.total_seconds(),
            60 * 60 * 24 * 365 * 10,
        )

    def test_invalid_code_cannot_access_or_spoof_decision_name(self):
        denied = self.client.post(
            "/api/auth/login",
            json={"access_code": "not-a-valid-member-code-123456"},
        )
        self.assertEqual(denied.status_code, 401)
        self.assertEqual(self.client.post(
            "/api/submit_allocation",
            json={"tender_no": "IND2708"},
        ).status_code, 401)

        self.login(self.client, "Kamal Sir")
        saved = self.client.post(
            "/api/submit_allocation",
            json={
                "tender_no": "IND2708",
                "approved_by": "Developer",
                "items": [],
            },
        )
        self.assertEqual(saved.status_code, 200)
        conn = tender_app.get_db()
        payload = json.loads(
            conn.execute("SELECT data_json FROM pending_sync").fetchone()["data_json"]
        )
        conn.close()
        self.assertEqual(payload["approved_by"], "Kamal Sir")

    def test_missing_codes_fail_closed_with_configuration_error(self):
        previous = {
            env_name: os.environ.pop(env_name, None)
            for env_name in tender_app.AUTH_CODE_ENV.values()
        }
        try:
            response = tender_app.app.test_client().post(
                "/api/auth/login",
                json={"access_code": self.access_codes["Developer"]},
            )
            self.assertEqual(response.status_code, 503)
            self.assertIn("not configured", response.get_json()["message"])
        finally:
            for env_name, value in previous.items():
                if value is not None:
                    os.environ[env_name] = value

    def test_scanner_sync_endpoints_remain_available_without_member_session(self):
        self.assertEqual(self.client.get("/api/pending_actions").status_code, 200)
        self.assertEqual(
            self.client.post(
                "/api/register_tender",
                json={
                    "tender_no": "IND9999",
                    "tender_name": "Test Tender",
                    "items": [],
                },
            ).status_code,
            200,
        )

    def test_session_signing_key_is_stable_from_render_environment_codes(self):
        tender_app._configure_session_secret()
        self.assertEqual(tender_app.app.secret_key, self.configured_secret_key)


if __name__ == "__main__":
    unittest.main()
