import assert from "node:assert/strict";
import test from "node:test";
import { renderCoachingBody } from "../src/lib/coaching-body.ts";
import { CHARACTERS, MBTI_TYPES, getCoachingTone } from "../src/lib/coaching-preview.ts";

// Synthetic examples of v1 payloads and their original rule-engine text.
const fixtures = {
  free: {
    coaching: `선택 기록
기기에서 수면으로 분류한 시간은 7시간입니다. 각성으로 분류한 시간은 30분입니다.

수면 패턴
최근 7일 · 유효 기록 3일 · 기록일 평균 400분
직전 7일 · 유효 기록 3일 · 기록일 평균 360분
평균 차이(최근 − 직전) +40분
기기 기록의 시작 시각 범위 20분

실천 제안
카페인을 섭취한 시각을 적고, 며칠 동안의 수면 기록과 함께 살펴보세요.

데이터 한계
선택 기록 · 기기가 추정한 한 건의 기록입니다. 평소 수면 패턴이나 변화의 원인을 판단하기에는 정보가 부족합니다.
평균은 유효한 기록이 있는 날의 기기 추정 수면 시간만 사용합니다.
시작 시각 변동은 기기 기록의 시작 시각 범위입니다.`,
    context: {
      engine: "rules",
      presentation: {
        version: 1,
        observation: {
          id: "device_sleep_estimate",
          asleep: {"valid":true,"minutes":420,"display":"7시간"},
          awake: {"valid":true,"minutes":30,"display":"30분"},
        },
        patterns: {
          recent: {"valid_days":3,"average_asleep_minutes":400,"average_display":"400분"},
          previous: {"valid_days":3,"average_asleep_minutes":360,"average_display":"360분"},
          comparison: {"status":"available","average_difference_minutes":40,"difference_display":"+40분"},
          regularity: {"status":"available","start_spread_minutes":20,"spread_display":"20분"},
        },
        suggestion_id: "track_caffeine_timing",
        limitation_ids: ["single_device_estimate","valid_days_device_estimates","device_start_range"],
      },
    },
  },
  zero: {
    coaching: `선택 기록
기기에서 수면으로 분류한 시간은 7시간입니다. 각성으로 분류한 시간은 30분입니다.

수면 패턴
최근 7일 · 유효 기록 3일 · 기록일 평균 400분
직전 7일 · 유효 기록 3일 · 기록일 평균 400분
평균 차이(최근 − 직전) +0분
기기 기록의 시작 시각 범위 20분

실천 제안
며칠 동안 수면 기록을 모아 날짜별 수면 시간을 비교해 보세요.

데이터 한계
선택 기록 · 기기가 추정한 한 건의 기록입니다. 평소 수면 패턴이나 변화의 원인을 판단하기에는 정보가 부족합니다.
평균은 유효한 기록이 있는 날의 기기 추정 수면 시간만 사용합니다.
시작 시각 변동은 기기 기록의 시작 시각 범위입니다.`,
    context: {
      engine: "rules",
      presentation: {
        version: 1,
        observation: {
          id: "device_sleep_estimate",
          asleep: {"valid":true,"minutes":420,"display":"7시간"},
          awake: {"valid":true,"minutes":30,"display":"30분"},
        },
        patterns: {
          recent: {"valid_days":3,"average_asleep_minutes":400,"average_display":"400분"},
          previous: {"valid_days":3,"average_asleep_minutes":400,"average_display":"400분"},
          comparison: {"status":"available","average_difference_minutes":0,"difference_display":"+0분"},
          regularity: {"status":"available","start_spread_minutes":20,"spread_display":"20분"},
        },
        suggestion_id: "compare_daily_sleep",
        limitation_ids: ["single_device_estimate","valid_days_device_estimates","device_start_range"],
      },
    },
  },
  insufficient: {
    coaching: `선택 기록
기기에서 수면으로 분류한 시간은 약 7시간입니다.

수면 패턴
최근 7일 · 유효 기록 1일 · 기록일 평균 419.5분
직전 7일 · 유효 기록 0일

실천 제안
며칠 동안 취침·기상 시각을 적어 보고, 일정에 맞춰 반복하기 쉬운 시간대를 찾아보세요.

데이터 한계
선택 기록 · 기기가 추정한 한 건의 기록입니다. 평소 수면 패턴이나 변화의 원인을 판단하기에는 정보가 부족합니다. 기록 안에 미기록 구간이 있습니다.
평균은 유효한 기록이 있는 날의 기기 추정 수면 시간만 사용합니다.
두 기간에 각각 유효 기록일이 3일 이상 있어야 평균 차이를 표시합니다.
시작 시각 변동을 계산하려면 최근 유효 기록일이 2일 이상 필요합니다.`,
    context: {
      engine: "rules",
      presentation: {
        version: 1,
        observation: {
          id: "device_sleep_estimate",
          asleep: {"valid":true,"minutes":419.5,"display":"약 7시간"},
          awake: {"valid":false,"minutes":null,"display":null},
        },
        patterns: {
          recent: {"valid_days":1,"average_asleep_minutes":419.5,"average_display":"419.5분"},
          previous: {"valid_days":0,"average_asleep_minutes":null,"average_display":null},
          comparison: {"status":"insufficient_days","average_difference_minutes":null,"difference_display":null},
          regularity: {"status":"insufficient_days","start_spread_minutes":null,"spread_display":null},
        },
        suggestion_id: "track_bed_and_wake_times",
        limitation_ids: ["single_device_estimate","unrecorded_segments","valid_days_device_estimates","insufficient_comparison_days","insufficient_start_days"],
      },
    },
  },
  unavailable: {
    coaching: `선택 기록
이 기록에서 수면 시간을 확인할 수 없습니다.

실천 제안
기기 앱에서 수면 시간이 기록됐는지 확인한 뒤 다시 불러와 보세요.

데이터 한계
선택 기록 · 수면 시간 값이 없거나 유효한 기록 범위를 벗어났습니다.
선택한 기록의 날짜와 시간 구간을 확인해 주세요.`,
    context: {
      engine: "rules",
      presentation: {
        version: 1,
        observation: {
          id: "sleep_duration_unavailable",
          asleep: {"valid":false,"minutes":null,"display":null},
          awake: {"valid":false,"minutes":null,"display":null},
        },
        patterns: {
          recent: null,
          previous: null,
          comparison: {"status":"invalid_reference","average_difference_minutes":null,"difference_display":null},
          regularity: {"status":"invalid_reference","start_spread_minutes":null,"spread_display":null},
        },
        suggestion_id: "check_device_record",
        limitation_ids: ["sleep_duration_unavailable","invalid_reference"],
      },
    },
  },
  notes: {
    coaching: `선택 기록
기기에서 수면으로 분류한 시간은 7시간입니다. 각성으로 분류한 시간은 30분입니다.

수면 패턴
최근 7일 · 유효 기록 3일 · 기록일 평균 400분
직전 7일 · 유효 기록 0일

실천 제안
다음 기록에는 아침에 느낀 휴식 정도를 함께 적어, 기기 기록과 비교해 보세요.

데이터 한계
선택 기록 · 기기가 추정한 한 건의 기록입니다. 평소 수면 패턴이나 변화의 원인을 판단하기에는 정보가 부족합니다.
평균은 유효한 기록이 있는 날의 기기 추정 수면 시간만 사용합니다.
날짜, 시간 구간 또는 수면 시간을 확인할 수 없는 기록은 집계에서 제외했습니다.
기록이 겹치거나 같은 기록 ID의 값이 다른 날은 집계에서 제외했습니다.
두 기간에 각각 유효 기록일이 3일 이상 있어야 평균 차이를 표시합니다.
날짜별 시작 시각을 하나씩 신뢰하기 어려워 시작 시각 변동을 보류했습니다.`,
    context: {
      engine: "rules",
      presentation: {
        version: 1,
        observation: {
          id: "device_sleep_estimate",
          asleep: {"valid":true,"minutes":420,"display":"7시간"},
          awake: {"valid":true,"minutes":30,"display":"30분"},
        },
        patterns: {
          recent: {"valid_days":3,"average_asleep_minutes":400,"average_display":"400분"},
          previous: {"valid_days":0,"average_asleep_minutes":null,"average_display":null},
          comparison: {"status":"insufficient_days","average_difference_minutes":null,"difference_display":null},
          regularity: {"status":"unreliable_start","start_spread_minutes":null,"spread_display":null},
        },
        suggestion_id: "track_morning_rest",
        limitation_ids: ["single_device_estimate","valid_days_device_estimates","unusable_records_excluded","ambiguous_records_excluded","insufficient_comparison_days","unreliable_start"],
      },
    },
  },
};

function render(fixture, mbti) {
  return renderCoachingBody(fixture.coaching, fixture.context, getCoachingTone(mbti));
}

test("all sixteen bodies and 64 style/character combinations preserve facts and action", () => {
  const { free } = fixtures;
  const original = structuredClone(free);
  const bodies = new Set();
  for (const mbti of MBTI_TYPES) {
    const body = render(free, mbti);
    assert.notEqual(body, free.coaching);
    bodies.add(body);
    for (const character of CHARACTERS) {
      const rendered = render(free, mbti);
      assert.equal(rendered, body, character.id);
      for (const display of ["7시간", "30분", "400분", "360분", "+40분", "20분"]) {
        assert.ok(rendered.includes(display), mbti + ": " + display);
      }
      assert.match(rendered, /최근 7일(?:의|을 보면,) 유효 기록은 3일[^\n]*400분/);
      assert.match(rendered, /직전 7일(?:의|을 보면,) 유효 기록은 3일[^\n]*360분/);
      assert.match(rendered, /카페인을 섭취한 시각을 적[\s\S]*그 시각을 며칠 동안의 수면 기록과 함께 살펴/);
      assert.match(rendered, /기기가 추정한 한 건의 기록/);
      assert.match(rendered, /평소 수면 패턴이나 변화의 원인을 판단하기에는 정보가 부족/);
      assert.match(rendered, /유효한 기록이 있는 날의 기기 추정 수면 시간만/);
      assert.match(rendered, /시작 시각 변동은 기기 기록의 시작 시각 범위/);
    }
  }
  assert.equal(bodies.size, 16);
  assert.deepEqual(free, original);
});

test("E and I change period and action sentences beyond the opening", () => {
  for (const type of MBTI_TYPES.filter(type => type.startsWith("E"))) {
    const quieter = "I" + type.slice(1);
    const lively = render(fixtures.free, type);
    const calm = render(fixtures.free, quieter);
    assert.match(lively, /최근 7일을 보면, 유효 기록은 3일/);
    assert.match(calm, /최근 7일의 유효 기록은 3일/);
    const action = text => text.split("\n\n").at(-2).split("\n").slice(1).join("\n");
    for (const fixture of [fixtures.free, fixtures.unavailable]) {
      assert.match(action(render(fixture, type)), /\?/);
      assert.doesNotMatch(action(render(fixture, quieter)), /\?/);
    }
    assert.doesNotMatch(lively, /!/);
  }
});

test("J and P change the actual steps without removing any suggestion conditions", () => {
  const cases = [
    [fixtures.free, "카페인을 섭취한 시각을 적어", "그 시각을 며칠 동안의 수면 기록과 함께 살펴"],
    [fixtures.zero, "며칠 동안 수면 기록을 모아", "날짜별 수면 시간을 비교해"],
    [fixtures.insufficient, "며칠 동안 취침·기상 시각을 적어", "그 기록을 보며 일정에 맞춰 반복하기 쉬운 시간대를 찾아"],
    [fixtures.unavailable, "기기 앱에서 수면 시간이 기록됐는지 확인해", "다시 불러와"],
    [fixtures.notes, "다음 기록에 아침에 느낀 휴식 정도를 함께 적어", "기기 기록과 비교해"],
  ];
  for (const type of MBTI_TYPES.filter(type => type.endsWith("J"))) {
    const flexible = type.slice(0, -1) + "P";
    for (const [fixture, first, next] of cases) {
      const action = mbti => render(fixture, mbti).split("\n\n").at(-2).split("\n").slice(1);
      const plannedLines = action(type);
      const flexibleLines = action(flexible);
      assert.equal(plannedLines.length, 2);
      assert.ok(plannedLines[0].startsWith("먼저 " + first), type);
      assert.ok(plannedLines[1].startsWith("그다음 " + next), type);
      assert.equal(flexibleLines.length, 1);
      assert.ok(flexibleLines[0].includes("편한 방식으로 " + first + " 본 뒤, " + next), flexible);
    }
  }
});

test("S/N comparison order and T/F endings still follow their presets", () => {
  for (const mbti of MBTI_TYPES) {
    const [, period] = render(fixtures.free, mbti).split("\n\n");
    const recent = period.indexOf("400분");
    const previous = period.indexOf("360분");
    const difference = period.indexOf("+40분");
    assert.ok(recent < previous);
    assert.equal(previous < difference, mbti[1] === "S");
    assert.ok(period.includes(mbti[2] === "T" ? "400분입니다." : "400분이에요."));
  }
});

test("zero and negative comparisons keep their signs and are not treated as withheld", () => {
  const zero = render(fixtures.zero, "INFP");
  assert.match(zero, /차이는 \+0분/);
  assert.doesNotMatch(zero, /평균 차이는 표시를 보류/);
  assert.match(zero, /며칠 동안 수면 기록을 모아 본 뒤, 날짜별 수면 시간을 비교/);
  const negative = structuredClone(fixtures.free);
  negative.coaching = negative.coaching.replace("360분", "440분").replace("+40분", "-40분");
  Object.assign(negative.context.presentation.patterns.previous, {
    average_asleep_minutes: 440, average_display: "440분",
  });
  Object.assign(negative.context.presentation.patterns.comparison, {
    average_difference_minutes: -40, difference_display: "-40분",
  });
  assert.match(render(negative, "ISTJ"), /차이는 -40분/);
});

test("insufficient data keeps the server's rounding, missing values, and reasons", () => {
  for (const mbti of MBTI_TYPES) {
    const body = render(fixtures.insufficient, mbti);
    assert.notEqual(body, fixtures.insufficient.coaching);
    assert.match(body, /약 7시간/);
    assert.match(body, /최근 7일(?:의|을 보면,) 유효 기록은 1일[^\n]*419\.5분/);
    assert.match(body, /직전 7일(?:의|을 보면,) 유효 기록은 0일[^\n]*기록일 평균은 표시할 수 없/);
    assert.match(body, /평균 차이는 표시를 보류/);
    assert.match(body, /두 기간에 각각 유효 기록일이 3일 이상/);
    assert.match(body, /최근 유효 기록일이 2일 이상/);
    assert.match(body, /미기록 구간|측정값이 없는 구간/);
    assert.match(body, /며칠 동안 취침·기상 시각을 적/);
    assert.match(body, /일정에 맞춰 반복하기 쉬운 시간대/);
    assert.doesNotMatch(body, /\+0분|각성으로 분류한 시간은|기기 기록의 시작 시각 범위는/);
  }
});

test("an invalid reference keeps the device check and does not invent a period", () => {
  const body = render(fixtures.unavailable, "ENFP");
  assert.notEqual(body, fixtures.unavailable.coaching);
  assert.match(body, /수면 시간을 확인할 수 없어요/);
  assert.match(body, /기기 앱에서 수면 시간이 기록됐는지 확인해 본 뒤, 다시 불러와/);
  assert.match(body, /수면 시간 값이 없거나 유효한 기록 범위를 벗어났어요/);
  assert.match(body, /선택한 기록의 날짜와 시간 구간/);
  assert.doesNotMatch(body, /최근 7일|직전 7일/);
});

test("excluded records, unreliable starts, and different timezones preserve distinct cautions", () => {
  const body = render(fixtures.notes, "ENFP");
  assert.notEqual(body, fixtures.notes.coaching);
  assert.match(body, /날짜, 시간 구간 또는 수면 시간을 확인할 수 없는 기록은 집계에 넣지 않았어요/);
  assert.match(body, /기록이 겹치거나 같은 기록 ID의 값이 다른 날은 집계에 넣지 않았어요/);
  assert.match(body, /날짜마다 믿을 만한 시작 시각을 하나씩 확인하기 어려워 시작 시각 변동은 표시를 보류/);
  assert.match(body, /다음 기록에 아침에 느낀 휴식 정도를 함께 적어 본 뒤, 기기 기록과 비교/);

  const mixed = structuredClone(fixtures.free);
  mixed.coaching = mixed.coaching.replace("\n기기 기록의 시작 시각 범위 20분", "")
    .replace("시작 시각 변동은 기기 기록의 시작 시각 범위입니다.", "최근 기록의 시간대 또는 UTC 오프셋이 달라 시작 시각 변동을 보류했습니다.");
  const presentation = mixed.context.presentation;
  presentation.patterns.regularity = {status: "mixed_timezones", start_spread_minutes: null, spread_display: null};
  presentation.limitation_ids[2] = "mixed_timezones";
  const mixedBody = render(mixed, "INFP");
  assert.match(mixedBody, /시간대 또는 UTC 오프셋이 달라 시작 시각 변동은 표시를 보류/);
  assert.doesNotMatch(mixedBody, /20분/);
});

test("original body is returned unchanged for unselected MBTI and historical advice", () => {
  const { free } = fixtures;
  assert.equal(render(free, null), free.coaching);
  const legacy = "  과거 OpenAI 조언 원문\n수면 시간 6시간 20분.\n\n";
  assert.equal(renderCoachingBody(legacy, {model: "openai-legacy"}, getCoachingTone("ENFP")), legacy);
  // An explicit non-rules engine cannot opt in, even with otherwise valid data.
  assert.equal(renderCoachingBody(free.coaching, {...free.context, engine: "openai"}, getCoachingTone("ENFP")), free.coaching);
  for (const context of [null, undefined, {engine: "rules"}]) {
    assert.equal(renderCoachingBody(legacy, context, getCoachingTone("ISTJ")), legacy);
  }
});

test("unsupported, incomplete, unknown, or inconsistent data falls back as a whole", () => {
  const edits = [
    data => { data.version = 2; },
    data => { delete data.observation.awake; },
    data => { data.observation.id = "unknown_observation"; },
    data => { delete data.patterns.previous.valid_days; },
    data => { delete data.patterns.comparison.average_difference_minutes; },
    data => { data.patterns.comparison.difference_display = "-40분"; },
    data => { data.patterns.regularity.status = "unknown_status"; },
    data => { data.suggestion_id = "unknown_suggestion"; },
    data => { data.suggestion_id = "track_morning_rest"; },
    data => { data.limitation_ids.push("__proto__"); },
    data => { data.limitation_ids.splice(1, 1); },
  ];
  for (const edit of edits) {
    const fixture = structuredClone(fixtures.free);
    edit(fixture.context.presentation);
    assert.equal(render(fixture, "ENFP"), fixture.coaching);
  }
  const droppedNote = structuredClone(fixtures.insufficient);
  // This optional caution cannot be inferred from the other v1 fields.
  droppedNote.context.presentation.limitation_ids.splice(1, 1);
  assert.equal(render(droppedNote, "INFP"), droppedNote.coaching);
  const changedBody = structuredClone(fixtures.free);
  changedBody.coaching += "\n서버가 새로 추가한 주의사항";
  assert.equal(render(changedBody, "ISTJ"), changedBody.coaching);
});
