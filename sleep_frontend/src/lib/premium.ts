export type PremiumStatus = {
  tier:"free"|"premium_demo";
  demo_available:boolean;
  paid_entitlement:false;
  live_ai_available:false;
  demo_expires_at:string|null;
};

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
