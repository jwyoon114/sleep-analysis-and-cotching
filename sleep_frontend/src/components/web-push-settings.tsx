"use client";

import {useEffect, useState} from "react";
import {ApiError, api} from "@/lib/sleep";
import {applicationServerKey, pushSupport, subscriptionId, type PushSupport} from "@/lib/web-push";

type Device = {id:string; this_session:boolean; registered_at:string; durable:boolean; reminders_enabled:boolean};
type Settings = {enabled:boolean; public_key:string|null; devices:Device[]; test_enabled?:boolean; scheduled_enabled?:boolean};

export default function WebPushSettings() {
  const [support,setSupport]=useState<PushSupport|null>(null);
  const [settings,setSettings]=useState<Settings|null>(null);
  const [registration,setRegistration]=useState<ServiceWorkerRegistration|null>(null);
  const [subscription,setSubscription]=useState<PushSubscription|null>(null);
  const [localId,setLocalId]=useState<string|null>(null);
  const [loadError,setLoadError]=useState(false);
  const [revision,setRevision]=useState(0);
  const [busy,setBusy]=useState(false);
  const [notice,setNotice]=useState("");
  const [error,setError]=useState("");
  const refresh=()=>setRevision(value=>value+1);

  useEffect(()=>{
    const controller=new AbortController();
    const device=pushSupport();
    setSupport(device);
    const reload=()=>setRevision(value=>value+1);
    window.addEventListener("daljam-native-ready",reload);
    window.addEventListener("focus",reload);
    if(device==="supported"){
      setLoadError(false);
      api<Settings>("web-push","GET",undefined,controller.signal).then(data=>{
        if(!controller.signal.aborted)setSettings(data);
      }).catch(()=>{if(!controller.signal.aborted)setLoadError(true);});
      navigator.serviceWorker.ready.then(async worker=>{
        const push=await worker.pushManager.getSubscription();
        const id=push?await subscriptionId(push):null;
        if(controller.signal.aborted)return;
        setRegistration(worker);setSubscription(push);setLocalId(id);
      }).catch(()=>{if(!controller.signal.aborted)setLoadError(true);});
    }
    return ()=>{
      controller.abort();
      window.removeEventListener("daljam-native-ready",reload);
      window.removeEventListener("focus",reload);
    };
  },[revision]);

  async function act(action:()=>Promise<string>) {
    setBusy(true);setError("");setNotice("");
    try{setNotice(await action());}
    catch(e){setError(e instanceof ApiError?e.message:"브라우저 알림 설정과 인터넷 연결을 확인해 주세요.");}
    finally{setBusy(false);refresh();}
  }

  const permission=support==="supported"?Notification.permission:null;
  const enrolled=settings?.devices.find(device=>device.id===localId&&device.this_session);

  function enable(){
    const publicKey=settings?.public_key;
    if(!registration||!publicKey||permission==="denied"||pushSupport()!=="supported")return;
    void act(async()=>{
      // Calling subscribe directly from this button preserves the iOS user gesture.
      const existing=permission==="granted"?subscription:null;
      const push=existing??await registration.pushManager.subscribe({
        userVisibleOnly:true,applicationServerKey:applicationServerKey(publicKey),
      });
      await api("web-push/subscriptions","POST",push.toJSON());
      return "이 기기의 알림을 연결했어요.";
    });
  }

  function reminders(device:Device,enabled:boolean){
    void act(async()=>{
      await api("web-push/subscriptions/"+device.id,"PATCH",{enabled});
      return enabled?"이 기기의 취침 준비 알림을 켰어요.":"이 기기의 취침 준비 알림을 껐어요.";
    });
  }

  function remove(device:Device){
    void act(async()=>{
      await api("web-push/subscriptions/"+device.id,"DELETE");
      if(device.id===localId&&subscription){
        const removed=await subscription.unsubscribe().catch(()=>false);
        if(!removed)return "서버에서 알림을 해제했어요. 브라우저의 알림 권한은 기기 설정에서 관리할 수 있어요.";
      }
      return "기기 알림을 해제했어요.";
    });
  }

  function test(){
    if(!enrolled||permission!=="granted")return;
    void act(async()=>{
      try{await api("web-push/test","POST",{id:enrolled.id});}
      catch(e){
        if(e instanceof ApiError&&e.status===410)await subscription?.unsubscribe().catch(()=>false);
        throw e;
      }
      return "푸시 서비스가 요청을 접수했어요. 이 기기의 알림을 확인해 주세요.";
    });
  }

  if(support==="native")return <p>설치형 Android 앱의 알림은 별도 개발이 필요해요. 지원되는 브라우저 웹앱에서 테스트할 수 있어요.</p>;
  if(support==="apple-tab")return <p>iPhone·iPad에서는 Safari 공유 메뉴에서 홈 화면에 추가한 뒤 달잠 아이콘으로 다시 열어 주세요. iOS·iPadOS 16.4 이상이 필요해요.</p>;
  if(support==="unsupported")return <p>이 브라우저에서는 Web Push를 사용할 수 없어요. HTTPS에서 지원되는 브라우저를 사용해 주세요.</p>;
  if(loadError)return <p role="alert">알림 설정을 불러오지 못했어요. <button type="button" className="button secondary" onClick={refresh}>다시 확인</button></p>;
  if(!settings)return <p role="status">알림 설정을 확인하고 있어요.</p>;
  if(!settings.enabled&&!settings.devices.length)return <p>이 환경에서는 Web Push 알림이 꺼져 있어요.</p>;

  return <>
    <p>브라우저 권한 {permission==="granted"?"허용":permission==="denied"?"차단":"미설정"} · 이 기기 {enrolled?"연결됨":"미연결"}</p>
    <p className="muted">{settings.scheduled_enabled?"취침 목표 30분 전 알림을 기기별로 받을 수 있어요.":"취침 30분 전 예약 발송은 이 환경에서 꺼져 있어요."}</p>
    {permission==="denied"&&<p className="muted">다시 받으려면 기기나 브라우저의 알림 설정에서 달잠을 허용해 주세요.</p>}
    {!registration&&<p className="muted">브라우저 등록을 기다리고 있어요. 계속 표시되면 인터넷 연결을 확인하고 페이지를 다시 열어 주세요.</p>}
    <div className="plan-actions">
      {settings.enabled&&(!enrolled||!enrolled.durable)&&<button type="button" className="button primary" disabled={!registration||busy||permission==="denied"} onClick={enable}>{enrolled?"이 기기 다시 연결":"이 기기 연결"}</button>}
      {enrolled&&<>
        {settings.test_enabled&&<button type="button" className="button secondary" disabled={busy||permission!=="granted"} onClick={test}>테스트 알림 보내기</button>}
        {enrolled.durable&&(settings.scheduled_enabled||enrolled.reminders_enabled)&&<button type="button" className="button secondary" disabled={busy||(!enrolled.reminders_enabled&&permission!=="granted")} onClick={()=>reminders(enrolled,!enrolled.reminders_enabled)}>{enrolled.reminders_enabled?"취침 알림 끄기":"취침 알림 켜기"}</button>}
        <button type="button" className="button secondary" disabled={busy} onClick={()=>remove(enrolled)}>이 기기 해제</button>
      </>}
    </div>
    {settings.devices.some(device=>device.id!==enrolled?.id)&&<details>
      <summary>다른 기기 관리</summary>
      <ul className="plan-summary">{settings.devices.filter(device=>device.id!==enrolled?.id).map(device=><li key={device.id}>
        <span>{new Date(device.registered_at).toLocaleString("ko-KR")}에 연결</span>
        <button type="button" className="button secondary" disabled={busy} onClick={()=>remove(device)}>해제</button>
      </li>)}</ul>
    </details>}
    {error&&<p className="plan-error" role="alert">{error}</p>}
    {notice&&<p className="plan-notice" role="status">{notice}</p>}
  </>;
}
