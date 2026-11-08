import assert from "node:assert/strict";
import test from "node:test";
import {
  MBTI_TYPES, CHARACTERS, COACHING_PRESETS, PREVIEW_ANALYSIS, PREVIEW_CONTENT,
  createCoachingPreview, getCharacter, isMbtiType,
} from "../src/lib/coaching-preview.ts";

const expectedTypes = [
  "ENFJ", "ENFP", "ENTJ", "ENTP", "ESFJ", "ESFP", "ESTJ", "ESTP",
  "INFJ", "INFP", "INTJ", "INTP", "ISFJ", "ISFP", "ISTJ", "ISTP",
];
const expectedAnalysis = {
  fictional: true, asleepMinutes: 380, awakeMinutes: 40,
  recordingStart: "23:30", recordingEnd: "06:30",
};
const expectedRecommendations = [
  "잠들기 전 화면을 잠시 내려놓고, 조용한 음악 듣기나 책 읽기 중 편한 휴식 활동을 골라보세요.",
  "다음 날에도 같은 방식으로 수면 기록을 남겨, 여러 날의 흐름을 살펴보세요.",
];
const expectedCautions = [
  "기능 체험을 위한 가상 기록이며, 실제 수면 분석 결과가 아닙니다.",
  "수면 기록만으로 수면의 질이나 질병을 판단할 수 없습니다.",
];

test("all sixteen MBTI types have distinct, nonempty expression presets", () => {
  assert.deepEqual([...MBTI_TYPES].sort(), expectedTypes);
  assert.deepEqual(Object.keys(COACHING_PRESETS).sort(), expectedTypes);
  const outputs = MBTI_TYPES.map(type => {
    const preview = createCoachingPreview(type);
    assert.equal(preview.mbti, type);
    assert.equal(preview.facets.length, 4);
    for (const text of Object.values(preview.preset)) assert.ok(text.trim());
    // Style framing must not add invented numeric measurements or times.
    assert.doesNotMatch(Object.values(preview.preset).join(" "), /\d/);
    return JSON.stringify([preview.preset, preview.expression]);
  });
  assert.equal(new Set(outputs).size, 16);
  assert.equal(new Set(MBTI_TYPES.map(t => COACHING_PRESETS[t].opening)).size, 16);
});

test("every type and animal combination preserves facts, actions and cautions", () => {
  const original = JSON.stringify(PREVIEW_CONTENT);
  let count = 0;
  for (const type of MBTI_TYPES) {
    for (const animal of CHARACTERS) {
      const preview = createCoachingPreview(type);
      const character = getCharacter(animal.id);
      assert.equal(character.id, animal.id);
      assert.deepEqual(preview.analysis, expectedAnalysis);
      assert.equal(preview.content.observation, "가상 기록의 수면 시간은 6시간 20분, 각성 시간은 40분이며, 기록 구간은 23:30~06:30입니다.");
      assert.deepEqual(preview.content.recommendations, expectedRecommendations);
      assert.deepEqual(preview.content.cautions, expectedCautions);
      assert.equal(preview.content.rationale, "한 번의 기록만으로 원인을 단정하지 않고, 여러 날의 기록을 비교하기 위한 제안입니다.");
      assert.equal(JSON.stringify(preview.content), original);
      count++;
    }
  }
  assert.equal(count, 64);
});

test("displayed numbers are consistent with the fictional input", () => {
  assert.deepEqual(PREVIEW_CONTENT.metrics, [
    {label: "수면 시간", value: "6시간 20분"},
    {label: "각성 시간", value: "40분"},
    {label: "기록 구간", value: "23:30~06:30"},
  ]);
  const [startHours, startMinutes] = PREVIEW_ANALYSIS.recordingStart.split(":").map(Number);
  const [endHours, endMinutes] = PREVIEW_ANALYSIS.recordingEnd.split(":").map(Number);
  const window = (endHours * 60 + endMinutes - startHours * 60 - startMinutes + 1440) % 1440;
  assert.equal(PREVIEW_ANALYSIS.asleepMinutes + PREVIEW_ANALYSIS.awakeMinutes, window);
});

test("E/I, S/N, T/F and J/P affect expression rather than core content", () => {
  const i = createCoachingPreview("ISTJ");
  const e = createCoachingPreview("ESTJ");
  assert.equal(i.facets[0], "차분한 표현");
  assert.equal(e.facets[0], "활기 있는 표현");
  assert.match(e.preset.opening, /!/);
  assert.doesNotMatch(i.preset.opening, /!/);
  assert.notEqual(i.expression.perspective, createCoachingPreview("INTJ").expression.perspective);
  assert.notEqual(i.expression.observationLead, createCoachingPreview("ISFJ").expression.observationLead);
  assert.equal(i.expression.listStyle, "steps");
  assert.equal(createCoachingPreview("ISTP").expression.listStyle, "bullets");
  for (const type of MBTI_TYPES) {
    const preview = createCoachingPreview(type);
    assert.strictEqual(preview.content, PREVIEW_CONTENT);
    assert.strictEqual(preview.analysis, PREVIEW_ANALYSIS);
  }
});

test("changing an animal does not select or alter an MBTI preset", () => {
  const before = createCoachingPreview("INFP");
  for (const {id} of CHARACTERS) getCharacter(id);
  assert.deepEqual(createCoachingPreview("INFP"), before);
  assert.deepEqual(CHARACTERS.map(c => c.id), ["cat", "rabbit", "bear", "owl"]);
  assert.equal(new Set(CHARACTERS.map(c => c.emoji)).size, 4);
});

test("unselected MBTI has a neutral preview with the same core information", () => {
  const preview = createCoachingPreview(null);
  assert.equal(preview.mbti, null);
  assert.equal(preview.preset.label, "기본 말투");
  assert.equal(preview.facets.length, 0);
  assert.strictEqual(preview.content, PREVIEW_CONTENT);
  assert.deepEqual(preview.analysis, expectedAnalysis);
});

test("unknown values are rejected rather than inferred from user information", () => {
  for (const value of ["", "INT", "INFX", "infp", null, undefined, 123, "<script>"]) {
    assert.equal(isMbtiType(value), false);
  }
  for (const type of MBTI_TYPES) assert.equal(isMbtiType(type), true);
  assert.throws(() => createCoachingPreview("UNKNOWN"), /지원하지 않는 MBTI/);
  assert.throws(() => getCharacter("unknown"), /지원하지 않는 캐릭터/);
});

test("preview rendering cannot mutate shared facts or preset definitions", () => {
  assert.throws(() => { PREVIEW_ANALYSIS.asleepMinutes = 0; }, TypeError);
  assert.throws(() => { PREVIEW_CONTENT.recommendations.push("changed"); }, TypeError);
  assert.throws(() => { PREVIEW_CONTENT.metrics[0].value = "changed"; }, TypeError);
  assert.throws(() => { COACHING_PRESETS.INTJ.opening = "changed"; }, TypeError);
  assert.throws(() => { CHARACTERS[0].id = "owl"; }, TypeError);
  assert.throws(() => { MBTI_TYPES.push("UNKNOWN"); }, TypeError);
  assert.deepEqual(PREVIEW_ANALYSIS, expectedAnalysis);
});
