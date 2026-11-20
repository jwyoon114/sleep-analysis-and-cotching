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
