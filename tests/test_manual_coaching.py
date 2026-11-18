"""Synthetic account data, isolated DBs and mocked Responses API only."""

import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import httpx
from openai import APIConnectionError, APIResponseValidationError, APIStatusError, APITimeoutError, AuthenticationError, OpenAI, RateLimitError

import coaching_service
import manual_coaching
from coaching_expression import expression_snapshot
from test_manual_sleep import ManualSleepFixture


def response(suggestions=None, questions=None, **kwargs):
    body = {"suggestions": suggestions if suggestions is not None else [
        {"text": "반복하기 쉬운 취침 시각을 정하고 잠자리에 들 준비를 미리 해 보세요.", "basis": "timing"},
    ], "questions": questions or []}
    return SimpleNamespace(status="completed", model="synthetic-model", output_text=json.dumps(body, ensure_ascii=False), **kwargs)


class ManualCoachingTests(ManualSleepFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.enterContext(patch.dict(os.environ, {"COACHING_ENGINE": "openai", "COACHING_MAX_INPUT_BYTES": "64000"}))
        self.settings = self.enterContext(patch.object(coaching_service, "settings", return_value=("synthetic-key", "synthetic-model")))
        self.sdk = self.enterContext(patch("openai.OpenAI"))
        self.create = self.sdk.return_value.__enter__.return_value.responses.create
        self.create.return_value = response()

    def coach(self, record_id=None, **lifestyle):
        if record_id is None:
            record_id = self.manual().raise_for_status().json()["record"]["analysis_id"]
        return self.client.post("/coach", headers=self.owner, json={"analysis_id": record_id, **lifestyle})

    def inputs(self):
        return json.loads(self.create.call_args.kwargs["input"])

    def test_single_record_calls_existing_provider_and_saves_source(self):
        result = self.coach().raise_for_status().json()
        self.assertEqual(result["context"]["engine"], "manual-openai")
        self.assertEqual(result["context"]["record_count"], 1)
        self.assertIn("추정 수면 시간은 8시간", result["coaching"])
        self.assertIn("비교할 이전 기록이 없어요", result["coaching"])
        self.assertIn("반복하기 쉬운 취침 시각", result["coaching"])
        call = self.create.call_args.kwargs
        self.assertEqual(call["model"], "synthetic-model")
        self.assertFalse(call["store"])
        self.assertTrue(call["text"]["format"]["strict"])
        self.sdk.assert_called_once_with(api_key="synthetic-key", timeout=45, max_retries=0)
        payload = self.inputs()
        self.assertEqual(payload, result["context"]["input_summary"])
        self.assertEqual(payload["lifestyle"], {})
        self.assertIsNone(payload["expression"]["mbti"])
        self.assertFalse(payload["expression"]["allow_profanity"])
        serialized = json.dumps(payload)
        for field in ("analysis_id", "subject", "account_id", "segments", "vitals", "stage_minutes", "asleep_minutes", "character"):
            self.assertNotIn(field, serialized)

    def test_history_comparison_midnight_and_explicit_lifestyle(self):
        for start, end in [("2024-11-12T23:50", "2024-11-13T07:00"), ("2024-11-14T00:10", "2024-11-14T07:10")]:
            self.manual(start, end).raise_for_status()
        self.create.return_value = response([
            {"text": "최근 입력 시각과 비교하며 반복할 수 있는 시간을 골라 보세요.", "basis": "history"},
            {"text": "카페인을 섭취한 시각도 함께 적어 보세요.", "basis": "caffeine"},
        ], ["휴일에도 비슷한 시각에 일어날 수 있나요?"])
        result = self.coach(caffeine="있음", regularity="자주 달라짐").raise_for_status().json()
        data = self.inputs()
        self.assertEqual(data["observations"]["previous_manual_count"], 2)
        self.assertEqual(data["observations"]["previous_manual_average_minutes"], 425)
        self.assertEqual(data["observations"]["manual_start_spread_minutes"], 70)
        self.assertEqual(data["observations"]["manual_end_spread_minutes"], 10)
        self.assertEqual(data["observations"]["regularity_sample_days"], 3)
        self.assertEqual(data["lifestyle"], {"caffeine": "있음", "regularity": "자주 달라짐"})
        self.assertIn("차이는 +55분", result["coaching"])
        self.assertIn("선택 확인 질문", result["coaching"])

    def test_real_sdk_serialization_uses_only_a_local_mock_transport(self):
        requests = []
        def handle(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={
                "id": "resp_synthetic", "object": "response", "created_at": 0,
                "status": "completed", "model": "synthetic-model",
                "output": [{"id": "msg_synthetic", "type": "message", "role": "assistant", "status": "completed",
                            "content": [{"type": "output_text", "text": response().output_text, "annotations": []}]}],
            })
        def client(**kwargs):
            return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handle)))
        self.sdk.side_effect = client
        result = self.coach().raise_for_status().json()
        self.assertEqual(result["context"]["engine"], "manual-openai")
        self.assertEqual(len(requests), 1)
        self.assertFalse(requests[0]["store"])
        self.assertEqual(requests[0]["text"]["format"]["type"], "json_schema")

    def test_mixed_history_keeps_wearable_metrics_out_and_deduplicates_intervals(self):
        earlier = self.manual("2024-11-13T23:00", "2024-11-14T07:00").json()["record"]
        self.upload("2024-11-13T23:15:00+09:00", "2024-11-14T07:10:00+09:00").raise_for_status()
        self.manual("2024-11-14T23:00", "2024-11-15T06:00").raise_for_status()
        result = self.coach().raise_for_status().json()
        data = self.inputs()
        self.assertEqual(result["context"]["record_count"], 3)
        self.assertNotIn(earlier["analysis_id"], result["context"]["record_ids"])
        measured = next(row for row in data["previous_records"] if row["source"] == "wearable")
        self.assertEqual(set(measured), {"source", "start", "end", "timezone"})
        self.assertEqual(data["observations"]["previous_manual_average_minutes"], 420)
        with patch.dict(os.environ, {"COACHING_ENGINE": "rules"}):
            wearable_id, = self.upload("2024-11-17T23:00:00+09:00", "2024-11-18T07:00:00+09:00").json()["analysis_ids"]
            automatic = self.coach(wearable_id).raise_for_status().json()
        self.assertEqual(automatic["context"]["engine"], "rules")
        self.assertNotIn(earlier["analysis_id"], automatic["context"]["record_ids"])

    def test_cross_account_missing_future_and_deleted_records_are_not_referenced(self):
        self.manual("2024-11-14T23:00", "2024-11-15T07:00", headers=self.other).raise_for_status()
        deleted = self.manual("2024-11-12T23:00", "2024-11-13T07:00").json()["record"]["analysis_id"]
        self.client.delete(f"/watch/sessions/{deleted}", headers=self.owner).raise_for_status()
        self.manual("2024-11-17T23:00", "2024-11-18T07:00").raise_for_status()
        old = self.manual("2024-10-01T23:00", "2024-10-02T07:00").json()["record"]["analysis_id"]
        record = self.manual().json()["record"]["analysis_id"]
        self.assertEqual(self.coach(record).json()["context"]["record_ids"], [record])
        self.assertEqual(self.inputs()["previous_records"], [])
        self.assertEqual(self.coach("missing").status_code, 404)
        self.assertEqual(self.client.post("/coach", headers=self.other, json={"analysis_id": record}).status_code, 404)
        self.create.assert_called_once()
        self.assertEqual(self.coach(old).json()["context"]["record_count"], 1)

    def test_known_provider_errors_are_labeled_rules_without_leaking_provider_text(self):
        request = httpx.Request("POST", "https://api.openai.com/v1/responses")
        def status_error(cls, status):
            return cls("synthetic-sensitive-provider-message", response=httpx.Response(status, request=request), body={})
        cases = [
            (APITimeoutError(request=request), "timeout"),
            (APIConnectionError(request=request), "connection"),
            (status_error(AuthenticationError, 401), "authentication"),
            (status_error(APIStatusError, 403), "authentication"),
            (status_error(RateLimitError, 429), "rate_limit"),
            (status_error(APIStatusError, 500), "provider_error"),
            (APIResponseValidationError(response=httpx.Response(200, request=request), body={}), "invalid_response"),
        ]
        for error, reason in cases:
            with self.subTest(reason=reason):
                self.create.side_effect = error
                result = self.coach().raise_for_status().json()
                self.assertEqual(result["context"]["engine"], "manual-rules")
                self.assertEqual(result["context"]["fallback_reason"], reason)
                self.assertNotIn("synthetic-sensitive", json.dumps(result))
                self.assertIn("추정 수면 시간", result["coaching"])
        self.assertEqual(self.create.call_count, len(cases))

    def test_malformed_unsupported_and_unprovided_claims_fall_back(self):
        invalid = [
            SimpleNamespace(status="incomplete", output_text=""),
            SimpleNamespace(status="completed", output_text=None),
            SimpleNamespace(status="completed", output_text="not JSON"),
            response([{"text": "깊은 수면이 충분하니 계속 유지하세요.", "basis": "timing"}]),
            response([{"text": "내일은 23시에 잠드세요.", "basis": "timing"}]),
            response([{"text": "카페인을 줄여 보세요.", "basis": "caffeine"}]),
            response([{"text": "이전 기록과 비교해 보세요.", "basis": "history"}]),
            response([{"text": ["unexpected"], "basis": "timing"}]),
            response([], []),
        ]
        for item in invalid:
            with self.subTest(response=item):
                self.create.return_value = item
                result = self.coach().raise_for_status().json()
                self.assertEqual(result["context"]["fallback_reason"], "invalid_response")
                self.assertNotRegex(result["coaching"], r"깊은 수면|23시에|카페인")

    def test_missing_configuration_or_large_input_does_not_call_provider(self):
        with patch.object(coaching_service, "settings", side_effect=ValueError("synthetic missing key")):
            self.assertEqual(self.coach().json()["context"]["fallback_reason"], "configuration")
        with patch.dict(os.environ, {"COACHING_MAX_INPUT_BYTES": "1"}):
            self.assertEqual(self.coach().json()["context"]["fallback_reason"], "input_limit")
        self.sdk.assert_not_called()

    def test_rules_mode_does_not_lookup_keys_and_has_six_distinct_wordings(self):
        record_id = self.manual().json()["record"]["analysis_id"]
        texts = []
        with patch.dict(os.environ, {"COACHING_ENGINE": "rules"}):
            for speech in ("polite", "casual"):
                for intensity in ("gentle", "firm", "direct"):
                    self.client.request("PATCH" if texts else "POST", "/auth/personalization", headers=self.owner, json={
                        "mbti": None, "speech": speech, "intensity": intensity,
                        "allow_profanity": False, "character": "cat",
                    }).raise_for_status()
                    result = self.coach(record_id).raise_for_status().json()
                    texts.append(result["coaching"])
                    self.assertEqual(result["context"]["engine"], "manual-rules")
                    self.assertNotIn("fallback_reason", result["context"])
        self.assertEqual(len(set(texts)), 6)
        self.settings.assert_not_called()
        self.sdk.assert_not_called()

    def test_current_expression_is_used_and_old_text_is_never_regenerated(self):
        record_id = self.manual().json()["record"]["analysis_id"]
        first = self.coach(record_id).json()
        profile = {"mbti": "INTP", "speech": "casual", "intensity": "direct", "allow_profanity": False, "character": "dog"}
        self.client.post("/auth/personalization", headers=self.owner, json=profile).raise_for_status()
        self.create.return_value = response([{"text": "내일도 반복할 시간을 정해서 적어 봐.", "basis": "timing"}])
        second = self.coach(record_id).json()
        self.assertEqual(self.inputs()["expression"], expression_snapshot(profile))
        self.assertIn("8시간이야", second["coaching"])
        profile["character"] = "rabbit"
        self.client.patch("/auth/personalization", headers=self.owner, json=profile).raise_for_status()
        third = self.coach(record_id).json()
        self.assertEqual(second["coaching"], third["coaching"])
        self.manual(end="2024-11-16T06:45", record_id=record_id).raise_for_status()
        with patch.dict(os.environ, {"COACHING_ENGINE": "rules"}):
            history = self.client.get(f"/watch/sessions/{record_id}/coaching", headers=self.owner).json()["history"]
        old = next(row for row in history if row["id"] == first["id"])
        self.assertEqual(old["coaching"], first["coaching"])
        self.assertEqual(old["context"], first["context"])
        self.assertEqual(self.create.call_count, 3)

    def test_record_modified_during_generation_does_not_save_stale_advice(self):
        record_id = self.manual().json()["record"]["analysis_id"]
        def change_then_respond(**kwargs):
            self.manual(end="2024-11-16T06:45", record_id=record_id).raise_for_status()
            return response()
        self.create.side_effect = change_then_respond
        failed = self.coach(record_id)
        self.assertEqual(failed.status_code, 503)
        self.assertIn("변경되어", failed.json()["detail"])
        self.assertEqual(self.client.get(f"/watch/sessions/{record_id}/coaching", headers=self.owner).json()["history"], [])

    def test_local_quota_is_not_bypassed_by_fallback_or_double_charged(self):
        self.create.side_effect = APITimeoutError(request=httpx.Request("POST", "https://api.openai.com/v1/responses"))
        with patch.dict(os.environ, {"COACHING_USER_LIMIT_24H": "1"}):
            first = self.coach().raise_for_status().json()
            self.assertEqual(first["context"]["fallback_reason"], "timeout")
            self.assertEqual(self.coach().status_code, 429)
        self.create.assert_called_once()


class ManualInputSummaryTests(unittest.TestCase):
    def test_timezone_dst_and_split_days_do_not_claim_regularity(self):
        selected = {"analysis_id": "selected", "data_type": "manual", "start": "2024-11-05T23:00:00-05:00",
                    "end": "2024-11-06T07:00:00-05:00", "timezone": "America/New_York", "estimated_sleep_minutes": 480}
        for changes in [
            {"start": "2024-11-02T23:00:00-04:00", "end": "2024-11-03T07:00:00-05:00"},
            {"start": "2024-11-03T23:00:00+09:00", "end": "2024-11-04T07:00:00+09:00", "timezone": "Asia/Seoul"},
            {"start": "2024-11-04T01:00:00-05:00", "end": "2024-11-04T02:00:00-05:00"},
        ]:
            prior = dict(selected, analysis_id="prior", **changes)
            other = dict(selected, analysis_id="other", start="2024-11-04T23:00:00-05:00", end="2024-11-05T07:00:00-05:00")
            facts = manual_coaching.observations(selected, [prior, other])
            self.assertNotIn("regularity_sample_days", facts)

    def test_lifestyle_allowlist_drops_arbitrary_text_and_unknown_fields(self):
        self.assertEqual(manual_coaching.clean_lifestyle({"caffeine": "있음", "regularity": "미입력",
                         "character": "cat", "notes": "sensitive free text", "age_group": ["성인"]}), {"caffeine": "있음"})
