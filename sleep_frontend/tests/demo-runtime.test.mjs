import {test} from "node:test";
import assert from "node:assert/strict";
import {demoEnvironment} from "../../deploy/start-demo.mjs";

test("demo launcher refuses missing, disabled and mistyped modes", () => {
  for (const value of [undefined, "0", "true", "", " 1"])
    assert.throws(() => demoEnvironment({DALJAM_DEMO_ONLY:value}));
});

test("demo launcher validates Render port and binds all interfaces", () => {
  for (const value of ["0", "65536", "x", "1e3", "-1", ""])
    assert.throws(() => demoEnvironment({DALJAM_DEMO_ONLY:"1", PORT:value}));
  const env = demoEnvironment({DALJAM_DEMO_ONLY:"1"});
  assert.equal(env.PORT, "10000");
  assert.equal(env.HOSTNAME, "0.0.0.0");
  assert.equal(demoEnvironment({DALJAM_DEMO_ONLY:"1", PORT:"12000"}).PORT, "12000");
});

test("demo runtime removes database, upstream and paid-model settings", () => {
  const original = {DALJAM_DEMO_ONLY:"1", DATABASE_URL:"synthetic", PGHOST:"synthetic",
    OPENAI_API_KEY:"synthetic", OPENAI_MODEL:"synthetic", SLEEP_API_URL:"synthetic",
    SLEEP_DB_PATH:"synthetic", SLEEP_DB_BACKEND:"postgresql", COACHING_ENGINE:"openai"};
  const env = demoEnvironment(original);
  for (const key of ["DATABASE_URL", "PGHOST", "OPENAI_API_KEY", "OPENAI_MODEL", "SLEEP_API_URL", "SLEEP_DB_PATH", "SLEEP_DB_BACKEND"])
    assert.equal(key in env, false);
  assert.equal(env.COACHING_ENGINE, "rules");
  assert.equal(original.COACHING_ENGINE, "openai");
});
