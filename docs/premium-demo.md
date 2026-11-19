# 달잠 프리미엄 발표 시연

## 현재 제공 범위

무료 이용자는 기존 자동 분석, 수동 기록, 측정 기록의 단계 그래프, 건강 데이터 가져오기, 규칙 기반 개인화 코칭, 취침 추천과 아침 계획을 이용한다. 홈과 코칭 화면의 `Premium 알아보기`에서 기능 비교와 발표 시연으로 이동한다.

실제 AI 프리미엄 서비스는 준비 중으로 표시한다. 가격과 구독 기간은 확정하지 않았다. 발표 시연은 소개 → 결제 시연 확인 → 모의 결제 완료 → 샘플 조언 → 무료 상태 초기화 순서로 진행한다. 카드번호·계좌번호·인증번호 입력란, 영수증, 실제 결제 내역과 결제 대행사 호출은 없다.

## 시연 활성화와 권한

서버의 `DALJAM_PREMIUM_DEMO=1` 설정과 `DALJAM_ENV=development`, `test`, `staging` 중 하나가 모두 필요하다. 기본값·미설정·알 수 없는 환경에서는 발급을 차단한다. `production`에서는 시연 플래그가 켜져 있어도 차단한다. 브라우저 설정이나 프런트엔드 환경변수로 권한을 발급하지 않는다.

시연은 인증된 계정 ID에 연결된 서버 프로세스 메모리에만 보관한다. 운영 DB의 결제·구독 상태를 저장하거나 변경하지 않으며 추가 마이그레이션도 없다. 결제 확인 토큰은 10분 동안 유효하다. 같은 확인 토큰의 동시·반복 완료 요청은 동일한 시연 상태를 반환한다. 다른 계정의 확인 토큰을 사용할 수 없다.

시연 권한은 활성화 후 최대 24시간 유지된다. 초기화, 성공한 로그아웃·계정 삭제, 서버 재시작으로 정리된다. 이 시간은 발표용 임시 권한의 수명이다. 여러 서버 프로세스 사이에서는 공유하지 않으므로 발표 환경은 단일 프로세스를 사용한다. 실제 구독 운영에는 별도의 영구 권한 저장과 결제 검증이 필요하다.

시연 계정의 `tier`는 `premium_demo`이며 `paid_entitlement`와 `live_ai_available`는 항상 `false`다. 공통 `coaching_service.generate`는 외부 AI 호출 전에 `has_paid_ai_entitlement`를 확인한다. 현재 이 검증 함수는 항상 `false`를 반환한다. 따라서 서버 엔진 설정이 `openai`여도 무료·시연 계정의 새 코칭은 규칙 기반으로 처리된다. 자동 Health Connect 코칭도 같은 검사를 거친다.

## API

모든 경로는 기존 계정 인증을 사용한다. Next.js 프록시도 해당 경로만 허용하며 변경 요청의 동일 출처 검사와 인증 쿠키를 적용한다.

| 경로 | 동작 |
| --- | --- |
| `GET /premium` | 서버 이용 등급과 시연 가능 여부 조회 |
| `POST /premium/demo/checkout` | 계정별 일회 확인 토큰 발급 |
| `POST /premium/demo/activate` | `checkout_token`, `acknowledged=true` 확인 후 시연 활성화 |
| `GET /premium/demo/preview` | 활성 시연 계정에 준비된 샘플 반환 |
| `DELETE /premium/demo` | 현재 계정의 시연 초기화 |

권한 없음은 403, 확인 토큰 오류·만료는 409, 알 수 없는 결제 입력 필드는 422로 처리한다. 조회 응답에는 `private, no-store`를 적용한다. 확인 토큰을 로그에 남기지 않는다.

## 샘플 코칭과 실제 AI 경로

샘플은 서버 코드에 준비한 가상 시각 세 건과 말투·강도별 여섯 가지 문장을 사용한다. `AI 코칭 시연 예시`, `준비된 가상 기록과 샘플 조언`이라는 안내를 표시한다. 현재 계정의 서버 저장 말투·강도만 적용하고 캐릭터는 표현에 영향을 주지 않는다. 수면 단계·생체지표·수면의 질에 대한 가상 측정값은 추가하지 않는다.

미리보기는 사용자의 실제 수면 기록을 조회하지 않으며 코칭 이력·수면 기록에 저장하지 않는다. 외부 모델과 통신하지 않는다. `source=prepared_sample`, `synthetic=true`, `model_called=false`, `saved_to_history=false`로 응답한다. 실제로 저장된 과거 AI 코칭은 기존 생성 방식과 원문으로 표시된다.

기존 OpenAI Responses API 어댑터와 수동 기록 전용 입력·응답 검증 코드는 보존한다. 어댑터 자동 테스트에서는 미래의 검증된 유료 권한을 모의로 부여하고 외부 응답을 모두 모의 처리한다. 실제 서버에 유료 권한을 발급하는 API나 설정은 추가하지 않았다.

## 로컬 발표 준비

격리된 로컬 테스트 DB와 테스트 계정을 사용한다. 기존 운영 DB 주소와 실제 사용자 계정을 사용하지 않는다. 기존 프로젝트 의존성을 설치한 환경에서 백엔드를 시작하는 셸에 다음 설정을 적용한다.

```powershell
$env:DALJAM_ENV = 'development'
$env:DALJAM_PREMIUM_DEMO = '1'
$env:COACHING_ENGINE = 'rules'
$env:SLEEP_DESKTOP_ALARMS = '0'
```

DB는 기존 프로젝트 방식으로 격리 구성하고 `0001`부터 `0004`까지 적용한다. 이번 변경은 새 마이그레이션을 요구하지 않는다. API는 로컬 FastAPI 개발 실행 경로를 사용한다. 운영용 `deploy/supervisor.py`는 기존 운영 검증 정책을 적용한다. 프런트엔드는 기존 Next.js 개발 서버에서 같은 로컬 API를 바라보도록 한다.

로그인·온보딩을 마친 뒤 홈의 `Premium 알아보기`를 누른다. 모의 결제 확인란을 선택하고 `모의 결제 완료`를 누르면 샘플이 표시된다. 마이페이지에서 말투·강도를 바꾸고 다시 열어 표현을 비교한다. `시연 초기화 · 무료로 돌아가기`로 처음 상태를 재현한다.

## 실제 결제·AI 활성화 전 필요한 작업

1. 승인된 가격·기간과 결제 대행사를 정하고, 검증된 서버 결제 이벤트를 계정별 유료 권한에 연결한다. 프런트엔드의 성공 화면을 권한 근거로 사용하지 않는다.
2. 실제 권한과 발표 시연 권한의 저장·검증 경로를 분리하고 취소·환불·만료·중복 웹훅 처리를 구현한다. `has_paid_ai_entitlement`와 상태 API를 실제 유료 권한 저장소에 연결한다.
3. 기존 OpenAI 키·모델 접근 권한을 서버 비밀값으로 관리하고 운영 시작 정책을 검토한다. 프런트엔드에 키를 전달하지 않는다.
4. 기존 계정별·전체 24시간 요청 제한에 더해 월간 비용 예산과 토큰 사용량 기록을 추가한다. 요청 전에 비용을 예약하고 실제 사용량으로 정산하며 다중 서버의 동시 요청에서도 한도를 지킨다.
5. 계정과 요청 ID를 기준으로 중복 모델 요청을 막는다. 네트워크 실패로 응답 확인이 어려울 때 재시도·비용 처리 기준을 정하고 제공자 사용량과 대조한다.
6. 최소한의 수면 요약과 명시적 생활습관만 전송한다. 개인정보 전송 안내·동의, 보관 및 삭제 정책을 확인한다. 오류·사용량 로그에는 원시 건강 기록·계정 토큰·구독 비밀값을 포함하지 않는다.
7. 수동 기록의 기존 규칙 기반 대체 경로를 검증하고, 자동 기록 경로에도 서비스 정책에 맞는 실패 대체를 검토한다. 생성 출처와 과거 원문 보존을 유지한다.
8. 승인된 비운영 계정에서 실제 모델 문장 안전성·지연·비용을 확인한 뒤 최신 A안·PWA 통합 코드와 회귀 검증을 수행한다.

이번 단계의 검증은 모의 결제와 준비된 샘플을 대상으로 하며 실제 결제·실제 모델 호출·실기기 수신 검증을 포함하지 않는다.

## 검증과 재현

2026-11-19 KST에 합성 계정, 임시 SQLite 및 일회용 TLS PostgreSQL을 사용했다.

| 검사 | 결과 |
| --- | --- |
| `python -B -m unittest discover -s tests -p test_premium_demo.py -v` · 임시 SQLite | 9개 통과 |
| `python -B -m unittest discover -s tests -v` · 격리 PostgreSQL 및 로컬 프록시·데모 HTTP 검사 활성화 | 176개 중 173개 통과, 3개 건너뜀 |
| `node --experimental-strip-types --test tests/*.test.mjs` | 45개 통과 |
| `npm run typecheck`, `.next-production` 프로덕션 빌드 | 통과 |
| `python -B tests/premium_browser_fixture.py --mode staging` | Chrome 320·390·430·1280px, 4개 테마, 소개·취소·확인·완료·샘플·재접속·초기화·포커스·기록 보존 확인 |
| `python -B tests/premium_browser_fixture.py --mode production` | 같은 로컬 격리 환경에서 시연 플래그가 켜져 있어도 버튼·권한 발급 차단 확인 |
| 기존 수동 기록·Health Connect·iPhone 가이드 브라우저 회귀 | 수동 저장·수정·삭제·규칙 코칭, 기존 브리지 오류별 안내, 7단계 사진, JSON v2 가져오기·중복 방지·오류 처리 통과 |

브라우저 실행기는 `DALJAM_TEST_POSTGRES_BIN`을 로컬 PostgreSQL 도구 경로로 지정하고 `SLEEP_NEXT_DIST_DIR=.next-production`으로 빌드한 뒤 실행한다. `DALJAM_TEST_OPENSSL`로 테스트 인증서용 실행 파일을 지정할 수 있다. Windows 기본 Chrome 경로를 사용하며 필요하면 `DALJAM_TEST_CHROME`을 지정한다. 실행기는 외부 DB URL을 사용하지 않고 새 loopback DB와 임의 로컬 포트를 생성한다. 브라우저 테스트는 loopback 주소만 허용하며 실제 AI 키 조회도 차단한다. 각 실행 후 테스트 서버와 DB를 정리한다.

운영 모드 검사도 로컬 합성 계정으로 수행하며 Render·운영 DB에 접근하지 않는다. Linux Docker 실행, POSIX SIGTERM, 선택 SQL 문법 파서 3개 검사는 현재 Windows 환경에서 건너뛰었다. 실제 휴대폰의 Safari·WebView·스크린리더는 추가 검증이 필요하다.

구현 중 새 프리미엄 화면과 기존 계획 화면 사이의 React 키 중복으로 화면이 중복 렌더링되는 문제를 확인해 고유 키로 수정했다. 브라우저 검사에 단일 화면 확인과 콘솔 오류 검사를 추가했다. PostgreSQL 계정 삭제 검사에는 해당 일회용 DB에 한정한 백업 정책 모의를 적용했다.

스크린샷과 로그는 `sleep_frontend/.runtime/premium-captures/`, `premium-chrome.log`, `premium-production-chrome.log`, `premium-python-full.log`, `premium-web.log`, `premium-build.log`에 로컬 보관한다. 캡처는 가상 수면 기록과 합성 계정만 포함한다.

## 변경 파일

| 파일 | 목적 |
| --- | --- |
| `premium_service.py` | 임시 시연 권한·결제 확인·초기화·샘플 및 실제 유료 권한 경계 |
| `api.py` | 인증된 시연 API와 로그아웃·삭제 시 정리 |
| `coaching_service.py` | 실제 모델 호출 전 서버 유료 권한 확인 |
| `Dockerfile.production` | 신규 서버 모듈 복사 |
| `sleep_frontend/src/components/premium-demo.tsx` | 소개·확인·활성화·샘플·초기화 UI |
| `sleep_frontend/src/components/premium-demo.module.css` | A안 4개 테마를 재사용하는 반응형 스타일 |
| `sleep_frontend/src/lib/premium.ts` | 시연 상태 및 샘플 응답 타입 |
| `sleep_frontend/src/components/sleep-app.tsx` | 홈·코칭 진입 및 무료 코칭 안내 |
| `sleep_frontend/src/app/api/sleep/[...path]/route.ts` | 시연 경로를 기존 인증 프록시 허용 목록에 추가 |
| `tests/test_premium_demo.py` | 권한·결제 시연·실제 호출 차단·데이터 보존 검사 |
| `tests/premium_browser_fixture.py` | 격리 DB와 로컬 서버를 시작·종료하는 브라우저 실행기 |
| `sleep_frontend/tests/premium-browser.mjs` | 전환·초기화·테마·화면 폭·포커스·운영 차단 검사 |
| `tests/test_coaching_service.py`, `tests/test_manual_coaching.py` | 보존된 모델 어댑터 검사에 미래 유료 권한 모의 적용 |
| `docs/premium-demo.md`, `docs/manual-sleep-health-connect.md` | 발표 절차·검증 및 향후 활성화 조건 문서화 |
