import assert from "node:assert/strict";
import {spawn} from "node:child_process";
import {mkdir,mkdtemp,writeFile} from "node:fs/promises";
import {join} from "node:path";

const origin=process.env.DALJAM_PREMIUM_TEST_ORIGIN;
assert.match(origin??"",/^http:\/\/127\.0\.0\.1:\d+$/,"Use the isolated premium_browser_fixture.py runner");
const runtime=join(process.cwd(),".runtime");
const output=join(runtime,"premium-captures");
await mkdir(output,{recursive:true});
const profile=await mkdtemp(join(runtime,"premium-chrome-"));
const chrome=spawn(process.env.DALJAM_TEST_CHROME??"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",[
  "--headless=new","--disable-gpu","--no-proxy-server","--disable-background-networking","--disable-extensions",
  "--no-first-run","--remote-debugging-port=0","--user-data-dir="+profile,"about:blank",
],{windowsHide:true,stdio:["ignore","ignore","pipe"]});
let stderr="",socket;
chrome.stderr.on("data",chunk=>{stderr+=String(chunk);});
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(probe,label){
  for(let i=0;i<140;i++){
    const value=await probe().catch(()=>false);
    if(value)return value;
    await pause(100);
  }
  throw new Error("Timeout "+label);
}
try{
  const port=await until(async()=>stderr.match(/DevTools listening on ws:\/\/127\.0\.0\.1:(\d+)/)?.[1],"CDP");
  const tabs=await(await fetch("http://127.0.0.1:"+port+"/json/list")).json();
  socket=new WebSocket(tabs.find(tab=>tab.type==="page").webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener("open",resolve,{once:true});socket.addEventListener("error",reject,{once:true});});
  const pending=new Map(),errors=[],requests=[];
  let sequence=0;
  const send=(method,params={})=>new Promise((resolve,reject)=>{
    const id=++sequence;
    pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));
  });
  socket.addEventListener("message",({data})=>{
    const event=JSON.parse(data);
    if(event.id){
      const promise=pending.get(event.id);pending.delete(event.id);
      if(event.error)promise?.reject(new Error(event.error.message));else promise?.resolve(event.result);
    }
    if(event.method==="Runtime.exceptionThrown")errors.push(event.params.exceptionDetails.text);
    if(event.method==="Runtime.consoleAPICalled"&&event.params.type==="error")errors.push(event.params.args.map(arg=>arg.value??arg.description).join(" "));
    if(event.method==="Network.requestWillBeSent")requests.push(event.params.request.url);
  });
  await send("Page.enable");await send("Runtime.enable");await send("Network.enable");
  if(process.env.PREMIUM_TEST_LIVE_MOCK==="1")await send("Page.addScriptToEvaluateOnNewDocument",{source:'Object.defineProperty(globalThis.crypto,"randomUUID",{value:undefined,configurable:true});'});
  await send("Network.setBypassServiceWorker",{bypass:true});
  const js=async expression=>{
    const result=await send("Runtime.evaluate",{expression,returnByValue:true,awaitPromise:true});
    if(result.exceptionDetails)throw new Error(result.exceptionDetails.exception?.description??result.exceptionDetails.text);
    return result.result.value;
  };
  const run=(fn,...args)=>js("("+fn.toString()+")("+args.map(value=>JSON.stringify(value)).join(",")+")");
  const visible=text=>until(()=>run(value=>document.body.innerText.includes(value),text),text);
  const click=async(label,selector="button")=>until(()=>run((label,selector)=>{
    const button=[...document.querySelectorAll(selector)].find(element=>element.getClientRects().length&&(!label||element.textContent.includes(label))&&!element.disabled);
    if(!button)return false;
    button.scrollIntoView({block:"center"});button.focus();button.click();return true;
  },label,selector),"click "+label);
  async function viewport(width){
    await send("Emulation.setDeviceMetricsOverride",{width,height:width===1280?900:844,deviceScaleFactor:1,mobile:width!==1280});
    await until(()=>run(value=>innerWidth===value,width),"width");
    assert.ok(await js("document.documentElement.scrollWidth<=innerWidth"),"horizontal overflow at "+width);
  }
  async function capture(name,width=390,section=""){
    await viewport(width);
    await js("document.fonts.ready");
    await run(section=>{if(section)document.querySelector(section)?.scrollIntoView({block:"start"});else window.scrollTo(0,0);},section);
    const image=await send("Page.captureScreenshot",{format:"png",captureBeyondViewport:false});
    await writeFile(join(output,name+".png"),Buffer.from(image.data,"base64"));
  }
  const api=async(path,method="GET",body)=>run(async(path,method,body)=>{
    const options={method};
    if(body!==null){options.headers={"Content-Type":"application/json"};options.body=JSON.stringify(body);}
    const response=await fetch("/api/sleep/"+path,options);
    return {status:response.status,body:await response.json()};
  },path,method,body??null);
  const checked=async(path,method,body,expected=200)=>{
    const result=await api(path,method,body);assert.equal(result.status,expected,path);return result.body;
  };
  const credentials={username:"premium-fixture-"+Date.now().toString(36),password:"synthetic-premium-password"};
  await send("Emulation.setDeviceMetricsOverride",{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await send("Page.navigate",{url:origin});
  await until(()=>js('!!document.querySelector(".auth-submit")'),"login form");
  await viewport(390);
  await checked("auth/register","POST",{...credentials,privacy_consent:true,health_consent:true,overseas_consent:true,adult_confirmed:true,policy_version:"2026-11-12-v1"},201);
  await checked("auth/login","POST",credentials);
  await checked("auth/personalization","POST",{mbti:null,speech:"casual",intensity:"firm",allow_profanity:false,character:"cat"});
  const record=await checked("watch/manual-sessions","POST",{start_local:"2024-11-15T23:15",end_local:"2024-11-16T06:00",timezone:"Asia/Seoul"});
  const advice=await checked("coach","POST",{analysis_id:record.record.analysis_id});
  assert.equal(advice.context.engine,"manual-rules");assert.equal(advice.context.fallback_reason,undefined);
  const recordsBefore=await checked("watch/sessions");
  let expectedRecords=recordsBefore;
  const mockLive=process.env.PREMIUM_TEST_LIVE_MOCK==="1";
  await send("Page.reload");await visible("추정 수면은 6시간 45분이에요");
  await click("Premium 알아보기");await visible("현재 이용 상태");
  assert.equal(await js('[...document.querySelectorAll("p")].filter(node=>node.textContent==="DALJAM PREMIUM").length'),1);
  assert.equal(await js('document.querySelectorAll(".main-tabs button").length'),4);
  for(const width of [320,390,430,1280])await viewport(width);
  await capture("01-premium-intro");await capture("01-premium-desktop",1280);
  if(process.env.PREMIUM_TEST_ENV==="production"){
    const status=await checked("premium");assert.equal(status.demo_available,false);
    assert.ok(await run(()=>[...document.querySelectorAll("button")].some(button=>button.textContent.includes("모의 결제로 체험하기")&&button.disabled)));
    assert.equal((await api("premium/demo/checkout","POST")).status,403);
    assert.equal((await api("premium/demo/preview")).status,403);
    assert.equal((await api("premium/demo/coach","POST",{analysis_id:record.record.analysis_id,request_id:"11111111-1111-4111-8111-111111111111"})).status,403);
    await visible("현재 환경에서는 결제 시연을 사용할 수 없어요");
    await run(()=>{[...document.querySelectorAll("h2")].find(node=>node.textContent==="프리미엄 업그레이드 시연").closest("section").id="fixture-demo-intro";});
    await capture("07-production-disabled",390,"#fixture-demo-intro");
    await send("Page.navigate",{url:origin});
    await click("수면 시간 직접 입력");
    await visible("취침 날짜와 시각");
    const field=(name,value)=>run((name,value)=>{
      const input=document.querySelector('input[name="'+name+'"]');
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(input,value);
      input.dispatchEvent(new Event("input",{bubbles:true}));
    },name,value);
    await field("start_local","2024-11-20T23:30");
    await field("end_local","2024-11-21T06:45");
    await field("timezone","Asia/Seoul");
    await click("수면 기록 저장");
    await visible("약 7시간 15분");
    await visible("생활습관 정보는 선택사항이에요.");
    const {sessions:entries}=await checked("watch/sessions");
    const first=entries.find(entry=>entry.start.includes("2024-11-20"));
    const history=await checked("watch/sessions/"+first.analysis_id+"/coaching");
    assert.equal(history.history.length,1);
    assert.ok(!JSON.stringify(history).includes("input_summary"));
    assert.ok(await run(()=>!document.querySelector('article[aria-label="수면 조언"] pre')));
    assert.ok(await js('![...document.querySelectorAll("h3")].some(node=>node.textContent==="수면 패턴")'));
    await click("생활습관과 평소 설정","summary");
    await visible("날짜별 입력 저장");
    for(const width of [320,390,430])await viewport(width);
    await capture("11-free-coaching-mobile");
    await click("무료 코칭 생성");
    await visible("이미 저장된 수면 조언을 열었어요.");
    assert.equal((await checked("watch/sessions/"+first.analysis_id+"/coaching")).history.length,1);
    const uploaded=await run(async()=>{
      const start="2024-11-22T23:00:00+09:00",end="2024-11-23T04:39:50+09:00";
      const data={schema_version:1,timezone:"Asia/Seoul",source:"synthetic-watch",
        sessions:[{start,end,segments:[{stage:"core",start,end}]}]};
      const form=new FormData();
      form.set("file",new File([JSON.stringify(data)],"synthetic.json",{type:"application/json"}));
      const response=await fetch("/api/sleep/analyze",{method:"POST",body:form});
      return {status:response.status,body:await response.json()};
    });
    assert.equal(uploaded.status,200);
    await send("Page.reload");
    await visible("수면 시간 직접 입력");
    await click("코칭",".dashboard-link");
    await visible("무료 코칭 생성");
    await run(id=>{
      const select=document.querySelector('select[aria-label="분석할 수면 기록"]');
      select.value=id;
      select.dispatchEvent(new Event("change",{bubbles:true}));
    },uploaded.body.analysis_ids[0]);
    await click("무료 코칭 생성");
    await visible("약 5시간 40분");
    console.log("PASS free manual auto-coaching, JSON upload coaching, privacy, deduplication and mobile 320/390/430");
    console.log("PASS Chrome production mode rejects demo grants even with flag=1; free manual coaching and premium introduction remain available");
  }else{
    await js('localStorage.setItem("premium","true")');
    assert.equal((await api("premium/demo/preview")).status,403);
    await click("모의 결제로 체험하기");await visible("결제 시연을 확인해 주세요");
    assert.ok(await js('document.activeElement?.tagName==="H2"'));
    assert.equal(await js('document.querySelectorAll("form input:not([type=checkbox])").length'),0);
    assert.equal(await js('document.querySelector("form button[type=submit]").disabled'),true);
    for(const width of [320,390,430,1280])await viewport(width);
    await capture("02-mock-checkout");
    await click("취소");await visible("프리미엄 업그레이드 시연");
    assert.equal((await checked("premium")).tier,"free");
    await click("모의 결제로 체험하기");await visible("결제 시연을 확인해 주세요");
    await click("","input[type=checkbox]");await click("모의 결제 완료");
    await visible("프리미엄 시연 활성화");await visible("내 기록으로 맞춤 조언 받기");
    const state=await checked("premium");assert.equal(state.tier,"premium_demo");assert.equal(state.paid_entitlement,false);assert.equal(state.live_ai_available,mockLive);
    if(!mockLive){
      assert.ok(await run(()=>[...document.querySelectorAll("button")].some(node=>node.textContent.includes("AI 맞춤 조언 생성")&&node.disabled)));
      assert.equal((await checked("premium/demo/coach","POST",{analysis_id:record.record.analysis_id,request_id:"11111111-1111-4111-8111-111111111111"})).kind,"sample");
    }
    if(mockLive){
      await click("수면 시간 직접 입력");await visible("취침 날짜와 시각");
      const field=(name,value)=>run((name,value)=>{
        const input=document.querySelector('input[name="'+name+'"]');
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(input,value);
        input.dispatchEvent(new Event("input",{bubbles:true}));
      },name,value);
      await field("start_local","2024-11-17T23:30");await field("end_local","2024-11-18T06:30");await field("timezone","Asia/Seoul");
      await capture("08-live-manual-input");
      await click("수면 기록 저장");await until(()=>run(()=>!document.querySelector('input[name="start_local"]')),"manual saved");
      await until(()=>run(()=>[...document.querySelectorAll("button")].some(node=>node.textContent.includes("AI 맞춤 조언 생성")&&!node.disabled)),"live request button ready");
      await run(()=>{const button=[...document.querySelectorAll("button")].find(node=>node.textContent.includes("AI 맞춤 조언 생성"));button.click();button.click();});
      await visible("AI가 실제 수면 기록을 바탕으로 생성한 조언");
      for(const width of [320,390,430,1280])await viewport(width);
      assert.equal((await checked("premium")).ai_usage.calls_started,1);
      await capture("09-live-ai-mocked",390,'h3[tabindex="-1"]');
      await click("생성 결과 다시 확인");await visible("저장된 동일 요청 결과");
      assert.equal((await checked("premium")).ai_usage.calls_started,1);
      await click("수면 시간 직접 입력");await visible("취침 날짜와 시각");
      await field("start_local","2024-11-18T22:45");await field("end_local","2024-11-19T06:30");await field("timezone","Asia/Seoul");
      await click("수면 기록 저장");await until(()=>run(()=>!document.querySelector('input[name="start_local"]')),"second manual saved");
      await click("AI 맞춤 조언 생성");await visible("기본 수면 조언 — AI 연결을 사용할 수 없어 대체 제공");
      assert.equal((await checked("premium")).ai_usage.calls_started,2);
      await capture("10-live-fallback-mocked",390,'h3[tabindex="-1"]');
      expectedRecords=await checked("watch/sessions");
      console.log("PASS mocked Responses API after manual save, double-click blocking, cached replay, quota accounting and clearly labeled rules fallback");
      await click("샘플 데이터 코칭 예시 보기","summary");
    }
    await visible("AI 코칭 시연 예시 — 샘플 데이터");
    const sample=await checked("premium/demo/preview");assert.equal(sample.source,"prepared_sample");assert.equal(sample.model_called,false);
    assert.equal(sample.expression.speech,"casual");assert.equal(sample.expression.intensity,"firm");
    assert.ok(!sample.coaching.includes("6시간 45분"));
    for(const width of [320,390,430,1280])await viewport(width);
    await capture("03-demo-active");
    for(const character of ["cat","raccoon","dog","rabbit"]){
      await checked("auth/personalization","PATCH",{mbti:null,speech:"casual",intensity:"firm",allow_profanity:false,character});
      await send("Page.reload");await visible("추정 수면은");
      await click("Premium 알아보기");await visible("내 기록으로 맞춤 조언 받기");
      if(mockLive)await click("샘플 데이터 코칭 예시 보기","summary");
      await visible("AI 코칭 시연 예시");
      assert.equal((await checked("premium/demo/preview")).coaching,sample.coaching);
      await capture("04-sample-"+character,390,"#premium-sample-title");
    }
    await capture("05-sample-desktop",1280,"#premium-sample-title");
    await click("시연 초기화 · 무료로 돌아가기");
    await visible("현재 이용 상태");
    assert.equal((await checked("premium")).tier,"free");
    assert.equal((await api("premium/demo/preview")).status,403);
    assert.deepEqual(await checked("watch/sessions"),expectedRecords);
    const saved=await checked("watch/sessions/"+record.record.analysis_id+"/coaching");
    assert.equal(saved.history.length,1);assert.equal(saved.history[0].coaching,advice.coaching);
    await capture("06-reset-free");
    console.log("PASS Chrome 320/390/430/1280, four themes, intro/checkout/cancel/confirmation/sample/reset/reload, focus, free coaching, separate sample/history and account data");
  }
  assert.deepEqual(errors,[]);
  assert.ok(requests.filter(url=>url.startsWith("http")).every(url=>url.startsWith(origin+"/")),"Unexpected external browser request");
} finally {socket?.close();chrome.kill();}
