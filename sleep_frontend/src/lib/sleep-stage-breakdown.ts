import type {SleepRecord, Stage} from "./sleep";

const displayOrder: readonly Stage[] = ["deep", "core", "rem", "wake", "unspecified"];

// Keep the chart denominator limited to measured stages. The wall-clock
// window may be longer when the device did not record part of the night.
export function sleepStageBreakdown(record: Pick<SleepRecord, "asleep_minutes" | "stage_minutes">) {
  const sleepMinutes = Number.isFinite(record.asleep_minutes) && record.asleep_minutes >= 0
    ? record.asleep_minutes
    : null;
  const measured = displayOrder
    .map(stage => ({stage, minutes:record.stage_minutes[stage]}))
    .filter(item => Number.isFinite(item.minutes) && item.minutes > 0);
  const measuredMinutes = measured.reduce((sum, item) => sum + item.minutes, 0);
  return {
    sleepMinutes,
    measuredMinutes,
    stages:measured.map(item => ({...item, percent:item.minutes / measuredMinutes * 100})),
  };
}
