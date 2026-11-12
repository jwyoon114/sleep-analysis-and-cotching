# PostgreSQL 스키마 준비 — 버전 0001

기준 브랜치: feature/cloud-deployment. 기존 연결 기반 커밋: 7d1a4b1.
실제 사용자 DB를 열지 않고 현재 Python 소스의 CREATE/ALTER 정의로 빈 메모리 SQLite 스키마를 재구성하여 비교했다.
이 문서는 Neon에 SQL을 적용하거나 기존 서비스를 PostgreSQL로 전환했다는 의미가 아니다.
실제 사용자 계정·수면·건강 데이터는 이관하지 않는다.

## 제공 파일과 적용 경계

- migrations/postgresql/0001_initial_schema.sql: 빈 PostgreSQL 대상에 한 번 적용할 초기 마이그레이션.
- migrations/postgresql/manifest.json: 버전, 파일명, LF 기준 SHA-256, 앱 테이블 수.
- tests/test_postgres_schema.py: 네트워크 없이 소스 DDL과 새 스키마의 계약을 비교하는 테스트.
- postgres_db.py와 기존 API/서비스의 연결 경로는 변경하지 않는다.

기존 앱 테이블 20개(85개 열), 기본 키 19개, 추가 UNIQUE 제약 3개, 명시적 조회 인덱스 6개, 외래 키 17개를 보존한다.
외래 키의 ON DELETE CASCADE는 기존 건강앱 관련 5개에만 적용하고 나머지 12개는 NO ACTION을 유지한다.
모든 외래 키는 ON UPDATE NO ACTION, NOT DEFERRABLE이다.
PK/UNIQUE가 만드는 22개 인덱스 외에 기존 조회 인덱스 6개를 생성한다. 불필요한 중복 인덱스는 추가하지 않는다.
앱 테이블과 별도로 적용 이력용 public.daljam_schema_migrations 1개를 추가하므로 PostgreSQL 전체 테이블 수는 21개다.

## 자료형·문자열·정합성 원칙

- TEXT는 TEXT로 유지한다. ID를 UUID로, JSON 문자열을 JSONB로, 앱의 날짜 문자열을 DATE/TIMESTAMPTZ로 바꾸지 않는다.
- 모든 TEXT 열에 COLLATE "C"를 명시하여 SQLite 기본 BINARY와 같은 UTF-8 바이트 정렬 및 대소문자 구분을 사용한다.
- SQLite INTEGER는 64비트이므로 PostgreSQL BIGINT로 옮긴다. INTEGER(int4)로 줄이지 않는다. position, auto_coach, enabled가 대상이다.
- SQLite REAL은 64비트 부동소수점이므로 PostgreSQL DOUBLE PRECISION을 사용한다. PostgreSQL REAL(float4)로 줄이지 않는다.
- auto_coach/enabled는 BIGINT 상태값으로 유지한다. BOOLEAN, 열거형, 새 CHECK 제약이나 시간·JSON 형식 제약을 추가하지 않는다.
- 앱 날짜/시각, 해시, salt, 제공자와 출처 ID의 문자열 형식 및 명시된 기본값을 유지한다.
- 이력 테이블의 applied_at만 새 메타데이터이므로 TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP를 사용한다.
- 열 이름은 모두 SQL 쌍따옴표로 감싼다. 향후 쿼리를 전환할 때도 start/end 등 식별자를 안전하게 인용해야 한다.

PostgreSQL PK는 NULL을 허용하지 않는다. SQLite 일반 테이블에서 PK지만 NOT NULL이 명시되지 않은 17개 열은 더 엄격해진다.
아래 차이를 숨기기 위해 기본 키를 제거하거나 NULL을 임의 값으로 바꾸지 않는다. 현재는 빈 대상만 준비하고 기존 데이터는 이관하지 않는다.
추후 정책이 바뀌면 NULL PK, 중복 PK/UNIQUE, 고아 FK, INTEGER 열의 비정수/범위 초과, TEXT의 NUL·잘못된 인코딩을 별도 승인 범위에서 사전 점검해야 한다.
SQLite의 느슨한 자료형 허용과 PostgreSQL의 엄격한 자료형 검사를 모든 임의 데이터에서 같게 만들 수는 없다.
또한 PostgreSQL의 기본 NULL 정렬 위치와 LIKE/문자열 함수의 동작은 SQLite와 같다고 가정하지 않는다.
향후 API 쿼리 전환에서 필요한 NULLS FIRST/LAST와 대소문자 비교를 명시하고 회귀 검사한다.

NULL 허용이 달라지는 PK 열:

- `accounts`: `id`
- `auth_tokens`: `token_hash`
- `coaching`: `id`
- `coaching_context`: `coaching_id`
- `coaching_requests`: `id`
- `health_connections`: `account_id`
- `import_sessions`: `import_id`, `session_id`
- `imports`: `id`
- `samples`: `id`
- `session_created`: `session_id`
- `sessions`: `id`
- `sleep_alarm_settings`: `account_id`
- `stages`: `session_id`, `position`
- `trash_coaching`: `coaching_id`
- `trash_sessions`: `session_id`

## 20개 앱 테이블의 열과 제약

아래는 SQLite 원본의 열 순서·자료형이다. !는 원본에 명시된 NOT NULL, =0은 기본값 0을 뜻한다.
별도 PK 열은 PostgreSQL에서 모두 NOT NULL이며 TEXT/INTEGER/REAL의 대응은 위 원칙을 따른다.
login_attempts에는 기존 구조대로 PK가 없다. 기존에 없던 소유권 FK나 UNIQUE를 임의로 추가하지 않는다.

| 테이블 | 열(원본 순서) | PK | 추가 UNIQUE |
|---|---|---|---|
| `accounts` | `id TEXT`, `username TEXT!`, `password_hash TEXT!`, `salt TEXT!`, `created_at TEXT!` | `id` | `username` |
| `auth_tokens` | `token_hash TEXT`, `account_id TEXT!`, `expires_at TEXT!` | `token_hash` | 없음 |
| `coaching` | `id TEXT`, `account_id TEXT!`, `session_id TEXT!`, `text TEXT!`, `lifestyle TEXT!`, `created_at TEXT!` | `id` | 없음 |
| `coaching_context` | `coaching_id TEXT`, `payload TEXT!` | `coaching_id` | 없음 |
| `coaching_requests` | `id TEXT`, `account_id TEXT`, `requested_at TEXT!` | `id` | 없음 |
| `health_advice_jobs` | `account_id TEXT!`, `session_id TEXT!` | `account_id, session_id` | 없음 |
| `health_connections` | `account_id TEXT`, `token_hash TEXT!`, `provider TEXT!`, `source_id TEXT!`, `source_name TEXT!`, `created_at TEXT!`, `expires_at TEXT!`, `last_synced_at TEXT`, `auto_coach INTEGER!=0`, `advice_status TEXT`, `last_window_end TEXT` | `account_id` | `token_hash` |
| `health_sync_sessions` | `account_id TEXT!`, `day TEXT!`, `session_id TEXT!` | `account_id, day` | `session_id` |
| `import_sessions` | `import_id TEXT`, `session_id TEXT` | `import_id, session_id` | 없음 |
| `imports` | `id TEXT`, `subject TEXT!`, `filename TEXT!`, `imported_at TEXT!` | `id` | 없음 |
| `login_attempts` | `username TEXT!`, `attempted_at TEXT!` | 없음 | 없음 |
| `permanent_deletions` | `kind TEXT!`, `record_id TEXT!`, `subject TEXT!`, `deleted_at TEXT!` | `kind, record_id, subject` | 없음 |
| `samples` | `id TEXT`, `subject TEXT!`, `metric TEXT`, `source TEXT`, `unit TEXT`, `start TEXT`, `end TEXT`, `value REAL` | `id` | 없음 |
| `session_created` | `session_id TEXT`, `created_at TEXT!` | `session_id` | 없음 |
| `sessions` | `id TEXT`, `subject TEXT!`, `start TEXT!`, `end TEXT!`, `payload TEXT!` | `id` | 없음 |
| `sleep_alarm_fires` | `account_id TEXT!`, `kind TEXT!`, `local_date TEXT!`, `fired_at TEXT!` | `account_id, kind, local_date` | 없음 |
| `sleep_alarm_settings` | `account_id TEXT`, `bedtime TEXT!`, `wake_time TEXT!`, `timezone TEXT!`, `enabled INTEGER!`, `coaching_id TEXT`, `updated_at TEXT!` | `account_id` | 없음 |
| `stages` | `session_id TEXT`, `position INTEGER`, `start TEXT`, `end TEXT`, `stage TEXT`, `minutes REAL` | `session_id, position` | 없음 |
| `trash_coaching` | `coaching_id TEXT`, `account_id TEXT!`, `deleted_at TEXT!` | `coaching_id` | 없음 |
| `trash_sessions` | `session_id TEXT`, `subject TEXT!`, `deleted_at TEXT!` | `session_id` | 없음 |

health_connections에는 과거 CREATE 뒤 ALTER로 추가되던 last_window_end TEXT도 포함한다.

## 외래 키 전체

모든 참조 열은 id다. ON UPDATE는 전부 NO ACTION이다.

| 자식 테이블.열 | 부모 테이블.열 | ON DELETE |
|---|---|---|
| `auth_tokens.account_id` | `accounts.id` | NO ACTION |
| `coaching.account_id` | `accounts.id` | NO ACTION |
| `coaching.session_id` | `sessions.id` | NO ACTION |
| `coaching_context.coaching_id` | `coaching.id` | NO ACTION |
| `health_advice_jobs.account_id` | `accounts.id` | CASCADE |
| `health_advice_jobs.session_id` | `sessions.id` | CASCADE |
| `health_connections.account_id` | `accounts.id` | CASCADE |
| `health_sync_sessions.account_id` | `accounts.id` | CASCADE |
| `health_sync_sessions.session_id` | `sessions.id` | CASCADE |
| `import_sessions.import_id` | `imports.id` | NO ACTION |
| `import_sessions.session_id` | `sessions.id` | NO ACTION |
| `session_created.session_id` | `sessions.id` | NO ACTION |
| `sleep_alarm_fires.account_id` | `accounts.id` | NO ACTION |
| `sleep_alarm_settings.account_id` | `accounts.id` | NO ACTION |
| `stages.session_id` | `sessions.id` | NO ACTION |
| `trash_coaching.coaching_id` | `coaching.id` | NO ACTION |
| `trash_sessions.session_id` | `sessions.id` | NO ACTION |

예를 들어 sessions.subject, imports.subject, coaching_requests.account_id, trash_*의 소유자 열, sleep_alarm_settings.coaching_id에는 기존에 FK가 없다.
같은 이름의 값이 들어갈 수 있다는 이유만으로 관계를 추가하지 않는다. 계정/기록 삭제 순서는 향후 서비스 전환에서 따로 검증한다.

## 명시적 조회 인덱스

| 이름 | 대상 열 |
|---|---|
| `coaching_account_session` | `coaching(account_id, session_id, created_at)` |
| `coaching_requests_time` | `coaching_requests(requested_at)` |
| `samples_observation` | `samples(subject, metric, source, unit, start, end)` |
| `sessions_subject_start` | `sessions(subject, start)` |
| `trash_coaching_owner_time` | `trash_coaching(account_id, deleted_at)` |
| `trash_sessions_owner_time` | `trash_sessions(subject, deleted_at)` |

## 마이그레이션 버전과 실패 처리

0001 파일은 BEGIN부터 COMMIT까지 하나의 트랜잭션이다. 잠금 대기는 5초, 개별 문장의 실행 제한은 60초로 두었다.
public 스키마를 명시하고 부모 테이블을 먼저 만든 뒤 자식 테이블과 인덱스를 생성한다.
이력 테이블을 먼저 생성하고 마지막에 버전 1과 이름 0001_initial_schema만 기록한다. 앱 테이블에 대한 데이터 INSERT/UPDATE/DELETE는 없다.
CREATE TABLE/INDEX에 IF NOT EXISTS를 사용하지 않는다. 이미 존재하는 객체와 충돌하면 적용을 실패시켜 다른 구조를 조용히 채택하지 않는다.
파일 전체를 같은 연결의 트랜잭션으로 실행해야 한다. 중간 오류가 나면 ROLLBACK 후 원인을 조사하며 일부 문장만 재실행하거나 기존 테이블을 삭제하지 않는다.
같은 0001의 재실행은 첫 이력 테이블 생성에서 실패하는 방식이다. 재실행을 자동 건너뛰는 도구는 이번 범위에 없다.
처음 적용하기 전에 이력과 대상 객체가 없는 새 전용 DB인지 확인한다. 이미 이력이 있으면 해당 버전과 배포 파일을 먼저 비교한다.

manifest의 SHA-256은 UTF-8, LF 줄바꿈 기준으로 검사하여 Windows CRLF 체크아웃도 동일하게 처리한다.
적용한 SQL 파일은 나중에 덮어쓰지 않는다. 후속 변경은 0002_이름.sql과 새 manifest 항목으로 추가한다.
현재 테스트는 초기 버전 1을 고정 검증한다. 후속 버전을 만들면 이력 순서·누적 스키마 검증도 확장해야 한다.
자동 적용기·앱 시작 시 마이그레이션·데이터 이관·DROP 기반 down 마이그레이션은 제공하지 않는다.

## 로컬 검증 방법과 한계

    python -B -m unittest discover -s tests -p test_postgres_schema.py -v

표준 라이브러리만으로 버전/체크섬, 제한된 SQL 문장 형태, 열/자료형/기본값/NULL, PK/UNIQUE/FK/인덱스를 비교한다.
원본 SQLite DDL은 AST에서 리터럴만 추출하고 서비스 코드는 실행하지 않는다. 실제 SQLite 파일과 DATABASE_URL은 읽지 않는다.
논리 검증용 메모리 DB에서는 public. 접두사만 제거하고 "C" 비교 함수를 등록한다. PostgreSQL 타입/명령의 전체 문법 검증이나 실제 엔진 실행을 대신하지 않는다.
합성 데이터로 계정/세션 CASCADE, NO ACTION, 중복 동기화 키 거부, 64비트 정수/부동소수점, NULL PK 거부를 확인한다.
pglast가 이미 설치된 환경에서는 추가 PostgreSQL 문법 파서 테스트도 실행하고, 없으면 그 테스트만 명확히 건너뛴다.
이 작업 환경에는 PostgreSQL 서버/CLI와 Docker가 없고 추가 파서 설치도 진행하지 않았다.
따라서 PostgreSQL 엔진에서의 실제 생성·롤백·동시 실행 검사는 아직 통과했다고 볼 수 없다. Neon에는 접속하지 않았다.

이번 실행 결과: 전체 60개 중 59개 통과, 선택적 PostgreSQL 파서 검사 1개 건너뜀.
기존 백엔드 검사 46개와 새 스키마 검사 13개가 통과했다. 외부 PostgreSQL 연결과 AI 호출은 0회다.
Python 3.15.2, 메모리/임시 SQLite 및 모의 연결만 사용했다.

## 실제 Neon 적용 전 확인

1. 팀과 마이그레이션 내용을 검토하고 실제 사용자 데이터 없이 시작한다는 정책을 재확인한다.
2. Neon의 실제 PostgreSQL 버전과 같은 버전의 분리된 로컬/개발 DB에서 파일 전체의 생성·실패 시 롤백·재실행 실패를 검증한다.
3. 대상이 기존 서비스 DB가 아닌 새 전용 DB인지 확인하고 public 스키마 CREATE 권한, 객체 충돌 여부, C 콜레이션과 UTF-8을 확인한다.
4. 자격증명은 서버 환경의 DATABASE_URL로만 관리한다. 실제 URL을 명령줄·문서·Git·브라우저 앱에 붙여 넣거나 출력하지 않는다.
5. 향후 적용 도구는 연결 풀의 세션 상태에 의존하지 않고 파일 전체를 동일 트랜잭션에서 실행하도록 검증한다. 이번 SQL은 SET LOCAL만 사용한다.
6. 스키마 적용과 API 전환은 별도 단계다. 빈 테이블을 만들어도 기존 API는 자동 전환되지 않으며 현재 SQLite 서비스는 계속 그대로 동작한다.
7. API 전환 전에 8개 DB 모듈의 파라미터, Row 접근, upsert, 경합 잠금, 삭제/백업 정책과 계정 격리 회귀 검사를 완료한다.
8. 이 단계에는 실제 데이터 복사나 기존 SQLite 초기화가 필요하지 않다. 기존 SQLite 파일과 백업을 그대로 보존한다.

관련 기존 문서: docs/postgresql-migration-plan.md.

공식 참고:
- PostgreSQL 제약조건: https://www.postgresql.org/docs/current/ddl-constraints.html
- PostgreSQL 숫자 자료형: https://www.postgresql.org/docs/current/datatype-numeric.html
- SQLite 자료형과 PK의 NULL 예외: https://www.sqlite.org/datatype3.html 및 https://www.sqlite.org/lang_createtable.html
- PostgreSQL C 콜레이션: https://www.postgresql.org/docs/current/collation.html
- 선택적 pglast 파서: https://pglast.readthedocs.io/en/latest/parser.html
