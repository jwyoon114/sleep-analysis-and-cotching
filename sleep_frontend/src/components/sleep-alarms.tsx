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
    try {const {desktop_available:_,...body}=settings;const s=await api<Settings>("alarms","POST",body);setSettings(s);setMessage(s.enabled?"매일 반복 알람을 저장했어요. PC와 프로그램 서버를 켜 두세요.":"알람을 껐어요. 설정한 시간은 보관됩니다.");}
    catch(e){setMessage(e instanceof Error?e.message:"알람을 저장하지 못했습니다.");}finally{setBusy(false);}
  }
  if (ready && !settings.desktop_available) {
    return <section className="panel alarm-panel">
      <h2><Bell size={19}/> 취침·기상 알림</h2>
      <p className="disclaimer">현재 달잠 웹과 갤럭시 테스트 앱은 휴대폰 알람이나 푸시 알림을 지원하지 않아요.</p>
    </section>;
  }
  return <section className="panel alarm-panel"><div className="panel-heading"><div><h2><Bell size={19}/> 취침·기상 알람</h2><p>AI 제안을 확인하고 내 생활에 맞게 시간을 정하세요.</p></div>{settings.desktop_available&&<span className="tag">매일 반복 · PC 알람</span>}</div>
    {proposal?<div className="soft-info"><div><strong>AI 제안 · {proposal.timezone}</strong><p>취침 {proposal.bedtime||"추가 정보 필요"} / 기상 {proposal.wake_time||"추가 정보 필요"}</p><p>{proposal.reason}</p><button className="button secondary compact" disabled={demo||!ready||busy||!proposal.bedtime||!proposal.wake_time} onClick={()=>{setSettings(s=>({...s,bedtime:proposal.bedtime!,wake_time:proposal.wake_time!,timezone:proposal.timezone,coaching_id:coaching!.id}));setMessage("제안 시간을 불러왔어요. 확인 후 알람을 켜고 저장하세요.");}}>AI 제안 시간 불러오기</button></div></div>:<p className="muted">이 코칭에는 알람 제안 시간이 없습니다. 새 코칭을 생성하거나 시간을 직접 입력하세요.</p>}
    <form onSubmit={e=>{e.preventDefault();void save();}}><div className="alarm-fields"><label><Moon size={16}/> 취침 시간<input type="time" required value={settings.bedtime} onChange={e=>setSettings(s=>({...s,bedtime:e.target.value,coaching_id:null}))}/></label><label><Sun size={16}/> 기상 시간<input type="time" required value={settings.wake_time} onChange={e=>setSettings(s=>({...s,wake_time:e.target.value,coaching_id:null}))}/></label><label>시간대<input required maxLength={80} value={settings.timezone} onChange={e=>setSettings(s=>({...s,timezone:e.target.value,coaching_id:null}))}/></label></div>
    <label className="alarm-switch"><input type="checkbox" checked={settings.enabled} disabled={!settings.desktop_available||demo} onChange={e=>setSettings(s=>({...s,enabled:e.target.checked}))}/> 매일 취침·기상 알람 켜기</label><div className="alarm-actions"><button className="button primary" disabled={!ready||busy||demo}>알람 설정 저장</button><button type="button" className="button secondary" disabled={!ready||busy||demo||!settings.desktop_available} onClick={async()=>{setBusy(true);try{await api("alarms/test","POST");setMessage("PC에서 알람 창과 소리를 확인하세요.");}catch(e){setMessage(e instanceof Error?e.message:"시험 알람 오류");}finally{setBusy(false);}}}>알람 소리 시험</button></div></form>
    <p role="status">{demo?"체험 모드에서는 알람을 저장하거나 울리지 않습니다.":message}</p>{settings.desktop_available&&<p className="disclaimer">Windows용 로컬 달잠이 실행 중일 때 해당 PC에서 알람 창이 열리고 소리가 재생됩니다.</p>}
  </section>;
}
