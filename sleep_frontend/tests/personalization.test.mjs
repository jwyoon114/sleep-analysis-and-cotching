import assert from "node:assert/strict";
import test from "node:test";
import {changeIntensity, CHARACTER_THEMES, INTENSITY_OPTIONS, SPEECH_OPTIONS} from "../src/lib/personalization.ts";

test("intensity changes preserve independent explicit consent; defaults stay opt-in", () => {
  for (const {value} of INTENSITY_OPTIONS) {
    assert.deepEqual(changeIntensity(value), {intensity:value});
    for(const allowed of [true,false]) {
      assert.equal(({allow_profanity:allowed,...changeIntensity(value)}).allow_profanity,allowed);
    }
  }
});

test("character options are visual and independent from coaching choices", () => {
  assert.deepEqual(CHARACTER_THEMES, {
    cat:{moon:"crescent"}, raccoon:{moon:"crescent"}, dog:{moon:"full"}, rabbit:{moon:"full"},
  });
  assert.deepEqual(SPEECH_OPTIONS.map(({value})=>value), ["polite","casual"]);
  assert.deepEqual(INTENSITY_OPTIONS.map(({value})=>value), ["gentle","firm","direct"]);
});
