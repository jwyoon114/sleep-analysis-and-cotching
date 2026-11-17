"use client";

import {useEffect,useRef,useState} from "react";
import {ArrowDown,ArrowUp,Bell,CalendarDays,Moon,Plus,Sparkles,Sun,Trash2,X} from "lucide-react";
import {api,minutes,type Coaching} from "@/lib/sleep";
import SleepAlarms,{saveSleepSchedule,type Schedule} from "./sleep-alarms";
import WebPushSettings from "./web-push-settings";

type Activity={id:string;title:string;completed:boolean};
type Plan={date:string;timezone:string;activities:Activity[]};
type Suggestion={title:string;days:number};
type Overview={today:string;next_date:string;timezone:string;today_plan:Plan|null;next_plan:Plan|null;suggestions:Suggestion[]};
type Estimate={status:"available";bedtime:string;bed_date:string;wake_date:string;wake_time:string;window_minutes:number;start_typical:string;end_typical:string;sleep_minutes:number};
type Recommendation={valid_nights:number;minimum_nights:number;lookback_days:number;timezone:string}&(Estimate|{status:"no_goal"|"insufficient"});
type Settings={schedule:Schedule;overview:Overview;recommendation:Recommendation};
const dateLabel=(date:string)=>date.slice(0,4)+"년 "+Number(date.slice(5,7))+"월 "+Number(date.slice(8,10))+"일";
const errorText=(error:unknown)=>error instanceof Error?error.message:"잠시 후 다시 시도해 주세요.";
const sameTitle=(title:string)=>title.trim().replace(/\s+/g," ").normalize("NFKC").toLowerCase();
const activityLimit=12;

function PlanChecklist({plan,busy,onMark}:{plan:Plan;busy:boolean;onMark:(id:string,completed:boolean)=>void}) {
  return <ul className="plan-checklist">{plan.activities.map(item=><li key={item.id}>
    <label><input type="checkbox" checked={item.completed} disabled={busy} onChange={event=>onMark(item.id,event.target.checked)}/>
      <span>{item.title}</span></label>
  </li>)}</ul>;
}

function MorningSheet({plan,onClose,onMark}:{plan:Plan;onClose:()=>void;onMark:(plan:Plan,id:string,completed:boolean)=>Promise<void>}) {
  const ref=useRef<HTMLDialogElement>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState("");
  useEffect(()=>{if(ref.current&&!ref.current.open)ref.current.showModal();},[]);
  return <dialog className="morning-sheet" aria-labelledby="morning-sheet-title" ref={ref} onClose={onClose}>
    <div className="panel-heading"><div><h2 id="morning-sheet-title"><Sun size={19}/> 오늘 아침 계획</h2>
      <p>{dateLabel(plan.date)} · {plan.timezone}</p></div>
      <button type="button" className="icon-button" aria-label="아침 계획 닫기" autoFocus onClick={()=>ref.current?.close()}><X size={21}/></button>
    </div>
    <PlanChecklist plan={plan} busy={busy} onMark={async(id,done)=>{
      setBusy(true);setError("");
      try{await onMark(plan,id,done);}catch(e){setError(errorText(e));}finally{setBusy(false);}
    }}/>
    {error&&<p role="alert" className="plan-error">{error}</p>}
    <button type="button" className="button secondary full" onClick={()=>ref.current?.close()}>닫기</button>
  </dialog>;
}

function PlanEditor({day,timezone,plan,suggestions,onSubmit,onDelete,onBack}:{
  day:string;timezone:string;plan:Plan|null;suggestions:Suggestion[];onSubmit:(activities:Activity[])=>Promise<void>;
  onDelete:()=>Promise<void>;onBack:()=>void;
}) {
  const [items,setItems]=useState(plan?.activities??[]);
  const [title,setTitle]=useState(""),[error,setError]=useState("");
  const [busy,setBusy]=useState(false),[confirmDelete,setConfirmDelete]=useState(false);
  const contains=(value:string)=>items.some(item=>sameTitle(item.title)===sameTitle(value));
  function add(value:string) {
    const clean=value.trim();
    if(!clean||contains(clean)||items.length>=activityLimit)return;
    setItems([...items,{id:crypto.randomUUID(),title:clean,completed:false}]);
    setTitle("");setError("");
  }
  function move(index:number,delta:number){
    const list=[...items],target=index+delta;
    [list[index],list[target]]=[list[target],list[index]];
    setItems(list);
  }
  async function save(remove=false){
    setBusy(true);setError("");
    try{if(remove)await onDelete();else await onSubmit(items);}
    catch(e){setError(errorText(e));}finally{setBusy(false);}
  }
  return <section className="panel morning-plan-editor">
    <h2><CalendarDays size={19}/> 아침 계획 {plan?"수정":"작성"}</h2>
    <p className="muted">{dateLabel(day)} · {timezone}</p>
    <fieldset disabled={busy}>
      <legend>추천 활동</legend>
      <p className="muted">{suggestions.some(s=>s.days>0)?"최근 14일 동안 계획에 저장한 횟수를 기준으로 골랐어요.":"아침에 해볼 만한 활동이에요."}</p>
      <div className="plan-suggestions">{suggestions.map(item=><button key={item.title} type="button" className="button secondary"
        disabled={contains(item.title)||items.length>=activityLimit} onClick={()=>add(item.title)}>
        <Plus size={16}/>{item.title}{item.days>0&&<small> 최근 {item.days}일</small>}
      </button>)}</div>
    </fieldset>
    <form className="plan-add" onSubmit={event=>{event.preventDefault();add(title);}}>
      <label>활동 직접 입력<input maxLength={80} required disabled={busy} value={title} onChange={event=>setTitle(event.target.value)}/></label>
      <button className="button secondary" type="submit" disabled={busy||!title.trim()||contains(title)||items.length>=activityLimit}>추가</button>
    </form>
    <h3>선택한 활동 <span>{items.length}/{activityLimit}</span></h3>
    {items.length===0?<p className="muted">추천 활동을 고르거나 직접 입력해 주세요.</p>:<ol className="plan-items">
      {items.map((item,index)=><li key={item.id}><span>{item.title}</span><div>
        <button type="button" className="icon-button" aria-label={item.title+" 위로 이동"} disabled={busy||index===0} onClick={()=>move(index,-1)}><ArrowUp size={16}/></button>
        <button type="button" className="icon-button" aria-label={item.title+" 아래로 이동"} disabled={busy||index===items.length-1} onClick={()=>move(index,1)}><ArrowDown size={16}/></button>
        <button type="button" className="icon-button" aria-label={item.title+" 제거"} disabled={busy} onClick={()=>setItems(items.filter(current=>current.id!==item.id))}><X size={16}/></button>
      </div></li>)}
    </ol>}
    {error&&<p className="plan-error" role="alert">{error}</p>}
    {confirmDelete&&<div className="plan-confirm"><p>이 날짜의 아침 계획을 삭제할까요?</p><button type="button" className="button secondary" disabled={busy} onClick={()=>void save(true)}>삭제하기</button>
      <button type="button" className="button secondary" disabled={busy} onClick={()=>setConfirmDelete(false)}>삭제 취소</button></div>}
    <div className="plan-actions">
      {plan&&!confirmDelete&&<button type="button" className="button secondary" disabled={busy} onClick={()=>setConfirmDelete(true)}><Trash2 size={16}/>계획 삭제</button>}
      <button type="button" className="button secondary" disabled={busy} onClick={onBack}>취소</button>
      <button type="button" className="button primary" disabled={busy||!items.length} onClick={()=>void save()}>계획 저장</button>
    </div>
  </section>;
}

export default function SleepPlan({active,demo,coaching}:{active:boolean;demo:boolean;coaching?:Coaching}) {
  const [data,setData]=useState<Settings|null>(null),[retry,setRetry]=useState(0);
  const [error,setError]=useState(""),[notice,setNotice]=useState("");
  const [mode,setMode]=useState<"schedule"|"recommendation"|"editor"|null>(null);
  const [editorDay,setEditorDay]=useState("");
  const [sheet,setSheet]=useState<Plan|null>(null),[applying,setApplying]=useState(false);
  const section=useRef<HTMLDivElement>(null);

  useEffect(()=>{
    if(!active||demo)return;
    const controller=new AbortController();
    Promise.all([
      api<Schedule>("alarms","GET",undefined,controller.signal),
      api<Overview>("plans","GET",undefined,controller.signal),
      api<Recommendation>("plans/bedtime","GET",undefined,controller.signal),
    ]).then(([schedule,overview,recommendation])=>{
      if(!controller.signal.aborted){setData({schedule,overview,recommendation});setError("");}
    }).catch(e=>{if(!controller.signal.aborted)setError(errorText(e));});
    return()=>controller.abort();
  },[active,demo,retry]);

  useEffect(()=>{
    if(demo)return;
    const controller=new AbortController();
    let pending=false;
    async function check(){
      if(pending||document.visibilityState!=="visible")return;
      pending=true;
      try{
        const {plan}=await api<{plan:Plan|null}>("plans/morning-view","POST",{},controller.signal);
        if(plan&&!controller.signal.aborted)setSheet(plan);
      }catch{/* A missed automatic check leaves the plan accessible from its tab. */}
      finally{pending=false;}
    }
    const frame=window.setTimeout(check,0);
    window.addEventListener("pageshow",check);
    document.addEventListener("visibilitychange",check);
    return()=>{window.clearTimeout(frame);controller.abort();window.removeEventListener("pageshow",check);document.removeEventListener("visibilitychange",check);};
  },[demo]);

  function show(next:typeof mode){
    setError("");setNotice("");setMode(next);
    requestAnimationFrame(()=>section.current?.scrollIntoView({block:"start"}));
  }
  function edit(day:string){setEditorDay(day);show("editor");}
  async function saveSchedule(settings:Schedule) {
    await saveSleepSchedule(settings);
    setData(null);
    show(null);setNotice("취침·기상 목표를 저장했어요.");setRetry(count=>count+1);
  }
  function update(date:string,plan:Plan|null) {
    setData(current=>{
      if(!current)return current;
      const {overview}=current;
      return {...current,overview:{...overview,
        today_plan:overview.today===date?plan:overview.today_plan,
        next_plan:overview.next_date===date?plan:overview.next_plan}};
    });
    setSheet(current=>current?.date===date?plan:current);
  }
  async function mark(plan:Plan,id:string,completed:boolean) {
    const {plan:saved}=await api<{plan:Plan}>("plans/"+plan.date,"PATCH",{id,completed});
    update(plan.date,saved);
  }
  async function savePlan(items:Activity[]) {
    const {plan}=await api<{plan:Plan}>("plans/"+editorDay,"POST",{activities:items.map(({id,title})=>({id,title}))});
    update(editorDay,plan);show(null);setNotice("아침 계획을 저장했어요.");setRetry(count=>count+1);
  }
  async function deletePlan() {
    await api("plans/"+editorDay,"DELETE");
    update(editorDay,null);show(null);setNotice("아침 계획을 삭제했어요.");setRetry(count=>count+1);
  }
  async function applyRecommendation(){
    if(!data||data.recommendation.status!=="available"||applying)return;
    setApplying(true);setError("");
    try{await saveSchedule({...data.schedule,bedtime:data.recommendation.bedtime,coaching_id:null});}
    catch(e){setError(errorText(e));}finally{setApplying(false);}
  }
  const {schedule,overview,recommendation}=data??{};
  const nextPlan=overview?.next_plan;
  const nextTitle=overview?.next_date===overview?.today?"오늘 아침 계획":"내일 아침 계획";

  return <>
    <div ref={section} className="plan-screen" hidden={!active}>
      {demo?<section className="panel"><h2>수면 계획</h2><p>체험 모드에서는 목표 시간이나 아침 계획을 저장하지 않아요.</p></section>
      : <>
        {notice&&<p role="status" className="plan-notice">{notice}</p>}
        {error&&<div role="alert" className="panel plan-error">{error} <button type="button" className="button secondary" onClick={()=>{setError("");setRetry(count=>count+1);}}>다시 불러오기</button></div>}
        {!data&&!error&&<section className="panel" role="status">계획을 불러오는 중이에요.</section>}
        {schedule&&overview&&recommendation&&(mode==="schedule"?<SleepAlarms settings={schedule} coaching={coaching} onSave={saveSchedule} onBack={()=>show(null)}/>
        : mode==="editor"?<PlanEditor key={editorDay} day={editorDay} timezone={overview.timezone}
            plan={editorDay===overview.today?overview.today_plan:overview.next_plan}
            suggestions={overview.suggestions} onSubmit={savePlan} onDelete={deletePlan} onBack={()=>show(null)}/>
        : mode==="recommendation"&&recommendation.status==="available"?<section className="panel plan-recommendation">
          <h2><Sparkles size={19}/> 추천 취침 시간</h2>
          <p className="plan-recommendation-time">{recommendation.bedtime}</p>
          <p>{dateLabel(recommendation.bed_date)} · {recommendation.timezone}</p>
          <dl><div><dt>사용한 기록</dt><dd>최근 {recommendation.lookback_days}일 중 {recommendation.valid_nights}일</dd></div>
            <div><dt>기기 기록의 대표 시작·종료 시각</dt><dd>{recommendation.start_typical} ~ {recommendation.end_typical}</dd></div>
            <div><dt>기기 기록 수면 시간 중앙값</dt><dd>{minutes(recommendation.sleep_minutes)}</dd></div>
            <div><dt>기기 기록 구간 중앙값</dt><dd>{minutes(recommendation.window_minutes)}</dd></div>
          </dl>
          <p className="muted">{dateLabel(recommendation.wake_date)} 목표 기상 {schedule.wake_time}{recommendation.wake_time!==schedule.wake_time?" (일광 절약 시간 반영 "+recommendation.wake_time+")":""}에서 기기 기록 구간의 중앙값을 빼서 계산했어요. 기기 기록 구간에는 각성이나 미기록 시간이 포함될 수 있어요.</p>
          <div className="plan-actions"><button type="button" className="button secondary" disabled={applying} onClick={()=>show(null)}>취소</button>
            <button type="button" className="button primary" disabled={applying} onClick={()=>void applyRecommendation()}>취침 목표에 적용</button></div>
        </section>:<>
          <section className="panel plan-schedule">
            <div className="panel-heading"><div><h2><CalendarDays size={19}/> 수면 스케줄</h2></div><button type="button" className="button secondary" onClick={()=>show("schedule")}>목표 설정</button></div>
            {schedule.saved?<><dl className="plan-goals"><div><dt><Moon size={17}/> 취침 목표</dt><dd>{schedule.bedtime}</dd></div><div><dt><Sun size={17}/> 기상 목표</dt><dd>{schedule.wake_time}</dd></div></dl>
              <p className="muted">{schedule.timezone}</p></>:<p>저장한 취침·기상 목표가 없어요.</p>}
            <div className="plan-suggestion"><h3><Sparkles size={17}/> 추천 취침 시간</h3>
              {recommendation.status==="available"?<><strong>{recommendation.bedtime}</strong>
                <button type="button" className="button secondary" onClick={()=>show("recommendation")}>계산 근거 보기</button></>
              : <p>{recommendation.status==="no_goal"?"기상 목표를 설정하면 취침 시간을 계산할 수 있어요.":"추천에 사용할 수면 기록이 부족해요."}</p>}
              <small>최근 {recommendation.lookback_days}일 유효 기록 {recommendation.valid_nights}일 · 최소 {recommendation.minimum_nights}일 필요</small>
            </div>
          </section>
          <section className="panel"><h2><Bell size={19}/> 취침 준비 알림</h2>
            <p>취침 30분 전 정기 알림은 검증 대기 중이에요.</p>
            {active&&<WebPushSettings/>}
            {schedule.saved&&schedule.desktop_available&&<p className="muted">Windows PC 알람 {schedule.enabled?"켜짐":"꺼짐"}</p>}
          </section>
          <section className="panel">
            <div className="panel-heading"><div><h2><Sun size={19}/> {nextTitle}</h2><p>{dateLabel(overview.next_date)} · {nextPlan?.timezone??overview.timezone}</p></div>
              <button type="button" className="button secondary" onClick={()=>edit(overview.next_date)}>{nextPlan?"계획 수정":"계획 작성"}</button></div>
            {nextPlan?<ul className="plan-summary">{nextPlan.activities.map(item=><li key={item.id}>{item.title}{item.completed&&<small>완료</small>}</li>)}</ul>
              :<p>저장된 활동이 없어요.</p>}
            {overview.today===overview.next_date&&overview.today_plan&&<button type="button" className="button secondary" onClick={()=>setSheet(overview.today_plan)}>계획 확인</button>}
          </section>
          {overview.today!==overview.next_date&&overview.today_plan&&<section className="panel">
            <div className="panel-heading"><div><h2>오늘 아침 계획</h2><p>{dateLabel(overview.today)} · {overview.today_plan.timezone}</p></div></div>
            <ul className="plan-summary">{overview.today_plan.activities.map(item=><li key={item.id}>{item.title}{item.completed&&<small>완료</small>}</li>)}</ul>
            <div className="plan-actions"><button type="button" className="button secondary" onClick={()=>edit(overview.today)}>계획 수정</button>
              <button type="button" className="button primary" onClick={()=>setSheet(overview.today_plan)}>계획 확인</button></div>
          </section>}
        </>)}
      </>}
    </div>
    {sheet&&<MorningSheet plan={sheet} onClose={()=>setSheet(null)} onMark={mark}/>}
  </>;
}
