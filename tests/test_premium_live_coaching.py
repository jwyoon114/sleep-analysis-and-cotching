"""Real-request control flow with synthetic records and a fully mocked OpenAI SDK."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, OpenAI, RateLimitError

import coaching_service
import health_records
import premium_ai_usage as usage
import premium_live_coaching as live
import premium_service
from test_manual_sleep import ManualSleepFixture
from test_manual_coaching import response


class PremiumLiveTests(ManualSleepFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.folder = Path(self.enterContext(TemporaryDirectory()))
        self.ledger = self.folder / "demo-usage.sqlite3"
        self.enterContext(patch.dict(os.environ, {
            "DALJAM_PREMIUM_DEMO": "1", "DALJAM_PREMIUM_AI_ENABLED": "1",
            "OPENAI_API_KEY": "synthetic-project-key", "OPENAI_PROJECT_ID": "synthetic-dev-project",
            "OPENAI_MODEL": "synthetic-model", "DALJAM_PREMIUM_AI_USAGE_DB": str(self.ledger),
            "DALJAM_PREMIUM_AI_MAX_INPUT_TOKENS": "8192", "DALJAM_PREMIUM_AI_MAX_OUTPUT_TOKENS": "512",
            "COACHING_ENGINE": "openai",
        }))
        self.enterContext(patch.dict(premium_service._grants, {}, clear=True))
        self.settings = self.enterContext(patch.object(coaching_service, "settings", side_effect=AssertionError("Legacy secrets must not be read")))
        self.addCleanup(self.settings.assert_not_called)
        self.sdk = self.enterContext(patch("openai.OpenAI"))
        self.create = self.sdk.return_value.__enter__.return_value.responses.create
        self.create.return_value = response(usage=SimpleNamespace(input_tokens=1000, output_tokens=100, total_tokens=1100))
        self.record_id = self.manual().raise_for_status().json()["record"]["analysis_id"]

    def activate(self, headers=None):
        headers = headers or self.owner
        token = self.client.post("/premium/demo/checkout", headers=headers).raise_for_status().json()["checkout_token"]
        return self.client.post("/premium/demo/activate", headers=headers, json={"checkout_token": token, "acknowledged": True}).raise_for_status().json()

    def generate(self, record_id=None, request_id=None, headers=None, **values):
        return self.client.post("/premium/demo/coach", headers=headers or self.owner, json={
            "analysis_id": record_id or self.record_id, "request_id": request_id or str(uuid4()), **values,
        })

    def test_free_account_and_forged_permissions_cannot_call_ai(self):
        self.assertEqual(self.generate().status_code, 403)
        self.assertEqual(self.generate(paid_entitlement=True).status_code, 422)
        self.assertEqual(self.client.post("/premium/demo/coach", json={"analysis_id": self.record_id, "request_id": str(uuid4())}).status_code, 401)
        normal = self.client.post("/coach", headers=self.owner, json={"analysis_id": self.record_id}).json()
        self.assertEqual(normal["context"]["engine"], "manual-rules")
        self.assertFalse(self.ledger.exists())
        self.sdk.assert_not_called()

    def test_disabled_missing_config_and_production_never_call_provider(self):
        self.activate()
        for name, value in [("DALJAM_PREMIUM_AI_ENABLED", "0"), ("OPENAI_API_KEY", ""),
                            ("OPENAI_PROJECT_ID", ""), ("OPENAI_MODEL", ""),
                            ("DALJAM_PREMIUM_AI_USAGE_DB", ""), ("DALJAM_PREMIUM_AI_MAX_OUTPUT_TOKENS", "0")]:
            with self.subTest(name=name), patch.dict(os.environ, {name: value}):
                result = self.generate().raise_for_status().json()
                self.assertEqual(result["kind"], "sample")
                self.assertEqual(result["label"], live.LABELS["sample"])
                self.assertFalse(self.client.get("/premium", headers=self.owner).json()["live_ai_available"])
        with patch.dict(os.environ, {"DALJAM_ENV": "production"}):
            self.assertEqual(self.generate().status_code, 403)
        self.assertFalse(self.ledger.exists())
        self.sdk.assert_not_called()

    def test_manual_request_records_usage_and_preserves_saved_source(self):
        state = self.activate()
        self.assertTrue(state["live_ai_available"])
        result = self.generate().raise_for_status().json()
        self.assertEqual(result["kind"], "openai")
        self.assertEqual(result["label"], live.LABELS["openai"])
        self.assertIn("추정 수면 시간은 8시간", result["coaching"]["coaching"])
        self.assertEqual(result["coaching"]["context"]["engine"], "manual-openai")
        self.assertEqual(result["usage"]["used"], 1)
        self.assertEqual(result["usage"]["remaining"], 2)
        self.assertEqual(result["usage"]["input_tokens"], 1000)
        self.assertEqual(result["usage"]["output_tokens"], 100)
        self.sdk.assert_called_once_with(api_key="synthetic-project-key", project="synthetic-dev-project",
                                         base_url="https://api.openai.com/v1", timeout=30, max_retries=0)
        call = self.create.call_args.kwargs
        self.assertEqual(call["max_output_tokens"], 512)
        self.assertFalse(call["store"])
        self.assertTrue(call["text"]["format"]["strict"])
        for forbidden in ("analysis_id", "account_id", "stage_minutes", "vitals", "segments", "character", "synthetic-project-key"):
            self.assertNotIn(forbidden, call["input"])
        before = result["coaching"]
        self.manual(end="2024-11-16T06:30", record_id=self.record_id).raise_for_status()
        saved = self.client.get(f"/watch/sessions/{self.record_id}/coaching", headers=self.owner).json()["history"][0]
        self.assertEqual(saved["coaching"], before["coaching"])
        self.assertEqual(saved["context"], before["context"])

    def test_history_personalization_ownership_and_automatic_records(self):
        self.activate()
        self.manual("2024-11-13T23:00", "2024-11-14T07:00").raise_for_status()
        self.manual("2024-11-14T23:30", "2024-11-15T07:00").raise_for_status()
        foreign = self.manual("2024-11-12T23:00", "2024-11-13T06:00", headers=self.other).json()["record"]["analysis_id"]
        self.client.post("/auth/personalization", headers=self.owner, json={
            "mbti": None, "speech": "casual", "intensity": "direct", "allow_profanity": False, "character": "dog",
        }).raise_for_status()
        self.create.return_value = response([{"text": "반복할 취침 시각을 정해서 적어 봐.", "basis": "history"}],
                                           usage=SimpleNamespace(input_tokens=1000, output_tokens=100, total_tokens=1100))
        result = self.generate().json()
        context = result["coaching"]["context"]
        self.assertEqual(context["record_count"], 3)
        self.assertEqual(context["expression"]["speech"], "casual")
        self.assertEqual(context["expression"]["intensity"], "direct")
        self.assertNotIn(foreign, context["record_ids"])
        self.assertEqual(self.generate(foreign).status_code, 404)
        self.assertEqual(self.generate(headers=self.other).status_code, 403)
        automatic_id, = self.upload("2024-11-17T23:00:00+09:00", "2024-11-18T07:00:00+09:00").json()["analysis_ids"]
        automatic = self.generate(automatic_id).raise_for_status().json()
        self.assertEqual(automatic["coaching"]["context"]["engine"], "wearable-openai")
        self.assertIn("측정 구간 길이는 8시간", automatic["coaching"]["coaching"])
        payload = json.loads(self.create.call_args.kwargs["input"])
        self.assertEqual(payload["selected_record"]["source"], "wearable")
        self.assertEqual(payload["selected_record"]["asleep_minutes"], 480)
        self.assertNotIn("stage_minutes", payload["selected_record"])

    def test_real_sdk_uses_only_mock_transport_and_explicit_dev_project(self):
        self.activate()
        observed = []
        def handle(request):
            observed.append(request)
            return httpx.Response(200, json={
                "id": "resp_synthetic", "object": "response", "created_at": 0,
                "status": "completed", "model": "synthetic-model",
                "usage": {"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100},
                "output": [{"id": "msg_synthetic", "type": "message", "role": "assistant", "status": "completed",
                            "content": [{"type": "output_text", "text": response().output_text, "annotations": []}]}],
            })
        def client(**kwargs):
            return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handle)))
        self.sdk.side_effect = client
        with patch.dict(os.environ, {"OPENAI_BASE_URL": "http://untrusted.invalid"}):
            result = self.generate().raise_for_status().json()
        self.assertEqual(result["kind"], "openai")
        self.assertEqual(len(observed), 1)
        self.assertEqual(str(observed[0].url), "https://api.openai.com/v1/responses")
        self.assertEqual(observed[0].headers["OpenAI-Project"], "synthetic-dev-project")
        self.assertEqual(result["usage"]["input_tokens"], 1000)

    def test_provider_errors_and_invalid_response_fall_back_with_safe_labels(self):
        self.activate()
        request = httpx.Request("POST", "https://api.openai.com/v1/responses")
        def status_error(cls, code):
            return cls("sensitive-provider-error", response=httpx.Response(code, request=request), body={})
        errors = [(APITimeoutError(request=request), "timeout"), (APIConnectionError(request=request), "connection"),
                  (status_error(AuthenticationError, 401), "authentication"), (status_error(RateLimitError, 429), "rate_limit"),
                  (status_error(APIStatusError, 500), "provider_error"), (None, "invalid_response")]
        for index, (error, reason) in enumerate(errors):
            with self.subTest(reason=reason), patch.dict(os.environ, {"DALJAM_PREMIUM_AI_USAGE_DB": str(self.folder / f"error-{index}.sqlite3")}):
                self.create.side_effect = error
                self.create.return_value = SimpleNamespace(status="completed", output_text="not JSON", usage=None)
                result = self.generate().raise_for_status().json()
                self.assertEqual(result["kind"], "rules_fallback")
                self.assertEqual(result["label"], live.LABELS["rules_fallback"])
                self.assertEqual(result["coaching"]["context"]["fallback_reason"], reason)
                self.assertEqual(result["usage"]["calls_started"], 1)
                self.assertEqual(result["usage"]["unknown_usage_calls"], 1)
                self.assertNotIn("sensitive-provider-error", json.dumps(result))

    def test_three_call_budget_survives_demo_reset_and_replays_after_limit(self):
        self.activate()
        first_id = str(uuid4())
        first = self.generate(request_id=first_id).json()
        for day in (17, 18):
            record_id = self.manual(f"2024-11-{day}T23:00", f"2024-11-{day+1}T07:00").json()["record"]["analysis_id"]
            self.generate(record_id).raise_for_status()
        fourth = self.manual("2024-11-20T23:00", "2024-11-21T07:00").json()["record"]["analysis_id"]
        self.assertEqual(self.generate(fourth).status_code, 429)
        replay = self.generate(request_id=first_id).raise_for_status().json()
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["coaching"]["id"], first["coaching"]["id"])
        self.client.delete("/premium/demo", headers=self.owner).raise_for_status()
        self.assertEqual(self.activate()["ai_usage"]["remaining"], 0)
        self.assertEqual(self.generate(fourth).status_code, 429)
        self.assertEqual(self.create.call_count, 3)
        self.assertEqual(self.client.post("/coach", headers=self.owner, json={"analysis_id": fourth}).status_code, 200)

    def test_simultaneous_duplicate_requests_call_provider_only_once(self):
        self.activate()
        started, release = Event(), Event()
        original = self.create.return_value
        def wait_for_release(**kwargs):
            started.set()
            if not release.wait(10):
                raise RuntimeError("Synthetic request was not released")
            return original
        self.create.side_effect = wait_for_release
        request_id = str(uuid4())
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.generate, request_id=request_id)
            try:
                self.assertTrue(started.wait(10))
                self.assertEqual(self.generate(request_id=request_id).status_code, 409)
                self.assertEqual(self.generate().status_code, 409)
            finally:
                release.set()
            saved = first.result().raise_for_status().json()
        self.assertEqual(self.generate().json()["coaching"]["id"], saved["coaching"]["id"])
        self.create.assert_called_once()

    def test_response_saved_before_ledger_finish_recovers_without_another_call(self):
        self.activate()
        request_id = str(uuid4())
        with patch.object(usage, "finish", side_effect=usage.UsageUnavailable("synthetic unavailable")):
            self.assertEqual(self.generate(request_id=request_id).status_code, 503)
        result = self.generate(request_id=request_id).raise_for_status().json()
        self.assertTrue(result["replayed"])
        self.assertEqual(result["usage"]["calls_started"], 1)
        self.create.assert_called_once()

    def test_ambiguous_save_failure_never_resends_or_exposes_exception_text(self):
        self.activate()
        request_id = str(uuid4())
        with patch.object(coaching_service, "save_generated", side_effect=RuntimeError("private-error-text")):
            failed = self.generate(request_id=request_id)
        self.assertEqual(failed.status_code, 503)
        self.assertNotIn("private-error-text", failed.text)
        self.assertEqual(self.generate(request_id=request_id).status_code, 409)
        self.assertEqual(self.generate().status_code, 409)
        self.create.assert_called_once()

    def test_input_budget_and_foreign_ledger_fail_closed(self):
        self.activate()
        with patch.dict(os.environ, {"DALJAM_PREMIUM_AI_MAX_INPUT_TOKENS": "2048"}):
            result = self.generate().raise_for_status().json()
            self.assertEqual(result["kind"], "rules_fallback")
            self.assertEqual(result["coaching"]["context"]["fallback_reason"], "input_limit")
            self.assertEqual(result["usage"]["calls_started"], 0)
            self.assertEqual(result["usage"]["remaining"], 3)
        foreign = self.folder / "unrelated.sqlite3"
        with closing(sqlite3.connect(foreign)) as db, db:
            db.execute("CREATE TABLE original(value TEXT)")
            db.execute("INSERT INTO original VALUES('synthetic-preserved')")
        with patch.dict(os.environ, {"DALJAM_PREMIUM_AI_USAGE_DB": str(foreign)}):
            self.assertEqual(self.generate().json()["kind"], "sample")
        with closing(sqlite3.connect(foreign)) as db:
            self.assertEqual(db.execute("SELECT value FROM original").fetchone()[0], "synthetic-preserved")
        self.sdk.assert_not_called()

    def test_request_ids_bind_inputs_and_usage_rows_do_not_store_health_text(self):
        self.activate()
        request_id = str(uuid4())
        result = self.generate(request_id=request_id).json()
        self.assertEqual(self.generate(request_id=request_id, caffeine="있음").status_code, 409)
        account_id = self.client.get("/auth/me", headers=self.owner).json()["user"]["id"]
        with closing(sqlite3.connect(self.ledger)) as db:
            row = str(db.execute("SELECT * FROM requests").fetchall())
            self.assertNotIn(account_id, row)
            self.assertNotIn("2024-11-15", row)
            self.assertNotIn("synthetic-project-key", row)
            self.assertNotIn(result["coaching"]["coaching"], row)
        self.create.assert_called_once()

    def test_parallel_distinct_requests_cannot_exceed_three_reservations(self):
        self.activate()
        records = [self.record_id]
        for day in (17, 18, 20):
            records.append(self.manual(f"2024-11-{day}T23:00", f"2024-11-{day+1}T07:00").json()["record"]["analysis_id"])
        with ThreadPoolExecutor(max_workers=4) as pool:
            codes = list(pool.map(lambda record_id: self.generate(record_id).status_code, records))
        self.assertEqual(sorted(codes), [200, 200, 200, 429])
        self.assertEqual(self.create.call_count, 3)

    def test_account_budgets_are_separate_and_window_uses_server_time(self):
        with patch("premium_ai_usage.time.time", return_value=1000000):
            self.activate()
            ids = [self.record_id]
            for day in (17, 18, 20):
                ids.append(self.manual(f"2024-11-{day}T23:00", f"2024-11-{day+1}T07:00").json()["record"]["analysis_id"])
            for record_id in ids[:3]:
                self.generate(record_id).raise_for_status()
            self.assertEqual(self.generate(ids[3]).status_code, 429)
            self.activate(self.other)
            other_record = self.manual(headers=self.other).json()["record"]["analysis_id"]
            self.assertEqual(self.generate(other_record, headers=self.other).json()["usage"]["remaining"], 2)
        with patch("premium_ai_usage.time.time", return_value=1000000 + usage.WINDOW_SECONDS + 1):
            self.activate()
            self.assertEqual(self.generate(ids[3]).json()["usage"]["remaining"], 2)
        # Count the SDK start time when reservation and actual submission differ.
        anchor = self.folder / "delayed-start.sqlite3"
        with patch("premium_ai_usage.time.time", return_value=1000):
            first, _ = usage.reserve(anchor, "synthetic-clock-account", str(uuid4()), "first", "record", "model", 5000)
            delayed, _ = usage.reserve(anchor, "synthetic-clock-account", str(uuid4()), "delayed", "record", "model", 5000)
        with patch("premium_ai_usage.time.time", return_value=1100):
            usage.mark_sent(anchor, first)
        with patch("premium_ai_usage.time.time", return_value=1000 + usage.WINDOW_SECONDS + 1):
            self.assertEqual(usage.summary(anchor, "synthetic-clock-account")["used"], 1)
            for fingerprint in ("new-first", "new-second"):
                usage.reserve(anchor, "synthetic-clock-account", str(uuid4()), fingerprint, "record", "model", 5000)
            with self.assertRaises(usage.DemoCallLimit):
                usage.mark_sent(anchor, delayed)
        duplicate_file = self.folder / "delayed-duplicate.sqlite3"
        with patch("premium_ai_usage.time.time", return_value=1000):
            old, _ = usage.reserve(duplicate_file, "clock-account", str(uuid4()), "same", "record", "model", 5000)
        with patch("premium_ai_usage.time.time", return_value=1000 + usage.WINDOW_SECONDS + 1):
            usage.reserve(duplicate_file, "clock-account", str(uuid4()), "same", "record", "model", 5000)
            with self.assertRaises(usage.DuplicateRequest):
                usage.mark_sent(duplicate_file, old)
