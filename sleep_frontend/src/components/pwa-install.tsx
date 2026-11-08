"use client";

import {useEffect,useRef,useState} from "react";
import {Download,Smartphone,X} from "lucide-react";
type InstallEvent=Event&{prompt:()=>Promise<void>;userChoice:Promise<{outcome:string}>};

export default function PwaInstall(){
  const [installed,setInstalled]=useState(false),[prompt,setPrompt]=useState<InstallEvent|null>(null),[open,setOpen]=useState(false),[message,setMessage]=useState("");
  const dialog=useRef<HTMLDialogElement>(null);
  useEffect(()=>{
    const query=window.matchMedia("(display-mode: standalone)");
    const detect=()=>setInstalled(query.matches||!!(navigator as Navigator&{standalone?:boolean}).standalone||!!window.DaljamNative);
    detect();query.addEventListener("change",detect);window.addEventListener("daljam-native-ready",detect);
    const before=(e:Event)=>{e.preventDefault();setPrompt(e as InstallEvent);};
    const done=()=>{setInstalled(true);setPrompt(null);setOpen(false);};
    window.addEventListener("beforeinstallprompt",before);window.addEventListener("appinstalled",done);
    if("serviceWorker" in navigator&&window.isSecureContext){navigator.serviceWorker.register("/sw.js",{scope:"/",updateViaCache:"none"}).catch(()=>{});}
    return()=>{query.removeEventListener("change",detect);window.removeEventListener("daljam-native-ready",detect);window.removeEventListener("beforeinstallprompt",before);window.removeEventListener("appinstalled",done);};
  },[]);
  useEffect(()=>{if(open)dialog.current?.showModal();else dialog.current?.close();},[open]);
  if(installed)return null;
  return <><button className="pwa-help-button" onClick={()=>setOpen(true)}><Smartphone size={17}/>앱 설치 안내</button><dialog ref={dialog} className="pwa-dialog" onClose={()=>setOpen(false)} onCancel={()=>setOpen(false)}><button className="icon-button pwa-close" aria-label="설치 안내 닫기" onClick={()=>setOpen(false)}><X/></button><span className="eyebrow">DALJAM ON YOUR PHONE</span><h2>달잠을 홈 화면에서 열어요</h2><p>아이폰과 안드로이드의 지원 브라우저에서 앱 아이콘으로 설치할 수 있어요.</p>
    {prompt&&<button className="button primary full" onClick={async()=>{try{await prompt.prompt();const result=await prompt.userChoice;if(result.outcome!=="accepted")setMessage("나중에 브라우저 메뉴에서도 설치할 수 있어요.");setPrompt(null);}catch{setMessage("브라우저 메뉴의 앱 설치 또는 홈 화면에 추가를 이용하세요.");}}}><Download size={17}/>이 기기에 설치</button>}
    <h3>아이폰 · 아이패드</h3><p>Safari에서 접속 → 공유 메뉴 → <strong>홈 화면에 추가</strong> → 표시되는 경우 ‘웹 앱으로 열기’ 켜기 → 추가</p><h3>안드로이드 · 갤럭시</h3><p>Chrome 또는 삼성 인터넷에서 접속 → 브라우저 메뉴 → <strong>앱 설치</strong> 또는 <strong>홈 화면에 추가</strong></p><h3>건강앱 자동 연결</h3><p>홈 화면에 추가하는 웹앱과 건강앱을 읽는 달잠 전용 모바일 앱은 설치 방식이 달라요. 건강앱 자동 연결은 달잠 전용 모바일 앱에서 사용할 수 있어요.</p><h3>연결이 필요해요</h3><p>인터넷과 서버 PC가 켜져 있어야 기록을 불러오고 분석할 수 있어요. 임시 공유 주소가 바뀌면 새 주소로 다시 설치해야 합니다.</p><p>수면 기록과 인증 정보는 오프라인 캐시에 저장하지 않습니다. 취침·기상 알람은 서버 PC에서 울리며 휴대폰 기본 알람에는 등록되지 않습니다.</p><p role="status">{message}</p><button className="button secondary full" onClick={()=>setOpen(false)}>확인했어요</button></dialog></>;
}
