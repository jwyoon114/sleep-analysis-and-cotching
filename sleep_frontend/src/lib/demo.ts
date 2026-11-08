import { type SleepRecord, type Coaching, dayBefore, today } from "./sleep";

export function demoRecords(): SleepRecord[] {
  const end = today();
  return [452,411,478,399,435,461,422,450,410,472,430,390,447,425].map((duration,i) => {
    const date = dayBefore(end,i), start = `${date}T23:15:00+09:00`;
    let cursor = new Date(start).getTime();
    const stages = [["core", duration*.45], ["deep",duration*.22],["wake",18+i%3*4],["rem",duration*.25],["core",duration*.08]] as const;
    const stage_minutes = {core:0,deep:0,rem:0,wake:0,unspecified:0};
    const local = (t: number) => new Date(t+9*3600000).toISOString().slice(0,19)+"+09:00";
    const segments = stages.map(([stage,raw])=>{const n=Math.round(raw),a=cursor;cursor+=n*60000;stage_minutes[stage]+=n;return {stage,minutes:n,start:local(a),end:local(cursor)};});
    return {analysis_id:`demo-${i}`,start,end:local(cursor),timezone:"Asia/Seoul",source:"가상 체험용 기록",asleep_minutes:stage_minutes.core+stage_minutes.deep+stage_minutes.rem,awake_minutes:stage_minutes.wake,unrecorded_minutes:0,wake_segment_count:1,coaching_count:1,warnings:[],stage_minutes,segments,vitals_summary:[]};
  });
}
export const demoCoaching: Coaching = {id:"demo-coach",created_at:new Date().toISOString(),coaching:"이번 체험 기록에서는 코어·깊은·렘수면 구간과 밤중 각성 구간을 확인할 수 있어요.\n\n매일 비슷한 시간에 하루를 마무리하는 작은 습관부터 시작해 보세요. 잠들기 전에는 화면 밝기를 낮추고, 몸과 마음이 쉴 시간을 마련해 보는 건 어떨까요?\n\n최근 취침 시간이 달라진 이유가 있었나요? 실제 기록과 생활습관을 함께 살펴보면 나에게 맞는 변화를 찾는 데 도움이 됩니다.\n\n이 문장은 화면 체험용 예시이며, 실제 AI 분석 결과가 아닙니다."};
