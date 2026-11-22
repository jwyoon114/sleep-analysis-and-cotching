import assert from "node:assert/strict";
import test from "node:test";
import {demoRequestId} from "../src/lib/premium.ts";

test("demo request IDs use native UUID generation when available",()=>{
  const id="11111111-1111-4111-8111-111111111111";
  assert.equal(demoRequestId({randomUUID:()=>id,getRandomValues:()=>{throw Error("Unexpected fallback");}}),id);
});

test("older WebCrypto implementations generate UUIDv4 without randomUUID",()=>{
  const id=demoRequestId({getRandomValues:bytes=>bytes.fill(0)});
  assert.equal(id,"00000000-0000-4000-8000-000000000000");
  assert.throws(()=>demoRequestId({}),/보안 연결/);
});
