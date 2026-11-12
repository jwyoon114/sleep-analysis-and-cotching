# 달잠 서버 개발 첫 단계 진단

기준일: 2026-11-12, Asia/Seoul. 이번 단계는 브랜치 준비·실제 코드 검토·합성 데이터 검사다.
애플리케이션 소스 수정, 기존 작업 복사·병합, 실제 배포는 하지 않았다.

## 결론과 다음 한 가지

새 통합 브랜치에는 무료 코칭·MBTI·PostgreSQL 스키마와 마이그레이션 실행기가 있다.
그러나 **FastAPI 저장소는 아직 SQLite이며 PostgreSQL API 전환은 완료되지 않았다.**
현재 소스에서 직접 실행할 Docker/Render 런타임도 없다. 따라서 이 커밋 그대로
Neon 환경변수를 넣고 공개 서비스를 만들면 정상적인 PostgreSQL 서비스가 되지 않는다.

오늘 HTTPS 링크 확보를 위한 다음 작업은 **기존 체험 화면을 재사용하는 체험 전용 배포 구성을
만들고 서버 측에서 실제 계정·건강 데이터 API를 차단하는 것**이다. 이번 진단에서는 구현하지 않았다.
전체 PostgreSQL API 전환은 기존 작업을 재사용할 수 있지만 실행기 계약 조정과 실제 DB 검증이 남아,
현재 상태에서 체험 공개보다 먼저 완료될 것으로 보장할 수 없다.

## 1. Git 기준과 작업 위치

| 항목 | 확인 결과 |
| --- | --- |
| 작업 폴더 | 기본 작업 공간 하위 `daljam-postgres-render-production` |
| 서버 브랜치 | `feature/postgres-render-production` 신규 생성 |
| 기준 원격 | `origin/feature/deployment-integration` |
| 기준 및 현재 HEAD | `68762198830906c4755edf391dbffa20150c44f8` |
| 원격 최신 확인 | fetch 후 전달받은 커밋과 정확히 일치. 이후 커밋 차이 없음 |
| 새 커밋 | 없음 |
| Push / Merge / PR | 없음 |
| 배포 커밋 / 공개 URL | 배포하지 않아 없음 |

원격 이력은 `6876219` 마이그레이션 실행기 추가, `a383756` PostgreSQL 기반 통합,
`81662dd` 무료 코칭 통합 순서다. 새 서버 브랜치의 upstream은 지정하지 않았다.
원격 통합 브랜치를 잘못 추적해 pull/push 대상으로 삼지 않게 하기 위한 로컬 설정이다.
브랜치 생성 전 같은 이름의 브랜치가 없는 것을 확인했다.

앱의 관리 worktree 목록은 비어 있고 채팅의 기본 저장소는 커밋이 없는 상위 폴더였다.
실제 Git 저장소가 하위 clone이므로 그 저장소에서 `git worktree add`로 새 작업 위치를 만들었다.

### 기존 작업 보존

- `sleep-analysis-and-cotching`: `codex/deploy-server`, HEAD `023cbc9bef4f05b8dc8e3312f4e7ca25f1b5cd34`.
- `daljam-server-postgres-render`: `feature/server-postgres-render`, HEAD `e99d1ef`.
- 두 곳 모두 기존 미커밋 변경을 유지했다. 시작 전 파일 해시와 진단 중 확인한 해시가 같고
  브랜치·HEAD도 그대로다. 최종 재확인 결과는 아래 최종 확인 항목에 기록한다.
- 팀원이 제공한 바탕화면 네 소스 폴더도 이번 단계에서 수정하지 않았다.
- 보존 해시 목록: 기본 작업 공간 `reports/deployment-diagnosis-before.json`.

## 2. 실제 DB와 API 구조

FastAPI 진입점은 루트 `api:app`이다. 인증은 `api.require_user()`에서 토큰을 검사한 뒤
`history_service.expire_trash()`를 호출한다. 일반 인증 요청도 만료 데이터 정리를 수행할 수 있다.

공통 저장소인 `health_records.connect()` (`health_records.py:141`)는 `SLEEP_DB_PATH` 또는
`data/sleep_records.sqlite3`에 연결하고 `sqlite3.Row`, PRAGMA, user_version에 따른 DDL을 실행한다.
여기에는 `postgres_db`나 `DATABASE_URL`을 선택하는 분기가 없다.

| 기능 | 저장소 및 SQLite 의존 |
| --- | --- |
| 계정·가입·로그인·토큰·로그인 제한 | `sleep_accounts.py` → health_records.connect; 계정 편집/삭제에 BEGIN IMMEDIATE, sqlite_master, PRAGMA |
| JSON/Markdown 수면 업로드·표본·단계·조회 | `health_records.py`; qmark 바인딩, INSERT OR IGNORE, 초기 DDL |
| 계정별 접근 제어 | subject/account_id 조건, `get_owned_session()`; PostgreSQL 전환 후에도 조건 보존 필요 |
| 무료 코칭·생성 이력·입력 JSON | `coaching_service.py`; BEGIN IMMEDIATE, 휴지통 INSERT OR IGNORE |
| 건강앱 연결·토큰·동기화·자동 코칭 작업 | `health_sync.py`; 연결 시 DDL/PRAGMA, INSERT OR REPLACE/IGNORE |
| 휴지통·복원·영구 삭제·기간 비교 | `history_service.py`; sqlite_master, PRAGMA secure_delete, 삭제 원장 |
| 백업 | `backup_policy.py`; 로컬 SQLite 파일 스냅샷·30일 정책·삭제 반영 |
| 알람·발송 중복 방지 | `sleep_alarms.py`; 연결 시 DDL, BEGIN IMMEDIATE, INSERT OR IGNORE |
| 요청 한도 | `service_limits.py`; SQLite 쓰기 트랜잭션 |

합성 확인에서 `DATABASE_URL=invalid-synthetic-url`, `SLEEP_DB_BACKEND=postgresql`을 설정해도
health_records.connect는 새 임시 SQLite 파일에 연결했다. PostgreSQL 연결 함수는 모의로 차단했고
호출되지 않았다. 임시 파일은 명시적으로 연결을 닫고 정리했다.
이는 ‘PostgreSQL 연결 실패 후 우회’가 아니라 **현재 API가 PostgreSQL 설정을 아예 사용하지 않는 상태**다.
별도 PostgreSQL 연결 모듈 자체에는 SQLite 우회가 없다.

## 3. PostgreSQL 연결·스키마·마이그레이션

`postgres_db.py`는 기존 두 서버 작업과 내용이 같다. 명시적인 단일 TCP 대상과 사용자·DB 이름을
요구하고 TLS require/verify-ca/verify-full만 허용한다. 타임아웃을 통제하며 원문 연결 오류와 비밀값을
기본 오류에 노출하지 않는다. import 시 연결하지 않는다. 결과는 dict 행이며 sqlite3.Row의 숫자 인덱스와
그대로 호환되지 않는다.

SQL·manifest도 기존 작업과 내용이 같다. v1은 앱 테이블 20개, 계정·기록·코칭·건강앱·알람을 포함한다.
기존 스키마를 다시 만들 필요가 없다.

새 통합의 실행기는 `postgres_migrate.py`다.

- LF로 읽은 SQL의 manifest SHA-256·버전·파일명을 연결 전 검사한다.
- v1 바깥 BEGIN/COMMIT을 제거하고 트랜잭션 안에서 SQL을 실행한다.
- READ COMMITTED, 5초 잠금 제한, 60초 쿼리 제한, transaction advisory lock을 사용한다.
- 적용 이력은 `public.daljam_schema_migrations(version,name,sha256,applied_at)`.
- v1 적용 중 sha256 열 및 형식 CHECK·NOT NULL을 추가한다. 과거 체크섬 없는 이력을 자동 채택하지 않는다.
- DB와 소스의 이름·버전·체크섬을 비교하고, 적용 실패 시 롤백한다.
- CLI는 현재 apply 전용이다. 기존 실행기의 `status`, `check-files` 명령과 호환되지 않는다.
  인수를 구분하는 파서가 없으므로 `--help` 등을 무해한 조회 명령으로 가정해 실행하면 안 된다.
  이번 진단에서는 연결을 수행하는 CLI를 실행하지 않았다.

### 기존 서버 작업과의 충돌·재사용

두 기존 작업 위치의 아래 핵심 구현은 서로 같다. 새 브랜치에 복사하지 않고 비교만 했다.

| 파일/범위 | 새 통합 대비 차이와 판단 |
| --- | --- |
| postgres_db.py, 초기 SQL, manifest | 동일. 그대로 재사용 가능 |
| coaching_free.py, coaching_patterns.py, coaching_rules.py | 동일. 무료 엔진 재작성 불필요 |
| 모바일 프록시, package.json | 동일. 엔드포인트와 코칭 검사 중복 작성 불필요 |
| postgres_migrate.py | 새 통합에만 있음. 앞으로 이 실행기를 기준으로 삼는 편이 변경 이력을 보존하기 좋음 |
| migration_runner.py | 기존 작업에만 있음. 새 실행기와 병존시키는 방식은 피해야 함 |
| app_database.py | 기존 작업에만 있음. 행/SQL/트랜잭션 호환을 재사용하되 migration_runner의 load_migrations·inspect_history 의존을 새 실행기 계약에 맞춰 조정해야 함 |
| health_records, sleep_accounts, health_sync, coaching_service, history_service, service_limits, sleep_alarms, backup_policy | 기존 작업에 PostgreSQL 변환이 있음. 파일 전체 덮어쓰기 대신 DB 변경 부분을 비교 반영할 후보 |
| api.py | 기존 작업에 안전한 503 응답과 readiness가 있음. 새 adapter 및 실행기에 맞춰 재검증 필요 |
| Dockerfile, .dockerignore, render.yaml, requirements-server.txt, deploy/supervisor.py | 기존 작업에만 있음. 실행기 파일명·복사 목록·부팅 조건이 달라 그대로 사용 불가 |
| Next config·정책 안내·웹 readiness | 기존 작업에 standalone/정책 보류 안내가 있음. UI 팀원 변경과 분리 검토 필요 |
| DB·API 통합 테스트 | 기존 테스트는 이전 실행기와 PGlite에 의존. 새 기준의 성공 결과로 간주할 수 없음 |

특히 두 실행기는 이력의 핵심 값은 같지만 잠금 번호가 다르다.
새 실행기는 `0x44616C6A616D`, 기존 migration_runner는 `731412810`을 사용한다.
동시에 실행해도 같은 잠금을 공유하지 않으므로 둘을 운영 적용 경로로 남기면 안 된다.
v1 sha256 열의 제약과 무이력 기존 테이블 처리 방식에도 차이가 있어 실제 DB 호환 검증이 필요하다.
새 스키마 생성이나 이력 초기화로 해결하지 않는다.

## 4. Next.js·API·배포 구성

- `src/app/page.tsx` → client `SleepApp`. `/?demo=1`은 가상 기록과 코칭을 보여 주는 기존 체험 진입점이다.
- `/api/sleep/[...path]`는 SLEEP_API_URL(기본 127.0.0.1:8011)로 프록시한다.
  API allowlist, 쓰기 Origin 검사, HttpOnly/sameSite 로그인 쿠키, 서버 측 Bearer 전달이 있다.
  로그인 응답의 token을 브라우저 JSON에서 제거한다. Render HTTPS 환경의 Secure 쿠키는 별도 검증 필요다.
- `/api/mobile/health-sync`는 네이티브 Bearer 토큰과 3MiB 제한을 사용하는 기존 엔드포인트다.
- 프론트 start/dev 명령은 127.0.0.1:3000 고정이다. Render 외부 PORT 바인딩용 시작 구성이 필요하다.
- next.config.ts에 standalone 출력이 없다. 한 서비스에서 두 서버를 실행하는 프로세스 관리자도 없다.
- 현재 `/health`는 프로세스 정보만 반환하며 DB를 확인하지 않는다. DB readiness와 `/api/ready`는 없다.
- 현재 브랜치에는 Dockerfile·Render 설정·서버 전용 requirements가 없다.
- 원격 main에는 `Dockerfile.cloud`와 render.yaml이 있지만, ZIP 내부 `/src/mobile_backend` 등을
  빌드하는 과거 시안이다. 현재 루트 `api:app` 소스를 직접 빌드하는 구성이 아니다. 복사하지 않았다.

무료 코칭은 `COACHING_ENGINE` 기본값 rules다. 명시적으로 openai를 선택하면 유료 호출 경로가 있다.
배포 시 rules를 고정하고 OPENAI_API_KEY·secrets.toml을 이미지에 넣지 않아야 한다.
무료 코칭이 존재한다는 사실과 외부 유료 API 경로가 완전히 제거됐다는 사실을 혼동하지 않는다.

## 5. 건강앱 위험과 공개 범위

다음은 코드 검토로 확인한 위험이며 실제 휴대폰에서 재현·수정한 결과가 아니다.

1. 일부 기록 누락: health_sync.py:163의 삭제 판정은 records가 있고 ignored가 없을 때
   범위 안 누락 날짜를 휴지통으로 옮긴다. 별도 ‘완전한 스냅샷’ 증명 필드는 없다.
   일부 권한/조회 누락이 삭제로 처리될 가능성은 실기기·부분 스냅샷 시험이 필요하다.
2. 시간대: normalize는 전달된 timezone과 현지 정오로 날짜를 나누며 ID는 account+day를 사용한다.
   휴대폰 시간대 변경 후 재그룹화·기존 날짜 처리에 대한 검증이 필요하다.
3. 자동 코칭 재시도: health_advice_jobs 표식을 코칭 생성 전에 커밋한다.
   실패 후에도 표식이 남아 같은 작업의 자동 재시도가 막힐 수 있다. 수동 코칭 경로는 별도다.

이번 단계에서 이 로직과 UI/코칭 개인화는 수정하지 않았다. 실제 건강 데이터 수집을 여는 전에는
우선 검증·정책 확정이 필요하다. 체험 공개에서는 동기화 자체를 비활성화하면 일정과 분리할 수 있다.
PostgreSQL 백업을 SQLite 30일 파일 백업과 동일하게 취급하는 문제도 해결해야 한다.
기존에 승인된 클라우드 영구 삭제·계정 삭제 보류 정책은 후속 전환에서 유지할 기준이다.

## 6. 이번에 직접 실행한 검사

이전 작업이나 팀원 보고를 이번 기준의 검사 결과로 재사용하지 않았다.
테스트는 임시 SQLite 또는 모의 연결을 사용하는지 먼저 읽었다. 자식 환경의 실제 DATABASE_URL,
PG 연결 설정, OPENAI_API_KEY 및 PostgreSQL 시험 opt-in 설정을 제거하고 desktop 알람을 껐다.

| 검사 | 결과 |
| --- | --- |
| Python unittest discover | 110개 실행: 101개 통과, 9개 건너뜀, 실패 0, 22.885초 |
| 건너뛴 항목 | 실제 로컬 PostgreSQL 실행 파일이 필요한 마이그레이션 8개, 선택 pglast 1개 |
| 프론트 코칭/MBTI | 19개 통과, 실패 0 |
| TypeScript | tsc --noEmit --project sleep_frontend/tsconfig.json 통과 |
| test:timeline에 해당하는 명령 | 실패: tests/timeline.test.mjs가 없음. 등록된 명령과 파일 목록 불일치 |
| PostgreSQL 설정 사용 여부 합성 probe | PostgreSQL 환경변수를 넣어도 sqlite3 연결. 실제 PG 연결 호출 없음 |
| 기본 Next 빌드 최초 시도 | 외부 node_modules junction이 Turbopack root 밖이라 next/package.json 해석 실패. 앱 코드 오류로 판정하지 않음 |
| Next 빌드 재검사 | 통과. Next.js 16.4.5 기본 Turbopack 빌드, 컴파일 48초·타입 검사 12.2초 |

PostgreSQL 실행 파일(initdb/pg_ctl)과 Docker는 PATH에서 찾지 못했고 통상 PostgreSQL 설치 폴더도 없다.
실제 PostgreSQL·Neon·TLS 연결·DB 재시작·API 영속성은 이번에 검증하지 않았다.
팀원 보고의 ‘109개 통과 및 실제 PostgreSQL 8개 통과’는 이 PC에서 재현된 결과가 아니다.
Docker 전체 빌드·Render/HTTPS·실제 모바일도 미실행이다.

Python 로그: 기본 작업 공간 `reports/integration-diagnosis/python-tests.log`.
빌드 로그: 같은 폴더의 `frontend-build.log`와 `frontend-build-local-deps.log`.
생성된 의존성·빌드 캐시는 Git에서 제외되며 배포 산출물로 취급하지 않는다.

## 7. 오늘 가능한 최소 공개 경로

권장 범위는 가상 기록의 대시보드·그래프·기존 코칭/표현 체험이다. 실제 회원가입, 파일 업로드,
건강앱 연결, 사용자 데이터 저장과 새 코칭 생성은 제공하지 않는다고 명시해야 한다.

기존 demo 플래그는 브라우저 편의 기능일 뿐 공개 API를 막는 보안 경계가 아니다.
후속 구현에서는 공개 실행을 강제로 체험 화면에 진입시키고, 모든 `/api/sleep/*` 및
`/api/mobile/health-sync`를 서버 측에서 차단해야 한다. 쿠키·Authorization 헤더를 넣어 직접 호출해도
차단되는지 시험해야 한다. FastAPI/DB를 체험 서비스에서 실행하지 않는 구성이 가장 단순하다.
실제 데이터 요청 본문을 로그에 남기지 않고 차단하며, 체험 전용 liveness를 따로 둔다.

서비스는 하나만 사용하고 나중에 같은 서비스에 정식 런타임을 배포해 URL을 유지하는 구성이 가능하다.
현재 Render 서비스·계정·요금제를 확인하지 않았으므로 존재 여부나 비용·메모리 적합성을 단정하지 않는다.
서비스 생성 전 사용자가 기존 서비스 유무와 선택 요금제를 확인해야 하며, 유료 생성·결제는 별도 확인이 필요하다.

승인 후 필요한 사용자 설정은 GitHub 개인 브랜치 연결, 단일 Web Service 선택, 외부 PORT 수신,
자동 배포 끄기, 체험 전용 환경 설정, HTTPS 확인이다. 체험 단계에서는 Neon/AI 키가 필요하지 않다.
이번에는 서비스 생성·설정 변경·결제·실제 배포를 수행하지 않았다.

## 8. 종료 시 최종 확인

- 기본 Next.js 프로덕션 빌드는 새 폴더 내부 의존성으로 재실행해 통과했다. 설정·소스 수정은 없었다.
- 새 worktree의 git diff 및 staged diff는 비어 있고, Git에 보이는 추가 파일은 이 진단 문서뿐이다.
- 기존 두 작업 위치의 파일 해시·브랜치·HEAD 최종 재확인: 모두 일치했다.
- 최종 보존 확인 파일은 기본 작업 공간 reports/integration-diagnosis/preservation-final.json이다.
- 새 기준에서 실제 HTTP 프록시·HTTPS 쿠키·모바일 실기기·Neon·Docker·Render 검증은 하지 않았다.
- 기존 두 서버 작업의 이전 통과 결과를 새 기준의 통과 결과로 표시하지 않았다.
- 애플리케이션 코드·팀원 UI·코칭 개인화·건강앱 정책은 변경하지 않았다.
- Commit·Push·Merge·PR·결제·서비스 생성·실제 배포·기존 데이터 이관/삭제/초기화는 하지 않았다.

작업 1(안전한 브랜치 준비)은 완료했다. 작업 2~4는 새 기준의 구조·재사용 후보를 진단한 상태이며,
PostgreSQL API 구현·실제 DB 기능 검증이 완료된 상태가 아니다. 작업 5(실제 배포)는 미착수다.
다음 한 가지는 위에 제시한 체험 전용 실행 구성과 서버 측 데이터 API 차단을 구현·검증하는 것이다.
