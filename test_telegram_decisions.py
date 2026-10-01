import json
import os
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

import app as tender_app


class _TelegramSuccessResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return b'{"ok": true, "result": {"message_id": 1}}'


class TelegramDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_db_path = tender_app.DB_PATH
        cls.original_secret_key = tender_app.app.secret_key
        cls.original_environment = {
            key: os.environ.get(key)
            for key in (
                *tender_app.AUTH_CODE_ENV.values(),
                "TELEGRAM_BOT_TOKEN",
                "TELEGRAM_CHAT_ID",
            )
        }
        cls.codes = {
            "Developer": "test-developer-access-code-" + ("x" * 24),
            "Kamal Sir": "test-kamal-access-code-" + ("y" * 24),
            "Uday Sir": "test-uday-access-code-" + ("z" * 24),
        }
        for role, env_name in tender_app.AUTH_CODE_ENV.items():
            os.environ[env_name] = cls.codes[role]
        tender_app._configure_session_secret()

        cls.temp_dir = tempfile.TemporaryDirectory()
        tender_app.DB_PATH = os.path.join(cls.temp_dir.name, "telegram_test.db")
        tender_app.init_db()
        tender_app.app.config["TESTING"] = True

    @classmethod
    def tearDownClass(cls):
        tender_app.DB_PATH = cls.original_db_path
        tender_app.app.secret_key = cls.original_secret_key
        for key, value in cls.original_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        cls.temp_dir.cleanup()

    def setUp(self):
        with closing(tender_app.get_db()) as conn:
            conn.execute("DELETE FROM pending_sync")
            conn.execute("DELETE FROM telegram_outbox")
            conn.commit()
        os.environ["TELEGRAM_BOT_TOKEN"] = "test-token-not-real"
        os.environ["TELEGRAM_CHAT_ID"] = "-1001234567890"
        self.client = tender_app.app.test_client()
        login = self.client.post(
            "/api/auth/login",
            json={"access_code": self.codes["Developer"]},
        )
        self.assertEqual(login.status_code, 200)

    def test_allocation_sends_only_decision_and_manufacturer_details(self):
        allocation = {
            "tender_no": "IND2712",
            "tender_name": "Tender IND2712",
            "allocations": [{
                "item_name": "Equipment Scope",
                "quantity": "1",
                "manufacturer": "GMPL",
            }],
            "document_path": "must-not-be-sent.pdf",
        }
        with patch.object(
            tender_app.urllib.request,
            "urlopen",
            return_value=_TelegramSuccessResponse(),
        ) as telegram_send:
            response = self.client.post("/api/submit_allocation", json=allocation)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["telegram_status"], "sent")
        request = telegram_send.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["chat_id"], "-1001234567890")
        self.assertIn("BID APPROVED &amp; MANUFACTURER ALLOCATED", body["text"])
        self.assertIn("IND2712", body["text"])
        self.assertIn("GMPL", body["text"])
        self.assertNotIn("must-not-be-sent.pdf", body["text"])
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertIn("/sendMessage", request.full_url)

        with closing(tender_app.get_db()) as conn:
            outbox = conn.execute(
                "SELECT sent_at FROM telegram_outbox"
            ).fetchone()
            self.assertIsNotNone(outbox["sent_at"])

    def test_rejection_sends_manager_decision_to_telegram(self):
        with patch.object(
            tender_app.urllib.request,
            "urlopen",
            return_value=_TelegramSuccessResponse(),
        ) as telegram_send:
            response = self.client.post(
                "/api/record_dontbid",
                json={"tender_no": "IND2495/CALL-3"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["telegram_status"], "sent")
        body = json.loads(telegram_send.call_args.args[0].data.decode("utf-8"))
        self.assertIn("TENDER DECISION — NOT BID", body["text"])
        self.assertIn("IND2495/CALL-3", body["text"])
        self.assertIn("Developer", body["text"])

    def test_telegram_failure_is_queued_and_retried_on_scanner_poll(self):
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test-token-not-real"}), \
                patch.object(
                    tender_app.urllib.request,
                    "urlopen",
                    side_effect=tender_app.urllib.error.URLError("offline"),
                ):
            response = self.client.post(
                "/api/record_dontbid",
                json={"tender_no": "IND-RETRY"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["telegram_status"], "pending")
        with closing(tender_app.get_db()) as conn:
            conn.execute("UPDATE telegram_outbox SET retry_after = 0")
            conn.commit()

        with patch.object(
            tender_app.urllib.request,
            "urlopen",
            return_value=_TelegramSuccessResponse(),
        ):
            self.assertEqual(self.client.get("/api/pending_actions").status_code, 200)

        with closing(tender_app.get_db()) as conn:
            sent_at = conn.execute(
                "SELECT sent_at FROM telegram_outbox"
            ).fetchone()["sent_at"]
        self.assertIsNotNone(sent_at)

    def test_missing_bot_configuration_is_reported_without_losing_cloud_action(self):
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        with patch.object(tender_app.urllib.request, "urlopen") as telegram_send:
            response = self.client.post(
                "/api/record_dontbid",
                json={"tender_no": "IND-NO-BOT"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["telegram_status"], "not_configured")
        telegram_send.assert_not_called()
        with closing(tender_app.get_db()) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM pending_sync WHERE tender_no = ?",
                    ("IND-NO-BOT",),
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM telegram_outbox").fetchone()[0],
                0,
            )


if __name__ == "__main__":
    unittest.main()
