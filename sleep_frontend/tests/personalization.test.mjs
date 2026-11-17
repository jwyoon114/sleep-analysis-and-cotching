import assert from "node:assert/strict";
import test from "node:test";
import {changeIntensity, CHARACTER_THEMES, INTENSITY_OPTIONS, SPEECH_OPTIONS} from "../src/lib/personalization.ts";

test("every explicit intensity change starts with profanity disabled", () => {
  for (const {value} of INTENSITY_OPTIONS) {
    assert.deepEqual(changeIntensity(value), {intensity:value, allow_profanity:false});
  }
});

test("character options are visual and independent from coaching choices", () => {
  assert.deepEqual(CHARACTER_THEMES, {
    cat:{moon:"crescent"}, raccoon:{moon:"crescent"}, dog:{moon:"full"}, rabbit:{moon:"full"},
  });
  assert.deepEqual(SPEECH_OPTIONS.map(({value})=>value), ["polite","casual"]);
  assert.deepEqual(INTENSITY_OPTIONS.map(({value})=>value), ["gentle","firm","direct"]);
});
