"use client";

import {useEffect,useRef,useState} from "react";
import {ArrowLeft,ArrowRight,ExternalLink,FileUp} from "lucide-react";
import {HEALTH_EXPORT_KIT_APP_STORE,IPHONE_SLEEP_STEPS} from "@/lib/iphone-sleep-guide";

export default function IphoneSleepGuide({onReturn,onChooseFile}:{
  onReturn:()=>void;
  onChooseFile:()=>void;
}) {
  const [index,setIndex]=useState(0);
  const heading=useRef<HTMLHeadingElement>(null);
  const step=IPHONE_SLEEP_STEPS[index];
  const count=IPHONE_SLEEP_STEPS.length;

  useEffect(()=>{
    const title=heading.current;
    title?.closest(".modal")?.scrollTo({top:0});
    title?.focus({preventScroll:true});
  },[index]);

  return <>
    <h2 id="upload-title">iPhone 수면 기록 가져오기</h2>
    <div className="iphone-guide-progress">
      <span aria-hidden="true">{index+1} / {count}단계</span>
      <progress max={count} value={index+1} aria-label={`가져오기 안내 ${count}단계 중 ${index+1}단계`}/>
    </div>
    <article className="iphone-guide-step">
      <h3 ref={heading} tabIndex={-1} data-initial-focus>{step.title}</h3>
      <p>{step.description}</p>
      {index===0&&<a className="button secondary" href={HEALTH_EXPORT_KIT_APP_STORE} target="_blank" rel="noopener noreferrer"
        aria-label="App Store에서 Health Export Kit 열기 (새 창)">
        App Store에서 열기 <ExternalLink size={16} aria-hidden="true"/>
      </a>}
      <div className="iphone-guide-photo">
        {/* Actual captures are cropped and encoded locally, with private pixels removed. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img key={step.photo} src={`/guides/iphone-sleep/${step.photo}.webp`} alt={step.alt}/>
        {step.highlights.map(([left,top,width,height],areaIndex)=><span key={areaIndex} aria-hidden="true"
          style={{left:`${left}%`,top:`${top}%`,width:`${width}%`,height:`${height}%`}}/>)}
      </div>
      {step.formatNotes&&<details className="iphone-guide-format">
        <summary>지원 형식과 Verbose export</summary>
        {step.formatNotes.map(note=><p key={note}>{note}</p>)}
      </details>}
    </article>
    <div className="iphone-guide-actions">
      <button type="button" className="button secondary" onClick={index===0?onReturn:()=>setIndex(index-1)}>
        <ArrowLeft size={16} aria-hidden="true"/>{index===0?"가져오기 화면":"이전"}
      </button>
      <button type="button" className="button primary" onClick={index===count-1?onChooseFile:()=>setIndex(index+1)}>
        {index===count-1?<><FileUp size={16} aria-hidden="true"/> JSON 파일 선택</>:<>다음<ArrowRight size={16} aria-hidden="true"/></>}
      </button>
    </div>
  </>;
}
