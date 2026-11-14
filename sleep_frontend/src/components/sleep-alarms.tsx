"use client";

import {useEffect,useState} from "react";
import {Bell, Moon, Sun} from "lucide-react";
import {api,type Coaching} from "@/lib/sleep";

type Settings={bedtime:string;wake_time:string;timezone:string;enabled:boolean;coaching_id?:string|null;desktop_available:boolean};
export default function SleepAlarms({coaching,demo}:{coaching?:Coaching;demo:boolean}) {
  const [settings,setSettings]=useState<Settings>({bedtime:"23:00",wake_time:"07:00",timezone:"Asia/Seoul",enabled:false,desktop_available:false});
  const [ready,setReady]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState("");
  const proposal=coaching?.context?.alarm_schedule;
  useEffect(()=>{
    if(demo)return;
    const c=new AbortController();
    api<Settings>("alarms","GET",undefined,c.signal).then(s=>{setSettings(s);setReady(true);}).catch(e=>{if(e.name!=="AbortError")setMessage(e.message);});
    return()=>c.abort();
  },[demo]);
  async function save(){
    setBusy(true);setMessage("");
    try {const {bedtime,wake_time,timezone,coaching_id}=settings;const s=await api<Settings>("alarms","POST",{bedtime,wake_time,timezone,coaching_id,enabled:settings.desktop_available&&settings.enabled});setSettings(s);setMessage("취침·기상 목표를 저장했어요.");}
    catch(e){setMessage(e instanceof Error?e.message:"알람을 저장하지 못했습니다.");}finally{setBusy(false);}
  }
  return <section className="panel alarm-panel"><div className="panel-heading"><div><h2><Bell size={19}/> 수면 스케줄</h2><p>목표 취침 시간과 기상 시간을 설정하세요.</p></div></div>
    {proposal?.bedtime&&proposal.wake_time&&coaching&&<div className="soft-info"><div><strong>이 코칭에 저장된 제안</strong><p>{proposal.bedtime} – {proposal.wake_time} · {proposal.timezone}</p><p>{proposal.reason}</p><button type="button" className="button secondary compact" disabled={!ready||busy||demo} onClick={()=>{setSettings(s=>({...s,bedtime:proposal.bedtime!,wake_time:proposal.wake_time!,timezone:proposal.timezone,coaching_id:coaching.id}));setMessage("제안 시간을 불러왔어요. 저장하기를 눌러 적용하세요.");}}>제안 시간 불러오기</button></div></div>}
    <form onSubmit={e=>{e.preventDefault();void save();}}>
      <fieldset disabled={(!ready&&!demo)||busy}>
        <div className="alarm-fields"><label><Moon size={16}/> 취침 목표<input type="time" required value={settings.bedtime} onChange={e=>setSettings(s=>({...s,bedtime:e.target.value,coaching_id:null}))}/></label><label><Sun size={16}/> 기상 목표<input type="time" required value={settings.wake_time} onChange={e=>setSettings(s=>({...s,wake_time:e.target.value,coaching_id:null}))}/></label><label>시간대<input required maxLength={80} value={settings.timezone} onChange={e=>setSettings(s=>({...s,timezone:e.target.value,coaching_id:null}))}/></label></div>
        {settings.desktop_available&&<label className="alarm-switch"><input type="checkbox" checked={settings.enabled} onChange={e=>setSettings(s=>({...s,enabled:e.target.checked}))}/> Windows PC 알람 켜기</label>}
        <div className="alarm-actions"><button className="button primary" disabled={!ready||busy||demo}>저장하기</button>{settings.desktop_available&&<button type="button" className="button secondary" disabled={!ready||busy||demo} onClick={async()=>{setBusy(true);try{await api("alarms/test","POST");setMessage("PC에서 알람 창과 소리를 확인하세요.");}catch(e){setMessage(e instanceof Error?e.message:"시험 알람 오류");}finally{setBusy(false);}}}>알람 소리 시험</button>}</div>
      </fieldset>
    </form>
    <p role="status">{demo?"체험 모드에서는 목표 시간을 저장하지 않아요.":message||(!ready?"설정을 불러오는 중이에요.":"")}</p>
  </section>;
}
