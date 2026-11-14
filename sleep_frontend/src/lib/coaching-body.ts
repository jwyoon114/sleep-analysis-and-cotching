import type { CoachingTone } from "./coaching-preview";

// Each entry starts with the exact v1 wording, followed by the two actions for styled display.
const SUGGESTIONS = {
  check_device_record: [
    "기기 앱에서 수면 시간이 기록됐는지 확인한 뒤 다시 불러와 보세요.",
    "기기 앱에서 수면 시간이 기록됐는지 확인해",
    "다시 불러와",
  ],
  track_caffeine_timing: [
    "카페인을 섭취한 시각을 적고, 며칠 동안의 수면 기록과 함께 살펴보세요.",
    "카페인을 섭취한 시각을 적어",
    "그 시각을 며칠 동안의 수면 기록과 함께 살펴",
  ],
  track_bed_and_wake_times: [
    "며칠 동안 취침·기상 시각을 적어 보고, 일정에 맞춰 반복하기 쉬운 시간대를 찾아보세요.",
    "며칠 동안 취침·기상 시각을 적어",
    "그 기록을 보며 일정에 맞춰 반복하기 쉬운 시간대를 찾아",
  ],
  track_morning_rest: [
    "다음 기록에는 아침에 느낀 휴식 정도를 함께 적어, 기기 기록과 비교해 보세요.",
    "다음 기록에 아침에 느낀 휴식 정도를 함께 적어",
    "기기 기록과 비교해",
  ],
  compare_daily_sleep: [
    "며칠 동안 수면 기록을 모아 날짜별 수면 시간을 비교해 보세요.",
    "며칠 동안 수면 기록을 모아",
    "날짜별 수면 시간을 비교해",
  ],
} as const;

const LIMITATIONS = {
  sleep_duration_unavailable: [
    "수면 시간 값이 없거나 유효한 기록 범위를 벗어났습니다.",
    "수면 시간 값이 없거나 유효한 기록 범위를 벗어났어요.",
  ],
  single_device_estimate: [
    "기기가 추정한 한 건의 기록입니다. 평소 수면 패턴이나 변화의 원인을 판단하기에는 정보가 부족합니다.",
    "기기가 추정한 한 건의 기록이에요. 평소 수면 패턴이나 변화의 원인을 판단하기에는 정보가 부족해요.",
  ],
  unrecorded_segments: ["기록 안에 미기록 구간이 있습니다.", "기록 안에 측정값이 없는 구간이 있어요."],
  invalid_reference: ["선택한 기록의 날짜와 시간 구간을 확인해 주세요.", "선택한 기록의 날짜와 시간 구간을 함께 확인해 봐요."],
  valid_days_device_estimates: [
    "평균은 유효한 기록이 있는 날의 기기 추정 수면 시간만 사용합니다.",
    "평균에는 유효한 기록이 있는 날의 기기 추정 수면 시간만 들어가요.",
  ],
  unusable_records_excluded: [
    "날짜, 시간 구간 또는 수면 시간을 확인할 수 없는 기록은 집계에서 제외했습니다.",
    "날짜, 시간 구간 또는 수면 시간을 확인할 수 없는 기록은 집계에 넣지 않았어요.",
  ],
  ambiguous_records_excluded: [
    "기록이 겹치거나 같은 기록 ID의 값이 다른 날은 집계에서 제외했습니다.",
    "기록이 겹치거나 같은 기록 ID의 값이 다른 날은 집계에 넣지 않았어요.",
  ],
  insufficient_comparison_days: [
    "두 기간에 각각 유효 기록일이 3일 이상 있어야 평균 차이를 표시합니다.",
    "두 기간에 각각 유효 기록일이 3일 이상 있어야 평균 차이를 볼 수 있어요.",
  ],
  mixed_timezones: [
    "최근 기록의 시간대 또는 UTC 오프셋이 달라 시작 시각 변동을 보류했습니다.",
    "최근 기록의 시간대 또는 UTC 오프셋이 달라 시작 시각 변동은 표시를 보류했어요.",
  ],
  unreliable_start: [
    "날짜별 시작 시각을 하나씩 신뢰하기 어려워 시작 시각 변동을 보류했습니다.",
    "날짜마다 믿을 만한 시작 시각을 하나씩 확인하기 어려워 시작 시각 변동은 표시를 보류했어요.",
  ],
  insufficient_start_days: [
    "시작 시각 변동을 계산하려면 최근 유효 기록일이 2일 이상 필요합니다.",
    "시작 시각 변동을 계산하려면 최근 유효 기록일이 2일 이상 필요해요.",
  ],
  device_start_range: [
    "시작 시각 변동은 기기 기록의 시작 시각 범위입니다.",
    "여기서 시작 시각 변동은 기기 기록의 시작 시각 범위를 뜻해요.",
  ],
} as const;

const REGULARITY_LIMIT = {
  available: "device_start_range",
  insufficient_days: "insufficient_start_days",
  mixed_timezones: "mixed_timezones",
  unreliable_start: "unreliable_start",
  invalid_reference: "invalid_reference",
} as const;

type Measurement = { valid: boolean; minutes: number | null; display: string | null };
type Period = { valid_days: number; average_asleep_minutes: number | null; average_display: string | null };
type Comparison = {
  status: "available" | "insufficient_days" | "invalid_reference";
  average_difference_minutes: number | null;
  difference_display: string | null;
};
type Regularity = {
  status: keyof typeof REGULARITY_LIMIT;
  start_spread_minutes: number | null;
  spread_display: string | null;
};
type PresentationV1 = {
  version: 1;
  observation: {
    id: "device_sleep_estimate" | "sleep_duration_unavailable";
    asleep: Measurement;
    awake: Measurement;
  };
  patterns: { recent: Period | null; previous: Period | null; comparison: Comparison; regularity: Regularity };
  suggestion_id: keyof typeof SUGGESTIONS;
  limitation_ids: (keyof typeof LIMITATIONS)[];
};

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isKey<T extends object>(options: T, value: unknown): value is keyof T & string {
  return typeof value === "string" && Object.hasOwn(options, value);
}

function hasDisplay(minutes: unknown, display: unknown, available: boolean, signed = false): boolean {
  if (!available) return minutes === null && display === null;
  return typeof minutes === "number" && Number.isFinite(minutes) && (signed || minutes >= 0)
    && typeof display === "string" && display.trim().length > 0;
}

function isMeasurement(value: unknown): value is Measurement {
  return isObject(value) && typeof value.valid === "boolean"
    && hasDisplay(value.minutes, value.display, value.valid);
}

function isPeriod(value: unknown): value is Period {
  return isObject(value) && typeof value.valid_days === "number" && Number.isInteger(value.valid_days)
    && value.valid_days >= 0 && value.valid_days <= 7
    && hasDisplay(value.average_asleep_minutes, value.average_display, value.valid_days > 0);
}

function isComparison(value: unknown): value is Comparison {
  return isObject(value)
    && (value.status === "available" || value.status === "insufficient_days" || value.status === "invalid_reference")
    && hasDisplay(value.average_difference_minutes, value.difference_display, value.status === "available", true);
}

function isRegularity(value: unknown): value is Regularity {
  return isObject(value) && isKey(REGULARITY_LIMIT, value.status)
    && hasDisplay(value.start_spread_minutes, value.spread_display, value.status === "available");
}

function isPresentation(value: unknown): value is PresentationV1 {
  if (!isObject(value) || value.version !== 1 || !isObject(value.observation) || !isObject(value.patterns)) return false;
  const { observation, patterns, suggestion_id: suggestion, limitation_ids: limits } = value;
  const { id, asleep, awake } = observation;
  if (!isMeasurement(asleep) || !isMeasurement(awake) || !isKey(SUGGESTIONS, suggestion)
      || !Array.isArray(limits) || ![...limits].every(limit => isKey(LIMITATIONS, limit))
      || new Set(limits).size !== limits.length) return false;

  if (asleep.valid) {
    if (id !== "device_sleep_estimate" || suggestion === "check_device_record" || limits[0] !== "single_device_estimate") return false;
  } else if (id !== "sleep_duration_unavailable" || awake.valid
      || suggestion !== "check_device_record" || limits[0] !== "sleep_duration_unavailable") return false;

  const { recent, previous, comparison, regularity } = patterns;
  if (!isComparison(comparison) || !isRegularity(regularity) || !limits.includes(REGULARITY_LIMIT[regularity.status])) return false;
  if (comparison.status === "invalid_reference") {
    return recent === null && previous === null && regularity.status === "invalid_reference";
  }
  if (!isPeriod(recent) || !isPeriod(previous) || regularity.status === "invalid_reference") return false;
  return limits.includes("valid_days_device_estimates")
    && (comparison.status !== "insufficient_days" || limits.includes("insufficient_comparison_days"));
}

const PERIOD_LABELS = { recent: "최근 7일", previous: "직전 7일" } as const;

function originalBody(data: PresentationV1): string {
  const { observation, patterns, suggestion_id, limitation_ids } = data;
  const { asleep, awake } = observation;
  const selected = asleep.display === null
    ? "이 기록에서 수면 시간을 확인할 수 없습니다."
    : "기기에서 수면으로 분류한 시간은 " + asleep.display + "입니다."
      + (awake.display === null ? "" : " 각성으로 분류한 시간은 " + awake.display + "입니다.");

  const patternLines = [];
  for (const key of ["recent", "previous"] as const) {
    const period = patterns[key];
    if (period !== null) {
      patternLines.push(PERIOD_LABELS[key] + " · 유효 기록 " + period.valid_days + "일"
        + (period.average_display === null ? "" : " · 기록일 평균 " + period.average_display));
    }
  }
  const difference = patterns.comparison.difference_display;
  if (difference !== null) patternLines.push("평균 차이(최근 − 직전) " + difference);
  const spread = patterns.regularity.spread_display;
  if (spread !== null) patternLines.push("기기 기록의 시작 시각 범위 " + spread);

  const [first, ...rest] = limitation_ids;
  let selectedLimits = "선택 기록 · " + LIMITATIONS[first][0];
  if (rest[0] === "unrecorded_segments") {
    selectedLimits += " " + LIMITATIONS.unrecorded_segments[0];
    rest.shift();
  }
  const limits = [selectedLimits, ...rest.map(id => LIMITATIONS[id][0])];

  return [
    "선택 기록\n" + selected,
    ...(patternLines.length ? ["수면 패턴\n" + patternLines.join("\n")] : []),
    "실천 제안\n" + SUGGESTIONS[suggestion_id][0],
    "데이터 한계\n" + limits.join("\n"),
  ].join("\n\n");
}

function periodSentence(label: string, period: Period, { lively, factual }: CoachingTone): string {
  const days = label + (lively ? "을 보면, 유효 기록은 " : "의 유효 기록은 ") + period.valid_days + "일";
  if (period.average_display === null) {
    return factual ? days + "이며, 기록일 평균은 표시할 수 없습니다."
      : days + "이에요. 기록일 평균은 표시할 수 없어요.";
  }
  return factual ? days + "이며, 기록일 평균 수면 시간은 " + period.average_display + "입니다."
    : days + "이에요. 기록이 있는 날의 평균 수면 시간은 " + period.average_display + "이에요.";
}

function styledSuggestion(id: PresentationV1["suggestion_id"], { factual, lively, planned }: CoachingTone): string {
  const [, first, next] = SUGGESTIONS[id];
  const ending = factual ? "보세요." : "봐요.";
  if (planned) {
    const firstEnding = lively ? (factual ? "보시겠어요?" : "볼까요?") : ending;
    return "먼저 " + first + " " + firstEnding + "\n그다음 " + next + " " + ending;
  }
  const lead = lively ? "어떻게 시작해 볼까요? " : "";
  return lead + "편한 방식으로 " + first + " 본 뒤, " + next + " " + ending;
}

function styledBody(data: PresentationV1, tone: CoachingTone): string {
  const { observation, patterns, suggestion_id, limitation_ids } = data;
  const { body, concrete, factual, planned } = tone;
  const sections = [];
  const selectedTitle = concrete ? "선택한 기록부터" : "수면 흐름의 출발점";
  const asleep = observation.asleep.display;
  const awake = observation.awake.display;
  const observed = asleep === null
    ? (factual ? "이 기록에서는 수면 시간을 확인할 수 없습니다." : "이 기록에서는 수면 시간을 확인할 수 없어요.")
    : (factual ? "기기가 수면으로 분류한 시간은 " + asleep + "입니다."
      : "기기가 수면으로 분류한 시간은 " + asleep + "이에요.")
      + (awake === null ? "" : " 각성으로 분류한 시간은 " + awake + (factual ? "입니다." : "이에요."));
  sections.push(selectedTitle + "\n" + body.opening + " " + observed);

  if (patterns.recent && patterns.previous) {
    const periods = [
      periodSentence(PERIOD_LABELS.recent, patterns.recent, tone),
      periodSentence(PERIOD_LABELS.previous, patterns.previous, tone),
    ];
    const difference = patterns.comparison.difference_display;
    const comparison = difference === null
      ? (factual ? "두 기간의 평균 차이는 표시를 보류했습니다." : "두 기간의 평균 차이는 표시를 보류했어요.")
      : "최근 7일 평균에서 직전 7일 평균을 뺀 차이는 " + difference + (factual ? "입니다." : "이에요.");
    const spread = patterns.regularity.spread_display;
    const lines = concrete ? [...periods, comparison] : [comparison, ...periods];
    if (spread !== null) {
      lines.push("기기 기록의 시작 시각 범위는 " + spread + (factual ? "입니다." : "이에요."));
    }
    if (difference !== null) lines.unshift(body.patternLead);
    sections.push((concrete ? "기간별 수면 기록" : "두 기간의 수면 흐름") + "\n" + lines.join("\n"));
  }

  sections.push((planned ? "차근차근 실천하기" : "생활에 맞춰 시도하기") + "\n" + styledSuggestion(suggestion_id, tone));
  sections.push((factual ? "해석에 필요한 한계" : "기록을 볼 때 함께 기억해요")
    + "\n" + limitation_ids.map(id => LIMITATIONS[id][factual ? 0 : 1]).join("\n"));
  return sections.join("\n\n");
}

function verifiedCoachingPresentation(savedBody: string, context: unknown): PresentationV1 | null {
  if (!isObject(context) || context.engine !== "rules") return null;
  const data = context.presentation;
  // Reproduce the saved body to detect dropped notes or mismatched display values without parsing it.
  return isPresentation(data) && originalBody(data) === savedBody ? data : null;
}

export function renderCoachingBody(savedBody: string, context: unknown, tone: CoachingTone | null): string {
  if (tone === null) return savedBody;
  const data = verifiedCoachingPresentation(savedBody, context);
  return data ? styledBody(data, tone) : savedBody;
}

export function coachingDataNotes(savedBody: string, context: unknown): string[] {
  const data = verifiedCoachingPresentation(savedBody, context);
  if (data === null) return [];

  const notes: string[] = [];
  if (!data.observation.asleep.valid) {
    notes.push("이 조언에 사용된 기록에서는 수면 시간을 확인할 수 없어요.");
  } else if (!data.observation.awake.valid) {
    notes.push("이 조언에 사용된 기록에서는 각성 시간을 확인할 수 없어요.");
  }
  if (data.limitation_ids.includes("unrecorded_segments")) {
    notes.push("이 조언에 사용된 수면 기록에는 기록이 비어 있는 구간이 있어요.");
  }
  const { comparison, recent, previous } = data.patterns;
  if (comparison.status === "invalid_reference") {
    notes.push("선택한 기록의 날짜와 시간 범위를 확인해야 두 기간을 비교할 수 있어요.");
  } else if (comparison.status === "insufficient_days" && recent && previous) {
    notes.push(
      "기간별 평균을 비교하려면 최근 7일과 그 직전 7일에 수면 시간을 확인할 수 있는 날이 각각 3일 이상 필요해요. "
      + "이 조언에 사용된 기록일은 최근 기간 " + recent.valid_days + "일, 직전 기간 " + previous.valid_days + "일이에요.",
    );
  }
  return notes;
}
