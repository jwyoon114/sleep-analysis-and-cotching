"use client";

import { useId } from "react";
import { ArrowDown, RotateCcw, ShieldCheck, Sparkles } from "lucide-react";
import {
  CHARACTERS, COACHING_PRESETS, MBTI_TYPES, createCoachingPreview, getCharacter, getCoachingPreset,
  type CharacterId, type MbtiType,
} from "@/lib/coaching-preview";
import styles from "./coaching-style-preview.module.css";

type CoachingStyle = {
  mbti: MbtiType | null;
  characterId: CharacterId;
};

function CoachingCharacter({ characterId }: Pick<CoachingStyle, "characterId">) {
  const character = getCharacter(characterId);
  return (
    <figure className={styles.character} data-character={characterId}>
      <span role="img" aria-label={"선택한 캐릭터: " + character.name}>{character.emoji}</span>
      <figcaption>{character.name}</figcaption>
    </figure>
  );
}

export function CoachingAdvice({ body, mbti, characterId }: CoachingStyle & { body: string }) {
  const preset = getCoachingPreset(mbti);
  return (
    <article aria-label="수면 조언">
      <div className={styles.introduction}>
        <CoachingCharacter characterId={characterId} />
        <div>
          <h3>{preset.label}</h3>
          <p>{preset.opening}</p>
        </div>
      </div>
      <p className="coach-text">{body}</p>
      <p className={styles.closing}>{preset.closing}</p>
    </article>
  );
}

type PreviewProps = CoachingStyle & {
  onMbtiChange: (mbti: MbtiType | null) => void;
  onCharacterChange: (characterId: CharacterId) => void;
};

export default function CoachingStylePreview({ mbti, characterId, onMbtiChange, onCharacterChange }: PreviewProps) {
  const id = useId();
  const preview = createCoachingPreview(mbti);
  const character = getCharacter(characterId);
  const RecommendationList = preview.expression.listStyle === "steps" ? "ol" : "ul";

  return (
    <section className={"panel " + styles.panel} aria-labelledby={id + "-title"}>
      <div className={styles.heading}>
        <div>
          <span className={styles.eyebrow}><Sparkles size={14} aria-hidden="true" /> 나의 코칭 스타일</span>
          <h2 id={id + "-title"}>나에게 편한 말투를 찾아봐요</h2>
          <p>같은 가상 기록, 다른 표현. 함께할 동물도 따로 골라보세요.</p>
        </div>
        <span className={styles.temporary}>현재 이용 중에만 적용</span>
      </div>

      <div className={styles.layout}>
        <div className={styles.controls}>
          <fieldset className={styles.fieldset} aria-describedby={id + "-hypothesis"}>
            <legend><span className={styles.step}>01</span> MBTI 말투 선택</legend>
            <p className={styles.hint}>고른 말투는 미리보기와 나의 수면 조언에 함께 적용돼요.</p>
            <div className={styles.mbtiGrid}>
              {MBTI_TYPES.map(type => (
                <label key={type} className={styles.mbtiOption}>
                  <input
                    className={styles.radio}
                    type="radio"
                    name={id + "-mbti"}
                    value={type}
                    checked={mbti === type}
                    onChange={() => onMbtiChange(type)}
                    aria-label={type + " · " + COACHING_PRESETS[type].label}
                  />
                  <span>{type}</span>
                </label>
              ))}
            </div>
            <div className={styles.selection}>
              <span>{mbti ? mbti + " · " + preview.preset.label : "미선택 · 기본 말투로 보고 있어요"}</span>
              {mbti && <button type="button" onClick={() => onMbtiChange(null)}><RotateCcw size={12} aria-hidden="true" />말투 초기화</button>}
            </div>
            <p id={id + "-hypothesis"} className={styles.hypothesis}>
              MBTI별 말투는 달잠의 표현 스타일 설계 가설이에요.
              실제 성격이나 수면 성향을 판단하는 데 사용하지 않아요.
            </p>
          </fieldset>

          <fieldset className={styles.fieldset}>
            <legend><span className={styles.step}>02</span> 함께할 동물 선택</legend>
            <p className={styles.hint}>캐릭터는 말투와 조언 내용에 영향을 주지 않아요.</p>
            <div className={styles.animalGrid}>
              {CHARACTERS.map(item => (
                <label key={item.id} className={styles.animalOption}>
                  <input
                    className={styles.radio}
                    type="radio"
                    name={id + "-character"}
                    value={item.id}
                    checked={characterId === item.id}
                    onChange={() => onCharacterChange(item.id)}
                    aria-label={item.name}
                  />
                  <span><span aria-hidden="true">{item.emoji}</span>{item.name}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <p className={styles.sessionNote}>
            선택은 현재 이용 중에 유지되며, 새로고침하거나 로그아웃하면 초기화돼요.
            말투와 캐릭터를 바꾸면 화면 표현만 바뀌어요.
          </p>
          <a className={styles.previewJump} href={"#" + id + "-preview"}>
            미리보기 조언 보기 <ArrowDown size={14} aria-hidden="true" />
          </a>
        </div>

        <article id={id + "-preview"} tabIndex={-1} className={styles.preview} aria-labelledby={id + "-preview-title"} data-testid="coaching-style-preview">
          <header className={styles.previewHeader}>
            <span>가상 수면 기록 · 표현 미리보기</span>
            <span className={styles.mbtiBadge}>{mbti || "기본 말투"}</span>
          </header>
          <div className={styles.introduction}>
            <CoachingCharacter characterId={characterId} />
            <div>
              <h3 id={id + "-preview-title"}>{preview.preset.label}</h3>
              <p data-testid="preview-opening">{preview.preset.opening}</p>
            </div>
          </div>

          <div className={styles.facets} aria-label="표현 스타일">
            {preview.facets.length ? preview.facets.map(facet => <span key={facet}>{facet}</span>) : <span>16가지 말투를 자유롭게 비교해 보세요</span>}
          </div>

          <dl className={styles.metrics} aria-label="모든 말투에 공통인 가상 분석 수치">
            {preview.content.metrics.map(metric => <div key={metric.label}><dt>{metric.label}</dt><dd>{metric.value}</dd></div>)}
          </dl>

          <div className={styles.observation}>
            <h4>{preview.expression.observationTitle}</h4>
            <p>{preview.expression.observationLead}</p>
            <p className={styles.fixedObservation} data-testid="preview-observation">{preview.content.observation}</p>
            <p>{preview.expression.perspective}</p>
          </div>

          <div className={styles.recommendations}>
            <h4>{preview.expression.recommendationTitle}</h4>
            <p className={styles.rationale} data-testid="preview-rationale">{preview.content.rationale}</p>
            <RecommendationList data-testid="preview-recommendations">
              {preview.content.recommendations.map(recommendation => <li key={recommendation}>{recommendation}</li>)}
            </RecommendationList>
          </div>

          <p className={styles.closing}>{preview.preset.closing}</p>
          <aside className={styles.caution} aria-label="모든 말투에 공통인 주의 사항" data-testid="preview-cautions">
            <ShieldCheck size={16} aria-hidden="true" />
            <div>{preview.content.cautions.map(caution => <p key={caution}>{caution}</p>)}</div>
          </aside>
        </article>
      </div>

      <p role="status" className="sr-only">
        {mbti || "기본"} 말투와 {character.name} 캐릭터로 가상 조언을 미리 보고 있습니다.
      </p>
    </section>
  );
}
