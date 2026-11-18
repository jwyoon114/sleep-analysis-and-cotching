import {ArrowRight, CalendarDays, LoaderCircle, Plus, RotateCcw} from "lucide-react";
import {clock, type Coaching, type SleepRecord} from "@/lib/sleep";
import SleepTimeline from "./sleep-timeline";

type Props = {
  record?: SleepRecord;
  recordsLoading: boolean;
  coaching?: Coaching;
  coachingStatus: "loading" | "ready" | "error";
  onUpload: () => void;
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

export default function SleepDashboard({record, recordsLoading, coaching, coachingStatus, onUpload, onRecord, onCoaching, onRetryCoaching, onMorningPlan}: Props) {
  const excerpt = coaching ? coachingExcerpt(coaching.coaching) : "";

  return <div className="sleep-dashboard">
    <section className="dashboard-card dashboard-sleep-card" aria-labelledby="dashboard-sleep-title">
      <header className="dashboard-card-heading">
        <div className="dashboard-card-title">
          <div>
            <h2 id="dashboard-sleep-title">수면 흐름</h2>
            {record && <p>{clock(record.start)} – {clock(record.end)}</p>}
          </div>
        </div>
      </header>
      {record ? <>
        <SleepTimeline key={record.analysis_id} record={record} compact interactive={false}/>
        <div className="dashboard-card-actions">
          <button type="button" className="dashboard-link" onClick={onRecord}>수면 기록 자세히 보기<ArrowRight size={16}/></button>
        </div>
      </> : recordsLoading ? <p className="dashboard-state" role="status"><LoaderCircle className="spin" size={17} aria-hidden="true"/>수면 기록 불러오는 중</p>
        : <div className="dashboard-empty">
          <p>아직 표시할 수면 기록이 없어요.</p>
          <p>수면 기록을 추가하면 시간에 따른 수면 단계 변화를 볼 수 있어요.</p>
          <button type="button" className="button secondary" onClick={onUpload}><Plus size={16}/>수면 데이터 가져오기</button>
        </div>}
    </section>

    <section className="dashboard-card dashboard-coaching-card" aria-labelledby="dashboard-coaching-title">
      <header className="dashboard-card-heading">
        <div className="dashboard-card-title">
          <h2 id="dashboard-coaching-title">오늘의 코칭</h2>
        </div>
        {record && <button type="button" className="dashboard-link" onClick={onCoaching}>{excerpt?"코칭 보기":"코칭 받기"}<ArrowRight size={16}/></button>}
      </header>
      {!record ? <p className="dashboard-state">수면 기록을 추가하면 코칭을 받을 수 있어요.</p>
        : coachingStatus === "loading" ? <p className="dashboard-state" role="status"><LoaderCircle className="spin" size={17} aria-hidden="true"/>저장된 코칭 불러오는 중</p>
        : coachingStatus === "error" ? <div className="dashboard-coaching-error">
          <p className="dashboard-state" role="alert">저장된 코칭을 불러오지 못했어요.</p>
          <button type="button" className="dashboard-link" onClick={onRetryCoaching}><RotateCcw size={15}/>다시 불러오기</button>
        </div>
        : excerpt ? <p className="dashboard-coaching-excerpt">{excerpt}</p>
        : <p className="dashboard-state">이 수면 기록에 저장된 코칭이 아직 없어요.</p>}
    </section>

    <nav className="dashboard-next-step" aria-label="다음 할 일">
      <button type="button" className="dashboard-link" onClick={onMorningPlan}><CalendarDays size={18} aria-hidden="true"/>내일 계획 세우기<ArrowRight size={16} aria-hidden="true"/></button>
    </nav>
  </div>;
}
