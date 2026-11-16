import type {CharacterId, MbtiType} from "./coaching-preview";

export const SPEECH_OPTIONS = [
  {value:"polite",label:"존댓말"},
  {value:"casual",label:"반말"},
] as const;
export const INTENSITY_OPTIONS = [
  {value:"gentle",label:"다정함"},
  {value:"firm",label:"단호함"},
  {value:"direct",label:"강한 직설"},
] as const;

export type Preferences = {
  mbti: MbtiType | null;
  speech: typeof SPEECH_OPTIONS[number]["value"];
  intensity: typeof INTENSITY_OPTIONS[number]["value"];
  allow_profanity: boolean;
  character: CharacterId;
};
export type Personalization = Preferences & {completed_at: string};
export type Draft = Omit<Preferences, "speech" | "intensity" | "character"> &
  Partial<Pick<Preferences, "speech" | "intensity" | "character">>;

export const CHARACTER_THEMES: Record<CharacterId, {moon:"crescent" | "full"}> = {
  cat:{moon:"crescent"},
  raccoon:{moon:"crescent"},
  dog:{moon:"full"},
  rabbit:{moon:"full"},
};

export function changeIntensity(intensity: Preferences["intensity"]): Pick<Preferences,"intensity" | "allow_profanity"> {
  return {intensity, allow_profanity:false};
}
