import {ChevronLeft, ChevronRight, Clock3, Moon, Plus, TrendingUp} from "lucide-react";
import {clock, dayBefore, minutes, shortDate, today, type SleepRecord} from "@/lib/sleep";
import {useState} from "react";

export default function MobileRecordList({records, loading, onOpen, onUpload, onCompare}: {
  records: SleepRecord[];
  loading: boolean;
  onOpen: (id:string)=>void;
  onUpload: ()=>void;
  onCompare: ()=>void;
}) {
  const [range,setRange]=useState<7|30|"all">("all");
  const [end,setEnd]=useState(today);
  const [query,setQuery]=useState("");
  const start=range==="all" ? null : dayBefore(end,range-1);
  const visible=start ? records.filter(record=>record.start.slice(0,10)>=start && record.start.slice(0,10)<=end) : records;
  const observed=visible.filter(record=>Number.isFinite(record.asleep_minutes) && record.asleep_minutes>=0);
  const average=observed.length ? observed.reduce((sum,record)=>sum+record.asleep_minutes,0)/observed.length : null;
  const results=visible.filter(record=>record.start.slice(0,10).includes(query.trim()));

  return <div className="record-list-screen">
    <div className="range-picker" aria-label="기록 기간">
      {([[7,"주간"],[30,"월간"],["all","전체"]] as const).map(([value,label])=><button type="button" key={value} aria-pressed={range===value} onClick={()=>{setRange(value);setEnd(today());}}>{label}</button>)}
    </div>
    {range!=="all" && start && <div className="record-period">
      <button type="button" className="icon-button" aria-label="이전 기간" onClick={()=>setEnd(dayBefore(end,range))}><ChevronLeft size={19}/></button>
      <strong>{shortDate(start)} ~ {shortDate(end)}</strong>
      <button type="button" className="icon-button" aria-label="다음 기간" disabled={end>=today()} onClick={()=>setEnd(dayBefore(end,-range))}><ChevronRight size={19}/></button>
    </div>}
    {visible.length>0 && <div className="record-summary">
      <div className="panel"><Moon size={20} aria-hidden="true"/><span>기록당 평균 수면</span><strong>{minutes(average)}</strong></div>
      <div className="panel"><Clock3 size={20} aria-hidden="true"/><span>수면 기록</span><strong>{visible.length}건</strong></div>
    </div>}
    <div className="record-list-heading"><h2>{range==="all"?"최근 기록":"기간 내 기록"}</h2><button type="button" className="dashboard-link" onClick={onCompare}><TrendingUp size={17}/>기간 비교</button></div>
    {visible.length>0&&<input className="record-search" aria-label="기록 날짜 검색" placeholder="날짜 검색 (예: 11-06)" value={query} onChange={event=>setQuery(event.target.value)}/>}
    {loading && !records.length ? <p role="status" className="panel">수면 기록을 불러오고 있어요.</p> : results.length ? <ul className="record-list-items">
      {results.map(record=><li key={record.analysis_id}><button type="button" className="record-row" onClick={()=>onOpen(record.analysis_id)}>
        <span><strong>{shortDate(record.start)}</strong><Moon size={17} aria-hidden="true"/></span>
        <span><strong>{minutes(Number.isFinite(record.asleep_minutes) && record.asleep_minutes>=0 ? record.asleep_minutes : null)}</strong><small>{clock(record.start)} – {clock(record.end)}</small></span>
        <ChevronRight size={19} aria-hidden="true"/>
      </button></li>)}
    </ul> : <div className="panel"><p>{visible.length?"검색에 맞는 날짜가 없어요.":records.length?"이 기간에는 수면 기록이 없어요.":"아직 수면 기록이 없어요."}</p>{!records.length&&<button type="button" className="dashboard-link" onClick={onUpload}><Plus size={17}/>수면 데이터 가져오기</button>}</div>}
  </div>;
}
