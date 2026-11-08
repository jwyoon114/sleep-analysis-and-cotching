import {NextRequest,NextResponse} from 'next/server';
export const runtime='nodejs';
export const dynamic='force-dynamic';
const LIMIT=3*1024*1024;
export async function POST(request:NextRequest){
  const fail=(detail:string,status:number)=>NextResponse.json({detail},{status,headers:{'Cache-Control':'no-store'}});
  const authorization=request.headers.get('authorization');
  if(!authorization||!/^Bearer [A-Za-z0-9_-]{40,200}$/.test(authorization))return fail('건강앱 연결이 필요합니다.',401);
  if(Number(request.headers.get('content-length')||0)>LIMIT)return fail('동기화 기록이 너무 큽니다.',413);
  // Read a bounded stream, including chunked requests without Content-Length.
  const reader=request.body?.getReader();if(!reader)return fail('동기화 기록이 없습니다.',400);
  const chunks:Uint8Array[]=[];let length=0;
  for(;;){const {done,value}=await reader.read();if(done)break;length+=value.byteLength;if(length>LIMIT){await reader.cancel();return fail('동기화 기록이 너무 큽니다.',413);}chunks.push(value);}
  const body=new Uint8Array(length);let at=0;for(const c of chunks){body.set(c,at);at+=c.byteLength;}
  try{
    const base=new URL(process.env.SLEEP_API_URL||'http://127.0.0.1:8011');
    const response=await fetch(new URL('/mobile/health-sync',base),{method:'POST',headers:{Authorization:authorization,'Content-Type':'application/json'},body,redirect:'error',cache:'no-store',signal:AbortSignal.timeout(45000)});
    const result=await response.json();return NextResponse.json(result,{status:response.status,headers:{'Cache-Control':'no-store, private'}});
  }catch{return fail('달잠 서버에 연결하지 못했어요. 다음에 다시 동기화합니다.',502);}
}
