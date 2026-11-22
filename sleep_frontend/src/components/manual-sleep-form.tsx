import {useState,type FormEvent} from "react";
import {minutes,type ManualSleepInput,type ManualSleepRecord} from "@/lib/sleep";

export default function ManualSleepForm({record,onSave,onCancel}:{
  record?:ManualSleepRecord; onSave:(values:ManualSleepInput)=>Promise<void>; onCancel:()=>void;
}) {
  const deviceZone=Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Seoul";
  const [start,setStart]=useState(record?.start.slice(0,16)??"");
  const [end,setEnd]=useState(record?.end.slice(0,16)??"");
  const [zone,setZone]=useState(record?.timezone??deviceZone);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const duration=zone.trim()===deviceZone ? (new Date(end).getTime()-new Date(start).getTime())/60_000 : NaN;

  async function submit(event:FormEvent<HTMLFormElement>){
    event.preventDefault();
    if(busy)return;
    setError("");
    if(end<=start){setError("기상 날짜와 시각은 취침 이후로 입력해 주세요.");return;}
    setBusy(true);
    try{await onSave({start_local:start,end_local:end,timezone:zone.trim()});}
    catch(error){setError(error instanceof Error?error.message:"기록을 저장하지 못했어요. 다시 시도해 주세요.");}
    finally{setBusy(false);}
  }

  return <form className="panel account-panel" onSubmit={submit}>
    <p>취침부터 기상까지의 시간으로 추정치를 계산해요. 자정을 넘겼다면 기상 날짜를 다음 날로 선택하세요.</p>
    <label>취침 날짜와 시각<input name="start_local" type="datetime-local" value={start} onChange={event=>setStart(event.target.value)} required disabled={busy}/></label>
    <label>기상 날짜와 시각<input name="end_local" type="datetime-local" value={end} onChange={event=>setEnd(event.target.value)} required disabled={busy}/></label>
    <label>시간대<input name="timezone" value={zone} onChange={event=>setZone(event.target.value)} placeholder="Asia/Seoul" maxLength={80} autoCapitalize="off" spellCheck={false} required disabled={busy}/></label>
    <p aria-live="polite">{duration>0?`추정 수면 시간 미리보기 · ${minutes(duration)}`:"저장하면 입력한 시간대 기준으로 추정 수면 시간을 표시해요."}</p>
    {error&&<p className="error" role="alert">{error}</p>}
    <div className="health-actions">
      <button type="submit" className="button primary" disabled={busy}>{busy?"저장하는 중":"수면 기록 저장"}</button>
      <button type="button" className="button secondary" disabled={busy} onClick={onCancel}>취소</button>
    </div>
  </form>;
}
