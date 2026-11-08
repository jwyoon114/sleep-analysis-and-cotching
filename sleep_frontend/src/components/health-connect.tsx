"use client";
import {useCallback,useEffect,useRef,useState} from 'react';
import {api,type User} from '@/lib/sleep';

type Source={id:string;name:string};
type NativeStatus={available:boolean;connected:boolean;provider:string;accountId?:string;lastSyncedAt?:string;background?:boolean;error?:string};
type Native={platform:'android'|'ios';request:<T>(method:string,payload?:unknown)=>Promise<T>};
declare global {interface Window {DaljamNative?:Native}}
export async function stopNativeHealth(){if(window.DaljamNative)await window.DaljamNative.request('disconnect');}

export default function HealthConnect({user,onSynced}:{user:User;onSynced:()=>void}){
  const adviceTimer=useRef<ReturnType<typeof setTimeout>|null>(null);
  const [remote,setRemote]=useState<{connected:boolean;connection?:{source_name:string;last_synced_at:string;advice_status?:string}}>();
  useEffect(()=>{api<typeof remote>('watch/health/connection').then(setRemote).catch(()=>{});return()=>{if(adviceTimer.current)clearTimeout(adviceTimer.current);};},[user.id]);
  const [native,setNative]=useState<Native>(),[state,setState]=useState<NativeStatus>(),[sources,setSources]=useState<Source[]>([]),[source,setSource]=useState('');
  const [busy,setBusy]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState(''),[autoCoach,setAutoCoach]=useState(false);
  const read=useCallback(async(n:Native)=>{const s=await n.request<NativeStatus>('status');if(s.connected&&s.accountId!==user.id){await n.request('disconnect');s.connected=false;}setState(s);return s;},[user.id]);
  const sync=useCallback(async(n:Native)=>{setBusy(true);setError('');try{
    const r=await n.request<{added_sessions:number;updated_sessions:number;ignored_incomplete:number;advice_queued:boolean;analysis_ids:string[]}>('sync');
    setMessage(r.ignored_incomplete?'동기화했어요. 수면 단계가 없는 일부 기록은 분석에서 제외했어요.':r.added_sessions||r.updated_sessions?'새 수면 기록을 가져와 분석했어요.':'최신 수면 기록을 확인했어요. 새 기록이 없다면 건강앱의 수면 기록과 접근 권한을 확인해 주세요.');
    await read(n);onSynced();
    if(r.advice_queued&&r.analysis_ids.length){
      if(adviceTimer.current)clearTimeout(adviceTimer.current);
      const id=r.analysis_ids.at(-1);let tries=0;
      const poll=async()=>{try{const c=await api<{history:unknown[]}>(`watch/sessions/${id}/coaching`);if(c.history.length){onSynced();setMessage('수면 분석과 AI 조언을 저장했어요.');return;}}catch{}if(++tries<20)adviceTimer.current=setTimeout(poll,3000);};
      adviceTimer.current=setTimeout(poll,3000);
    }
  }catch(e){setError(e instanceof Error?e.message:'건강앱 연결을 확인해 주세요.');await read(n).catch(()=>{});}finally{setBusy(false);}},[read,onSynced]);
  useEffect(()=>{
    let alive=true;let running=false;
    const start=async()=>{const n=window.DaljamNative;if(!n||running)return;running=true;try{if(alive)setNative(n);const s=await read(n);if(alive&&s.connected)await sync(n);}catch(e){if(alive)setError(e instanceof Error?e.message:'연결을 확인해 주세요.');}finally{running=false;}};
    const visible=()=>{if(document.visibilityState==='visible')void start();};
    void start();window.addEventListener('daljam-native-ready',start);document.addEventListener('visibilitychange',visible);
    return()=>{alive=false;window.removeEventListener('daljam-native-ready',start);document.removeEventListener('visibilitychange',visible);};
  },[read,sync]);
  async function authorize(){if(!native)return;setBusy(true);setError('');try{const r=await native.request<{sources:Source[]}>('authorize');setSources(r.sources);setSource(r.sources[0]?.id||'');if(!r.sources.length)setMessage('접근 가능한 수면 기록이 없어요. 건강앱에 기록이 있는지, 수면 읽기 권한을 허용했는지 확인해 주세요.');}catch(e){setError(e instanceof Error?e.message:'건강앱 권한을 확인해 주세요.');}finally{setBusy(false);}}
  async function connect(){if(!native||!source)return;setBusy(true);setError('');let issued=false;try{
    const selected=sources.find(s=>s.id===source)!;
    const pair=await api<{sync_token:string;account_id:string}>('watch/health/connection','POST',{provider:native.platform==='ios'?'healthkit':'health_connect',source_id:source,source_name:selected.name,auto_coach:autoCoach});issued=true;
    await native.request('configure',{token:pair.sync_token,accountId:pair.account_id,sourceId:source,sourceName:selected.name});setSources([]);await sync(native);
  }catch(e){if(issued)await api('watch/health/connection','DELETE').catch(()=>{});setError(e instanceof Error?e.message:'연결하지 못했어요. 다시 시도해 주세요.');}finally{setBusy(false);}}
  async function disconnect(){if(!native)return;setBusy(true);setError('');try{try{await api('watch/health/connection','DELETE');}finally{await stopNativeHealth();}await read(native);setMessage('자동 연결을 해제했어요. 이미 저장된 기록은 분석 기록에서 관리할 수 있어요.');}catch(e){setError(e instanceof Error?e.message:'연결 해제를 다시 시도해 주세요.');}finally{setBusy(false);}}
  return <section className="panel health-connect"><h2>건강앱 자동 연결</h2>
    <p>수면 기록을 파일로 옮기지 않아도, 달잠이 가져와 분석해요.</p>
    {!native?<><p className="muted">자동 연결은 달잠의 안드로이드·아이폰 앱에서 사용할 수 있어요. 웹에서는 동기화된 기록과 AI 조언을 볼 수 있어요.</p>{remote?.connected&&<><p>{remote.connection?.source_name} 연결됨 · 마지막 동기화: {remote.connection?.last_synced_at?new Date(remote.connection.last_synced_at).toLocaleString('ko-KR'):'아직 없음'}</p>{remote.connection?.advice_status&&<p>{remote.connection.advice_status}</p>}<button className="button secondary" disabled={busy} onClick={async()=>{setBusy(true);try{await api('watch/health/connection','DELETE');setRemote({connected:false});setMessage('휴대폰의 자동 전송을 중지했어요.');}catch{setError('연결 해제를 다시 시도해 주세요.');}finally{setBusy(false);}}}>휴대폰 자동 연결 해제</button></>}</>:<>
      <p>{native.platform==='ios'?'Apple 건강':'삼성헬스 · Health Connect'} · {state?.connected?'연결됨':'아직 연결되지 않았어요'}</p>
      {state?.connected?<><p>마지막 동기화: {state.lastSyncedAt?new Date(state.lastSyncedAt).toLocaleString('ko-KR'):'첫 기록을 기다리고 있어요'}</p><p className="muted">{state.background?'백그라운드 동기화를 사용해요.':'앱을 열면 자동으로 동기화해요. 백그라운드 접근은 휴대폰 설정에 따라 제한될 수 있어요.'} PC 서버가 꺼져 있으면 다음 연결 때 다시 가져와요.</p><div className="health-actions"><button className="button secondary" disabled={busy} onClick={()=>sync(native)}>지금 확인</button><button className="button secondary" disabled={busy} onClick={disconnect}>연결 해제</button></div></>:sources.length?<><label>가져올 기록 출처<select value={source} onChange={e=>setSource(e.target.value)}>{sources.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label><p className="muted">같은 수면이 중복되지 않도록 한 출처를 선택해요.</p><label className="checkbox-label"><input type="checkbox" checked={autoCoach} onChange={e=>setAutoCoach(e.target.checked)}/>새 기록의 AI 조언 자동 생성</label><p className="muted">켜면 최신 기록을 기존 AI 코칭 서비스로 보내 조언을 만들어요. 서버의 API 설정이 필요하며 이용료가 발생할 수 있어요.</p><button className="button primary" disabled={busy||!source} onClick={connect}>이 출처로 자동 연결</button></>:<><button className="button primary" disabled={busy||state?.available===false} onClick={authorize}>건강앱 연결하기</button>{state?.available===false&&<p>이 휴대폰에서 건강 데이터 기능을 사용할 수 없어요. Health Connect 설치·업데이트와 기기 지원 여부를 확인해 주세요.</p>}</>}
    </>}
    {busy&&<p role="status">건강앱 기록을 확인하고 있어요…</p>}{message&&<p role="status">{message}</p>}{(error||state?.error)&&<p className="error" role="alert">{error||state?.error}</p>}
    <a href="/health-privacy" target="_blank" rel="noreferrer">건강 데이터 사용 안내</a>
  </section>;
}
