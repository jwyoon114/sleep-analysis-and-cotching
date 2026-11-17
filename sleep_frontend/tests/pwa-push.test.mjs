import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import vm from "node:vm";
import {isAppleMobile} from "../src/lib/web-push.ts";

const source=readFileSync(new URL("../public/sw.js",import.meta.url),"utf8");
const origin="https://daljam.example";

function worker(windows=[]){
  const listeners={};
  const calls=[];
  const self={
    location:{origin},
    addEventListener:(type,listener)=>{listeners[type]=listener;},
    skipWaiting:()=>{},
    registration:{showNotification:async(...args)=>{calls.push(["display",...args]);}},
    clients:{
      claim:async()=>{calls.push(["claim"]);},
      matchAll:async()=>windows,
      openWindow:async url=>{calls.push(["open",url]);},
    },
  };
  const caches={
    open:async name=>({add:async url=>{calls.push(["cache",name,url]);}}),
    keys:async()=>["daljam-offline-v2","daljam-offline-v3","other-cache"],
    delete:async name=>{calls.push(["delete",name]);},
    match:async url=>{calls.push(["match",url]);return "public offline page";},
  };
  vm.runInNewContext(source,{self,caches,URL,Response,fetch:async()=>{throw Error("offline");}});
  async function event(type,options={}){
    let pending;
    const wait=promise=>{pending=promise;};
    listeners[type]({...options,waitUntil:wait,respondWith:wait});
    return await pending;
  }
  return {calls,event};
}

test("worker migration caches only the public offline page and never handles API or APK",async()=>{
  const {calls,event}=worker();
  await event("install");await event("activate");
  assert.deepEqual(calls,[["cache","daljam-offline-v3","/offline.html"],["delete","daljam-offline-v2"],["claim"]]);
  for(const path of ["/api/sleep/watch/sessions","/downloads/daljam-android.apk"])
    assert.equal(await event("fetch",{request:{mode:"navigate",method:"GET",url:origin+path}}),undefined);
  assert.equal(await event("fetch",{request:{mode:"navigate",method:"GET",url:origin+"/?tab=plan"}}),"public offline page");
});

test("push shows only the fixed message and its click preserves a same-origin plan destination",async()=>{
  const {calls,event}=worker();
  await event("push",{data:{json:()=>({kind:"unknown"})}});
  assert.deepEqual(calls,[]);
  await event("push",{data:{json:()=>({kind:"bedtime-test",body:"sensitive",url:"https://example.invalid/"})}});
  assert.equal(calls[0][1],"달잠 테스트 알림");
  assert.ok(!JSON.stringify(calls).includes("sensitive"));
  await event("notificationclick",{notification:{tag:"daljam-bedtime-test",close:()=>calls.push(["close"])}});
  assert.deepEqual(calls.slice(-2),[["close"],["open",origin+"/?tab=plan"]]);
});

test("click focuses an existing app window after navigating to plan",async()=>{
  const navigation=[];
  const {calls,event}=worker([
    {url:"https://other.example/",navigate:async()=>assert.fail("cross-origin client")},
    {url:origin+"/",navigate:async url=>{navigation.push(url);return {focus:async()=>navigation.push("focus")};}},
  ]);
  await event("notificationclick",{notification:{tag:"daljam-bedtime-test",close:()=>{}}});
  assert.deepEqual(navigation,[origin+"/?tab=plan","focus"]);
  assert.deepEqual(calls,[]);
});

test("Apple Home Screen help includes iPad with a desktop identity",()=>{
  assert.equal(isAppleMobile({userAgent:"Version/18.0 Safari",platform:"MacIntel",maxTouchPoints:5}),true);
  assert.equal(isAppleMobile({userAgent:"Version/18.0 Safari",platform:"MacIntel",maxTouchPoints:0}),false);
  assert.equal(isAppleMobile({userAgent:"iPhone",platform:"iPhone",maxTouchPoints:5}),true);
});
