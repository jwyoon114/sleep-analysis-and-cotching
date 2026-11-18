import type {SleepRecord} from "./sleep";

export function homeSummary(record: SleepRecord | undefined, loading: boolean) {
  if (!record) return loading
    ? {title:"수면 기록을 확인하고 있어요", description:"최근 수면 기록을 불러오는 중이에요."}
    : {title:"나의 수면 기록부터 연결해요", description:"기록을 가져오면 수면 시간과 나에게 맞는 코칭을 확인할 수 있어요."};
  const date=record.start.slice(0,10).replaceAll("-", ".");
  if (!Number.isFinite(record.asleep_minutes) || record.asleep_minutes < 0)
    return {title:"최근 수면 기록을 살펴봐요",description:`${date} 기록 · 수면 시간을 확인할 정보가 부족해요.`};
  const total=Math.round(record.asleep_minutes);
  const duration=total<60?`${total}분`:`${Math.floor(total/60)}시간${total%60?` ${total%60}분`:""}`;
  return {
    title:record.unrecorded_minutes>0?`확인된 수면은 ${duration}이에요`:`지난 수면은 ${duration}이었어요`,
    description:record.unrecorded_minutes>0
      ? `${date} 기록 · 비어 있는 구간은 상세 기록에서 확인해 주세요.`
      : `${date} 기록을 바탕으로 수면 흐름을 정리했어요.`,
  };
}
