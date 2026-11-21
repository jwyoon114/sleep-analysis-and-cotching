import {ArrowRight, CalendarDays, LoaderCircle, Moon, RotateCcw, Sun} from "lucide-react";
import type {ReactNode} from "react";
import {clock, type Coaching, type SleepRecord} from "@/lib/sleep";
import SleepTimeline from "./sleep-timeline";

type Props = {
  record?: SleepRecord;
  recordsStatus: "loading" | "ready" | "error";
  coaching?: Coaching;
  coachingStatus: "loading" | "ready" | "error";
  connection: ReactNode;
  onRetryRecords: () => void;
  onRecord: () => void;
  onCoaching: () => void;
  onRetryCoaching: () => void;
  onMorningPlan: () => void;
};

function coachingExcerpt(text: string) {
  const paragraphs = text.trim().split(/\r?\n(?:[ \t]*\r?\n)+/);
  const suggestion = paragraphs.find(paragraph => /^실천 제안\r?\n/.test(paragraph));
  return (suggestion?.replace(/^실천 제안\r?\n/, "") ?? paragraphs[0]).trim();
}

export default function SleepDashboard({record, recordsStatus, coaching, coachingStatus, connection, onRetryRecords, onRecord, onCoaching, onRetryCoaching, onMorningPlan}: Props) {
  const excerpt = coaching ? coachingExcerpt(coaching.coaching) : "";

  return <div className="sleep-dashboard">
    {record ? <section className="dashboard-card dashboard-sleep-card" aria-labelledby="dashboard-sleep-title">
      <header className="dashboard-card-title"><h2 id="dashboard-sleep-title">수면 흐름</h2></header>
      <dl className="dashboard-sleep-times">
        <div><dt><Moon size={16} aria-hidden="true"/>취침</dt><dd>{clock(record.start)}</dd></div>
        <div><dt><Sun size={17} aria-hidden="true"/>기상</dt><dd>{clock(record.end)}</dd></div>
      </dl>
      {(!Number.isFinite(record.asleep_minutes)||record.asleep_minutes<0)&&
        <p className="dashboard-state">수면 시간을 확인할 정보가 부족해요.</p>}
      <SleepTimeline key={record.analysis_id} record={record} compact interactive={false}/>
      <div className="dashboard-card-actions">
        <button type="button" className="dashboard-link" onClick={onRecord}>수면 기록 자세히 보기<ArrowRight size={16} aria-hidden="true"/></button>
      </div>
    </section> : recordsStatus === "loading" ? <div className="dashboard-card">
        <p className="dashboard-state" role="status"><LoaderCircle className="spin" size={17} aria-hidden="true"/>최근 기록을 확인하고 있어요.</p>
      </div> : recordsStatus === "error" ? <div className="dashboard-card">
        <button type="button" className="button secondary" onClick={onRetryRecords}><RotateCcw size={16} aria-hidden="true"/>기록 다시 불러오기</button>
      </div> : connection}

    {record&&<section className="dashboard-card dashboard-coaching-card" aria-labelledby="dashboard-coaching-title">
      <header className="dashboard-card-heading">
        <div className="dashboard-card-title">
          <h2 id="dashboard-coaching-title">오늘의 코칭</h2>
        </div>
        {coachingStatus === "ready" && <button type="button" className="dashboard-link" onClick={onCoaching}>{excerpt?"코칭 보기":"코칭 받기"}<ArrowRight size={16} aria-hidden="true"/></button>}
      </header>
      {coachingStatus === "loading" ? <p className="dashboard-state" role="status"><LoaderCircle className="spin" size={17} aria-hidden="true"/>저장된 코칭 불러오는 중</p>
        : coachingStatus === "error" ? <div className="dashboard-coaching-error">
          <p className="dashboard-state" role="alert">저장된 코칭을 불러오지 못했어요.</p>
          <button type="button" className="dashboard-link" onClick={onRetryCoaching}><RotateCcw size={15}/>다시 불러오기</button>
        </div>
        : excerpt ? <p className="dashboard-coaching-excerpt">{excerpt}</p>
        : <p className="dashboard-state">이 수면 기록에 저장된 코칭이 아직 없어요.</p>}
    </section>}

    <nav className="dashboard-next-step" aria-label="다음 할 일">
      <button type="button" className="dashboard-link" onClick={onMorningPlan}><CalendarDays size={18} aria-hidden="true"/>내일 계획 세우기<ArrowRight size={16} aria-hidden="true"/></button>
    </nav>
  </div>;
}
