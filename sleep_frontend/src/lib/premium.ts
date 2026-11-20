export type PremiumStatus = {
  tier:"free"|"premium_demo";
  demo_available:boolean;
  paid_entitlement:false;
  live_ai_available:boolean;
  demo_expires_at:string|null;
  ai_usage?:AIUsage|null;
};

export type AIUsage = {limit:number; window_hours:number; used:number; calls_started:number; remaining:number; input_tokens:number; output_tokens:number; unknown_usage_calls:number};

export function demoRequestId(source:Pick<Crypto,"getRandomValues"> & Partial<Pick<Crypto,"randomUUID">> = globalThis.crypto):string {
  if(typeof source?.randomUUID==="function")return source.randomUUID();
  if(typeof source?.getRandomValues!=="function")throw new Error("보안 연결에서 달잠을 다시 열어 주세요.");
  const bytes=source.getRandomValues(new Uint8Array(16));
  bytes[6]=(bytes[6]&0x0f)|0x40;
  bytes[8]=(bytes[8]&0x3f)|0x80;
  const hex=Array.from(bytes,value=>value.toString(16).padStart(2,"0")).join("");
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}

export type PremiumAIResult = {kind:"sample";label:string;sample:PremiumSample;replayed:boolean;usage:null}
  | {kind:"openai"|"rules_fallback";label:string;coaching:import("./sleep").Coaching;request_id:string;replayed:boolean;usage:AIUsage};

export type PremiumSample = {
  title:string;
  source:"prepared_sample";
  synthetic:true;
  model_called:false;
  saved_to_history:false;
  expression:{speech:"polite"|"casual"; intensity:"gentle"|"firm"|"direct"};
  sample_records:{label:string; bedtime:string; wake_time:string; estimated_sleep_minutes:number}[];
  coaching:string;
  notice:string;
};
