import type {SleepRecord, Stage} from "./sleep";

const displayOrder: readonly Stage[] = ["deep", "core", "rem", "wake", "unspecified"];

// Keep the chart denominator limited to measured stages. The wall-clock
// window may be longer when the device did not record part of the night.
export function sleepStageBreakdown(record: Pick<SleepRecord, "asleep_minutes" | "stage_minutes">) {
  const sleepMinutes = record.asleep_minutes !== null && Number.isFinite(record.asleep_minutes) && record.asleep_minutes >= 0
    ? record.asleep_minutes
    : null;
  const measured = displayOrder
    .flatMap(stage => {
      const minutes = record.stage_minutes[stage];
      return minutes !== undefined && Number.isFinite(minutes) && minutes > 0 ? [{stage, minutes}] : [];
    });
  const measuredMinutes = measured.reduce((sum, item) => sum + item.minutes, 0);
  return {
    sleepMinutes,
    measuredMinutes,
    stages:measured.map(item => ({...item, percent:item.minutes / measuredMinutes * 100})),
  };
}
