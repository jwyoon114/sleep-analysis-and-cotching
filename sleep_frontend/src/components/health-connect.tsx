"use client";
import {useCallback,useEffect,useRef,useState} from 'react';
import {api,type User} from '@/lib/sleep';
import {emptyHealthResult,healthIssue,healthSyncNotice,type HealthNotice,type HealthOperation} from '@/lib/health-sync-notice';

type Source={id:string;name:string};
type NativeStatus={available:boolean;connected:boolean;provider:string;accountId?:string;lastSyncedAt?:string;background?:boolean;error?:string};
export type AndroidConnection = "checking" | "connected" | "disconnected" | "unavailable" | "error";
type Native={platform:'android'|'ios';request:<T>(method:string,payload?:unknown)=>Promise<T>};
declare global {interface Window {DaljamNative?:Native}}
export async function stopNativeHealth(){if(window.DaljamNative)await window.DaljamNative.request('disconnect');}

export default function HealthConnect({user,onSynced,onAndroidStatus,onManualEntry}:{user:User;onSynced:()=>void;onAndroidStatus:(status:AndroidConnection)=>void;onManualEntry?:()=>void}){
  const adviceTimer=useRef<ReturnType<typeof setTimeout>|null>(null);
  const [remote,setRemote]=useState<{connected:boolean;connection?:{source_name:string;last_synced_at:string;advice_status?:string}}>();
  useEffect(()=>{api<typeof remote>('watch/health/connection').then(setRemote).catch(()=>{});return()=>{if(adviceTimer.current)clearTimeout(adviceTimer.current);};},[user.id]);
  const [native,setNative]=useState<Native>(),[state,setState]=useState<NativeStatus>(),[sources,setSources]=useState<Source[]>([]),[source,setSource]=useState('');
  const [busy,setBusy]=useState(false),[notice,setNotice]=useState<HealthNotice|null>(null),[autoCoach,setAutoCoach]=useState(false);
  const inFlight=useRef(false);
  const read=useCallback(async(n:Native)=>{
    try{
      const s=await n.request<NativeStatus>('status');
      if(s.connected&&s.accountId!==user.id){await n.request('disconnect');s.connected=false;}
      setState(s);
      if(n.platform==='android')onAndroidStatus(!s.available?'unavailable':s.connected?'connected':s.error?'error':'disconnected');
      return s;
    }catch(error){
      if(n.platform==='android')onAndroidStatus('error');
      throw error;
    }
  },[user.id,onAndroidStatus]);
  const run=useCallback(async (action:()=>Promise<void>)=>{
    if(inFlight.current)return;
    inFlight.current=true;
    if(adviceTimer.current)clearTimeout(adviceTimer.current);
    adviceTimer.current=null;
    setBusy(true);setNotice(null);
    try{await action();}
    finally{inFlight.current=false;setBusy(false);}
  },[]);
  const sync=useCallback(async(n:Native)=>{
    try{
      const result=await n.request<{added_sessions:number;updated_sessions:number;ignored_incomplete:number;advice_queued:boolean;analysis_ids:string[]}>('sync');
      setNotice(healthSyncNotice(result));
      await read(n).catch(()=>{});
      onSynced();
      if(result.advice_queued&&result.analysis_ids.length){
        const id=result.analysis_ids.at(-1);
        let tries=0;
        const poll=async()=>{
          const scheduled=adviceTimer.current;
          try{
            const result=await api<{history:unknown[]}>(`watch/sessions/${id}/coaching`);
            if(adviceTimer.current!==scheduled)return;
            if(result.history.length){onSynced();return;}
          }catch{}
          if(adviceTimer.current===scheduled&&++tries<20)adviceTimer.current=setTimeout(poll,3000);
        };
        adviceTimer.current=setTimeout(poll,3000);
      }
    }catch(error){
      await read(n).catch(()=>{});
      setNotice(healthIssue('sync',error instanceof Error?error.message:error,n.platform));
    }
  },[read,onSynced]);
  useEffect(()=>{
    let alive=true;
    const start=()=>{
      const n=window.DaljamNative;
      if(!n)return;
      setNative(n);
      void run(async()=>{
        try{const state=await read(n);if(alive&&state.connected)await sync(n);}
        catch(error){if(alive)setNotice(healthIssue('read',error instanceof Error?error.message:error,n.platform));}
      });
    };
    const visible=()=>{if(document.visibilityState==='visible')start();};
    start();window.addEventListener('daljam-native-ready',start);document.addEventListener('visibilitychange',visible);
    return()=>{alive=false;window.removeEventListener('daljam-native-ready',start);document.removeEventListener('visibilitychange',visible);};
  },[read,run,sync]);
  function authorize(){
    if(!native)return;
    void run(async()=>{
      try{
        const result=await native.request<{sources:Source[]}>('authorize');
        setSources(result.sources);
        setSource(result.sources[0]?.id||'');
        setNotice(result.sources.length?{role:'status',text:'수면 기록을 가져올 건강앱을 선택해 주세요.'}:emptyHealthResult(native.platform));
      }catch(error){setNotice(healthIssue('read',error instanceof Error?error.message:error,native.platform));}
    });
  }
  function connect(){
    const selected=sources.find(item=>item.id===source);
    if(!native||!selected)return;
    void run(async()=>{
      let operation:HealthOperation='server';
      try{
        const pair=await api<{sync_token:string;account_id:string}>('watch/health/connection','POST',{provider:native.platform==='ios'?'healthkit':'health_connect',source_id:source,source_name:selected.name,auto_coach:autoCoach});
        operation='configure';
        await native.request('configure',{token:pair.sync_token,accountId:pair.account_id,sourceId:source,sourceName:selected.name});
        setSources([]);
        await sync(native);
      }catch(error){
        if(operation==='configure')await api('watch/health/connection','DELETE').catch(()=>{});
        setNotice(healthIssue(operation,error instanceof Error?error.message:error,native.platform));
      }
    });
  }
  function disconnect(){
    void run(async()=>{
      try{
        if(native){try{await api('watch/health/connection','DELETE');}finally{await stopNativeHealth();}await read(native);}
        else {await api('watch/health/connection','DELETE');setRemote({connected:false});}
        setNotice({role:'status',text:'자동 연결을 해제했어요. 이미 저장된 수면 기록은 유지됩니다.'});
      }catch(error){setNotice(healthIssue('disconnect',error instanceof Error?error.message:error,native?.platform));}
    });
  }
  const result=notice??(state?.error?healthIssue('sync',state.error,native?.platform):null);
  return <section className="panel health-connect"><h2>건강앱 자동 연결</h2>
    <p>동기화하거나 가져온 수면 기록은 로그인한 계정에서 확인할 수 있어요.</p>
    {!native?<><p className="muted">삼성 헬스 자동 연결은 갤럭시 테스트 앱에서 사용할 수 있어요. iPhone은 Apple 건강 기록을 수면 JSON으로 내보낸 뒤 가져올 수 있어요.</p>{remote?.connected&&<><p>{remote.connection?.source_name} 연결됨 · 마지막 동기화: {remote.connection?.last_synced_at?new Date(remote.connection.last_synced_at).toLocaleString('ko-KR'):'아직 없음'}</p>{remote.connection?.advice_status&&<p>{remote.connection.advice_status}</p>}<button className="button secondary" disabled={busy} onClick={disconnect}>휴대폰 자동 연결 해제</button></>}</>:<>
      <p>{native.platform==='ios'?'Apple 건강':'삼성헬스 · Health Connect'} · {state?.connected?'연결됨':'아직 연결되지 않았어요'}</p>
      {state?.connected?<><p>마지막 동기화: {state.lastSyncedAt?new Date(state.lastSyncedAt).toLocaleString('ko-KR'):'첫 기록을 기다리고 있어요'}</p><p className="muted">{state.background?'백그라운드 동기화를 사용해요.':'달잠을 열거나 ‘지금 확인’을 누르면 동기화해요.'} 연결이 끊기면 인터넷을 확인한 뒤 다시 시도해 주세요.</p><div className="health-actions"><button className="button secondary" disabled={busy} onClick={()=>void run(()=>sync(native))}>지금 확인</button><button className="button secondary" disabled={busy} onClick={disconnect}>연결 해제</button></div></>:sources.length?<><label>가져올 기록 출처<select value={source} onChange={e=>setSource(e.target.value)}>{sources.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label><p className="muted">같은 수면이 중복되지 않도록 한 출처를 선택해요.</p><label className="checkbox-label"><input type="checkbox" checked={autoCoach} onChange={e=>setAutoCoach(e.target.checked)}/>새 기록의 무료 코칭 자동 생성</label><p className="muted">켜면 새로 저장한 수면 기록으로 조언을 만들어요.</p><button className="button primary" disabled={busy||!source} onClick={connect}>이 출처로 자동 연결</button></>:<><button className="button primary" disabled={busy||state?.available===false} onClick={authorize}>건강앱 연결하기</button>{state?.available===false&&<p>이 휴대폰에서 건강 데이터 기능을 사용할 수 없어요. Health Connect 설치·업데이트와 기기 지원 여부를 확인해 주세요.</p>}</>}
    </>}
    {busy?<p role="status">건강앱 연결과 수면 기록을 확인하고 있어요…</p>:result&&<div>
      <p role={result.role} className={result.role==='alert'?'error':undefined}>{result.text}</p>
      {result.manual&&onManualEntry&&<button type="button" className="button secondary" onClick={onManualEntry}>수면 시간 직접 입력</button>}
    </div>}
    {!busy&&!result&&native&&state?.available===false&&onManualEntry&&
      <button type="button" className="button secondary" onClick={onManualEntry}>수면 시간 직접 입력</button>}
    <a href="/health-privacy" target="_blank" rel="noreferrer">건강 데이터 사용 안내</a>
  </section>;
}
