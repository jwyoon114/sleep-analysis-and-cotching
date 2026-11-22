import assert from "node:assert/strict";
import test from "node:test";
import {coachingSections} from "../src/lib/coaching-sections.ts";

test("legacy pattern sections disappear without empty cards", () => {
  const body = "수면 패턴\n비교 내용\n\n선택 기록\n밤 기록\n\n실천 제안\n다음 행동\n\n데이터 한계\n";
  assert.deepEqual(coachingSections(body), [
    {title: "선택 기록", text: "밤 기록"},
    {title: "실천 제안", text: "다음 행동"},
  ]);
});

test("saved direct speech and limited rough emphasis survive rendering verbatim", () => {
  const selected="직접 입력한 추정 수면 시간은 6시간 30분이야.";
  const action="젠장, 우선순위를 정해.\n1. 다음 이틀의 실제 시작 시각을 적어.\n실행 방법 · 혼자 보는 체크 메모를 선택해.";
  const limit="실제로 잠든 시간이나 수면 단계는 확인할 수 없어.";
  assert.deepEqual(coachingSections(`선택 기록\n${selected}\n\n실천 제안\n${action}\n\n데이터 한계\n${limit}`),[
    {title:"선택 기록",text:selected},{title:"실천 제안",text:action},{title:"데이터 한계",text:limit},
  ]);
});
