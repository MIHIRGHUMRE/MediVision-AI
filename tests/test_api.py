import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings


class ApiTests(unittest.TestCase):
    def test_production_rejects_the_development_api_key(self):
        with self.assertRaisesRegex(ValueError, "Production requires a unique API_KEY"):
            create_app(
                Settings(
                    app_env="production",
                    database_url="sqlite:///./unused.db",
                    api_key="development-only-change-me",
                    max_upload_bytes=1024,
                    upload_file_limit=1,
                )
            )

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_file = (Path(self.temp_dir.name) / "cases.db").as_posix()
        self.app = create_app(
            Settings(
                app_env="test",
                database_url=f"sqlite:///{database_file}",
                api_key="test-key",
                max_upload_bytes=1024,
                upload_file_limit=2,
            )
        )
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.headers = {"Authorization": "Bearer test-key"}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.app.state.db_engine.dispose()
        self.temp_dir.cleanup()

    def create_case(self):
        return self.client.post(
            "/api/cases",
            data={"body_region": "brain"},
            files=[("files", ("scan.dcm", b"sample image bytes", "application/octet-stream"))],
            headers=self.headers,
        )

    def test_health_and_database_readiness(self):
        self.assertEqual(self.client.get("/api/health").json()["status"], "ok")
        self.assertEqual(
            self.client.get("/api/ready").json(),
            {"status": "ready"},
        )
        self.assertEqual(
            self.client.get("/api/ready").headers["x-content-type-options"], "nosniff"
        )
        schema = self.client.get("/openapi.json").json()
        self.assertEqual(
            schema["paths"]["/api/cases"]["get"]["security"],
            [{"BearerAuth": []}],
        )

    def test_data_endpoints_require_the_bearer_key(self):
        response = self.client.get("/api/cases")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            self.client.get("/api/cases", headers=self.headers).status_code, 200
        )

    def test_upload_draft_review_and_persistence(self):
        created = self.create_case()
        self.assertEqual(created.status_code, 200, created.text)
        case = created.json()
        self.assertTrue(case["created_at"].endswith("+00:00"))
        self.assertEqual(case["images"], [{"format": "dcm", "bytes": 18}])
        self.assertNotIn("filename", case["images"][0])

        draft = self.client.post(
            f"/api/cases/{case['id']}/draft",
            json={
                "indication": "Demo",
                "findings": "Manually entered finding.",
                "impression": "Manual review required.",
            },
            headers=self.headers,
        )
        self.assertEqual(draft.status_code, 200, draft.text)
        self.assertEqual(draft.json()["report"]["status"], "pending_review")

        signed = self.client.post(
            f"/api/cases/{case['id']}/review",
            json={"action": "sign", "reviewer": "Demo reviewer"},
            headers=self.headers,
        )
        self.assertEqual(signed.status_code, 200, signed.text)
        self.assertEqual(signed.json()["report"]["status"], "signed")

        fetched = self.client.get(
            f"/api/cases/{case['id']}", headers=self.headers
        )
        self.assertEqual(fetched.json()["report"]["status"], "signed")
        self.assertEqual(fetched.json()["version"], 3)

    def test_upload_validation_and_size_limit(self):
        unsupported = self.client.post(
            "/api/cases",
            data={"body_region": "brain"},
            files=[("files", ("report.pdf", b"data", "application/pdf"))],
            headers=self.headers,
        )
        self.assertEqual(unsupported.status_code, 422)

        too_large = self.client.post(
            "/api/cases",
            data={"body_region": "brain"},
            files=[("files", ("scan.dcm", b"x" * 1025, "application/octet-stream"))],
            headers=self.headers,
        )
        self.assertEqual(too_large.status_code, 413)

    def test_review_request_rejects_unrecognized_action(self):
        created = self.create_case().json()
        self.client.post(
            f"/api/cases/{created['id']}/draft",
            json={"findings": "Finding", "impression": "Impression"},
            headers=self.headers,
        )
        response = self.client.post(
            f"/api/cases/{created['id']}/review",
            json={"action": "auto-diagnose", "reviewer": "Reviewer"},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
