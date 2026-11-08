import type { SleepRecord } from "./sleep";

export function buildTimeline(record: Pick<SleepRecord,"start"|"end"|"segments">) {
  const start=Date.parse(record.start), end=Date.parse(record.end);
  if(!Number.isFinite(start)||!Number.isFinite(end)||end<=start)return null;
  const segments=record.segments.map(s=>({...s,from:Math.max(start,Date.parse(s.start)),to:Math.min(end,Date.parse(s.end))}))
    .filter(s=>Number.isFinite(s.from)&&Number.isFinite(s.to)&&s.to>s.from)
    .sort((a,b)=>a.from-b.from||a.to-b.to);
  const gaps:{from:number;to:number}[]=[];
  let cursor=start;
  for(const segment of segments){if(segment.from>cursor)gaps.push({from:cursor,to:segment.from});cursor=Math.max(cursor,segment.to);}
  if(cursor<end)gaps.push({from:cursor,to:end});
  return {start,end,duration:end-start,segments,gaps};
}

export function segmentAt(segments:{from:number;to:number}[], time:number) {
  let low=0, high=segments.length-1;
  while(low<=high){const middle=(low+high)>>1;if(segments[middle].from<=time)low=middle+1;else high=middle-1;}
  return high>=0 && time<segments[high].to ? high : -1;
}
