import assert from "node:assert/strict";
import test from "node:test";
import {homeSummary} from "../src/lib/home-summary.ts";

const record={start:"2026-11-16T23:00:00+09:00",asleep_minutes:451,unrecorded_minutes:0};
test("shows the measured duration and recorded date without asserting sleep quality",()=>{
  const summary=homeSummary(record,false);
  assert.equal(summary.title,"지난 수면은 7시간 31분이었어요");
  assert.match(summary.description,/2026\.11\.16/);
});
test("does not label incomplete observations as total sleep",()=>{
  const summary=homeSummary({...record,unrecorded_minutes:30},false);
  assert.equal(summary.title,"확인된 수면은 7시간 31분이에요");
  assert.match(summary.description,/비어 있는 구간/);
});
test("distinguishes loading, empty and unavailable duration",()=>{
  assert.equal(homeSummary(undefined,true).title,"수면 기록을 확인하고 있어요");
  assert.equal(homeSummary(undefined,false).title,"나의 수면 기록부터 연결해요");
  for(const duration of [NaN,Infinity,-1])assert.equal(homeSummary({...record,asleep_minutes:duration},false).title,"최근 수면 기록을 살펴봐요");
});
test("formats short records and rounding across an hour",()=>{
  assert.equal(homeSummary({...record,asleep_minutes:55},false).title,"지난 수면은 55분이었어요");
  assert.equal(homeSummary({...record,asleep_minutes:59.6},false).title,"지난 수면은 1시간이었어요");
});
