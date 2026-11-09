/** Display-only coaching styles shared by saved advice and the fictional preview. */
export const MBTI_TYPES = Object.freeze([
  "ISTJ", "ISFJ", "INFJ", "INTJ",
  "ISTP", "ISFP", "INFP", "INTP",
  "ESTP", "ESFP", "ENFP", "ENTP",
  "ESTJ", "ESFJ", "ENFJ", "ENTJ",
] as const);

export type MbtiType = typeof MBTI_TYPES[number];
export type CharacterId = "cat" | "rabbit" | "bear" | "owl";

export const CHARACTERS = Object.freeze([
  Object.freeze({ id: "cat", name: "고양이", emoji: "🐱" }),
  Object.freeze({ id: "rabbit", name: "토끼", emoji: "🐰" }),
  Object.freeze({ id: "bear", name: "곰", emoji: "🐻" }),
  Object.freeze({ id: "owl", name: "부엉이", emoji: "🦉" }),
] as const);

type Preset = Readonly<{ label: string; opening: string; closing: string }>;

/** Product writing hypotheses, not scientifically established MBTI preferences. */
export const COACHING_PRESETS = Object.freeze({
  ISTJ: Object.freeze({
    label: "차분한 기록과 순서",
    opening: "기록에서 확인할 수 있는 내용을 차분히 짚고, 실천 제안을 순서대로 살펴보겠습니다.",
    closing: "기록과 실천을 한 항목씩 확인하며 마무리해 보세요.",
  }),
  ISFJ: Object.freeze({
    label: "다정한 일상 안내",
    opening: "기록을 편안하게 살펴보고, 일상에서 해볼 일을 함께 읽어봐요.",
    closing: "작은 실천을 차근차근 이어갈 수 있도록 응원할게요.",
  }),
  INFJ: Object.freeze({
    label: "차분한 의미와 격려",
    opening: "기록을 조용히 돌아보며, 작은 실천이 이어지는 의미를 생각해 볼게요.",
    closing: "한 번의 평가보다, 기록을 이어가는 과정에 다정한 마음을 보태요.",
  }),
  INTJ: Object.freeze({
    label: "차분한 근거와 계획",
    opening: "기록의 근거를 먼저 확인하고, 실천의 방향과 연결해 보겠습니다.",
    closing: "관찰한 내용과 실천 계획을 구분해 차분히 이어가 보세요.",
  }),
  ISTP: Object.freeze({
    label: "담백한 관찰과 선택",
    opening: "기록에서 확인되는 것부터 간단히 살피고, 적용할 방법을 생각해 볼게요.",
    closing: "제안을 생활에 적용할 방법은 상황에 맞게 생각해 보세요.",
  }),
  ISFP: Object.freeze({
    label: "편안한 일상 제안",
    opening: "기록을 부담 없이 읽고, 제안을 내 일상에서 어떻게 받아들일지 살펴봐요.",
    closing: "제안을 읽고, 내 일상에 적용할 방법을 편안하게 떠올려 봐요.",
  }),
  INFP: Object.freeze({
    label: "부드러운 변화 탐색",
    opening: "기록을 천천히 읽으며, 작은 실천을 이어가는 나만의 방식을 생각해 봐요.",
    closing: "지금의 기록을 돌아보고, 내 속도에 맞춰 변화를 생각해 봐요.",
  }),
  INTP: Object.freeze({
    label: "차분한 근거 탐색",
    opening: "기록에서 확인된 것과 해석할 수 있는 범위를 나누어 살펴보겠습니다.",
    closing: "관찰과 제안을 구분해 읽으면 기록의 의미를 살피기 편합니다.",
  }),
  ESTP: Object.freeze({
    label: "경쾌한 관찰과 선택",
    opening: "기록의 핵심부터 바로 살펴봐요! 일상에 적용할 방법도 함께 볼게요.",
    closing: "제안을 어떻게 적용할지는 지금 상황에 맞춰 생각해 봐요!",
  }),
  ESFP: Object.freeze({
    label: "밝은 일상 응원",
    opening: "기록을 함께 펼쳐봐요! 일상에서 해볼 수 있는 일을 가볍게 살펴봐요.",
    closing: "편하게 읽고, 일상에 어울리는 방법을 떠올려 봐요!",
  }),
  ENFP: Object.freeze({
    label: "활기찬 가능성 응원",
    opening: "이 기록에서 시작해 봐요! 작은 실천이 내게 어떤 변화로 이어질지 생각해 봐요.",
    closing: "내 속도에 맞춰 변화를 이어가는 과정을 응원해요!",
  }),
  ENTP: Object.freeze({
    label: "활기찬 근거 탐색",
    opening: "기록이 말해 주는 범위부터 짚어봐요! 같은 근거에서 어떻게 제안으로 이어지는지 살펴볼게요.",
    closing: "근거를 확인했다면 적용할 방법은 유연하게 생각해 봐요!",
  }),
  ESTJ: Object.freeze({
    label: "명료한 기록과 계획",
    opening: "기록에서 확인된 내용을 먼저 봐요! 이어서 실천 제안을 순서대로 읽어볼게요.",
    closing: "확인한 기록과 실천 제안을 한 항목씩 정리해 봐요!",
  }),
  ESFJ: Object.freeze({
    label: "따뜻한 일상 계획",
    opening: "기록을 함께 살펴봐요! 일상에서 차근차근 해볼 일을 같이 읽어봐요.",
    closing: "일상에서 해볼 일을 하나씩 정리하는 과정도 응원할게요!",
  }),
  ENFJ: Object.freeze({
    label: "함께 그리는 변화",
    opening: "기록을 바탕으로 다음 걸음을 함께 그려봐요! 실천의 방향을 차근차근 살펴봐요.",
    closing: "지금 살펴본 방향을 조금씩 이어가는 과정을 응원해요!",
  }),
  ENTJ: Object.freeze({
    label: "명료한 목표와 계획",
    opening: "기록의 근거부터 정리해 봐요! 관찰에서 실천의 방향으로 이어가 볼게요.",
    closing: "관찰한 근거와 실천할 방향을 나누어 정리해 봐요!",
  }),
} satisfies Record<MbtiType, Preset>);

/** Keep facts and content separate from every style preset and character. */
export const PREVIEW_ANALYSIS = Object.freeze({
  fictional: true,
  asleepMinutes: 380,
  awakeMinutes: 40,
  recordingStart: "23:30",
  recordingEnd: "06:30",
});

function durationLabel(value: number) {
  return value < 60 ? value + "분" : Math.floor(value / 60) + "시간 " + value % 60 + "분";
}

const asleepLabel = durationLabel(PREVIEW_ANALYSIS.asleepMinutes);
const awakeLabel = durationLabel(PREVIEW_ANALYSIS.awakeMinutes);
const recordingWindow = PREVIEW_ANALYSIS.recordingStart + "~" + PREVIEW_ANALYSIS.recordingEnd;

export const PREVIEW_CONTENT = Object.freeze({
  metrics: Object.freeze([
    Object.freeze({ label: "수면 시간", value: asleepLabel }),
    Object.freeze({ label: "각성 시간", value: awakeLabel }),
    Object.freeze({ label: "기록 구간", value: recordingWindow }),
  ]),
  observation: "가상 기록의 수면 시간은 " + asleepLabel + ", 각성 시간은 " + awakeLabel + "이며, 기록 구간은 " + recordingWindow + "입니다.",
  rationale: "한 번의 기록만으로 원인을 단정하지 않고, 여러 날의 기록을 비교하기 위한 제안입니다.",
  recommendations: Object.freeze([
    "잠들기 전 화면을 잠시 내려놓고, 조용한 음악 듣기나 책 읽기 중 편한 휴식 활동을 골라보세요.",
    "다음 날에도 같은 방식으로 수면 기록을 남겨, 여러 날의 흐름을 살펴보세요.",
  ]),
  cautions: Object.freeze([
    "기능 체험을 위한 가상 기록이며, 실제 수면 분석 결과가 아닙니다.",
    "수면 기록만으로 수면의 질이나 질병을 판단할 수 없습니다.",
  ]),
});

export function isMbtiType(value: unknown): value is MbtiType {
  return typeof value === "string" && MBTI_TYPES.some(type => type === value);
}

export function getCharacter(id: CharacterId) {
  const character = CHARACTERS.find(item => item.id === id);
  if (!character) throw new Error("지원하지 않는 캐릭터입니다.");
  return character;
}

const DEFAULT_PRESET: Preset = Object.freeze({
  label: "기본 말투",
  opening: "수면 기록을 바탕으로 한 조언을 살펴보세요.",
  closing: "조언과 함께 기록에서 확인할 수 있는 범위도 살펴보세요.",
});

export function getCoachingPreset(mbti: MbtiType | null): Preset {
  if (mbti !== null && !isMbtiType(mbti)) throw new Error("지원하지 않는 MBTI입니다.");
  return mbti === null ? DEFAULT_PRESET : COACHING_PRESETS[mbti];
}

/** The renderer can change wording and list presentation, never the content. */
export function createCoachingPreview(mbti: MbtiType | null) {
  const preset = getCoachingPreset(mbti);
  const facets = mbti === null ? [] : [
    mbti[0] === "E" ? "활기 있는 표현" : "차분한 표현",
    mbti[1] === "S" ? "구체적인 일상" : "목표와 변화의 의미",
    mbti[2] === "T" ? "수치와 근거" : "공감과 격려",
    mbti[3] === "J" ? "분명한 실천 순서" : "유연한 휴식 선택",
  ];
  return Object.freeze({
    mbti,
    preset,
    analysis: PREVIEW_ANALYSIS,
    content: PREVIEW_CONTENT,
    facets: Object.freeze(facets),
    expression: Object.freeze({
      observationTitle: mbti === null ? "같은 가상 기록" : mbti[2] === "T" ? "수치와 근거로 살펴보기" : "기록을 다정하게 살펴보기",
      observationLead: mbti === null ? "아래 기록은 모든 말투에 동일하게 사용됩니다." : mbti[2] === "T"
        ? "기록에 있는 수치와 해석의 범위를 나눠 확인하겠습니다."
        : "기록을 잘잘못으로 평가하기보다, 편안하게 실천을 이어갈 수 있도록 살펴봐요.",
      perspective: mbti === null ? "표현만 바뀌며, 분석 결과와 조언의 핵심 내용은 바뀌지 않습니다." : mbti[1] === "S"
        ? "오늘 밤과 다음 날의 일상에서 적용할 구체적인 행동을 중심으로 볼게요."
        : "작은 실천과 여러 날의 기록을 연결해, 변화의 흐름을 살펴볼게요.",
      recommendationTitle: mbti === null ? "공통 실천 제안" : mbti[3] === "J" ? "차근차근 이어갈 실천 순서" : "휴식 방법을 유연하게 고르는 실천 제안",
      listStyle: mbti?.[3] === "J" ? "steps" as const : "bullets" as const,
    }),
  });
}
