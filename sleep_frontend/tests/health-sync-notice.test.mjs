import assert from "node:assert/strict";
import test from "node:test";
import {emptyHealthResult, healthIssue, healthSyncNotice} from "../src/lib/health-sync-notice.ts";

const noChanges = {added_sessions:0, updated_sessions:0, ignored_incomplete:0};

test("the Android APK empty-read rejection is informational and offers manual entry", () => {
  const issue = healthIssue("sync", "접근 가능한 수면 기록이 없어요. 건강앱의 기록과 권한을 확인해 주세요.", "android");
  assert.deepEqual(issue, emptyHealthResult("android"));
  assert.equal(issue.role,"status");
  assert.equal(issue.manual,true);
  assert.match(issue.text,/삼성 헬스.*직접 입력/);
});

test("explicit permissions, retrieval errors, and reported server errors stay distinct", () => {
  for (const message of ["수면 읽기 권한을 허용해 주세요.","수면 읽기 권한이 꺼졌어요. 연결을 해제한 뒤 다시 연결해 주세요."]) {
    const notice = healthIssue("sync",message,"android");
    assert.equal(notice.role,"alert");
    assert.match(notice.text,/읽기 권한을 허용/);
  }
  assert.match(healthIssue("read","Unknown native failure","android").text,/조회하지 못했어요/);
  assert.match(healthIssue("sync","달잠 서버에 연결하지 못했어요. 다음에 다시 동기화합니다.","android").text,/전송하거나 저장하지 못했어요/);
  assert.match(healthIssue("sync",'{"code":"database_unavailable","message":"데이터베이스를 사용할 수 없습니다."}',"android").text,/전송하거나 저장하지 못했어요/);
  assert.match(healthIssue("sync","건강앱 연결이 해제되었거나 만료되었습니다. 다시 연결해 주세요.","android").text,/연결을 다시 설정/);
  assert.match(healthIssue("sync","Unknown native failure","android").text,/동기화하지 못했어요/);
});

test("unchanged sync is distinct from excluded and successfully saved records", () => {
  assert.match(healthSyncNotice(noChanges).text,/저장하거나 갱신할 수면 기록이 없어요/);
  for (const saved of [0, 1]) {
    const notice = healthSyncNotice({...noChanges, added_sessions:saved, ignored_incomplete:2});
    assert.match(notice.text,/2건은 분석에서 제외/);
    assert.equal(notice.text.includes("저장했어요"), Boolean(saved));
    assert.equal(notice.manual,!saved);
  }
  assert.match(healthSyncNotice({...noChanges,updated_sessions:1}).text,/연결되어 있고 수면 기록을 저장/);
});
