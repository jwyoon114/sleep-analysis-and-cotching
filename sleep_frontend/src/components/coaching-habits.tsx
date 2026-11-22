"use client";

import {useEffect, useState} from "react";
import {api} from "@/lib/sleep";

type Preferences = {
  age_group: string | null;
  usual_bedtime: string | null;
  usual_wake_time: string | null;
};
type Habits = {caffeine: string | null; satisfaction: string | null};
type Night = {day: string; habits: Habits};

export default function CoachingHabits({recordId, busy}: {recordId: string; busy: boolean}) {
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [night, setNight] = useState<Night | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [retry, setRetry] = useState(0);
  const path = `coach/habits/${recordId}`;

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      api<Preferences>("coach/preferences", "GET", undefined, controller.signal),
      api<Night>(path, "GET", undefined, controller.signal),
    ]).then(([settings, daily]) => {
      if (controller.signal.aborted) return;
      setPreferences(settings);
      setNight(daily);
    }).catch(() => {
      if (!controller.signal.aborted) setMessage("선택 입력을 불러오지 못했어요.");
    });
    return () => controller.abort();
  }, [path, retry]);

  async function save(form: HTMLFormElement, daily: boolean) {
    const values = Object.fromEntries([...new FormData(form)].map(([key, value]) => [key, value || null]));
    setSaving(true);
    setMessage("");
    try {
      if (daily) setNight(await api<Night>(path, "PATCH", values));
      else setPreferences(await api<Preferences>("coach/preferences", "PATCH", values));
      setMessage(daily ? "이 날짜의 생활습관을 저장했어요." : "평소 설정을 저장했어요.");
    } catch {
      setMessage("입력을 저장하지 못했어요. 다시 시도해 주세요.");
    } finally {
      setSaving(false);
    }
  }

  function select(name: keyof (Habits & Preferences), label: string, value: string | null, choices: string[]) {
    return <label>{label}<select name={name} defaultValue={value ?? ""}>
      <option value="">미입력</option>
      {choices.map(choice => <option key={choice}>{choice}</option>)}
    </select></label>;
  }

  return <details className="coaching-optional">
    <summary>생활습관과 평소 설정</summary>
    {night && preferences ? <>
      <form onSubmit={event => {event.preventDefault(); void save(event.currentTarget, true);}}>
        <h3>{night.day.replaceAll("-", ".")} 생활습관</h3>
        {select("caffeine", "취침 전 6시간 이내 카페인 섭취", night.habits.caffeine, ["없음", "있음"])}
        {select("satisfaction", "수면 만족도", night.habits.satisfaction, ["좋음", "보통", "나쁨"])}
        <button className="button secondary" disabled={busy || saving}>날짜별 입력 저장</button>
      </form>
      <form onSubmit={event => {event.preventDefault(); void save(event.currentTarget, false);}}>
        <h3>평소 설정</h3>
        <p>이 계정의 다음 기록에도 적용돼요.</p>
        {select("age_group", "연령 구분", preferences.age_group, ["성인", "미성년자"])}
        <label>평소 취침 시각<input name="usual_bedtime" type="time" defaultValue={preferences.usual_bedtime ?? ""}/></label>
        <label>평소 기상 시각<input name="usual_wake_time" type="time" defaultValue={preferences.usual_wake_time ?? ""}/></label>
        <button className="button secondary" disabled={busy || saving}>평소 설정 저장</button>
      </form>
    </> : message ? <button className="button secondary" onClick={() => {setMessage(""); setRetry(value => value + 1);}}>다시 불러오기</button>
      : <p>선택 입력 불러오는 중</p>}
    {message && <p role="status">{message}</p>}
  </details>;
}
