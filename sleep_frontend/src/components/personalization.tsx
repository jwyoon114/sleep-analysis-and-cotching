"use client";

import {useEffect,useRef,useState} from "react";
import {ChevronRight, Circle, Moon} from "lucide-react";
import {CHARACTERS} from "@/lib/coaching-preview";
import {CHARACTER_THEMES, INTENSITY_OPTIONS, SPEECH_OPTIONS, type Draft, type Personalization, type Preferences} from "@/lib/personalization";
import {PreferenceField, STEPS, type Step} from "./personalization-fields";

const instructions = [
  "MBTI별 표현을 고르거나 이 단계를 건너뛸 수 있어요.",
  "저장할 말투를 선택해 주세요.",
  "편안하게 받아들일 수 있는 조언 표현을 골라주세요.",
  "캐릭터는 테마만 바꿔요. 코칭의 말투와 강도는 따로 선택해요.",
];

function completeDraft(draft:Draft):Preferences|null {
  const {mbti,speech,intensity,allow_profanity,character}=draft;
  return speech&&intensity&&character ? {mbti,speech,intensity,allow_profanity,character} : null;
}

export function Onboarding({onComplete,onLogout}:{
  onComplete:(preferences:Preferences)=>Promise<void>;onLogout:()=>void;
}) {
  const [step,setStep]=useState(0);
  const [draft,setDraft]=useState<Draft>({mbti:null,allow_profanity:false});
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const heading=useRef<HTMLHeadingElement>(null);
  useEffect(()=>{
    heading.current?.focus({preventScroll:true});
    window.scrollTo(0,0);
  },[step]);
  const character=draft.character??"cat";
  const MoonIcon=CHARACTER_THEMES[character].moon==="full"?Circle:Moon;
  const ready=[draft.mbti!==null,!!draft.speech,!!draft.intensity,!!draft.character][step];

  async function finish() {
    const values=completeDraft(draft);
    if(!values||busy)return;
    setBusy(true);setError("");
    try {await onComplete(values);}
    catch {setError("설정을 저장하지 못했어요. 연결을 확인하고 다시 시도해 주세요.");}
    finally {setBusy(false);}
  }

  return <main className="personalization-screen onboarding-screen" data-daljam-theme={character}>
    <section className="onboarding-card" aria-labelledby="onboarding-title">
      <header className="onboarding-hero">
        <div className="onboarding-brand"><MoonIcon size={22} fill="currentColor" aria-hidden="true"/>달잠</div>
        <div className="onboarding-progress">
          <p className="onboarding-progress-text" aria-live="polite">{step+1} / {STEPS.length}</p>
          <div className="onboarding-dots" aria-hidden="true">
            {STEPS.map((item,index)=><span key={item} data-progress={index===step?"current":index<step?"complete":"pending"}/>)}
          </div>
          <progress className="sr-only" value={step+1} max={STEPS.length} aria-label="첫 설정 진행 단계"/>
        </div>
      </header>
      <div className="onboarding-content">
        <h1 id="onboarding-title" ref={heading} tabIndex={-1}>{STEPS[step]} 선택</h1>
        <p className="onboarding-hint">{instructions[step]}</p>
        <PreferenceField key={step} step={STEPS[step]} draft={draft} onChange={change=>setDraft(current=>({...current,...change}))}/>
        {error&&<p className="preference-error" role="alert">{error}</p>}
      </div>
      <footer className="onboarding-footer">
        <div className="preference-actions onboarding-actions">
          {step>0&&<button type="button" className="button secondary" disabled={busy} onClick={()=>{setError("");setStep(step-1);}}>이전</button>}
          {step===0&&<button type="button" className="button secondary" onClick={()=>{setDraft(current=>({...current,mbti:null}));setStep(1);}}>건너뛰기</button>}
          <button type="button" className="button primary" disabled={!ready||busy}
            onClick={()=>step===3?void finish():setStep(step+1)}>
            {busy?"저장 중…":step===3?"설정 완료":"다음"}
          </button>
        </div>
        <button type="button" className="text-button onboarding-logout" disabled={busy} onClick={onLogout}>로그아웃</button>
      </footer>
    </section>
  </main>;
}

export function ProfilePreferences({profile,onSave}:{profile:Personalization;onSave:(preferences:Preferences)=>Promise<void>}) {
  const [editing,setEditing]=useState<Step|null>(null);
  const [draft,setDraft]=useState<Draft>(profile);
  const [saving,setSaving]=useState(false);
  const [feedback,setFeedback]=useState<{error:boolean;text:string}|null>(null);

  async function submit() {
    const values=completeDraft(draft);
    if(saving||!values)return;
    setSaving(true);setFeedback(null);
    try {
      await onSave(values);
      setFeedback({error:false,text:"개인화 설정을 저장했어요."});
      setEditing(null);
    } catch {
      setFeedback({error:true,text:"개인화 설정을 저장하지 못했어요. 다시 시도해 주세요."});
    } finally {setSaving(false);}
  }

  const labels = [
    profile.mbti??"선택 안 함",
    SPEECH_OPTIONS.find(option=>option.value===profile.speech)?.label,
    INTENSITY_OPTIONS.find(option=>option.value===profile.intensity)?.label,
    CHARACTERS.find(option=>option.id===profile.character)?.name,
  ];

  return <>
    <p className="muted">선택한 설정이 이 계정에 저장돼요. 존댓말·반말, 강도와 비속어 설정은 코칭에 아직 반영되지 않아요.</p>
    {STEPS.map((step,index)=><div key={step} className="preference-profile-item">
      <button type="button" disabled={saving} className="profile-setting preference-profile-row" aria-expanded={editing===step}
        onClick={()=>{setFeedback(null);setEditing(editing===step?null:step);setDraft(profile);}}>
        <span>{step}</span>
        <span className="profile-setting-value">
          {step==="캐릭터"&&<span className="profile-theme-thumbnail" data-daljam-theme={profile.character} aria-hidden="true"/>}
          <strong>{labels[index]}</strong><ChevronRight size={17} aria-hidden="true"/>
        </span>
      </button>
      {editing===step&&<form className="preference-editor" onSubmit={event=>{event.preventDefault();void submit();}}>
        <fieldset disabled={saving}>
          <legend className="sr-only">{step} 변경</legend>
          <PreferenceField step={step} draft={draft} onChange={change=>setDraft(current=>({...current,...change}))}/>
          <div className="preference-actions">
            <button type="button" className="button secondary" onClick={()=>{setEditing(null);setFeedback(null);}}>취소</button>
            <button type="submit" className="button primary">{saving?"저장 중…":"저장"}</button>
          </div>
        </fieldset>
      </form>}
    </div>)}
    {feedback&&<p className={feedback.error?"preference-error":"preference-success"} role={feedback.error?"alert":"status"}>{feedback.text}</p>}
  </>;
}
