"use client";

import {useId,useMemo,useState,type PointerEvent} from "react";
import {ChevronLeft,ChevronRight,Clock3,MoveHorizontal} from "lucide-react";
import {clock,colors,labels,shortDate,type SleepRecord,type Stage} from "@/lib/sleep";
import {buildTimeline,segmentAt} from "@/lib/timeline";

const WIDTH=600,LEFT=72,RIGHT=18,TOP=25,ROW=39;

export default function SleepTimeline({record}:{record:SleepRecord}) {
  const model=useMemo(()=>buildTimeline(record),[record]);
  const [active,setActive]=useState(0);
  const pattern=useId().replaceAll(":","");
  const titleId=useId(), descriptionId=useId();
  // Reuse SVG geometry while moving through a record; only the selection changes.
  const drawing=useMemo(()=>{
  if(!model||!model.segments.length)return null;
  const {start,end,duration,segments,gaps}=model;
  const stages:Stage[]=["wake","rem","core","deep",...(segments.some(s=>s.stage==="unspecified")?["unspecified" as const]:[])];
  const bottom=TOP+(stages.length-1)*ROW+19,height=bottom+53;
  const x=(t:number)=>LEFT+(t-start)/duration*(WIDTH-LEFT-RIGHT);
  const y=(stage:Stage)=>TOP+stages.indexOf(stage)*ROW;
  const number=(n:number)=>Number(n.toFixed(2));
  const paths=Object.fromEntries(stages.map(stage=>[stage,segments.filter(s=>s.stage===stage).map(s=>`M${number(x(s.from))},${y(stage)-7}h${number(x(s.to)-x(s.from))}v14H${number(x(s.from))}Z`).join("")])) as Record<Stage,string>;
  const connectors=segments.slice(1).map((s,i)=>segments[i].to===s.from&&segments[i].stage!==s.stage?`M${number(x(s.from))},${y(segments[i].stage)}V${y(s.stage)}`:"").join("");
  const gapPath=gaps.map(g=>`M${number(x(g.from))},${TOP-17}h${number(x(g.to)-x(g.from))}V${bottom}H${number(x(g.from))}Z`).join("");
  const hour=3600000;
  const step=duration<=2*hour?hour/2:duration<=9*hour?hour:duration<=18*hour?2*hour:Math.ceil(duration/(8*hour))*hour;
  const ticks:number[]=[];
  for(let tick=Math.ceil(start/step)*step;tick<end;tick+=step){if(x(tick)>LEFT+34&&x(tick)<WIDTH-RIGHT-34)ticks.push(tick);}
  return {start,end,duration,segments,gaps,stages,bottom,height,x,y,paths,connectors,gapPath,ticks};
  },[model]);
  if(!drawing)return <p className="muted">시간별 수면 구간이 없어 그래프를 표시할 수 없습니다.</p>;
  const {start,duration,segments,gaps,stages,bottom,height,x,y,paths,connectors,gapPath,ticks}=drawing;
  const formatTime=(value:number)=>new Intl.DateTimeFormat("ko-KR",{timeZone:record.timezone,hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).format(value);
  const selected=segments[active];
  function point(event:PointerEvent<SVGSVGElement>){
    const bounds=event.currentTarget.getBoundingClientRect(),position=(event.clientX-bounds.left)/bounds.width*WIDTH;
    if(position<LEFT||position>WIDTH-RIGHT)return;
    setActive(segmentAt(segments,start+(position-LEFT)/(WIDTH-LEFT-RIGHT)*duration));
  }
  return <section className="sleep-timeline" aria-label="시간별 수면 양상">
    <div className="timeline-heading"><div><h3><Clock3 size={16}/>시간별 수면 양상</h3><p>{shortDate(record.start)} {clock(record.start)} – {shortDate(record.end)} {clock(record.end)}</p></div><span className="tag">{record.timezone}</span></div>
    <div className="timeline-scroll" tabIndex={0} aria-label="시간별 수면 단계 그래프. 작은 화면에서는 좌우로 스크롤할 수 있습니다.">
      <svg className="hypnogram" viewBox={`0 0 ${WIDTH} ${height}`} role="img" aria-labelledby={`${titleId} ${descriptionId}`} onPointerDown={point} onPointerMove={e=>{if(e.pointerType==="mouse")point(e);}}>
        <title id={titleId}>수면 시작부터 종료까지 시간별 단계 변화</title>
        <desc id={descriptionId}>가로축은 {record.timezone} 시각, 세로축은 기기에 기록된 수면 단계입니다. 빗금 영역은 미기록 구간이며, 이 구간에서는 단계를 연결하지 않습니다. 아래 구간 선택기를 사용하면 각 구간의 정확한 시각을 확인할 수 있습니다.</desc>
        <defs><pattern id={pattern} width="7" height="7" patternUnits="userSpaceOnUse"><path d="M0 7L7 0" stroke="#e4dfea" strokeWidth="1"/></pattern></defs>
        {stages.map(stage=><g key={stage}><line x1={LEFT} x2={WIDTH-RIGHT} y1={y(stage)} y2={y(stage)} stroke="#ece7f2" strokeDasharray="3 4"/><text x={LEFT-12} y={y(stage)+4} textAnchor="end" className="timeline-stage-label">{labels[stage]}</text></g>)}
        {ticks.map(tick=><g key={tick}><line x1={x(tick)} x2={x(tick)} y1={TOP-17} y2={bottom} stroke="#f0ecf5"/><text x={x(tick)} y={bottom+22} textAnchor="middle" className="timeline-tick">{formatTime(tick)}</text></g>)}
        <path d={gapPath} fill={`url(#${pattern})`}/>
        <path d={connectors} fill="none" stroke="#baabd0" strokeWidth="1.3"/>
        {stages.map(stage=><path key={stage} d={paths[stage]} fill={colors[stage]} opacity={stage==="wake"?.95:.9}/>)}
        {selected&&<g pointerEvents="none"><line x1={x((selected.from+selected.to)/2)} x2={x((selected.from+selected.to)/2)} y1={TOP-17} y2={bottom} stroke="#9e82ba" strokeDasharray="2 3"/><rect x={x(selected.from)} y={y(selected.stage)-9} width={Math.max(1,x(selected.to)-x(selected.from))} height={18} rx="2" fill="none" stroke="#70518d" strokeWidth="1.5"/></g>}
        <line x1={LEFT} x2={WIDTH-RIGHT} y1={bottom} y2={bottom} stroke="#e9e2f0"/>
        <text x={LEFT} y={bottom+40} className="timeline-endpoint">{record.start.slice(5,10).replace("-",".")} {clock(record.start)}</text>
        <text x={WIDTH-RIGHT} y={bottom+40} textAnchor="end" className="timeline-endpoint">{record.end.slice(5,10).replace("-",".")} {clock(record.end)}</text>
      </svg>
    </div>
    <div className="timeline-mobile-hint"><MoveHorizontal size={13}/>그래프를 좌우로 움직여 시간대를 살펴보세요.</div>
    <div className="timeline-selection" aria-live="polite" aria-atomic="true">{selected?<><span className="timeline-stage-badge"><i style={{background:colors[selected.stage]}}/>{labels[selected.stage]}</span><strong>{clock(selected.start)} – {clock(selected.end)}</strong><span>{Number(((selected.to-selected.from)/60000).toFixed(1))}분</span><small>{active+1} / {segments.length} 구간</small></>:<><span className="timeline-stage-badge">미기록 구간</span><span>이 시간대에는 단계 기록이 없습니다.</span></>}</div>
    <div className="timeline-controls"><button className="icon-button" aria-label="이전 수면 구간" disabled={active<=0} onClick={()=>setActive(n=>n-1)}><ChevronLeft size={17}/></button><input type="range" min={0} max={segments.length-1} value={Math.max(0,active)} aria-label="수면 구간 선택" aria-valuetext={selected?`${labels[selected.stage]} ${clock(selected.start)}부터 ${clock(selected.end)}까지`:"미기록 구간"} onChange={e=>setActive(Number(e.target.value))}/><button className="icon-button" aria-label="다음 수면 구간" disabled={active>=segments.length-1} onClick={()=>setActive(n=>n+1)}><ChevronRight size={17}/></button></div>
    <p className="timeline-note">그래프를 가리키거나 누르면 해당 구간이 표시됩니다.{gaps.length>0?" 빗금은 미기록 구간입니다.":""} 수면 단계는 웨어러블 기기의 추정값입니다.</p>
  </section>;
}
