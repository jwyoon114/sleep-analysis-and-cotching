import type {SleepRecord} from "./sleep";

export function homeSummary(record: SleepRecord | undefined, status: "loading" | "ready" | "error") {
  if (!record) {
    if (status === "loading") return {title:"수면 기록을 불러오고 있어요"};
    if (status === "error") return {title:"수면 기록을 불러오지 못했어요"};
    return {title:"아직 수면 기록이 없어요"};
  }
  const [year, month, day] = record.end.slice(0,10).split("-");
  const description = `${year}년 ${Number(month)}월 ${Number(day)}일 기상 기록`;
  const manual = record.data_type === "manual";
  const sleep = manual ? record.estimated_sleep_minutes : record.asleep_minutes;
  if (!Number.isFinite(sleep) || sleep < 0)
    return {title:"최근 수면 기록을 살펴봐요", description};
  const total=Math.round(sleep);
  const duration=total<60?`${total}분`:`${Math.floor(total/60)}시간${total%60?` ${total%60}분`:""}`;
  if(manual)return {title:`추정 수면은 ${duration}이에요`,description:`${description} · 직접 입력`};
  const partial = record.unrecorded_minutes > 0;
  return {
    title:partial ? `확인된 수면은 ${duration}이에요` : `최근에 ${duration} 잤어요`,
    description,
  };
}
