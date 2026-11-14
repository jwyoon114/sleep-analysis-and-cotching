"use client";

import {useCallback, useEffect, useMemo, useRef, useState, type FormEvent} from "react";
import {ArrowDown, ArrowDownToLine, ArrowLeft, ArrowRight, ArrowUpRight, CalendarDays, Check, ChevronDown, ChevronRight, CircleHelp, Clock3, CloudUpload, Coffee, FileJson, FileText, Heart, LayoutDashboard, LoaderCircle, LogOut, Menu, Moon, Plus, RotateCcw, Settings2, ShieldCheck, Sparkles, Sun, Trash2, TrendingUp, X, type LucideIcon} from "lucide-react";
import {api, ApiError, clock, colors, compare, daily, labels, minutes, shortDate, today, type Coaching, type Daily, type SleepRecord, type Stage, type Trash, type User} from "@/lib/sleep";
import {demoCoaching, demoRecords} from "@/lib/demo";
import {coachingDataNotes} from "@/lib/coaching-body";
import RegistrationConsent from "./registration-consent";
import SleepTimeline from "./sleep-timeline";
import SleepDashboard from "./sleep-dashboard";
import SleepAlarms from "./sleep-alarms";
import HealthConnect, {stopNativeHealth} from "./health-connect";
import CoachingStylePreview, { CoachingAdvice } from "./coaching-style-preview";
import type { CharacterId, MbtiType } from "@/lib/coaching-preview";

type Page = "dashboard" | "records" | "coaching" | "comparison" | "trash" | "account";
type Confirmation = {title:string; description:string; permanent?:boolean; run:()=>Promise<void>};
type CoachingHistory = {recordId:string; status:"loading"|"ready"|"error"; items:Coaching[]};
type CoachingRequestState = {recordId:string; kind:"submitting"} | {recordId:string; kind:"error"; status:number|null};
const navigation: {id:Page;label:string;icon:LucideIcon}[] = [
  {id:"dashboard",label:"수면 대시보드",icon:LayoutDashboard},
  {id:"records",label:"분석 기록",icon:Moon},
  {id:"coaching",label:"AI 수면 코칭",icon:Sparkles},
  {id:"comparison",label:"기간별 비교",icon:TrendingUp},
];
const titles: Record<Page,[string,string]> = {dashboard:["수면 대시보드",""],records:["차곡차곡 쌓인 나의 밤","기록을 선택해 수면 흐름을 자세히 살펴보세요."],coaching:["나를 위한 수면 코칭","기록과 일상에서, 나에게 맞는 작은 변화를 찾아보세요."],comparison:["시간이 보여 주는 나의 변화","이번 기간과 이전 기간의 수면 패턴을 비교해 보세요."],trash:["휴지통과 백업","삭제한 기록은 30일 동안 다시 복원할 수 있어요."],account:["나의 계정","계정 정보와 소중한 기록을 관리하세요."]};

function Mark({small=false}:{small?:boolean}) {return <div className={`brand ${small?"brand-small":""}`}><span className="brand-icon"><Moon size={small?21:24} strokeWidth={1.6}/><i/></span><span>달잠<small>나의 수면 리포트</small></span></div>;}
function Busy({text="불러오는 중"}:{text?:string}) {return <span className="busy"><LoaderCircle size={17} className="spin"/>{text}</span>;}
function Empty({title,children}:{title:string;children:React.ReactNode}) {return <div className="empty"><span className="empty-icon"><Moon size={28}/></span><h3>{title}</h3><div>{children}</div></div>;}
function Tag({children}:{children:React.ReactNode}) {return <span className="tag">{children}</span>;}

function coachingDate(value: string): string | null {
  if(typeof value!=="string"||!value.trim())return null;
  const date=new Date(value);
  return Number.isFinite(date.getTime()) ? date.toLocaleString("ko-KR") : null;
}

function SleepChart({rows,large=false}:{rows:Daily[];large?:boolean}) {
  const max = Math.max(600,...rows.map(r=>r.asleep_minutes||0));
  return <div className={`sleep-chart ${large?"chart-large":""}`} role="img" aria-label="날짜별 수면 시간 막대 그래프. 기록이 없는 날짜는 비워 표시합니다.">
    <div className="chart-axis">{[1,.75,.5,.25].map(n=><span key={n}>{Math.round(max*n/60)}h</span>)}</div>
    <div className="chart-plot"><div className="grid-lines">{[0,1,2,3].map(i=><i key={i}/>)}</div><div className="chart-columns">{rows.map((r,i)=><div className="chart-column" key={r.date}><div className="bar-slot">{r.asleep_minutes!=null?<div className={`chart-bar ${i===rows.length-1?"latest":""}`} style={{height:`${Math.max(1,r.asleep_minutes/max*100)}%`}} tabIndex={0} aria-label={`${r.date} ${minutes(r.asleep_minutes)}`}><span className="chart-tooltip">{shortDate(r.date)}<strong>{minutes(r.asleep_minutes)}</strong></span></div>:<span className="no-record" title={`${r.date} 기록 없음`}>·</span>}</div><span className="chart-date">{rows.length<=7?new Date(r.date+"T12:00:00").toLocaleDateString("ko-KR",{weekday:"short"}):i%5===0||i===rows.length-1?r.date.slice(8):""}</span><small>{rows.length<=7?r.date.slice(5).replace("-","."):""}</small></div>)}</div></div>
  </div>;
}

function StageChart({record}:{record:SleepRecord}) {
  const total = Object.values(record.stage_minutes).reduce((s,n)=>s+n,0)||1;
  const stages: Stage[] = ["deep","core","rem","wake","unspecified"];
  return <><div className="stage-total">{stages.filter(s=>record.stage_minutes[s]>0).map(s=><div key={s} style={{width:`${record.stage_minutes[s]/total*100}%`,background:colors[s]}} title={`${labels[s]} ${minutes(record.stage_minutes[s])}`}/>)}</div><div className="stage-legend">{stages.filter(s=>record.stage_minutes[s]>0).map(s=><div key={s}><span><i style={{background:colors[s]}}/>{labels[s]}</span><strong>{minutes(record.stage_minutes[s])}</strong></div>)}</div></>;
}

function Auth({onLogin,onDemo,error:connectionError,status}:{onLogin:(u:User)=>void;onDemo:()=>void;error:string;status?:string}) {
  const [register,setRegister]=useState(false),[error,setError]=useState(""),[busy,setBusy]=useState(false);
  async function submit(e:FormEvent<HTMLFormElement>) {
    e.preventDefault();setBusy(true);setError("");
    const data=new FormData(e.currentTarget),username=String(data.get("username")||""),password=String(data.get("password")||"");
    try {
      if(register) {if(password!==data.get("confirmation")) throw new Error("비밀번호 확인이 일치하지 않습니다."); await api("auth/register","POST",{username,password,privacy_consent:data.get("privacy_consent")==="on",health_consent:data.get("health_consent")==="on",overseas_consent:data.get("overseas_consent")==="on",adult_confirmed:data.get("adult_confirmed")==="on",policy_version:String(data.get("policy_version")||"")});}
      const result=await api<{user:User}>("auth/login","POST",{username,password});onLogin(result.user);
    } catch(err) {setError(err instanceof Error?err.message:"로그인을 확인해 주세요.");}finally{setBusy(false);}
  }
  return <main className="auth-page"><section className="auth-story"><Mark/><div className="auth-copy"><Tag>BETTER NIGHTS, BRIGHTER DAYS</Tag><h1>오늘 밤의 기록이,<br/>내일의 나를<br/><em>더 편안하게.</em></h1><p>나의 수면을 이해하는 가장 다정한 방법.<br/>기록부터 나에게 맞는 작은 습관까지, 달잠과 함께해요.</p></div><div className="night-art" aria-hidden="true"><div className="moon-glow"/><div className="art-moon"/><i className="star s1">✧</i><i className="star s2">✦</i><i className="star s3">✧</i><div className="hill hill1"/><div className="hill hill2"/><div className="hill hill3"/><div className="art-caption"><Moon size={15}/> A LITTLE CLOSER TO A RESTFUL NIGHT</div></div><div className="auth-trust"><ShieldCheck size={17}/>기록은 계정별로 안전하게 분리됩니다.</div></section><section className="auth-form-side"><div className="auth-mobile-brand"><Mark/></div><div className="auth-form-card"><div className="eyebrow"><span/>YOUR PERSONAL SLEEP JOURNAL</div><h2>{register?"나만의 수면 여정 시작하기":"반가워요, 잘 쉬셨나요?"}</h2><p>{register?"계정을 만들고 나의 밤을 기록해 보세요.":"로그인하고 나의 밤 이야기를 이어가세요."}</p>{status&&<div className="auth-success" role="status"><Check size={15}/>{status}</div>}<div className="auth-tabs"><button className={!register?"active":""} onClick={()=>{setRegister(false);setError("");}}>로그인</button><button className={register?"active":""} onClick={()=>{setRegister(true);setError("");}}>회원가입</button></div><form onSubmit={submit} key={String(register)}><label>아이디<input name="username" autoComplete="username" required minLength={3} maxLength={40} placeholder="아이디를 입력해 주세요"/></label><label>비밀번호<input name="password" type="password" autoComplete={register?"new-password":"current-password"} required minLength={register?10:1} maxLength={128} placeholder={register?"10자 이상의 비밀번호":"비밀번호를 입력해 주세요"}/></label>{register&&<label>비밀번호 확인<input name="confirmation" type="password" autoComplete="new-password" required minLength={10} maxLength={128} placeholder="한 번 더 입력해 주세요"/></label>}{register&&<RegistrationConsent/>}{(error||connectionError)&&<div className="error" role="alert">{error||connectionError}</div>}<button className="button primary auth-submit" disabled={busy}>{busy?<Busy text="확인 중"/>:register?"계정 만들고 시작하기":"나의 수면 리포트 열기"}<ArrowRight size={18}/></button></form><div className="auth-divider"><span>달잠이 처음이라면</span></div><button className="button demo-button" onClick={onDemo}><Sparkles size={17}/>가상 기록으로 먼저 둘러보기<ArrowUpRight size={16}/></button><p className="auth-footnote">체험 모드에는 실제 건강 정보가 포함되지 않습니다.<br/>웨어러블 기록은 의학적 진단을 대신하지 않아요.</p></div><span className="auth-bottom">조금 더 나은 밤, 조금 더 가벼운 아침.</span></section></main>;
}

export default function SleepApp() {
  const [boot,setBoot]=useState(true),[user,setUser]=useState<User|null>(null),[demo,setDemo]=useState(false);
  const [page,setPage]=useState<Page>("dashboard"),[mobile,setMobile]=useState(false),[records,setRecords]=useState<SleepRecord[]>([]),[selected,setSelected]=useState("");
  const [coachHistory,setCoachHistory]=useState<CoachingHistory|null>(null);
  const [coachRequest,setCoachRequest]=useState<CoachingRequestState|null>(null);
  const [coachingId,setCoachingId]=useState(""),[trash,setTrash]=useState<Trash>({sessions:[],coaching:[]});
  const [mbti, setMbti] = useState<MbtiType | null>(null);
  const [characterId, setCharacterId] = useState<CharacterId>("cat");
  const [loading,setLoading]=useState(false),[busy,setBusy]=useState(false),[revision,setRevision]=useState(0);
  const [coachingRevision,setCoachingRevision]=useState(0);
  const [error,setError]=useState(""),[notice,setNotice]=useState(""),[days,setDays]=useState(7),[end,setEnd]=useState(today),[query,setQuery]=useState("");
  const [upload,setUpload]=useState(false),[file,setFile]=useState<File|null>(null),[dragging,setDragging]=useState(false),[confirmation,setConfirmation]=useState<Confirmation|null>(null),[phrase,setPhrase]=useState("");
  const [backup,setBackup]=useState<{backup_count:number;retention_days:number;pending:number}|null>(null);
  const fileInput=useRef<HTMLInputElement>(null);
  const latest=records[0];
  const coachingRecordId=page==="dashboard" ? latest?.analysis_id : selected;
  const healthSynced=useCallback(()=>setRevision(n=>n+1),[]);
  const reset=useCallback(()=>{setUser(null);setDemo(false);setRecords([]);setCoachHistory(null);setCoachRequest(null);setCoachingId("");setTrash({sessions:[],coaching:[]});setSelected("");setPage("dashboard");setBackup(null);setUpload(false);setConfirmation(null);setMbti(null);setCharacterId("cat");},[]);
  useEffect(()=>{if(new URLSearchParams(window.location.search).get("demo")==="1"){setDemo(true);setUser({id:"demo",username:"체험"});setBoot(false);return;} const c=new AbortController();api<{user:User}>("auth/me","GET",undefined,c.signal).then(r=>setUser(r.user)).catch(e=>{if(e.name!=="AbortError"&&e.status!==401)setError(e.message);}).finally(()=>setBoot(false));return()=>c.abort();},[]);
  useEffect(()=>{if(!notice)return;const t=setTimeout(()=>setNotice(""),6000);return()=>clearTimeout(t);},[notice]);
  useEffect(()=>{
    if(!user)return;
    if(demo){const r=demoRecords();setRecords(r);setSelected(s=>s||r[0].analysis_id);return;}
    const c=new AbortController();setLoading(true);
    api<{sessions:SleepRecord[]}>("watch/sessions","GET",undefined,c.signal).then(r=>{setRecords(r.sessions);setSelected(s=>r.sessions.some(v=>v.analysis_id===s)?s:r.sessions[0]?.analysis_id||"");}).catch(e=>{if(e.name==="AbortError")return;if(e.status===401)reset();setError(e.message);}).finally(()=>{if(!c.signal.aborted)setLoading(false);});return()=>c.abort();
  },[user,demo,revision,reset]);
  useEffect(()=>{
    if(!coachingRecordId||!user)return;
    if(demo){setCoachHistory({recordId:coachingRecordId,status:"ready",items:[demoCoaching]});setCoachingId(demoCoaching.id);return;}
    const c=new AbortController();
    setCoachHistory({recordId:coachingRecordId,status:"loading",items:[]});
    api<{history:Coaching[]}>(`watch/sessions/${coachingRecordId}/coaching`,"GET",undefined,c.signal).then(result=>{
      if(c.signal.aborted)return;
      if(!Array.isArray(result?.history))throw new Error("Invalid coaching history");
      setCoachHistory({recordId:coachingRecordId,status:"ready",items:result.history});
      setCoachingId(id=>result.history.some(item=>item.id===id)?id:result.history[0]?.id||"");
    }).catch(error=>{
      if(c.signal.aborted)return;
      if(error instanceof ApiError&&error.status===401){reset();setError(error.message);return;}
      setCoachHistory({recordId:coachingRecordId,status:"error",items:[]});
    });
    return()=>c.abort();
  },[coachingRecordId,user,demo,revision,coachingRevision,reset]);
  useEffect(()=>{
    if(page!=="trash"||!user)return;if(demo){setTrash({sessions:[],coaching:[]});return;}
    const c=new AbortController();setLoading(true);Promise.all([api<Trash>("watch/trash","GET",undefined,c.signal),api<{backup_count:number;retention_days:number;pending:number}>("watch/backup-policy","GET",undefined,c.signal)]).then(([t,b])=>{setTrash(t);setBackup(b);}).catch(e=>{if(e.name!=="AbortError"){if(e.status===401)reset();setError(e.message);}}).finally(()=>{if(!c.signal.aborted)setLoading(false);});return()=>c.abort();
  },[page,user,demo,revision,reset]);
  useEffect(()=>{
    if(!upload&&!confirmation)return;
    const previous=document.activeElement as HTMLElement|null;
    const dialog=document.querySelector<HTMLElement>('[role="dialog"],[role="alertdialog"]');
    const overflow=document.body.style.overflow;
    document.body.style.overflow="hidden";
    const controls=()=>Array.from(dialog?.querySelectorAll<HTMLElement>('button:not([disabled]),input:not([disabled]):not([type="file"]),select:not([disabled])')||[]).filter(e=>e.getClientRects().length);
    const frame=requestAnimationFrame(()=>controls()[0]?.focus());
    const close=(e:KeyboardEvent)=>{
      if(e.key==="Escape"&&!busy){setUpload(false);setConfirmation(null);}
      if(e.key==="Tab"){
        const items=controls(),first=items[0],last=items.at(-1);
        if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}
        else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}
      }
    };
    window.addEventListener("keydown",close);
    return()=>{cancelAnimationFrame(frame);window.removeEventListener("keydown",close);document.body.style.overflow=overflow;previous?.focus();};
  },[upload,confirmation,busy]);
  const record=records.find(s=>s.analysis_id===selected);
  const dashboardHistory=latest && coachHistory?.recordId===latest.analysis_id ? coachHistory : null;
  const dashboardCoaching=dashboardHistory?.items[0];
  const rows=useMemo(()=>daily(records,end,days),[records,end,days]);
  const comparison=useMemo(()=>compare(records,end,days),[records,end,days]);
  const average=comparison.current.average_asleep_minutes_per_recorded_day;
  const history=coachHistory?.recordId===selected ? coachHistory : null;
  const coaching=history?.items ?? [];
  const coachLoading=!!selected && (history===null || history.status==="loading");
  const saved=coaching.find(c=>c.id===coachingId)||coaching[0];
  const activeRequest=coachRequest?.recordId===selected ? coachRequest : null;
  const requestInFlight=activeRequest?.kind==="submitting";
  const requestFailure=activeRequest?.kind==="error" ? activeRequest : null;
  const savedDate=saved ? coachingDate(saved.created_at) : null;
  const savedNotes=saved && page==="coaching" ? coachingDataNotes(saved.coaching,saved.context) : [];
  let recordNote="";
  if(record){
    if(!Number.isFinite(record.asleep_minutes)||record.asleep_minutes<0){
      recordNote="선택한 기록에서 수면 시간을 확인할 수 없어요. 기기 앱에서 기록을 확인해 주세요.";
    }else if(Number.isFinite(record.unrecorded_minutes)&&record.unrecorded_minutes>0){
      recordNote="선택한 수면 기록에는 기록이 비어 있는 구간이 있어요.";
    }
  }

  function reloadCoachingHistory(){setCoachingRevision(n=>n+1);}

  async function requestCoaching(event:FormEvent<HTMLFormElement>){
    event.preventDefault();
    if(busy||coachLoading||!record)return;
    if(demo){setNotice("체험 모드예요. 로그인하면 내 수면 기록으로 조언을 요청할 수 있어요.");return;}
    const recordId=record.analysis_id;
    const lifestyle=Object.fromEntries(new FormData(event.currentTarget));
    setBusy(true);
    setError("");
    setCoachRequest({recordId,kind:"submitting"});
    try{
      const result=await api<Pick<Coaching,"id">>("coach","POST",{analysis_id:recordId,...lifestyle});
      if(typeof result?.id!=="string"||!result.id)throw new Error("Invalid coaching response");
      setCoachingId(result.id);
      setCoachRequest(null);
      setRevision(n=>n+1);
      setNotice("새 수면 조언을 저장했어요.");
    }catch(error){
      if(error instanceof ApiError&&error.status===401){reset();setError(error.message);return;}
      setCoachRequest({recordId,kind:"error",status:error instanceof ApiError?error.status:null});
    }finally{setBusy(false);}
  }
  function navigate(p:Page){setPage(p);setMobile(false);setError("");if(p==="dashboard"&&records[0])setSelected(records[0].analysis_id);}
  function openDashboardPage(destination:"records"|"comparison"|"coaching"){
    if(latest && destination!=="comparison")setSelected(latest.analysis_id);
    if(destination==="coaching" && dashboardCoaching)setCoachingId(dashboardCoaching.id);
    navigate(destination);
    window.scrollTo(0,0);
  }
  async function perform(run:()=>Promise<void>,message?:string){if(demo){setNotice("체험 모드예요. 로그인하면 나의 기록을 저장하고 관리할 수 있어요.");return false;}setBusy(true);setError("");try{await run();if(message)setNotice(message);return true;}catch(e){if(e instanceof ApiError&&e.status===401)reset();setError(e instanceof Error?e.message:"다시 시도해 주세요.");return false;}finally{setBusy(false);}}
  function ask(title:string,description:string,run:()=>Promise<void>,permanent=false){if(demo){setNotice("체험 기록은 수정되지 않아요. 로그인 후 내 기록을 관리해 주세요.");return;}setPhrase("");setConfirmation({title,description,run,permanent});}
  function chooseFile(f:File|undefined){if(!f)return;if(!/\.(md|json)$/i.test(f.name)){setError("수면 기록 .md 또는 .json 파일을 선택해 주세요.");return;}if(f.size>4*1024*1024){setError("파일은 4MiB 이하여야 합니다.");return;}setError("");setFile(f);}
  function openUpload(){if(demo){setNotice("체험 모드에서는 가상 기록을 보여 드려요. 로그인을 하면 내 파일을 분석할 수 있습니다.");return;}setFile(null);setError("");setUpload(true);}
  async function importFile(){if(!file)return;const form=new FormData();form.set("file",file);await perform(async()=>{const r=await api<{added_sessions:number;analysis_ids:string[]}>("analyze","POST",form);setUpload(false);setSelected(r.analysis_ids[0]||"");setRevision(n=>n+1);setPage("records");setNotice(r.added_sessions?"수면 기록을 분석하고 저장했어요.":"이미 저장된 기록이에요. 기존 분석을 열었어요.");});}
  function exportRecord(){if(!record)return;const segments=record.segments.map(({start,end,stage})=>({start,end,stage}));const text=JSON.stringify({schema_version:1,timezone:record.timezone,source:record.source,sessions:[{start:record.start,end:record.end,segments,vitals_summary:record.vitals_summary}]},null,2);const url=URL.createObjectURL(new Blob([text],{type:"application/json"}));const a=document.createElement("a");a.href=url;a.download=`sleep-${record.start.slice(0,10)}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  if(boot)return <div className="boot"><Mark/><Busy text="나의 수면 공간을 준비하고 있어요"/></div>;
  if(!user)return <Auth onLogin={u=>{setError("");setUser(u);}} onDemo={()=>{setDemo(true);setUser({id:"demo",username:"체험"});setError("");}} error={error} status={notice}/>;

  const recordSelector=<select aria-label="분석할 수면 기록" value={selected} onChange={e=>setSelected(e.target.value)}>{records.map(r=><option key={r.analysis_id} value={r.analysis_id}>{shortDate(r.start)} · {clock(r.start)} · {minutes(r.asleep_minutes)}</option>)}</select>;

  return <div className={`app-shell${page==="dashboard"?" dashboard-shell":""}`}>
    {mobile&&<div className="mobile-scrim" onClick={()=>setMobile(false)}/>}
    <aside className={`sidebar ${mobile?"open":""}`}><Mark/><button className="sidebar-close icon-button" onClick={()=>setMobile(false)} aria-label="메뉴 닫기"><X size={20}/></button><div className="nav-caption">MY SLEEP SPACE</div><nav aria-label="주요 메뉴">{navigation.map(({id,label,icon:Icon})=><button key={id} className={`nav-item ${page===id?"active":""}`} onClick={()=>navigate(id)}><Icon size={19} strokeWidth={1.65}/>{label}{id==="coaching"&&<span className="ai-label">AI</span>}{page===id&&<i/>}</button>)}</nav><div className="sidebar-note"><div className="little-moon"><Moon size={23}/><span>✧</span></div><strong>잘 쉬는 것도, 나를 위한 일.</strong><p>오늘도 나만의 속도로<br/>편안한 밤을 준비해 보세요.</p></div><div className="sidebar-bottom"><button className={`nav-item ${page==="trash"?"active":""}`} onClick={()=>navigate("trash")}><Trash2 size={18}/>휴지통·백업</button><button className={`nav-item ${page==="account"?"active":""}`} onClick={()=>navigate("account")}><Settings2 size={18}/>계정 설정</button><div className="profile"><span className="avatar">{user.username.slice(0,1).toUpperCase()}</span><div><strong>{user.username} 님</strong><small>{demo?"가상 기록 체험 중":"나만의 수면 공간"}</small></div><button className="icon-button" aria-label={demo?"체험 종료":"로그아웃"} onClick={()=>{if(demo){reset();window.history.replaceState(null,"",window.location.pathname);}else perform(async()=>{if(window.DaljamNative){await stopNativeHealth();await api("watch/health/connection","DELETE").catch(()=>{});}await api("auth/logout","POST");reset();});}} disabled={busy}><LogOut size={17}/></button></div></div></aside>
    <div className="main-shell"><header className="topbar"><div className="topbar-left"><button className="icon-button mobile-toggle" onClick={()=>setMobile(true)} aria-label="메뉴 열기"><Menu size={22}/></button><span className="topbar-label">나의 수면 공간</span><ChevronRight size={13}/><strong>{page==="trash"?"휴지통·백업":page==="account"?"계정 설정":navigation.find(n=>n.id===page)?.label}</strong></div><div className="topbar-right">{demo&&<span className="demo-pill"><span/>체험 모드 · 가상 데이터</span>}<span className="today"><CalendarDays size={15}/>{today().replaceAll("-",". ")}</span><button className="help-button icon-button" aria-label="사용 안내" onClick={()=>setNotice("MD·JSON 수면 기록을 추가하면 분석할 수 있어요. AI 코칭은 별도 생성 버튼을 눌러야 요청됩니다.")}><CircleHelp size={18}/></button></div></header>
    <main className="content"><div className={`page-heading${page==="dashboard"?" dashboard-page-heading":""}`}><div>{page!=="dashboard"&&<div className="eyebrow">YOUR PERSONAL SLEEP JOURNAL</div>}<h1>{titles[page][0]}<span className="heading-dot">.</span></h1>{titles[page][1]&&<p>{titles[page][1]}</p>}</div><button className="button primary" onClick={openUpload} disabled={busy}><Plus size={18}/>수면 기록 추가</button></div>
    {demo&&<div className="demo-banner"><Sparkles size={16}/><span>지금은 가상의 기록을 보고 있어요. 실제 수면 분석이나 AI 생성 결과가 아닙니다.</span><button onClick={()=>{reset();window.history.replaceState(null,"",window.location.pathname);}}>내 기록으로 시작하기<ArrowRight size={14}/></button></div>}
    {error&&<div className="error inline-alert" role="alert"><span>{error}</span><button className="icon-button" onClick={()=>setError("")} aria-label="오류 메시지 닫기"><X size={17}/></button></div>}
    {notice&&<div className="toast" role="status"><Check size={17}/>{notice}<button className="icon-button" aria-label="알림 닫기" onClick={()=>setNotice("")}><X size={15}/></button></div>}

    {page==="dashboard"&&<SleepDashboard
      record={latest}
      recordsLoading={loading}
      coaching={dashboardCoaching}
      coachingStatus={dashboardHistory?.status ?? "loading"}
      onUpload={openUpload}
      onRecord={()=>openDashboardPage("records")}
      onCoaching={()=>openDashboardPage("coaching")}
      onRetryCoaching={reloadCoachingHistory}
      onCompare={()=>openDashboardPage("comparison")}
      onMorningPlan={()=>setNotice("내일 아침 계획 기능은 준비 중이에요.")}
    />}

    {!demo&&(page==="dashboard"||page==="account")&&<HealthConnect user={user} onSynced={healthSynced}/>}

    {page==="records"&&<div className="records-layout"><section className="panel records-list"><div className="panel-heading"><h2>나의 기록 <span className="count">{records.length}</span></h2></div><label className="search-field"><CalendarDays size={16}/><input aria-label="기록 날짜 검색" placeholder="날짜 검색 (예: 11-06)" value={query} onChange={e=>setQuery(e.target.value)}/></label>{loading?<Busy/>:records.filter(r=>r.start.slice(0,10).includes(query)).map(r=><button key={r.analysis_id} className={`list-record ${selected===r.analysis_id?"selected":""}`} onClick={()=>setSelected(r.analysis_id)}><span className="record-moon"><Moon size={19}/></span><span><strong>{shortDate(r.start)}</strong><small>{clock(r.start)} – {clock(r.end)}</small></span><span><b>{minutes(r.asleep_minutes)}</b><small>코칭 {r.coaching_count||0}건</small></span></button>)}{!records.filter(r=>r.start.slice(0,10).includes(query)).length&&<p className="muted padded">표시할 기록이 없습니다.</p>}</section><section className="panel record-detail">{record?<><div className="panel-heading"><div><Tag>SLEEP REPORT</Tag><h2 className="detail-title">{shortDate(record.start)}의 밤</h2><p>{clock(record.start)} – {clock(record.end)} · {record.timezone}</p></div><button className="icon-button" onClick={exportRecord} aria-label="선택 기록 JSON 다운로드"><ArrowDownToLine size={19}/></button></div><div className="detail-metrics"><div><span>수면 시간</span><strong>{minutes(record.asleep_minutes)}</strong></div><div><span>각성 시간</span><strong>{minutes(record.awake_minutes)}</strong></div><div><span>각성 구간</span><strong>{record.wake_segment_count}<small> 회</small></strong></div></div><SleepTimeline key={record.analysis_id} record={record}/><h3 className="section-subtitle">수면 단계별 시간</h3><StageChart record={record}/><details><summary>수면·각성 구간 전체 보기<ChevronDown size={16}/></summary><div className="table-scroll"><table><thead><tr><th>시작</th><th>종료</th><th>단계</th><th>분</th></tr></thead><tbody>{record.segments.map((s,i)=><tr key={i}><td>{clock(s.start)}</td><td>{clock(s.end)}</td><td><span className="table-dot" style={{background:colors[s.stage]}}/>{labels[s.stage]}</td><td>{Math.round(s.minutes)}</td></tr>)}</tbody></table></div></details><h3 className="section-subtitle">함께 측정된 생체지표</h3>{record.vitals_summary.length?<div className="vitals-grid">{record.vitals_summary.map((v,i)=><div key={i}><Heart size={16}/><span>{({heartRate:"심박수",hrvSDNN:"심박변이도",respiratoryRate:"호흡수",oxygenSaturation:"산소포화도"} as Record<string,string>)[v.metric]||v.metric}</span><strong>{v.avg} <small>{v.unit}</small></strong><small>표본 {v.n}개 · {v.min}–{v.max}</small></div>)}</div>:<p className="muted">이 기록에는 생체지표 요약이 없습니다.</p>}{record.unrecorded_minutes>0&&<div className="soft-warning">미기록 구간 {minutes(record.unrecorded_minutes)}이 있습니다.</div>}{record.warnings?.map((w,i)=><div className="soft-warning" key={i}>{w}</div>)}<div className="detail-actions"><button className="button secondary" onClick={()=>navigate("coaching")}><Sparkles size={16}/>이 기록의 AI 코칭</button><button className="text-button danger" disabled={busy} onClick={()=>ask("분석 기록을 휴지통으로 옮길까요?","연결된 AI 코칭도 함께 숨겨지며, 30일 안에 복원할 수 있습니다.",async()=>{await api(`watch/sessions/${selected}`,"DELETE");setRevision(n=>n+1);})}><Trash2 size={15}/>기록 삭제</button></div><p className="disclaimer">웨어러블 기기의 추정 기록이며, 수면검사나 진단 결과가 아닙니다.</p></>:<Empty title="어떤 밤을 살펴볼까요?"><p>수면 기록을 추가하거나 왼쪽 기록을 선택해 주세요.</p></Empty>}</section></div>}

    {page==="coaching"&&<>
      <CoachingStylePreview mbti={mbti} characterId={characterId} onMbtiChange={setMbti} onCharacterChange={setCharacterId}/>
      <SleepAlarms key={user.id} coaching={saved} demo={demo}/>
      {records.length ? <>
        <div className="coaching-toolbar">
          <label>함께 살펴볼 수면 기록{recordSelector}</label>
          <span className="privacy-note"><ShieldCheck size={15}/>수면 기록 기반 조언</span>
        </div>
        <div className="coach-layout">
          <section className="panel coach-form-panel">
            <div className="panel-heading"><div><span className="eyebrow">A LITTLE ABOUT YOUR DAY</span><h2>오늘의 나를 알려주세요</h2><p>입력한 생활습관을 코칭에 참고해요.</p></div></div>
            <form onSubmit={requestCoaching}>
              {[{name:"age_group",label:"연령 구분",icon:Sun,options:["미입력","성인","미성년자"]},{name:"caffeine",label:"취침 전 6시간 이내 카페인",icon:Coffee,options:["미입력","없음","있음"]},{name:"regularity",label:"평소 취침·기상 시간",icon:Clock3,options:["미입력","대체로 일정함","자주 달라짐"]},{name:"satisfaction",label:"나의 수면 만족도",icon:Moon,options:["미입력","좋음","보통","나쁨"]}].map(({name,label,icon:Icon,options})=>
                <label key={name}><span><Icon size={16}/>{label}</span><select name={name}>{options.map(o=><option key={o}>{o}</option>)}</select></label>
              )}
              <div className="soft-info"><ShieldCheck size={15}/><p>기본 조언은 달잠 서버에서 기록과 생활습관을 분석해 생성합니다. 서버에서 OpenAI 방식을 활성화한 경우 기록 요약과 입력이 전송되며 API 사용료가 발생할 수 있어요.</p></div>
              {recordNote && <p className="coaching-data-guide">{recordNote}</p>}
              {requestFailure && <div className="error coaching-request-error" role="alert">
                <strong>조언 요청에 문제가 있었어요</strong>
                <p>{requestFailure.status===429
                  ? "요청 한도에 도달했어요. 잠시 뒤 같은 입력으로 다시 요청해 주세요."
                  : requestFailure.status===404
                    ? "선택한 수면 기록을 찾지 못했어요. 수면 기록을 다시 선택해 주세요."
                    : "결과를 확인하지 못했어요. 저장된 조언을 다시 불러와 확인한 뒤 필요하면 다시 요청해 주세요."}</p>
                {requestFailure.status!==429 && requestFailure.status!==404 && <button type="button" className="text-button" disabled={busy||coachLoading} onClick={reloadCoachingHistory}>저장된 조언 다시 불러오기</button>}
              </div>}
              <button type="submit" className="button primary full" disabled={busy||coachLoading||!record}>
                {requestInFlight ? <Busy text="코칭을 작성하고 있어요"/> : <><Sparkles size={17}/>{requestFailure ? "조언 다시 요청하기" : "나에게 맞는 코칭 생성"}</>}
              </button>
            </form>
          </section>
          <section className="panel saved-coaching">
            <div className="panel-heading"><div className="inline-title"><span className="spark-icon"><Sparkles size={19}/></span><h2>나의 수면 코칭</h2></div><Tag>PERSONAL COACH</Tag></div>
            {!demo && <aside className="coaching-data-guide" aria-label="수면 수치 안내">
              <strong>기기가 추정한 수면 수치예요</strong>
              <p>수면·각성 시간은 기기가 분류한 구간을 바탕으로 한 추정치예요. 수면 기록을 이해하는 데 참고해 주세요.</p>
            </aside>}
            {coaching.length>0 && <label className="history-selector">저장된 코칭 {coaching.length}건<select value={coachingId} onChange={e=>setCoachingId(e.target.value)}>{coaching.map((c,index)=><option value={c.id} key={c.id}>{demo?"가상 체험용 코칭":coachingDate(c.created_at) ?? `저장된 조언 ${index+1}`}</option>)}</select></label>}
            {coachLoading ? <div className="coaching-history-state" role="status"><Busy text="저장된 코칭 불러오는 중"/></div>
              : history?.status==="error" ? <div className="coaching-history-state" role="alert">
                <strong>저장된 조언을 불러오지 못했어요</strong>
                <p>다시 불러와 저장된 조언을 확인해 주세요.</p>
                <button type="button" className="button secondary" disabled={busy} onClick={reloadCoachingHistory}><RotateCcw size={15}/>다시 불러오기</button>
              </div>
              : saved ? <>
                {demo ? <p className="coach-timestamp">화면 체험용 예시</p> : <>
                  <div className="coaching-data-guide">
                    <strong>조언을 만들 때 참고한 기록</strong>
                    <p>저장된 조언은 생성 당시의 수면 기록과 생활습관 입력을 기준으로 해요.</p>
                    {savedNotes.length>0 && <ul>{savedNotes.map(note=><li key={note}>{note}</li>)}</ul>}
                  </div>
                  {savedDate && <div className="coach-timestamp"><Sparkles size={13}/><span><time dateTime={saved.created_at}>{savedDate}</time>에 생성</span></div>}
                </>}
                <CoachingAdvice body={saved.coaching} context={saved.context} mbti={mbti} characterId={characterId}/>
                <details><summary>생성 근거와 생활습관 보기<ChevronDown size={16}/></summary>
                  {saved.context?<><p>모델: {saved.context.model}<br/>지침: {saved.context.prompt_version}<br/>참고 기록: {saved.context.record_count}회</p><pre>{JSON.stringify(saved.context.input_summary,null,2)}</pre></>:<p className="muted">이 코칭의 생성 근거는 저장되어 있지 않습니다.</p>}
                  {saved.lifestyle&&<div className="lifestyle-summary">{Object.entries(saved.lifestyle).map(([k,v])=><span key={k}>{({age_group:"연령",caffeine:"카페인",regularity:"규칙성",satisfaction:"만족도"} as Record<string,string>)[k]||k}: {v}</span>)}</div>}
                </details>
                <button className="text-button danger" disabled={busy} onClick={()=>ask("이 코칭을 삭제할까요?","선택한 코칭만 휴지통으로 옮깁니다. 수면 분석 기록은 유지됩니다.",async()=>{await api(`watch/sessions/${selected}/coaching/${saved.id}`,"DELETE");setRevision(n=>n+1);})}><Trash2 size={14}/>선택한 코칭 삭제</button>
              </> : <div className="coaching-history-state">
                <Sparkles size={23} aria-hidden="true"/>
                <h3>아직 저장된 조언이 없어요</h3>
                <p>{requestFailure ? "요청 안내를 확인한 뒤 필요하면 조언을 다시 요청해 주세요." : "생활습관을 선택하고 ‘나에게 맞는 코칭 생성’을 눌러 첫 조언을 받아 보세요."}</p>
              </div>}
            <p className="disclaimer">AI 코칭은 생활습관 참고용입니다. 질환의 진단이나 치료를 대신하지 않습니다.</p>
          </section>
        </div>
      </> : loading ? <section className="panel coaching-history-state" role="status"><Busy text="수면 기록 불러오는 중"/></section>
        : <section className="panel"><Empty title="코칭의 첫걸음은 나의 기록부터"><p>수면 기록을 추가한 뒤 맞춤 코칭을 받아 보세요.</p><button className="button secondary" onClick={openUpload}><Plus size={16}/>수면 기록 추가</button></Empty></section>}
    </>}

    {page==="comparison"&&<><div className="comparison-toolbar"><div className="segmented"><button className={days===7?"active":""} onClick={()=>setDays(7)}>최근 7일</button><button className={days===30?"active":""} onClick={()=>setDays(30)}>최근 30일</button></div><label className="date-field"><CalendarDays size={16}/>기준일<input aria-label="비교 기준일" type="date" value={end} onChange={e=>{if(e.target.value)setEnd(e.target.value);}}/></label></div><div className="comparison-stats">{[{title:"기록일당 평균 수면",current:minutes(average),previous:minutes(comparison.previous.average_asleep_minutes_per_recorded_day),icon:Moon},{title:"기록이 있는 날짜",current:`${comparison.current.recorded_days}일`,previous:`${comparison.previous.recorded_days}일`,icon:CalendarDays},{title:"기록일당 평균 각성",current:minutes(comparison.current.average_awake_minutes_per_recorded_day),previous:minutes(comparison.previous.average_awake_minutes_per_recorded_day),icon:Sun}].map(({title,current,previous,icon:Icon})=><section className="panel comparison-stat" key={title}><Icon size={21}/><span>{title}</span><strong>{current}</strong><small>이전 기간 {previous}</small></section>)}</div><section className="panel"><div className="panel-heading"><div><h2>이번 {days}일의 수면 흐름</h2><p>{comparison.current.start} – {comparison.current.end}</p></div><Tag>기록일 합계 기준</Tag></div><SleepChart rows={rows} large/><div className="compare-periods"><div><span>이번 기간</span><strong>{comparison.current.start} – {comparison.current.end}</strong></div><ArrowLeft size={16}/><div><span>이전 기간</span><strong>{comparison.previous.start} – {comparison.previous.end}</strong></div></div><p className="disclaimer">미기록 날짜는 평균에서 제외합니다. 같은 날 시작한 기록은 합산하며, 수면의 질이나 건강 점수로 환산하지 않습니다.</p></section></>}

    {page==="trash"&&<><div className="soft-info retention-note"><RotateCcw size={20}/><div><strong>마음이 바뀌어도 괜찮아요.</strong><p>삭제한 기록은 30일 동안 복원할 수 있습니다. 기간이 지난 항목은 앱 이용 시 정리됩니다. 영구 삭제한 기록은 복원할 수 없어요.</p></div></div><section className="panel"><div className="panel-heading"><h2>휴지통 <span className="count">{trash.sessions.length+trash.coaching.length}</span></h2>{loading&&<Busy/>}</div>{!trash.sessions.length&&!trash.coaching.length?<Empty title="휴지통이 비어 있어요"><p>삭제한 분석과 코칭은 이곳에서 관리할 수 있습니다.</p></Empty>:<div className="trash-list">{([...[...trash.sessions].map(t=>({id:t.id,kind:"session",title:`${shortDate(t.record.start)} 수면 분석`,expires_at:t.expires_at,blocked:false})),...[...trash.coaching].map(t=>({id:t.id,kind:"coaching",title:t.coaching.slice(0,65),expires_at:t.expires_at,blocked:!!t.parent_in_trash}))]).map(t=><div className="trash-row" key={t.kind+t.id}><span className="record-moon">{t.kind==="session"?<Moon size={19}/>:<Sparkles size={19}/>}</span><div><strong>{t.title}</strong><p>{shortDate(t.expires_at)}까지 복원 가능{t.blocked?" · 연결된 분석을 먼저 복원하세요":""}</p></div><button className="button secondary compact" disabled={busy||t.blocked} onClick={()=>perform(async()=>{await api(`watch/trash/${t.kind}/${t.id}/restore`,"POST");setRevision(n=>n+1);},"기록을 복원했어요.")}><RotateCcw size={14}/>복원</button><button className="icon-button danger" aria-label={`${t.title} 영구 삭제`} disabled={busy} onClick={()=>ask("이 기록을 영구 삭제할까요?","앱 DB와 관리 대상 백업에 삭제를 반영합니다. 이 작업은 되돌릴 수 없습니다.",async()=>{await api(`watch/trash/${t.kind}/${t.id}`,"DELETE");setRevision(n=>n+1);},true)}><Trash2 size={17}/></button></div>)}</div>}</section><section className="panel backup-panel"><div className="inline-title"><ShieldCheck size={21}/><h2>백업 보관 안내</h2></div><p>관리 대상 백업은 {backup?.retention_days||30}일 보관합니다. 기록·계정 영구 삭제는 해당 백업에도 반영됩니다.</p>{backup&&<Tag>관리 중인 백업 {backup.backup_count}개 · 정리 재시도 {backup.pending}개</Tag>}<p className="disclaimer">원본 파일, 다운로드한 파일, 외부 복사본은 앱의 삭제 관리 범위에 포함되지 않습니다.</p></section></>}

    {page==="account"&&<div className="account-grid"><section className="panel account-panel"><div className="account-profile"><span className="avatar large">{user.username.slice(0,1).toUpperCase()}</span><div><h2>{user.username} 님의 계정</h2><p>소중한 나의 밤을 위한 공간</p></div></div><h3>아이디 변경</h3><form onSubmit={async e=>{e.preventDefault();const f=new FormData(e.currentTarget);await perform(async()=>{await api("auth/me","PATCH",Object.fromEntries(f));reset();setNotice("아이디를 변경했어요. 새 아이디로 다시 로그인해 주세요.");});}}><label>새 아이디<input name="new_username" required minLength={3} maxLength={40} autoComplete="username" placeholder="새 아이디" defaultValue={user.username}/></label><label>현재 비밀번호<input name="current_password" type="password" autoComplete="current-password" required maxLength={128}/></label><button className="button secondary" disabled={busy||demo}>아이디 변경</button></form><hr/><h3>비밀번호 변경</h3><form onSubmit={async e=>{e.preventDefault();const f=new FormData(e.currentTarget);if(f.get("new_password")!==f.get("confirmation")){setError("새 비밀번호 확인이 일치하지 않습니다.");return;}f.delete("confirmation");await perform(async()=>{await api("auth/me","PATCH",Object.fromEntries(f));reset();setNotice("비밀번호를 변경했어요. 다시 로그인해 주세요.");});}}><label>현재 비밀번호<input name="current_password" type="password" autoComplete="current-password" required maxLength={128}/></label><label>새 비밀번호<input name="new_password" type="password" autoComplete="new-password" required minLength={10} maxLength={128} placeholder="10자 이상 입력해 주세요"/></label><label>새 비밀번호 확인<input name="confirmation" type="password" autoComplete="new-password" required minLength={10} maxLength={128}/></label><button className="button secondary" disabled={busy||demo}>비밀번호 변경</button></form><p className="disclaimer">변경하면 모든 로그인 세션이 종료됩니다. 기존 기록과 코칭은 유지됩니다.</p></section><section className="panel account-panel account-danger"><span className="danger-icon"><Trash2 size={22}/></span><h2>계정 삭제</h2><p>계정과 연결된 분석, 코칭, 휴지통, 원시 기록을 영구 삭제합니다. 관리 대상 백업에도 삭제를 반영합니다.</p><div className="soft-warning">삭제한 계정과 기록은 복원할 수 없습니다. 같은 아이디로 다시 가입해도 이전 기록은 돌아오지 않습니다.</div><form onSubmit={async e=>{e.preventDefault();const f=new FormData(e.currentTarget);await perform(async()=>{const result=await api<{backups?:{pending:number}}>("auth/me","DELETE",{current_password:f.get("current_password"),confirmation:f.get("confirmation")});reset();setNotice(result.backups?.pending?"계정은 삭제됐지만 일부 백업 정리가 남아 있습니다. 관리자에게 알려주세요.":"계정과 연결된 기록을 삭제했습니다.");});}}><label>현재 비밀번호<input name="current_password" type="password" autoComplete="current-password" required maxLength={128}/></label><label>확인을 위해 ‘계정 삭제’를 입력해 주세요<input name="confirmation" pattern="계정 삭제" required placeholder="계정 삭제" autoComplete="off"/></label><label className="checkbox-label"><input type="checkbox" required/>계정과 기록을 영구 삭제하며 복원할 수 없음을 이해했습니다.</label><button className="button danger-button" disabled={busy||demo}>계정 영구 삭제</button></form></section></div>}
    <footer className="footer"><span><Moon size={14}/>달잠 · 조금 더 나은 밤을 위해</span><span>웨어러블 추정 기록 기반 · 의료 진단 서비스가 아닙니다</span></footer>
    </main></div>

    {upload&&<div className="modal-overlay" onClick={()=>{if(!busy)setUpload(false);}}><section role="dialog" aria-modal="true" aria-labelledby="upload-title" className="modal" onClick={e=>e.stopPropagation()}><div className="modal-header"><span className="modal-symbol"><CloudUpload size={26}/></span><button className="icon-button" aria-label="업로드 닫기" disabled={busy} onClick={()=>setUpload(false)}><X size={21}/></button></div><span className="eyebrow">A NEW PAGE IN YOUR SLEEP JOURNAL</span><h2 id="upload-title">새로운 밤을 기록해요</h2><p>웨어러블에서 내보낸 수면 파일을 올려 주세요.</p><input ref={fileInput} className="sr-only" type="file" accept=".md,.json" aria-label="수면 파일 선택" onChange={e=>chooseFile(e.target.files?.[0])}/><button className={`dropzone ${dragging?"dragging":""}`} onClick={()=>fileInput.current?.click()} onDragOver={e=>{e.preventDefault();setDragging(true);}} onDragLeave={()=>setDragging(false)} onDrop={e=>{e.preventDefault();setDragging(false);chooseFile(e.dataTransfer.files[0]);}}><span><FileText size={24}/><FileJson size={24}/></span><strong>{file?file.name:"파일을 여기에 놓거나 클릭해 주세요"}</strong><small>{file?`${(file.size/1024).toFixed(1)} KB · 다른 파일 선택`:"Markdown (.md), JSON (.json) · 최대 4MiB"}</small></button><div className="soft-info"><ShieldCheck size={16}/><p>Health Data Export MD, 수면 JSON v1, Health Export Kit JSON v2를 지원합니다. Apple 건강 앱의 XML·ZIP은 지원하지 않습니다.</p></div>{error&&<div className="error" role="alert">{error}</div>}<button className="button primary full" disabled={!file||busy} onClick={importFile}>{busy?<Busy text="수면 기록을 분석하고 있어요"/>:<><Sparkles size={17}/>분석하고 내 기록에 저장</>}</button><p className="disclaimer">분석·저장은 AI 코칭을 자동으로 요청하지 않습니다.</p></section></div>}
    {confirmation&&<div className="modal-overlay"><section className="modal confirm-modal" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title"><div className="modal-header"><span className="danger-icon"><Trash2 size={23}/></span><button className="icon-button" aria-label="취소" disabled={busy} onClick={()=>setConfirmation(null)}><X size={20}/></button></div><h2 id="confirm-title">{confirmation.title}</h2><p>{confirmation.description}</p>{confirmation.permanent&&<label>확인을 위해 ‘영구 삭제’를 입력해 주세요<input value={phrase} onChange={e=>setPhrase(e.target.value)} placeholder="영구 삭제" autoFocus/></label>}{error&&<div className="error" role="alert">{error}</div>}<div className="modal-actions"><button className="button secondary" disabled={busy} onClick={()=>setConfirmation(null)}>취소</button><button className="button danger-button" disabled={busy||!!confirmation.permanent&&phrase!=="영구 삭제"} onClick={async()=>{const ok=await perform(confirmation.run,"기록을 정리했어요.");if(ok)setConfirmation(null);}}>{busy?<Busy text="처리 중"/>:confirmation.permanent?"영구 삭제":"휴지통으로 이동"}</button></div></section></div>}
  </div>;
}
