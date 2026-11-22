import assert from "node:assert/strict";
import test from "node:test";
import {homeSummary} from "../src/lib/home-summary.ts";

const record={start:"2026-11-16T23:00:00+09:00",end:"2026-11-17T07:00:00+09:00",asleep_minutes:451,unrecorded_minutes:0};
test("marks user-entered time as an estimate instead of presenting it as measured sleep",()=>{
  const summary=homeSummary({...record,data_type:"manual",estimated_sleep_minutes:450,asleep_minutes:null},"ready");
  assert.equal(summary.title,"추정 수면은 7시간 30분이에요");
  assert.match(summary.description,/직접 입력/);
});
test("shows the measured duration and recorded local wake date across midnight",()=>{
  const summary=homeSummary(record,"ready");
  assert.equal(summary.title,"최근에 7시간 31분 잤어요");
  assert.equal(summary.description,"2026년 11월 17일 기상 기록");
});
test("does not label incomplete observations as total sleep",()=>{
  const summary=homeSummary({...record,unrecorded_minutes:30},"ready");
  assert.equal(summary.title,"확인된 수면은 7시간 31분이에요");
});
test("distinguishes loading, a failed fetch, a confirmed empty list, and unavailable duration",()=>{
  assert.equal(homeSummary(undefined,"loading").title,"수면 기록을 불러오고 있어요");
  assert.equal(homeSummary(undefined,"error").title,"수면 기록을 불러오지 못했어요");
  assert.equal(homeSummary(undefined,"ready").title,"아직 수면 기록이 없어요");
  for(const duration of [NaN,Infinity,-1])assert.equal(homeSummary({...record,asleep_minutes:duration},"ready").title,"최근 수면 기록을 살펴봐요");
});
test("formats short records and rounding across an hour",()=>{
  assert.equal(homeSummary({...record,asleep_minutes:55},"ready").title,"최근에 55분 잤어요");
  assert.equal(homeSummary({...record,asleep_minutes:59.6},"ready").title,"최근에 1시간 잤어요");
});
