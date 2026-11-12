# 달잠 체험 전용 배포 준비

2026-11-12. 현재 상태는 로컬 구현·검증이며 실제 공개 배포가 아니다.
작업 브랜치는 `feature/postgres-render-production`, 기준 HEAD는 `6876219`다.
기존 두 서버 작업과 팀원 UI·코칭·건강앱 로직을 보존한다.

## 제공 범위

기존 가상 기록으로 대시보드, 수면 그래프, 기록 상세, 코칭 예시, MBTI 표현과 동물 캐릭터를 체험한다.
실제 회원가입·로그인·파일 업로드·건강앱 동기화·새 코칭 생성·데이터 저장은 제공하지 않는다.
화면 상단에 이 제한을 안내한다. 기존 팀원 컴포넌트는 수정하지 않고 서버 페이지에 안내만 추가했다.

## 구현

| 파일 | 역할 |
| --- | --- |
| sleep_frontend/src/lib/demo-mode.ts | 서버 런타임 플래그와 공통 403 demo_only 응답 |
| sleep_frontend/src/proxy.ts | 체험 진입 강제, /api 전체 차단, 유일한 체험 health 경로 허용 |
| 두 기존 API route.ts | Proxy를 통과하더라도 본문/쿠키/토큰 처리 전에 체험 모드 차단 |
| sleep_frontend/src/app/page.tsx | 실제 기능과 가상 체험을 구분하는 안내. 런타임 렌더링 |
| sleep_frontend/src/app/api/demo-health/route.ts | DB와 무관한 체험 웹 상태. demo 플래그가 없으면 404 |
| sleep_frontend/next.config.ts | standalone 출력과 메모리 캐시 비활성화 |
| deploy/start-demo.mjs | 체험 모드·PORT 검증, DB/AI 설정 제거, 단일 Node 프로세스 실행 |
| Dockerfile / .dockerignore | 현재 프론트 소스만 직접 빌드. ZIP·DB·Python API·비밀 파일 제외 |
| render.yaml | 단일 유료 Web Service 준비, 자동 배포 끄기, 체험 health 사용 |

`DALJAM_DEMO_ONLY=1`은 서버 전용 런타임 환경변수다. NEXT_PUBLIC 변수가 아니다.
브라우저 쿼리·쿠키·Bearer 토큰으로 해제할 수 없다. `/` 또는 `/?demo=0` 요청은 `/?demo=1`로 이동한다.
`/api/demo-health` 외 API는 알려지지 않은 경로와 향후 경로도 Proxy에서 거부한다.
기존 두 데이터 라우트도 별도로 차단한다. 오류 응답에는 no-store를 적용하고 입력 값을 되돌려주지 않는다.

실행기는 플래그가 없거나 1이 아니면 서버를 시작하지 않는다. DATABASE_URL, PG* 및 OPENAI_*와
기존 DB 경로·백엔드 URL 설정을 제거하며, 체험 이미지에는 FastAPI나 Python DB 코드가 없다.
Next.js가 외부 PORT와 0.0.0.0에서 수신한다. 단일 프로세스의 종료 처리는 Next.js가 담당한다.
Linux SIGTERM과 Docker 전체 실행은 아직 검증하지 않았다.

정상 개발 모드에서 DALJAM_DEMO_ONLY를 해제하면 기존 앱과 프록시가 유지된다.
다만 이 체험 전용 Dockerfile의 실행기는 해제된 상태로 실행할 수 없다. 정식 PostgreSQL 서비스로
전환하려면 별도 검증된 런타임 변경이 필요하다.

## 실행과 검사

```powershell
cd sleep_frontend
npm ci
npm run test:coaching
npm run test:demo
npm run typecheck
npm run build
cd ..
```

Windows standalone 로컬 검증은 public 및 .next/static을 standalone 폴더에 복사해야 한다.
아래 HTTP 검사기는 그 복사를 수행하고 임시 모의 API와 체험 서버를 실행한 뒤 정리한다.

```powershell
$env:DALJAM_RUN_DEMO_HTTP = '1'
python -m unittest discover -s tests -p test_demo_web_integration.py -v
```

Node가 PATH에 없으면 DALJAM_TEST_NODE에 로컬 node 실행 파일 경로만 설정한다.
실제 DB URL이나 AI 키는 필요하지 않다. 일반 Python 검사에서는 이 HTTP 검사가 opt-in으로 건너뛰어진다.

수동 로컬 확인:

```powershell
$env:DALJAM_DEMO_ONLY = '1'
$env:PORT = '10000'
node deploy/start-demo.mjs sleep_frontend/.next/standalone/server.js
```

Docker 사용 가능한 환경에서 검사할 명령은 `docker build -t daljam-demo .` 및
`docker run --rm -p 10000:10000 daljam-demo`다. 현재 PC에서는 Docker가 없어 실행하지 않았다.
Windows에서 생성한 standalone의 junction 산출물을 업로드하지 않고 Linux Docker 빌드로 다시 만든다.

## 검증 결과

- 체험 실행기 검사 3개 통과: 플래그 오류 거부, PORT/바인딩, DB·유료 모델 설정 제거.
- 기존 프론트 코칭·MBTI 19개와 실행기 3개를 함께 실행하여 총 22개 통과, 실패 0을 확인했다.
- 타입 검사와 Next.js 16.4.5 기본 Turbopack standalone 빌드 통과.
- 실제 standalone HTTP 검사 1개 최초 실행 통과: 12개 API 경로 × 7개 메서드 84개 요청 403,
  가짜 쿠키·Bearer·Origin·demo=0에도 차단, 가상 화면·JS·아이콘·PWA 파일 제공,
  체험 health 200, 모드 해제 후 기존 프록시가 모의 API로 전달됨을 확인.
- 최종 HTTP 검사 1개 통과(21.271초). 실행기 없이 체험 플래그와 모의 upstream을 직접 지정한
  추가 시나리오도 통과했고 데이터 API가 upstream으로 전달되지 않았다.
- 브라우저에서 기본 휴대폰 크기와 1366×900 PC 크기로 대시보드를 확인했다.
  코칭 페이지의 ENFP 선택에 따른 표현 전환도 확인했고 확인 시 콘솔 오류·경고는 없었다.
- 스크린샷은 기본 작업 공간 reports/integration-diagnosis/demo-mobile.png 및 demo-desktop.png다.
- 이번 작업은 Python API 소스를 바꾸지 않았다. 앞 진단의 Python 결과는 101개 통과·9개 건너뜀이다.
  기존 test:timeline의 누락된 시험 파일 문제는 그대로이며 이 단계에서 수정하지 않았다.

로그는 기본 작업 공간 reports/integration-diagnosis/의 demo-build.log, demo-frontend-tests.log,
demo-http.log, demo-http-final.log에 저장한다. 실제 Neon·Render·외부 HTTPS·실제 모바일 기기 검증은 미실행이다.

## 승인 후 Render 설정 — 서비스는 아직 생성하지 않음

사용자는 현재 기존 Render 서비스가 없다고 확인했다. 새 서비스는 한 개만 만든다.

1. 먼저 아래 변경 파일을 검토하고 개인 브랜치 Commit·Push 승인을 받는다.
   현재 GitHub에는 이 미커밋 체험 변경이 없으므로 현재 원격 브랜치를 배포하면 이 버전이 실행되지 않는다.
2. Render에서 New → Web Service → GitHub 저장소를 연결한다.
3. Branch는 feature/postgres-render-production, Language/Runtime은 Docker, 저장소 루트는 기본값,
   Dockerfile 경로는 ./Dockerfile로 선택한다.
4. 싱가포르 리전, 인스턴스 한 개, 0.5c-512mb 요금제를 선택한다.
   [공식 가격표](https://render.com/pricing)에서 이 플랜은 월 $7의 컴퓨트 비용으로 표시된다.
   이는 컴퓨트 기준이며 세금·환율·대역폭 등 추가 항목과 최종 결제 화면을 사용자가 확인해야 한다.
   유료 workspace 업그레이드나 별도 DB·디스크·추가 서비스를 임의로 선택하지 않는다.
5. 환경변수 DALJAM_DEMO_ONLY=1만 추가한다. PORT는 Render 제공값을 사용한다.
   DATABASE_URL, OPENAI_API_KEY, SLEEP_API_URL은 추가하지 않는다.
6. Health Check Path는 /api/demo-health, Auto-Deploy는 Off로 둔다.
   필드는 [공식 Blueprint 스펙](https://render.com/docs/blueprint-spec)을 기준으로 준비했다.
7. 유료 생성·결제·실제 배포는 별도 확인 뒤 진행한다. 승인 전 Create/Deploy 버튼을 누르지 않는다.
8. 배포된 브랜치·커밋, 로그의 체험 시작, 실제 onrender.com HTTPS 화면, API 403, 모바일 접속을 확인한다.
   행사 개최자에게 전달할 주소는 이때 확인한 웹앱 URL이다. 로컬 주소나 health 경로는 공개 링크가 아니다.

현재는 실제 HTTPS URL이 없다. 월 $7 플랜의 부하·메모리 적합성도 클라우드에서 검증하지 않았다.
후속 정식 서비스를 같은 Render 서비스에 배포하면 URL을 유지할 수 있지만, 체험에서 정상 모드로
플래그만 바꾸어 서비스를 공개하면 안 된다. PostgreSQL API 전환·백업 정책·실제 DB 검증이 선행돼야 한다.

## 준비 검증 당시 확인

- 프론트 검사 22개 및 실제 HTTP 통합 검사 1개 통과. 타입 검사·standalone 빌드도 통과했다.
- 기본 API·건강앱·무료 코칭·DB 실행기·팀원 UI 컴포넌트 파일은 수정하지 않았다.
- 기존 두 서버 작업의 파일 해시·브랜치·HEAD는 진단 시작 전 목록과 모두 일치한다.
- 현재 브랜치는 feature/postgres-render-production, HEAD 6876219 그대로이며 새 커밋·Push는 없다.
- Render 계정/서비스 설정 변경, 결제, 실제 배포, 실제 DB 접근은 하지 않았다.
- 다음 작업은 변경 검토 후 개인 브랜치 Commit·Push 및 단일 Render 유료 서비스 배포에 대한 명시 승인이다.
  기존 main/develope/통합 브랜치 병합은 필요하지 않다.


## 사용자 배포 승인

2026-11-12 사용자가 개인 브랜치 Commit·Push와 기본 컴퓨트 월 US$7의 Render 서비스 한 개
생성·배포를 승인했다. 보호 브랜치 병합은 승인 범위에 포함하지 않는다.
검증된 체험 변경을 개인 브랜치에 올린 뒤 Render 로그인·저장소 연결·요금 설정을 진행한다.
계정 로그인과 인증코드·카드 정보는 채팅으로 전달받지 않는다.
실제 배포 커밋, 서비스 주소와 외부 검증 결과는 확인 후 별도 기록한다.
