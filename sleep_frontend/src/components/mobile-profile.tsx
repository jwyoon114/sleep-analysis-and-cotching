import {Bell, ChevronRight, HeartPulse, Info, LogOut, Moon, Settings2, Trash2} from "lucide-react";

import {useRef, type ReactNode} from "react";

export default function MobileProfile({username, preferences, onAccount, onPlan, onTrash, onUpload, onLogout, demo, busy, health}: {
  username:string; preferences:ReactNode;

  onAccount:()=>void; onPlan:()=>void; onTrash:()=>void; onUpload:()=>void; onLogout:()=>void;
  demo:boolean; busy:boolean; health?:ReactNode;
}) {
  const galaxyHealth=useRef<HTMLDivElement>(null);
  return <div className="profile-menu">
    <section className="panel">
      <h2><Moon size={21}/>개인화 설정</h2>
      {preferences}
    </section>
    <button type="button" className="profile-link panel" onClick={onAccount}><Settings2 size={21}/><span><strong>계정 정보 및 관리</strong><small>{username} 님</small></span><ChevronRight size={19}/></button>
    <button type="button" className="profile-link panel" onClick={onPlan}><Bell size={21}/><span><strong>취침 알림 설정</strong><small>취침·기상 목표 · 휴대폰 알림 준비 중</small></span><ChevronRight size={19}/></button>
    <section className="panel profile-health">
      <h2><HeartPulse size={21}/>건강 데이터 연결</h2>
      <div className="profile-health-actions">
        <button type="button" className="button secondary" onClick={onUpload}>iPhone · JSON 가져오기</button>
        <button type="button" className="button secondary" onClick={()=>{
          galaxyHealth.current?.focus({preventScroll:true});
          galaxyHealth.current?.scrollIntoView({block:"start"});
        }}>Galaxy · Health Connect</button>
      </div>
      <p className="muted">iPhone은 Apple 건강 기록을 지원하는 JSON 파일로 가져와요.</p>
      <div ref={galaxyHealth} id="galaxy-health" role="region" aria-label="Galaxy 건강 데이터 연결" tabIndex={-1}>{health??<p className="muted">갤럭시 테스트 앱에 로그인하면 Health Connect를 연결할 수 있어요.</p>}</div>
    </section>
    <button type="button" className="profile-link panel" onClick={onTrash}><Trash2 size={21}/><span><strong>내 데이터 관리</strong><small>휴지통과 복원</small></span><ChevronRight size={19}/></button>
    <section className="panel profile-info"><h2><Info size={21}/>앱 정보 및 도움말</h2><a href="/privacy">개인정보 처리 안내</a><a href="/health-privacy">건강 데이터 사용 안내</a></section>
    <button type="button" className="button secondary" disabled={busy} onClick={onLogout}><LogOut size={17}/>{demo?"체험 종료":"로그아웃"}</button>
  </div>;
}
