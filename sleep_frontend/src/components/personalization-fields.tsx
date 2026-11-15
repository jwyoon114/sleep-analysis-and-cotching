"use client";

import {useId, useLayoutEffect, useRef, useState, type KeyboardEvent} from "react";
import {CHARACTERS, MBTI_TYPES, type MbtiType} from "@/lib/coaching-preview";
import {changeIntensity, INTENSITY_OPTIONS, SPEECH_OPTIONS, type Draft} from "@/lib/personalization";

export const STEPS = ["MBTI", "말투", "코칭 강도", "캐릭터"] as const;
export type Step = typeof STEPS[number];

export function MbtiWheel({value,onChange}:{value:MbtiType|null;onChange:(value:MbtiType|null)=>void}) {
  const id=useId();
  const wheel=useRef<HTMLDivElement>(null);
  const [active,setActive]=useState(() => value ? MBTI_TYPES.indexOf(value) : 0);

  function move(index:number) {
    const next=Math.max(0,Math.min(MBTI_TYPES.length-1,index));
    setActive(next);
    const target=wheel.current;
    if(target)target.scrollTop=next*target.children[0].clientHeight;
  }

  useLayoutEffect(()=>{
    const target=wheel.current;
    if(target && value)target.scrollTop=MBTI_TYPES.indexOf(value)*target.children[0].clientHeight;
  },[value]);

  function keyboard(event:KeyboardEvent<HTMLDivElement>) {
    switch(event.key){
      case "ArrowUp": move(active-1); break;
      case "ArrowDown": move(active+1); break;
      case "Home": move(0); break;
      case "End": move(MBTI_TYPES.length-1); break;
      case "Enter":
      case " ": onChange(MBTI_TYPES[active]); break;
      default: return;
    }
    event.preventDefault();
  }

  return <div className="mbti-field">
    <p id={id+"-guide"} className="muted">휠을 밀거나 방향키로 이동한 뒤 원하는 유형을 선택하세요.</p>
    <div className="mbti-wheel" role="listbox" tabIndex={0} ref={wheel} aria-label="MBTI 유형" aria-describedby={id+"-guide"}
      aria-activedescendant={id+"-"+MBTI_TYPES[active]} onKeyDown={keyboard} onScroll={event=>{
        const target=event.currentTarget;
        const rowHeight=target.children[0].clientHeight;
        if(rowHeight) setActive(Math.min(MBTI_TYPES.length-1,Math.round(target.scrollTop/rowHeight)));
      }}>
      {MBTI_TYPES.map((type,index)=><div key={type} id={id+"-"+type} role="option" aria-selected={value===type}
        className={index===active?"wheel-current":undefined} onClick={()=>{move(index);onChange(type);}}>{type}</div>)}
    </div>
    <p className="mbti-selection" aria-live="polite">{value ? value+" 선택됨" : "선택 안 함"}</p>
    <div className="mbti-actions">
      <button type="button" className="button secondary" onClick={()=>onChange(MBTI_TYPES[active])}>{MBTI_TYPES[active]} 선택</button>
      {value&&<button type="button" className="text-button" onClick={()=>onChange(null)}>선택 해제</button>}
    </div>
  </div>;
}

function Choices<T extends string>({label,options,value,onChange}:{
  label:string; options:readonly {value:T;label:string;icon?:string}[];
  value:T|undefined;onChange:(value:T)=>void;
}) {
  const name=useId();
  return <fieldset className="preference-choices">
    <legend className="sr-only">{label}</legend>
    {options.map(option=><label key={option.value} className="preference-choice">
      <input type="radio" name={name} value={option.value} checked={value===option.value} onChange={()=>onChange(option.value)}/>
      {option.icon&&<span aria-hidden="true">{option.icon}</span>}{option.label}
    </label>)}
  </fieldset>;
}

function IntensityField({draft,onChange}:{draft:Draft;onChange:(change:Partial<Draft>)=>void}) {
  const id=useId();
  const dialog=useRef<HTMLDialogElement>(null);
  const deny=useRef<HTMLButtonElement>(null);
  const opener=useRef<HTMLElement|null>(null);
  function ask() {
    const popup=dialog.current;
    if(!popup||popup.open)return;
    opener.current=document.activeElement as HTMLElement;
    popup.showModal();
    deny.current?.focus();
  }

  function chooseConsent(allowed:boolean) {
    onChange({allow_profanity:allowed});
    dialog.current?.close();
  }

  return <>
    <Choices label="코칭 강도" options={INTENSITY_OPTIONS} value={draft.intensity} onChange={value=>{
      onChange(changeIntensity(value));
      if(value==="direct")ask();
    }}/>
    {draft.intensity==="direct"&&<p className="preference-consent">
      <span>비속어 사용 {draft.allow_profanity?"허용":"미허용"}</span>
      <button type="button" className="button secondary" onClick={ask}>변경</button>
    </p>}
    <dialog ref={dialog} className="preference-dialog" aria-labelledby={id+"-title"} aria-describedby={id+"-description"}
      onClose={()=>{if(!dialog.current?.open)opener.current?.focus();}}>
      <h2 id={id+"-title"}>비속어 사용을 허용할까요?</h2>
      <p id={id+"-description"}>기본값은 미허용이에요. 어떤 강도에서도 인신공격이나 차별적 표현은 허용하지 않아요.</p>
      <div className="preference-actions">
        <button ref={deny} type="button" className="button primary" onClick={()=>chooseConsent(false)}>허용 안 함</button>
        <button type="button" className="button secondary" onClick={()=>chooseConsent(true)}>허용</button>
      </div>
    </dialog>
  </>;
}

const animals = CHARACTERS.map(({id,name,emoji})=>({value:id,label:name,icon:emoji}));

export function PreferenceField({step,draft,onChange}:{step:Step;draft:Draft;onChange:(change:Partial<Draft>)=>void}) {
  switch(step){
    case "MBTI": return <MbtiWheel value={draft.mbti} onChange={mbti=>onChange({mbti})}/>;
    case "말투": return <Choices label={step} options={SPEECH_OPTIONS} value={draft.speech} onChange={speech=>onChange({speech})}/>;
    case "코칭 강도": return <IntensityField draft={draft} onChange={onChange}/>;
    case "캐릭터": return <Choices label={step} options={animals} value={draft.character} onChange={character=>onChange({character})}/>;
  }
}
