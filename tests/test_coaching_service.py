"""Verify coaching entry points with synthetic records and a temporary database."""

from contextlib import closing
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from fastapi import BackgroundTasks, HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import api
import coaching_service
import health_records
import health_sync
from coaching_free import generate_free_coaching


class CoachingServiceTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.db = Path(directory) / "synthetic.sqlite3"
        self.user = {"id": "synthetic-account"}
        self.enterContext(patch.object(health_records, "DB_PATH", self.db))
        self.enterContext(patch.dict(os.environ, {
            "COACHING_USER_LIMIT_24H": "0",
            "COACHING_GLOBAL_LIMIT_24H": "0",
            "COACHING_MAX_INPUT_BYTES": "64000",
            "OPENAI_API_KEY": "synthetic-test-value",
        }))
        os.environ.pop("COACHING_ENGINE", None)
        sdk = self.enterContext(patch("openai.OpenAI", side_effect=AssertionError("OpenAI call blocked")))
        settings = self.enterContext(patch.object(
            coaching_service, "settings", side_effect=AssertionError("Unexpected key lookup")
        ))
        self.addCleanup(sdk.assert_not_called)
        self.addCleanup(settings.assert_not_called)
        with closing(health_records.connect(self.db)) as db, db:
            db.execute("INSERT INTO accounts VALUES(?,?,?,?,?)",
                       (self.user["id"], "synthetic-account", "test", "test", "2025-01-01"))

    def add_session(self, day, asleep, clock="23:50"):
        start = datetime.fromisoformat(f"{day}T{clock}:00+09:00")
        if start.hour < 12:
            start += timedelta(days=1)
        sleep_end = start + timedelta(minutes=asleep)
        end = sleep_end + timedelta(minutes=30)
        record = {
            "analysis_id": f"record-{day}",
            "source": "synthetic wearable",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "timezone": "Asia/Seoul",
            "recorded_minutes": asleep + 30,
            "asleep_minutes": asleep,
            "awake_minutes": 30,
            "unrecorded_minutes": 0,
            "stage_minutes": {"core": asleep, "wake": 30},
            "wake_segment_count": 1,
            "vitals_summary": [],
            "warnings": [],
            "segments": [
                {"stage": "core", "start": start.isoformat(), "end": sleep_end.isoformat()},
                {"stage": "wake", "start": sleep_end.isoformat(), "end": end.isoformat()},
            ],
            "health_sync": {"day": day, "provider": "healthkit", "source_id": "synthetic"},
        }
        with closing(health_records.connect(self.db)) as db, db:
            db.execute("INSERT INTO sessions VALUES(?,?,?,?,?)", (
                record["analysis_id"], self.user["id"], record["start"], record["end"],
                json.dumps(record),
            ))
        return record

    def test_manual_route_defaults_to_rules_and_preserves_old_history(self):
        selected = self.add_session("2025-11-14", 420, "23:55")
        for day, minutes, clock in (
            ("2025-11-01", 350, "23:50"), ("2025-11-04", 360, "23:50"),
            ("2025-11-07", 370, "23:50"), ("2025-11-08", 380, "23:50"),
            ("2025-11-13", 400, "00:10"),
        ):
            self.add_session(day, minutes, clock)
        self.add_session("2025-10-31", 100)
        for day in range(15, 30):
            self.add_session(f"2025-11-{day}", 600)

        sid = selected["analysis_id"]
        old_context = {
            "model": "synthetic legacy model", "prompt_version": "wearable-ko-v1",
            "record_ids": [sid], "record_count": 1, "recent_count": 1,
            "window_start": selected["start"], "window_end": selected["end"],
            "input_summary": {},
            "alarm_schedule": {"bedtime": "23:00", "wake_time": "07:00", "timezone": "Asia/Seoul", "reason": "가상 제안"},
        }
        with closing(health_records.connect(self.db)) as db, db:
            db.execute("INSERT INTO coaching VALUES(?,?,?,?,?,?)",
                       ("legacy-id", self.user["id"], sid, "가상 과거 조언", "{}", "2025-11-15"))
            db.execute("INSERT INTO coaching_context VALUES(?,?)", ("legacy-id", json.dumps(old_context)))
        old = coaching_service.list_coaching(self.user["id"], sid)[0]
        request = api.CoachingRequest(analysis_id=sid, caffeine="있음")
        with self.assertRaises(HTTPException) as error:
            api.coach(request, user={"id": "another-account"})
        self.assertEqual(error.exception.status_code, 404)

        result = api.coach(request, user=self.user)

        self.assertEqual(set(result), {"id", "analysis_id", "coaching", "created_at", "context"})
        self.assertEqual(result["analysis_id"], sid)
        self.assertIn("수면으로 분류한 시간은 7시간", result["coaching"])
        self.assertIn("최근 7일 · 유효 기록 3일 · 기록일 평균 400분", result["coaching"])
        self.assertIn("직전 7일 · 유효 기록 3일 · 기록일 평균 360분", result["coaching"])
        self.assertIn("평균 차이(최근 − 직전) +40분", result["coaching"])
        self.assertIn("기기 기록의 시작 시각 범위 20분", result["coaching"])
        self.assertIn("카페인을 섭취한 시각", result["coaching"])
        self.assertIn("데이터 한계", result["coaching"])
        context = result["context"]
        self.assertEqual(context["engine"], "rules")
        self.assertEqual(context["record_count"], 6)
        self.assertEqual(context["window_end"], selected["end"])
        self.assertEqual(context["input_summary"]["recorded_period"]["comparison"]["average_difference_minutes"], 40)
        self.assertNotIn("alarm_schedule", context)
        history = api.saved_coaching(sid, user=self.user)["history"]
        self.assertEqual(history[0]["id"], result["id"])
        self.assertEqual(history[0]["coaching"], result["coaching"])
        self.assertEqual(history[0]["context"], context)
        self.assertEqual(history[1], old)
        self.assertEqual(health_records.get_owned_session(sid, self.user["id"]), selected)

    def test_sync_background_task_generates_free_coaching_once(self):
        token = health_sync.pair(
            self.user["id"], "healthkit", "synthetic-source", "synthetic", auto_coach=True, path=self.db
        )["sync_token"]
        start = "2025-11-14T23:00:00+09:00"
        end = "2025-11-15T07:00:00+09:00"
        snapshot = {
            "provider": "healthkit", "source_id": "synthetic-source", "timezone": "Asia/Seoul",
            "window_start": "2025-11-13T00:00:00Z", "window_end": "2025-11-16T00:00:00Z",
            "records": [{"id": "synthetic-night", "start": start, "end": end,
                         "segments": [{"start": start, "end": end, "stage": "unspecified"}]}],
        }
        tasks = BackgroundTasks()
        synced = api.sync_health(
            snapshot, tasks, HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        )
        self.assertTrue(synced["advice_queued"])
        self.assertEqual(len(tasks.tasks), 1)
        task = tasks.tasks[0]
        task.func(*task.args, **task.kwargs)
        task.func(*task.args, **task.kwargs)

        saved = coaching_service.list_coaching(self.user["id"], synced["analysis_ids"][0])
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["context"]["engine"], "rules")
        self.assertIn("수면으로 분류한 시간은 8시간", saved[0]["coaching"])

    def test_streamlit_form_uses_the_same_service_and_reads_saved_context(self):
        selected = self.add_session("2025-11-14", 380)
        st = MagicMock()
        st.session_state = {}
        st.sidebar.date_input.side_effect = lambda *args, **kwargs: kwargs["value"]
        st.selectbox.side_effect = lambda label, options, **kwargs: "있음" if "카페인" in label else options[0]
        st.columns.return_value = [MagicMock(), MagicMock(), MagicMock()]
        st.form_submit_button.return_value = True
        st.button.return_value = False
        with patch.dict(sys.modules, {"streamlit": st, "altair": MagicMock(), "pandas": MagicMock()}):
            view = runpy.run_path(str(Path(__file__).resolve().parents[1] / "apple_watch_ui.py"))
            render = view["render_records"]
            with patch.dict(render.__globals__, {
                "render_sleep_pattern": MagicMock(), "render_alarm_settings": MagicMock(),
            }):
                render(self.user)

        st.error.assert_not_called()
        saved = coaching_service.list_coaching(self.user["id"], selected["analysis_id"])[0]
        self.assertEqual(saved["context"]["engine"], "rules")
        self.assertIn("6시간 20분", saved["coaching"])
        self.assertEqual(st.session_state[f"coaching_history_{selected['analysis_id']}"], saved["id"])
        st.json.assert_called_with(saved["context"]["input_summary"], expanded=False)

    def test_rule_error_does_not_fall_back_or_save_a_coaching(self):
        selected = self.add_session("2025-11-14", 420)
        sid = selected["analysis_id"]
        with patch.object(coaching_service, "generate_free_coaching", side_effect=RuntimeError("가상 엔진 오류")):
            with self.assertRaisesRegex(RuntimeError, "가상 엔진 오류"):
                coaching_service.generate(self.user["id"], sid, {})
        self.assertEqual(coaching_service.list_coaching(self.user["id"], sid), [])

    def test_checks_that_referenced_sessions_are_active_before_insert(self):
        selected = self.add_session("2025-11-14", 420)
        earlier = self.add_session("2025-11-13", 380)

        def generate_then_trash(*args):
            result = generate_free_coaching(*args)
            health_records.delete_session(earlier["analysis_id"], self.user["id"], self.db)
            return result

        with patch.object(coaching_service, "generate_free_coaching", side_effect=generate_then_trash):
            with self.assertRaisesRegex(ValueError, "참고한 분석 기록이 삭제"):
                coaching_service.generate(self.user["id"], selected["analysis_id"], {})
        self.assertEqual(coaching_service.list_coaching(self.user["id"], selected["analysis_id"]), [])

    def test_legacy_adapter_requires_explicit_opt_in_and_uses_mock_provider(self):
        selected = self.add_session("2025-11-14", 420)
        with (
            patch.dict(os.environ, {"COACHING_ENGINE": "openai"}),
            patch.object(coaching_service, "settings", return_value=("mock-key", "synthetic-model")),
            patch("openai.OpenAI") as sdk,
        ):
            create = sdk.return_value.__enter__.return_value.responses.create
            create.return_value = SimpleNamespace(
                status="completed", model="synthetic-model",
                output_text='가상 레거시 조언\nALARM_SCHEDULE: {"bedtime":"23:00","wake_time":"07:00","reason":"가상"}',
            )
            result = coaching_service.generate(self.user["id"], selected["analysis_id"], {})
        self.assertEqual(result["coaching"], "가상 레거시 조언")
        self.assertEqual(result["context"]["alarm_schedule"]["bedtime"], "23:00")
        self.assertFalse(create.call_args.kwargs["store"])
        create.assert_called_once()
