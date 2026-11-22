"use client";

import {useEffect, useRef, useState, type FormEvent} from "react";
import {ArrowRight, Check, LoaderCircle, Moon, RotateCcw, Sparkles} from "lucide-react";
import {api, minutes} from "@/lib/sleep";
import type {PremiumSample, PremiumStatus} from "@/lib/premium";
import styles from "./premium-demo.module.css";
import PremiumLiveCoaching from "./premium-live-coaching";

export function PremiumEntry({onOpen}:{onOpen:()=>void}) {
  return <button type="button" className={styles.entry} onClick={onOpen}>
    <span className={styles.entryIcon}><Sparkles size={22} aria-hidden="true"/></span>
    <span><strong>Premium 알아보기</strong><small>더 깊은 수면 습관 코칭과 발표 시연</small></span>
    <ArrowRight size={20} aria-hidden="true"/>
  </button>;
}

export default function PremiumDemo({onManualSaved}:{onManualSaved:()=>void}) {
  const [status,setStatus]=useState<PremiumStatus|null>(null);
  const [view,setView]=useState<"intro"|"checkout"|"active">("intro");
  const [ticket,setTicket]=useState("");
  const [acknowledged,setAcknowledged]=useState(false);
  const [sample,setSample]=useState<PremiumSample|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const heading=useRef<HTMLHeadingElement>(null);

  useEffect(()=>{
    const controller=new AbortController();
    api<PremiumStatus>("premium","GET",undefined,controller.signal).then(async value=>{
      if(value.tier==="premium_demo"){
        const preview=await api<PremiumSample>("premium/demo/preview","GET",undefined,controller.signal);
        setSample(preview);
        setView("active");
      }
      setStatus(value);
    }).catch(error=>{
      if(!controller.signal.aborted)setError(error instanceof Error?error.message:"이용 상태를 확인하지 못했어요.");
    });
    return()=>controller.abort();
  },[]);

  useEffect(()=>{
    if(view!=="intro")heading.current?.focus();
  },[view]);

  async function refresh() {
    setBusy(true);setError("");
    try {
      const value=await api<PremiumStatus>("premium");
      setStatus(value);
      setTicket("");setAcknowledged(false);
      if(value.tier==="premium_demo"){
        setView("active");
        setSample(await api<PremiumSample>("premium/demo/preview"));
      }else{
        setSample(null);setView("intro");
      }
    } catch(error) {
      setError(error instanceof Error?error.message:"이용 상태를 확인하지 못했어요.");
    } finally {setBusy(false);}
  }

  async function checkout() {
    setBusy(true);setError("");
    try {
      const result=await api<{checkout_token:string}>("premium/demo/checkout","POST");
      setTicket(result.checkout_token);setAcknowledged(false);setView("checkout");
    } catch(error) {
      setError(error instanceof Error?error.message:"결제 시연을 시작하지 못했어요.");
    } finally {setBusy(false);}
  }

  async function activate(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if(!acknowledged||!ticket||busy)return;
    setBusy(true);setError("");
    try {
      const value=await api<PremiumStatus>("premium/demo/activate","POST",{checkout_token:ticket,acknowledged:true});
      setStatus(value);setView("active");setTicket("");
      setSample(await api<PremiumSample>("premium/demo/preview"));
    } catch(error) {
      setError(error instanceof Error?error.message:"시연 상태를 확인하지 못했어요.");
    } finally {setBusy(false);}
  }

  async function reset() {
    setBusy(true);setError("");
    try {
      setStatus(await api<PremiumStatus>("premium/demo","DELETE"));
      setSample(null);setTicket("");setAcknowledged(false);setView("intro");
      requestAnimationFrame(()=>heading.current?.focus());
    } catch(error) {
      setError(error instanceof Error?error.message:"시연을 초기화하지 못했어요.");
    } finally {setBusy(false);}
  }

  return <div className={styles.page} aria-busy={busy}>
    {error&&<div className="error" role="alert"><p>{error}</p><button type="button" className="button secondary" disabled={busy} onClick={refresh}>이용 상태 다시 확인</button></div>}
    {!status&&!error&&<p className={styles.loading} role="status"><LoaderCircle className="spin" size={18}/>이용 상태를 확인하고 있어요</p>}
    {view==="intro"&&<>
      <section className={`panel ${styles.intro}`}>
        <Moon size={28} className={styles.moon} aria-hidden="true"/>
        <p className={styles.eyebrow}>DALJAM PREMIUM</p>
        <h2 ref={heading} tabIndex={-1}>내 수면 습관을 조금 더 깊이</h2>
        <p>매일의 기록을 이어가는 무료 기능과, 준비 중인 프리미엄 코칭을 살펴보세요.</p>
        {status&&<p className={styles.state}>현재 이용 상태 <strong>무료</strong></p>}
      </section>
      <div className={styles.comparison} aria-label="무료와 프리미엄 기능 비교">
        <section className="panel"><h2>무료</h2><p>지금처럼 나의 밤을 기록해요.</p><ul>
          <li>자동·수동 수면 기록과 분석</li><li>측정 기록의 수면 단계 그래프</li>
          <li>Health Connect·iPhone JSON 가져오기</li><li>규칙 기반 개인화 코칭</li><li>취침 목표·추천과 아침 계획</li>
        </ul></section>
        <section className={`panel ${styles.premiumCard}`}><h2>Premium <span>준비 중</span></h2><p>무료 기능을 모두 포함해요.</p><ul>
          <li>실제 AI 모델 기반 개인화 코칭</li><li>최근 기록을 종합한 심화 습관 분석</li><li>기록에 맞춘 행동 제안</li>
          <li>선택한 코칭 말투·강도 반영</li>
        </ul><p className={styles.note}>실제 AI 서비스는 준비 중이에요. 가격과 구독 기간은 아직 정해지지 않았어요.</p></section>
      </div>
      <section className={`panel ${styles.demoCard}`}>
        <h2>프리미엄 업그레이드 시연</h2>
        <p>실제 청구 없이 모의 결제를 진행하고, 준비된 개인화 코칭 예시를 체험해 보세요.</p>
        <button type="button" className="button primary" disabled={busy||!status?.demo_available} onClick={checkout}>
          {busy?<LoaderCircle className="spin" size={18}/>:<Sparkles size={18}/>}모의 결제로 체험하기
        </button>
        {status&&!status.demo_available&&<p className={styles.note}>현재 환경에서는 결제 시연을 사용할 수 없어요. 서비스 소개를 확인할 수 있어요.</p>}
      </section>
    </>}
    {view==="checkout"&&<section className={`panel ${styles.checkout}`}>
      <p className={styles.eyebrow}>발표 전용 · 모의 결제</p>
      <h2 ref={heading} tabIndex={-1}>결제 시연을 확인해 주세요</h2>
      <p>프리미엄 시연을 활성화하면 가상 수면 기록으로 준비한 샘플 조언을 볼 수 있어요.</p>
      <div className={styles.notice}><strong>실제 결제가 발생하지 않아요.</strong><p>금전 거래와 자동 갱신이 없으며 카드·계좌·인증 정보를 입력하지 않아요.</p></div>
      <form onSubmit={activate}>
        <label className={styles.consent}><input type="checkbox" checked={acknowledged} onChange={event=>setAcknowledged(event.target.checked)} required/><span>실제 청구가 없는 발표 시연임을 확인했어요.</span></label>
        <div className={styles.actions}>
          <button type="button" className="button secondary" disabled={busy} onClick={()=>{setView("intro");setTicket("");setError("");requestAnimationFrame(()=>heading.current?.focus());}}>취소</button>
          <button type="submit" className="button primary" disabled={busy||!acknowledged}>{busy?<LoaderCircle className="spin" size={18}/>:<Check size={18}/>}모의 결제 완료</button>
        </div>
      </form>
    </section>}
    {view==="active"&&<>
      <section className={`panel ${styles.demoCard}`}>
        <p className={styles.eyebrow}>모의 결제 완료</p>
        <h2 ref={heading} tabIndex={-1}>프리미엄 시연 활성화</h2>
        <p>모의 결제로 발표용 체험이 활성화됐어요. 일반 코칭은 무료 규칙 기반이며, 아래 전용 버튼은 서버의 실제 AI 시연 설정에 따라 동작해요.</p>
        <p className={styles.note}>시연은 초기화·로그아웃·서버 재시작 또는 활성화 후 24시간 경과 시 종료돼요.</p>
      </section>
      {status&&<PremiumLiveCoaching status={status} onManualSaved={onManualSaved}/>}
      <details open={!status?.live_ai_available} className={styles.sampleDetails}><summary>샘플 데이터 코칭 예시 보기</summary>
      {sample?<section className={`panel ${styles.sample}`} aria-labelledby="premium-sample-title">
        <h2 id="premium-sample-title"><Sparkles size={21} aria-hidden="true"/>{sample.title}</h2>
        <p className={styles.note}>{sample.notice}</p>
        <div className={styles.sampleRecords}>{sample.sample_records.map(row=><div key={row.label}>
          <strong>{row.label}</strong><span>{row.bedtime} 취침 · {row.wake_time} 기상</span>
          <small>추정 수면 시간 {minutes(row.estimated_sleep_minutes)}</small>
        </div>)}</div>
        <p className={styles.sampleText}>{sample.coaching}</p>
        <p className={styles.note}>현재 말투는 {sample.expression.speech==="casual"?"반말":"존댓말"}, 강도는 {{gentle:"다정함",firm:"단호함",direct:"강한 직설"}[sample.expression.intensity]}이에요. 마이페이지에서 바꾼 뒤 다시 열어 비교할 수 있어요.</p>
      </section>:<p role="status" className={styles.loading}>샘플 조언을 확인하고 있어요.</p>}
      </details>
      <button type="button" className="button secondary" disabled={busy} onClick={reset}><RotateCcw size={17}/>시연 초기화 · 무료로 돌아가기</button>
    </>}
  </div>;
}
