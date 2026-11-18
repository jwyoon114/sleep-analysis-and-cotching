# Health Connect 안내와 수동 수면 기록

## 기준

2026-11-19 KST에 확인한 운영 브랜치 HEAD는 `0cd63aa`였다. 열린 PR #7의 HEAD `b001bb5`는 그 직접 자식이다. 작업 브랜치는 PR #7의 A안 UI를 포함한 `b001bb5`에서 시작했다. Health Connect 안내는 QA 커밋 `679a288`의 응답 매핑과 회귀 사례를 확인해 반영했다.

## 데이터 및 호환성

- 설정 저장과 가져오기·동기화 API는 그대로 사용한다. 기존 Android 브리지가 전달하는 빈 조회 응답은 정보로, 명시적인 권한·조회·전송 오류는 각각 안내한다. 기존 응답에서 원인을 알 수 없는 동기화 실패에는 공통 재시도 안내를 표시한다.
- 인증된 `POST /watch/manual-sessions`와 `PATCH /watch/manual-sessions/{analysis_id}`를 추가했다. 조회와 휴지통 삭제는 기존 세션 API를 사용한다. DB의 계정별 세션 payload에 `data_type: manual` 및 `estimated_sleep_minutes`를 저장한다. 수면 단계, 측정 수면 시간, 각성 시간은 없으며 새 마이그레이션은 필요 없다.
- 현지 날짜·시각과 IANA 시간대를 검증한 뒤 실제 경과 시간으로 계산한다. 존재하지 않거나 두 번 나타나는 일광절약시간 전환 시각은 다시 입력하도록 안내한다.
- 동일 수동 기록 재요청은 기존 기록을 반환한다. 저장·수정 시 활성 기록과 겹치면 사용자에게 알려준다. 나중에 동기화된 자동 기록은 계속 보존하며, 수동 기록을 측정 통계와 취침 추천에서 제외해 중복 집계를 막는다.
- 수동 코칭의 기본 모드는 규칙 기반이다. 기존 서버의 명시적인 `COACHING_ENGINE=openai` 설정에서는 OpenAI Responses API를 재사용할 수 있다. 수동 기록 수정 후에도 기존에 저장된 코칭 문장은 보존된다.

## 로컬 검증

| 명령 또는 환경 | 결과 |
| --- | --- |
| `node --experimental-strip-types --test tests/*.test.mjs` · `sleep_frontend`에서 실행 | 44개 통과 |
| `npm run typecheck`, `npm run build` | 통과 |
| `python -B -m unittest discover -s tests -v` · 격리 PostgreSQL, 로컬 HTTP 프록시·데모 옵션 활성 | 150개 통과, Linux Docker·POSIX 종료·선택 SQL 파서 3개 건너뜀 |
| `python -B -m unittest discover -s tests -p test_manual_sleep.py -v` · 격리 PostgreSQL 및 별도 임시 SQLite | 각각 3개 통과 |
| 로컬 프로덕션 빌드와 격리 PostgreSQL을 연결한 Chrome 확인 | 320·390·430·1280px, 네 테마, Android 브리지 모의 응답, 수동 저장·수정·삭제·코칭, 기존 그래프 및 iPhone 사진 가이드·JSON 가져오기 통과 |

운영 반영 검토 시 PR #7 반영 이후 최신 운영 HEAD와 다시 비교한다. `sleep-app.tsx`, `health-connect.tsx`, `api.py`, Next.js 프록시를 중심으로 PWA 및 Android 담당 브랜치의 변경을 대조한다. 실제 Galaxy에서 권한 거부·재허용, 읽을 수 있는 기록 없음, 실제 저장 및 네트워크 오류를 확인한다. 실제 iPhone에서도 수동 날짜 입력과 기존 파일 앱 가져오기를 확인한다.

## 수동 기록 코칭 고도화

### 기존 AI 경로 조사

`coaching_service.py`의 자동 기록 경로에는 `OpenAI.responses.create` 호출이 이미 있다. `feature/ai-coaching`의 커밋된 서버 코드에서도 같은 외부 모델 경로를 확인했다. 해당 브랜치의 미커밋 변경은 프런트엔드 코칭 표시 관련 4개 파일이며 읽기 전용으로 검토했다.

기존 수동 코칭은 엔진 설정에 관계없이 규칙을 사용하고, 직전 기록 한 개만 참고하며 생활습관 입력을 버렸다. 이번 변경은 수동 기록용 제한된 입력과 별도 지침을 추가하고 기존 API 클라이언트 설정을 재사용한다. 자동 기록의 프롬프트·응답 및 측정 통계 계산은 기존 경로를 따른다.

### 사용 정보와 생성 방식

- 선택한 수동 기록의 취침·기상 시각, 시간대와 추정 수면 시간만 요약한다. 최근 14일 범위에서 선택 기록 이전에 끝난 활성 기록을 최대 14개 참고한다. 나중에 가져온 자동 기록과 수동 기록이 겹치면 참고 구간 한 개를 선택해 중복 비교를 방지한다.
- 이전 수동 기록의 평균 추정 시간과 이번 기록의 차이를 서버에서 계산한다. 자동 기록은 시작·종료 시각과 출처만 참고하며 수동 평균에 포함하지 않는다. 측정 통계와 취침 추천에도 수동 기록을 추가하지 않는다.
- 서로 다른 날짜의 수동 기록이 선택 기록을 포함해 3개 이상이고 시간대 및 UTC 오프셋 구성이 같을 때 시각 변동 범위를 계산한다. 기존 수면 패턴 계산과 같은 최소 시계 원호 방식을 사용한다. 자정 전후 시각을 연속된 범위로 다루며 여행·DST 변경·하루 여러 기록에서는 반복성 수치 표시를 보류한다.
- 사용자가 선택한 연령 구분·카페인·규칙성·만족도만 허용 목록으로 전달한다. 미입력과 임의 필드·자유 텍스트는 전송하지 않는다. MBTI·말투·강도·비속어 허용은 서버 저장 설정의 생성 시점 스냅샷을 사용하며 캐릭터 값은 전달하지 않는다.
- OpenAI는 구조화된 실천 제안과 선택 확인 질문을 작성한다. 수치 관찰과 데이터 한계 문장은 서버가 작성한다. 응답의 필드·타입·길이·근거 항목을 검증하고 측정되지 않은 단계·생체지표·진단 표현 및 새로운 숫자가 포함된 결과는 대체 처리한다. 이 검사는 실서비스 모델의 모든 부정확한 표현을 보장하는 수단이 아니므로 승인된 제한 테스트에서 문장 품질도 확인해야 한다.
- 계정 ID, 기록 ID, 기기명, 원시 구간, 수면 단계와 생체지표는 외부 입력에 포함하지 않는다. `store=False`, 기존 45초 타임아웃과 SDK 자동 재시도 없음 설정을 사용한다. 외부 전송에는 수면 시각과 개인화 입력이 포함되므로 기존 해외 전송 안내·동의와 제공자 정책을 운영 검토 시 확인한다.

### 실패 처리와 과거 코칭

타임아웃, API 인증 실패, 제공자 사용량 제한, 연결 실패, 제공자 오류, 응답 검증 실패와 설정 누락은 규칙 기반 조언으로 대체한다. 안전한 `fallback_reason` 코드만 보존하며 제공자의 원문 오류·거절된 응답·비밀키는 저장하거나 표시하지 않는다. 앱 자체의 계정별 요청 제한은 기존 HTTP 429로 유지하고 대체 처리에서 다시 예약하지 않는다.

기존 `coaching.text`와 `coaching_context.payload`를 재사용한다. 생성 결과에는 `manual-openai` 또는 `manual-rules`, 실제 모델, `manual-ko-v2` 지침 버전, 표현 설정, 입력 요약과 참고 기록 ID를 저장한다. 새 DB 마이그레이션은 필요 없다. 화면의 생성 방식 표시는 저장된 context를 읽으며 과거 본문을 재생성하지 않는다. 생성 도중 참고 기록의 시각이 바뀌거나 기록이 삭제되면 저장을 중지한다.

### 로컬 검증 결과

2026-11-19 KST에 합성 계정과 임시 DB만 사용했다. 실제 OpenAI 요청과 과금은 발생시키지 않았다.

| 명령 또는 환경 | 결과 |
| --- | --- |
| `python -B -m unittest discover -s tests -p 'test_manual*.py' -v` · 임시 SQLite | 17개 통과 |
| `python -B -m unittest discover -s tests -v` · `DALJAM_TEST_POSTGRES_BIN`을 임시 클러스터 도구로 지정, `DALJAM_RUN_PROXY_SMOKE=1`, `DALJAM_RUN_DEMO_HTTP=1`, `DALJAM_TEST_DIST_DIR=.next-production` | 167개 중 164개 통과, 3개 건너뜀 |
| `node --experimental-strip-types --test tests/*.test.mjs` | 45개 통과 |
| `npm run typecheck`, `SLEEP_NEXT_DIST_DIR=.next-production npm run build` | 통과 |
| 로컬 프로덕션 빌드·격리 TLS PostgreSQL·Chrome | 수동 저장·수정·삭제·코칭, 단계 그래프 제외, Health Connect 기존 브리지 모의 응답, 생성 방식·대체 안내, 4개 테마, 320·390·430·1280px 및 글자 200% 확인 |
| 기존 iPhone 사진 가이드·JSON 업로드 브라우저 회귀 | 7단계 사진·버튼·포커스, 4개 테마, JSON v2 가져오기·중복 방지·형식 오류 확인 |

AI 정상 응답과 오류 사례는 SDK 모의 객체 또는 실제 SDK에 연결한 로컬 HTTP 모의 전송으로 검증했다. 다른 계정·삭제된 기록·선택 기록 이후의 기록을 제외하고, 설정 변경과 수동 기록 수정 이후에도 저장된 코칭 원문이 유지됨을 확인했다. Linux Docker 실행, POSIX SIGTERM, 선택 SQL 문법 파서 검사는 이 환경에서 건너뛰었다.

처음 전체 테스트 실행에서는 검증용 `.next-test` 경로를 지정해 HTTP 테스트 두 개의 경로 검사에 실패했다. 테스트가 지원하는 `.next-production`으로 빌드하고 전체 검사를 다시 실행해 위 결과를 확인했다.

화면 캡처는 `sleep_frontend/.runtime/manual-captures/`에 로컬로 보관한다. `manual-openai-mocked-ui.png`와 `manual-fallback-mocked-ui.png`는 생성 방식 표시를 위한 모의 응답 화면이다. 실제 OpenAI 문장 품질, 실제 Galaxy·iPhone 입력·키보드·스크린리더 동작은 추가 검증이 필요하다.

### GitHub 통합 전 인계

현재 `deploy/supervisor.py`는 규칙 엔진만 허용하고 `OPENAI_` 환경변수를 자식 서버에 전달하지 않는다. 이번 작업은 이 운영 정책과 Render 설정을 보존한다. 따라서 현재 배포 방식에서는 규칙 기반으로 동작한다. 실제 외부 AI 활성화는 서버 담당자가 기존 키·모델 권한·비용 한도와 운영 실행 정책을 별도로 검토하고 승인해야 한다. 승인된 비운영 환경에서 실제 모델의 구조화 응답·문장 안전성·지연·비용을 검증한 뒤 통합한다.

Docker 파일의 변경은 새 `manual_coaching.py`를 런타임 이미지에 포함하는 항목뿐이다. DB/API 계약·APK·Health Connect 브리지·PWA 작업은 변경하지 않는다. 원격 통합 전에는 최신 A안 및 서버 담당 브랜치와 `coaching_service.py`, `sleep-app.tsx`, 코칭 표시 유틸리티와 Docker 복사 목록의 충돌을 확인한다.
