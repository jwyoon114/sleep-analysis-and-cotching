"use client";

import {useState} from "react";
import {Moon, Sun} from "lucide-react";
import {api,type Coaching} from "@/lib/sleep";
import ClassicDialog from "./classic-dialog";

export type Schedule={bedtime:string;wake_time:string;timezone:string;enabled:boolean;coaching_id?:string|null;desktop_available:boolean;saved:boolean};

export function saveSleepSchedule(settings:Schedule) {
  const {bedtime,wake_time,timezone,coaching_id}=settings;
  return api<Schedule>("alarms","POST",{bedtime,wake_time,timezone,coaching_id,enabled:settings.desktop_available&&settings.enabled});
}

export default function SleepAlarms({settings,coaching,onSave,onBack}:{
  settings:Schedule;coaching?:Coaching;onSave:(settings:Schedule)=>Promise<void>;onBack:()=>void;
}) {
  const [draft,setDraft]=useState(()=>settings.saved?settings:{
    ...settings,bedtime:"",wake_time:"",timezone:Intl.DateTimeFormat().resolvedOptions().timeZone||settings.timezone,
  });
  const [busy,setBusy]=useState(false),[message,setMessage]=useState(""),[error,setError]=useState("");
  const proposal=coaching?.context?.alarm_schedule;

  async function save(){
    setBusy(true);setError("");
    try {await onSave(draft);}
    catch(e){setError(e instanceof Error?e.message:"목표 시간을 저장하지 못했어요.");}
    finally{setBusy(false);}
  }

  return <ClassicDialog className="alarm-panel" title="수면 스케줄 설정" description="목표 취침 시간과 기상 시간을 설정하세요."
    busy={busy} onDismiss={onBack}>
    {!draft.desktop_available&&<p className="muted">휴대폰 알람과 푸시 알림은 아직 지원되지 않아요. 취침·기상 목표는 저장할 수 있어요.</p>}
    {proposal?.bedtime&&proposal.wake_time&&coaching&&<div className="soft-info"><div>
      <strong>이 코칭에 저장된 제안</strong><p>{proposal.bedtime} – {proposal.wake_time} · {proposal.timezone}</p><p>{proposal.reason}</p>
      <button type="button" className="button secondary compact" disabled={busy} onClick={()=>{
        setDraft(s=>({...s,bedtime:proposal.bedtime!,wake_time:proposal.wake_time!,timezone:proposal.timezone,coaching_id:coaching.id}));
        setMessage("제안 시간을 불러왔어요. 저장하기를 눌러 적용하세요.");
      }}>제안 시간 불러오기</button>
    </div></div>}
    <form onSubmit={event=>{event.preventDefault();void save();}}>
      <fieldset disabled={busy}>
        <div className="alarm-fields">
          <label><span><Moon size={16} aria-hidden="true"/>취침 목표</span><input type="time" name="bedtime" required value={draft.bedtime} onChange={e=>setDraft(s=>({...s,bedtime:e.target.value,coaching_id:null}))}/></label>
          <label><span><Sun size={16} aria-hidden="true"/>기상 목표</span><input type="time" name="wake_time" required value={draft.wake_time} onChange={e=>setDraft(s=>({...s,wake_time:e.target.value,coaching_id:null}))}/></label>
          <label><span>시간대</span><input name="timezone" required maxLength={80} value={draft.timezone} onChange={e=>setDraft(s=>({...s,timezone:e.target.value,coaching_id:null}))}/></label>
        </div>
        {draft.desktop_available&&<label className="alarm-switch"><input type="checkbox" checked={draft.enabled} onChange={e=>setDraft(s=>({...s,enabled:e.target.checked}))}/> Windows PC 알람 켜기</label>}
        <div className="alarm-actions">
          <button className="button primary">저장하기</button>
          <button type="button" className="button secondary" onClick={onBack}>취소</button>
          {draft.desktop_available&&<button type="button" className="button secondary" onClick={async()=>{
            setBusy(true);setError("");try{await api("alarms/test","POST");setMessage("PC에서 알람 창과 소리를 확인하세요.");}
            catch(e){setError(e instanceof Error?e.message:"시험 알람 오류");}finally{setBusy(false);}
          }}>알람 소리 시험</button>}
        </div>
      </fieldset>
    </form>
    {error&&<p role="alert" className="plan-error">{error}</p>}{message&&<p role="status">{message}</p>}
  </ClassicDialog>;
}
