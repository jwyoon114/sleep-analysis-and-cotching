import assert from "node:assert/strict";
import test from "node:test";
import {buildTimeline, segmentAt} from "../src/lib/timeline.ts";

const start = "2026-11-11T23:30:00+09:00";
const end = "2026-11-12T01:00:00+09:00";
const timestamp = Date.parse;
const segment = (stage, start, end) => ({stage, start, end});

test("clips and sorts measured stages while preserving a gap across midnight", () => {
  const timeline = buildTimeline({start, end, segments:[
    segment("rem", "2026-11-12T00:15:00+09:00", "2026-11-12T02:00:00+09:00"),
    segment("core", "2026-11-11T23:00:00+09:00", "2026-11-11T23:55:00+09:00"),
    segment("wake", "invalid", end),
  ]});
  const gapStart = timestamp("2026-11-11T23:55:00+09:00");
  const gapEnd = timestamp("2026-11-12T00:15:00+09:00");
  assert.equal(timeline.duration, 90 * 60_000);
  assert.deepEqual(timeline.segments.map(({stage, from, to}) => [stage, from, to]), [
    ["core", timestamp(start), gapStart],
    ["rem", gapEnd, timestamp(end)],
  ]);
  assert.deepEqual(timeline.gaps, [{from:gapStart, to:gapEnd}]);
  assert.equal(segmentAt(timeline.segments, gapStart), -1);
  assert.equal(segmentAt(timeline.segments, gapEnd), 1);
  assert.equal(segmentAt(timeline.segments, timestamp(end)), -1);
});

test("does not fill missing stages or turn invalid bounds into a timeline", () => {
  const timeline = buildTimeline({start, end, segments:[]});
  assert.deepEqual(timeline.segments, []);
  assert.deepEqual(timeline.gaps, [{from:timestamp(start), to:timestamp(end)}]);
  assert.equal(segmentAt(timeline.segments, timestamp(start)), -1);
  assert.equal(buildTimeline({start, end:start, segments:[]}), null);
  assert.equal(buildTimeline({start:"invalid", end, segments:[]}), null);
});
