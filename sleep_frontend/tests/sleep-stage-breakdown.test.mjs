import assert from "node:assert/strict";
import test from "node:test";
import {sleepStageBreakdown} from "../src/lib/sleep-stage-breakdown.ts";

test("the chart includes wake without adding it to the actual sleep time", () => {
  const record = {
    asleep_minutes:451, awake_minutes:18, recorded_minutes:479, unrecorded_minutes:10,
    stage_minutes:{deep:99, core:239, rem:113, wake:18, unspecified:0},
  };
  const result = sleepStageBreakdown(record);
  assert.equal(result.sleepMinutes, 451);
  assert.equal(result.measuredMinutes, 469);
  assert.equal(result.measuredMinutes, record.recorded_minutes - record.unrecorded_minutes);
  assert.deepEqual(result.stages.map(({stage, minutes, percent}) => [stage, minutes, Math.round(percent)]), [
    ["deep", 99, 21],
    ["core", 239, 51],
    ["rem", 113, 24],
    ["wake", 18, 4],
  ]);
});

test("uses the source sleep duration and keeps unclassified sleep in the ratio", () => {
  const result = sleepStageBreakdown({
    asleep_minutes:85, stage_minutes:{deep:0, core:0, rem:0, wake:15, unspecified:85},
  });
  assert.equal(result.sleepMinutes, 85);
  assert.equal(result.measuredMinutes, 100);
  assert.deepEqual(result.stages.map(({stage, percent}) => [stage, percent]), [["wake",15], ["unspecified",85]]);
});

test("omits empty stages and distinguishes measured zero sleep from unavailable sleep", () => {
  const empty = {deep:0, core:0, rem:0, wake:0, unspecified:0};
  assert.deepEqual(sleepStageBreakdown({asleep_minutes:null, stage_minutes:empty}),
    {sleepMinutes:null, measuredMinutes:0, stages:[]});
  assert.deepEqual(sleepStageBreakdown({asleep_minutes:0, stage_minutes:{...empty, wake:18}}),
    {sleepMinutes:0, measuredMinutes:18, stages:[{stage:"wake", minutes:18, percent:100}]});
});
