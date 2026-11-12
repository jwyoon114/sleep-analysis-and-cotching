export type User = {id: string; username: string};
export type Stage = "core" | "deep" | "rem" | "wake" | "unspecified";
export type SleepRecord = {
  analysis_id: string; start: string; end: string; timezone: string; source: string;
  asleep_minutes: number; awake_minutes: number; unrecorded_minutes: number;
  wake_segment_count: number; coaching_count: number; warnings: string[];
  stage_minutes: Record<Stage, number>;
  segments: {start: string; end: string; stage: Stage; minutes: number}[];
  vitals_summary: {metric: string; unit: string; n: number; avg: number; min: number; max: number}[];
};
export type Coaching = {id: string; coaching: string; created_at: string; lifestyle?: Record<string,string>; context?: {engine?: string; presentation?: unknown; model: string; record_count: number; prompt_version: string; window_start: string; window_end: string; input_summary: unknown; alarm_schedule?: {bedtime:string|null;wake_time:string|null;timezone:string;reason:string}} | null};
export type Trash = {sessions: {id: string; deleted_at: string; expires_at: string; record: SleepRecord}[]; coaching: {id: string; coaching: string; expires_at: string; parent_in_trash: boolean}[]};
export type Daily = {date: string; asleep_minutes: number | null; awake_minutes: number | null; session_count: number};
export type Period = {start: string; end: string; session_count: number; recorded_days: number; average_asleep_minutes_per_recorded_day: number | null; average_awake_minutes_per_recorded_day: number | null; daily: Daily[]};
export type Comparison = {days: number; current: Period; previous: Period};
export const labels: Record<Stage,string> = {deep: "깊은 수면", core: "코어 수면", rem: "렘수면", wake: "각성", unspecified: "미분류"};
export const colors: Record<Stage,string> = {deep: "#6856a5", core: "#a18acb", rem: "#d0c0e8", wake: "#e9b590", unspecified: "#c8ccd3"};
export const minutes = (n: number | null | undefined) => n == null ? "기록 없음" : `${Math.floor(Math.round(n) / 60)}시간 ${Math.round(n) % 60}분`;
// Preserve the recorded local clock, rather than silently shifting timezones.
export const clock = (value: string) => value.slice(11, 16);
export const shortDate = (value: string) => new Date(value.slice(0,10) + "T12:00:00").toLocaleDateString("ko-KR", {month:"long",day:"numeric"});
export const today = () => new Intl.DateTimeFormat("en-CA", {timeZone:"Asia/Seoul",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());
export function dayBefore(value: string, offset: number) { const d = new Date(value + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() - offset); return d.toISOString().slice(0,10); }
export function daily(records: SleepRecord[], end: string, days: number): Daily[] {
  return Array.from({length:days}, (_,i) => {
    const date = dayBefore(end, days - i - 1), rows = records.filter(r => r.start.slice(0,10) === date);
    return {date, asleep_minutes: rows.length ? rows.reduce((sum,r) => sum + r.asleep_minutes,0) : null, awake_minutes: rows.length ? rows.reduce((sum,r) => sum + r.awake_minutes,0) : null, session_count: rows.length};
  });
}
export function compare(records: SleepRecord[], end: string, days: number): Comparison {
  const period = (last: string): Period => {
    const rows = daily(records,last,days), observed = rows.filter(d => d.asleep_minutes != null);
    return {start: rows[0].date,end:last,daily:rows,recorded_days:observed.length,session_count:rows.reduce((s,d)=>s+d.session_count,0),average_asleep_minutes_per_recorded_day:observed.length ? observed.reduce((s,d)=>s+(d.asleep_minutes||0),0)/observed.length : null,average_awake_minutes_per_recorded_day:observed.length ? observed.reduce((s,d)=>s+(d.awake_minutes||0),0)/observed.length : null};
  };
  return {days,current:period(end),previous:period(dayBefore(end,days))};
}
export class ApiError extends Error { constructor(message: string, public status: number) {super(message);} }
export async function api<T>(path: string, method = "GET", body?: unknown, signal?: AbortSignal): Promise<T> {
  const isFile = body instanceof FormData;
  const response = await fetch(`/api/sleep/${path}`, {method,signal,cache:"no-store",headers:body && !isFile ? {"Content-Type":"application/json"} : undefined,body:body ? isFile ? body as FormData : JSON.stringify(body) : undefined});
  const result = await response.json();
  if (!response.ok) {
    const detail = result.detail;
    const message = typeof detail === "string" ? detail : detail?.message || (Array.isArray(detail) ? "입력한 값의 형식과 길이를 확인해 주세요." : "요청을 처리하지 못했습니다.");
    throw new ApiError(message,response.status);
  }
  return result;
}
