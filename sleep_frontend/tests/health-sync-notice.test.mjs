import assert from "node:assert/strict";
import test from "node:test";
import {healthSyncIssue, healthSyncMessage} from "../src/lib/health-sync-notice.ts";

const emptyRead = "접근 가능한 수면 기록이 없어요. 건강앱의 기록과 권한을 확인해 주세요.";
const noChanges = {added_sessions:0, updated_sessions:0, ignored_incomplete:0};

test("the distributed Android bridge's empty read is an informational status", () => {
  assert.deepEqual(healthSyncIssue("android", emptyRead), {
    role:"status", text:"선택한 건강앱 출처에서 읽을 수 있는 수면 기록이 없어요.",
  });
});

test("permission and transport failures still display as alerts", () => {
  for (const message of [
    "Health Connect에서 수면 읽기 권한을 확인해 주세요.",
    "수면 읽기 권한이 꺼졌어요. 연결을 해제한 뒤 다시 연결해 주세요.",
    "달잠 서버가 응답하지 못했어요. 잠시 뒤 다시 시도해 주세요.",
  ]) {
    assert.deepEqual(healthSyncIssue("android", message), {role:"alert", text:message});
  }
  assert.deepEqual(healthSyncIssue("ios", emptyRead), {role:"alert", text:emptyRead});
  assert.equal(healthSyncIssue("android"), null);
});

test("a successful response with no changes does not claim missing permission", () => {
  assert.equal(healthSyncMessage(noChanges), "확인을 마쳤어요. 새로 분석해 저장한 수면 기록은 없어요.");
});

test("the exclusion count does not imply records were saved", () => {
  assert.equal(healthSyncMessage({...noChanges, ignored_incomplete:2}),
    "분석할 수면 단계가 없는 기록 2건은 분석에서 제외했어요.");
  assert.equal(healthSyncMessage({...noChanges, added_sessions:1, ignored_incomplete:1}),
    "새 수면 기록을 가져와 분석했어요. 분석할 수면 단계가 없는 기록 1건은 분석에서 제외했어요.");
  assert.equal(healthSyncMessage({...noChanges, updated_sessions:1}), "새 수면 기록을 가져와 분석했어요.");
});
