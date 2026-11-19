"use client";

import {useEffect, useRef, useState} from "react";
import {LoaderCircle, Plus, Sparkles} from "lucide-react";
import {api, recordDuration, shortDate, clock, type ManualSleepInput, type SleepRecord} from "@/lib/sleep";
import {demoRequestId, type PremiumAIResult, type PremiumStatus} from "@/lib/premium";
import ManualSleepForm from "./manual-sleep-form";
import styles from "./premium-demo.module.css";

export default function PremiumLiveCoaching({status,onManualSaved}:{status:PremiumStatus;onManualSaved:()=>void}) {
  const [records,setRecords]=useState<SleepRecord[]>([]);
  const [selected,setSelected]=useState("");
  const [editing,setEditing]=useState(false);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [result,setResult]=useState<PremiumAIResult|null>(null);
  const [budget,setBudget]=useState(status.ai_usage);
  const [revision,setRevision]=useState(0);
  const inFlight=useRef(false);
  const requestId=useRef<string|null>(null);
  const resultHeading=useRef<HTMLHeadingElement>(null);
  const record=records.find(row=>row.analysis_id===selected);

  useEffect(()=>{
    const controller=new AbortController();
    setLoading(true);
    api<{sessions:SleepRecord[]}>("watch/sessions","GET",undefined,controller.signal).then(value=>{
      if(!controller.signal.aborted){setRecords(value.sessions);setSelected(current=>value.sessions.some(row=>row.analysis_id===current)?current:value.sessions[0]?.analysis_id||"");}
    }).catch(error=>{
      if(!controller.signal.aborted)setError(error instanceof Error?error.message:"기록을 불러오지 못했어요.");
    }).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[revision]);

  useEffect(()=>{setBudget(status.ai_usage);},[status.ai_usage]);

  function clearRequest() {requestId.current=null;setResult(null);setError("");}

  async function saveManual(input:ManualSleepInput) {
    const saved=await api<{record:SleepRecord}>("watch/manual-sessions","POST",input);
    clearRequest();setSelected(saved.record.analysis_id);setEditing(false);setRevision(value=>value+1);onManualSaved();
  }

  async function generate() {
    if(inFlight.current||!record||!status.live_ai_available)return;
    inFlight.current=true;setBusy(true);setError("");
    try {
      requestId.current??=demoRequestId();
      const value=await api<PremiumAIResult>("premium/demo/coach","POST",{analysis_id:record.analysis_id,request_id:requestId.current});
      setResult(value);setBudget(value.usage);
      requestAnimationFrame(()=>resultHeading.current?.focus());
      if(value.kind!=="sample")onManualSaved();
    } catch(error) {
      setError(error instanceof Error?error.message:"생성 결과를 확인하지 못했어요.");
    } finally {inFlight.current=false;setBusy(false);}
  }

  return <section className={`panel ${styles.live}`} aria-labelledby="premium-live-title" aria-busy={busy}>
    <h2 id="premium-live-title">내 기록으로 맞춤 조언 받기</h2>
    <p>직접 입력한 시각 또는 연결한 기기의 기록을 선택해 주세요. 직접 입력한 시간은 추정 수면 시간으로 다뤄요.</p>
    {error&&<div className="error" role="alert"><p>{error}</p><button type="button" className="button secondary" disabled={busy} onClick={()=>{clearRequest();setRevision(value=>value+1);}}>기록 다시 불러오기</button></div>}
    {loading?<p role="status">저장된 수면 기록을 확인하고 있어요.</p>:records.length>0?<label className={styles.recordSelector}>
      조언에 사용할 기록<select aria-label="AI 조언에 사용할 수면 기록" value={selected} disabled={busy||editing} onChange={event=>{setSelected(event.target.value);clearRequest();}}>
        {records.map(row=><option key={row.analysis_id} value={row.analysis_id}>{shortDate(row.start)} · {clock(row.start)} · {recordDuration(row)}</option>)}
      </select>
    </label>:<p>먼저 수면 시간을 직접 입력해 주세요. 기기 없이도 기록할 수 있어요.</p>}
    {record&&<p className={styles.note}>{record.data_type==="manual"?"직접 입력한 기록":"기기에서 가져온 기록"} · {recordDuration(record)} · {record.timezone}</p>}
    {!editing&&<button type="button" className="button secondary" disabled={busy} onClick={()=>setEditing(true)}><Plus size={17}/>수면 시간 직접 입력</button>}
    {editing&&<ManualSleepForm onSave={saveManual} onCancel={()=>setEditing(false)}/>}
    {status.live_ai_available?<>
      <p className={styles.note}>버튼을 누르면 실제 수면 시각·기록 요약과 개인화 설정을 OpenAI로 보내요. 개발용 API 비용이 발생할 수 있어요. 최근 24시간에 최대 3회 요청할 수 있어요.</p>
      {budget&&<p role="status">AI 요청 예산 {budget.remaining}회 남음 · 최근 24시간 최대 {budget.limit}회</p>}
    </>:<p className={styles.note}>현재 실제 AI 호출은 비활성 상태예요. 아래의 샘플 데이터로 시연을 계속할 수 있어요.</p>}
    <button type="button" className="button primary" disabled={busy||loading||editing||!record||!status.live_ai_available} onClick={generate}>
      {busy?<><LoaderCircle className="spin" size={18}/>AI 조언을 생성하고 있어요</>:<><Sparkles size={18}/>{result&&result.kind!=="sample"?"생성 결과 다시 확인":"AI 맞춤 조언 생성"}</>}
    </button>
    {result&&<div className={styles.liveResult}>
      <h3 ref={resultHeading} tabIndex={-1}>{result.label}</h3>
      {result.kind==="sample"?<><p className={styles.note}>{result.sample.notice}</p><p className={styles.sampleText}>{result.sample.coaching}</p></>
        :<><p className={styles.sampleText}>{result.coaching.coaching}</p><p className={styles.note}>{result.replayed?"저장된 동일 요청 결과를 다시 확인했어요.":"조언을 내 수면 기록에 저장했어요."} 기록·코칭 화면에서도 확인할 수 있어요.</p>
          <details><summary>시연 사용량 확인</summary><p>시작한 요청 {result.usage.calls_started}회 · 확인된 입력 {result.usage.input_tokens}토큰 · 출력 {result.usage.output_tokens}토큰</p>
            {result.usage.unknown_usage_calls>0&&<p>사용량을 확인하지 못한 요청 {result.usage.unknown_usage_calls}회도 호출 예산에 포함해요.</p>}</details></>}
    </div>}
  </section>;
}
