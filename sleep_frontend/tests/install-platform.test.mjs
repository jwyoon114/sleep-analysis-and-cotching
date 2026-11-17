import assert from "node:assert/strict";
import test from "node:test";
import {installPlatform} from "../src/lib/install-platform.ts";

const galaxy = {userAgent:"Mozilla/5.0 (Linux; Android 15; SM-S921N) Chrome/138 Mobile Safari/537.36",platform:"Linux armv8l",maxTouchPoints:5};
const iphone = {userAgent:"Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",platform:"iPhone",maxTouchPoints:5};
const mac = {userAgent:"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Version/18.0 Safari/605.1.15",platform:"MacIntel",maxTouchPoints:0};

test("the native bridge supersedes the Android browser identity", () => {
  assert.equal(installPlatform(galaxy,true),"native");
  assert.equal(installPlatform(galaxy,false),"android");
});

test("Apple mobile browsers include iPadOS with a desktop user agent", () => {
  assert.equal(installPlatform(iphone,false),"ios");
  assert.equal(installPlatform({...mac,maxTouchPoints:5},false),"ios");
  assert.equal(installPlatform(mac,false),"web");
});

test("a touchscreen Windows PC remains on general web help", () => {
  assert.equal(installPlatform({...mac,userAgent:"Mozilla/5.0 (Windows NT 10.0; Win64; x64)",platform:"Win32",maxTouchPoints:10},false),"web");
});
