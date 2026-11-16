"use client";

import {useEffect,useRef,useState} from "react";
import {ChevronRight, Moon} from "lucide-react";
import {INTENSITY_OPTIONS, SPEECH_OPTIONS, type Draft, type Personalization, type Preferences} from "@/lib/personalization";
import ClassicDialog from "./classic-dialog";
import {PreferenceField, STEPS, type Step} from "./personalization-fields";

const instructions = [
  "MBTI별 표현을 고르거나 이 단계를 건너뛸 수 있어요.",
  "저장할 말투를 선택해 주세요.",
  "편안하게 받아들일 수 있는 조언 표현을 골라주세요.",
];

function completeDraft(draft:Draft):Preferences|null {
  const {mbti,speech,intensity,allow_profanity,character}=draft;
  return speech&&intensity&&character ? {mbti,speech,intensity,allow_profanity,character} : null;
}

export function Onboarding({onComplete,onLogout}:{
  onComplete:(preferences:Preferences)=>Promise<void>;onLogout:()=>void;
}) {
  const [step,setStep]=useState(0);
  const [draft,setDraft]=useState<Draft>({mbti:null,allow_profanity:false,character:"cat"});
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const heading=useRef<HTMLHeadingElement>(null);
  useEffect(()=>{
    heading.current?.focus({preventScroll:true});
    window.scrollTo(0,0);
  },[step]);
  const ready=[draft.mbti!==null,!!draft.speech,!!draft.intensity][step];
  const last=step===STEPS.length-1;

  async function finish() {
    const values=completeDraft(draft);
    if(!values||busy)return;
    setBusy(true);setError("");
    try {await onComplete(values);}
    catch {setError("설정을 저장하지 못했어요. 연결을 확인하고 다시 시도해 주세요.");}
    finally {setBusy(false);}
  }

  return <main className="personalization-screen onboarding-screen">
    <section className="onboarding-card" aria-labelledby="onboarding-title">
      <header className="onboarding-hero">
        <div className="onboarding-brand"><span className="classic-brand-symbol"><Moon size={23} aria-hidden="true"/></span>달잠</div>
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
            onClick={()=>last?void finish():setStep(step+1)}>
            {busy?"저장 중…":last?"설정 완료":"다음"}
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
  const [feedback,setFeedback]=useState("");
  const [saveError,setSaveError]=useState("");

  async function submit() {
    const values=completeDraft(draft);
    if(saving||!values)return;
    setSaving(true);setFeedback("");setSaveError("");
    try {
      await onSave(values);
      setFeedback("개인화 설정을 저장했어요.");
      setEditing(null);
    } catch {
      setSaveError("개인화 설정을 저장하지 못했어요. 다시 시도해 주세요.");
    } finally {setSaving(false);}
  }

  const labels = [
    profile.mbti??"선택 안 함",
    SPEECH_OPTIONS.find(option=>option.value===profile.speech)?.label,
    INTENSITY_OPTIONS.find(option=>option.value===profile.intensity)?.label,
  ];

  return <>
    <p className="muted">말투와 강도는 다음 코칭부터 적용돼요. 이미 저장된 조언은 생성 당시 문장 그대로 표시돼요.</p>
    {STEPS.map((step,index)=><div key={step} className="preference-profile-item">
      <button type="button" className="profile-setting preference-profile-row" aria-haspopup="dialog"
        onClick={()=>{setFeedback("");setSaveError("");setEditing(step);setDraft(profile);}}>
        <span>{step}</span>
        <span className="profile-setting-value">
          <strong>{labels[index]}</strong><ChevronRight size={17} aria-hidden="true"/>
        </span>
      </button>
    </div>)}
    {editing&&<ClassicDialog title={editing+" 변경"} description="변경한 설정은 다음 코칭부터 적용돼요." busy={saving} onDismiss={()=>setEditing(null)}>
      <form className="preference-editor" onSubmit={event=>{event.preventDefault();void submit();}}>
        <fieldset disabled={saving}>
          <legend className="sr-only">{editing} 선택</legend>
          <PreferenceField step={editing} draft={draft} onChange={change=>setDraft(current=>({...current,...change}))}/>
          {saveError&&<p className="preference-error" role="alert">{saveError}</p>}
          <div className="preference-actions">
            <button type="button" className="button secondary" onClick={()=>setEditing(null)}>취소</button>
            <button type="submit" className="button primary">{saving?"저장 중…":"저장"}</button>
          </div>
        </fieldset>
      </form>
    </ClassicDialog>}
    {feedback&&<p className="preference-success" role="status">{feedback}</p>}
  </>;
}
