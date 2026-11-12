# PostgreSQL 전환 준비 — 연결 기반 단계

## 이번 단계의 경계

기준: feature/cloud-deployment, 기준 커밋 023cbc9.
기존 SQLite 서비스를 실행하는 주요 DB 모듈 8개와 그 호출부는 수정하지 않는다.
postgres_db.py는 명시적으로 호출할 때만 DATABASE_URL을 읽는다. 모듈 import는 연결을 만들지 않는다.
DATABASE_URL을 설정해도 기존 API는 계속 health_records.connect()와 SQLite를 사용한다.
이는 PostgreSQL 연결 실패 후 SQLite로 전환하는 fallback이 아니라, 두 경로를 의도적으로 분리한 상태다.

이번 단계에는 외부 DB 접속, 테이블 생성, SQL 실행, 데이터 복사, 마이그레이션 적용, API 연결 전환이 없다.
연결 드라이버의 connect 호출은 단위 테스트에서 모두 모의 객체로 대체한다.

## 선택적 의존성과 연결 계약

requirements-mobile.txt는 기존 SQLite/데스크톱 환경용으로 그대로 유지한다.
PostgreSQL 준비를 사용할 환경에만 requirements-postgres.txt를 추가 설치한다.
검증한 선택적 드라이버는 Psycopg 3.3.8의 binary 배포본이다.

    python -m pip install -r requirements-postgres.txt

DATABASE_URL은 환경변수 관리 기능에서 제공한다. 실제 URL이나 키를 소스·문서·로그·모바일 앱에 넣지 않는다.
Git에 실제 .env 파일이나 인증서를 추가하지 않는다.
별도의 설정 객체 repr에는 접속 대상과 계정·비밀번호가 나타나지 않도록 했다.
설정 객체의 내부 속성을 직접 덤프하거나 원본 드라이버 예외를 기록하지 않는다.

connect_postgres()는 단일 TCP 호스트·계정·DB 이름이 명시된 PostgreSQL URL만 허용한다.
누락된 접속 대상, libpq service, hostaddr, Unix socket, 복수 호스트 설정은 거부한다.
환경의 PGSERVICE/PGHOSTADDR도 대상 선택을 우회할 수 있으므로 값이 있으면 연결 전에 거부한다.
포트는 명시된 값 또는 5432로 고정하여 주변 PGPORT 값에 따라 바뀌지 않게 한다.
TLS는 require/verify-ca/verify-full만 허용하며 기본값은 require다.
Neon URL의 channel_binding 같은 추가 보안 옵션은 유지한다.
연결 대기 시간은 함수 인자로 1~60초 범위에서 지정하며 기본값은 10초다.
URL 안의 connect_timeout보다 이 함수 인자가 우선한다.

성공하면 autocommit=False인 Psycopg 연결을 반환한다.
조회 행은 dict_row이며 기존 sqlite3.Row의 숫자 인덱스와 호환되지 않는다.
연결·트랜잭션의 종료는 호출자가 관리한다. Psycopg의 연결 컨텍스트는 정상 종료 시 commit,
예외 시 rollback 후 close하는 방식이므로 다음 전환 단계에서 실제 서비스와 맞춰 검증해야 한다.

실제 DB가 준비된 다음 단계에서만 명시적으로 연결 함수를 호출한다.
현재 API에는 이 함수를 연결하지 않는다.
설정·드라이버·접속 실패는 각각 PostgresConfigurationError,
PostgresDriverUnavailable, PostgresConnectionError로 구분한다.
실패 시 재시도, 다른 DB 선택, SQLite 파일 생성, 데이터 삭제는 수행하지 않는다.
드라이버의 원본 오류는 일반 traceback에 노출하지 않는다.

## 현재 SQLite 스키마 — 20개 테이블

다음 목록은 실제 사용자 DB를 열어 확인한 것이 아니라 현재 소스의 테이블 정의를 기준으로 한다.

| 소유 모듈 | 테이블 |
|---|---|
| health_records.py | imports, sessions, import_sessions, stages, samples, accounts, auth_tokens, login_attempts, coaching, trash_sessions, trash_coaching, coaching_context, permanent_deletions, session_created, coaching_requests |
| health_sync.py | health_connections, health_sync_sessions, health_advice_jobs |
| sleep_alarms.py | sleep_alarm_settings, sleep_alarm_fires |

health_records.py의 PRAGMA user_version은 기본 스키마만 관리한다.
건강앱·알람 테이블은 각 모듈이 필요할 때 생성한다.
PostgreSQL에서는 이 동작을 그대로 요청마다 반복하지 말고 명시적 스키마 마이그레이션으로 통합해야 한다.

## 파일별 다음 수정 범위

| 파일 | 현재 SQLite 전용 동작 | PostgreSQL 전환 시 필요한 결정과 검증 |
|---|---|---|
| health_records.py | sqlite3.connect/Row, PRAGMA foreign_keys/user_version, executescript, ?, INSERT OR IGNORE, sqlite_master 조회 | 공통 연결·스키마 마이그레이션, 파라미터 방식과 행 반환 형식, ON CONFLICT DO NOTHING, FK·인덱스·기록 중복 방지 검증. 현재 API의 함수 시그니처와 JSON 응답을 유지할 것 |
| health_sync.py | 연결마다 CREATE/ALTER, PRAGMA table_info, BEGIN IMMEDIATE, INSERT OR REPLACE/IGNORE, rowcount | 테이블 변경을 마이그레이션으로 이동. 계정별 스냅샷·연결 키 회수를 트랜잭션에서 잠금. 연결 교체 시 last_window_end/last_synced_at/advice_status 등 이전 상태 초기화 의미 보존. 중복 기록·원본 삭제·삭제 기록 부활 방지 검사 |
| sleep_accounts.py | ?, BEGIN IMMEDIATE, sqlite_master, PRAGMA secure_delete | 인증·계정 수정/삭제 트랜잭션과 실패 시도 기록을 보존. 사용자명 고유성과 토큰 회수·건강앱 연결 삭제 검증. 기존 해시·salt·계정 ID를 임의 변환하지 않을 것 |
| history_service.py | sqlite_master, PRAGMA secure_delete, BEGIN IMMEDIATE, INSERT OR REPLACE, ? | 삭제 원장 upsert와 FK 삭제 순서, 휴지통 복구·만료의 소유권 검사 및 원자성 보존 |
| coaching_service.py | ?, 동적 IN 자리표시자, INSERT OR IGNORE, BEGIN IMMEDIATE | 조언 저장 전 모든 참조 기록이 활성 상태인지 검사하는 경합 보호. API 호출 중 트랜잭션을 장시간 잡지 않으면서 삭제된 기록에 조언을 저장하지 않는 동작 검증 |
| service_limits.py | BEGIN IMMEDIATE로 요청 집계·삽입을 직렬화 | 단순 BEGIN으로 교체하면 한도 경합이 생길 수 있음. 전체/계정별 제한에 맞는 행 잠금 또는 트랜잭션 범위 잠금·원자적 카운터 설계 |
| sleep_alarms.py | executescript, ?, BEGIN IMMEDIATE, INSERT OR IGNORE, enabled=1 | 설정 테이블과 중복 실행 방지 키를 이전. ON CONFLICT 구문 중 유지 가능한 부분과 파라미터·행 조회를 분리 검토. 클라우드에서는 Windows 알람을 계속 비활성화 |
| backup_policy.py | 로컬 .bak 파일, SQLite backup(), sqlite_master, PRAGMA, total_changes, VACUUM, 파일 삭제/mtime | 현재 모듈에 PostgreSQL 연결을 그대로 넘기지 말 것. Neon 복구 또는 별도 pg_dump/보관 정책으로 재설계. 삭제 원장을 백업에 전파하던 의미와 복원 후 삭제 정책을 별도로 검증 |

## SQL·자료형 차이

- 물음표 파라미터는 Psycopg에서는 그대로 사용할 수 없다. 바인딩 파라미터로 변경하고 문자열 보간으로 대체하지 않는다.
- INSERT OR IGNORE는 고유 키와 ON CONFLICT DO NOTHING의 의미를 테이블별로 정해야 한다.
- INSERT OR REPLACE는 SQLite에서 삭제 후 삽입할 수 있다. PostgreSQL upsert와 동일하다고 가정하지 말고 초기화·FK 동작을 검사한다.
- BEGIN IMMEDIATE의 DB 전체 쓰기 직렬화는 PostgreSQL의 일반 BEGIN과 다르다.
- sqlite3.Row는 이름과 숫자 인덱스를 모두 지원하지만 새 dict_row는 이름 기반이다. fetchone()[0]와 row["name"]이 혼재한 호출부를 모두 검토한다.
- PRAGMA, sqlite_master, executescript는 SQLite 인터페이스다. PostgreSQL 정보 스키마와 명시적 마이그레이션으로 대체해야 한다.
- 현재 ID·시각·JSON 대부분은 TEXT다. ID를 일괄 UUID로 바꾸면 기존 비UUID 식별자와 테스트가 깨질 수 있다.
- 시각을 TIMESTAMPTZ로 바꾸면 datetime 반환을 기존 ISO 문자열 API에 맞게 직렬화해야 한다.
- JSON을 JSONB로 바꾸면 드라이버가 dict/list를 반환할 수 있으므로 기존 json.loads와 응답 생성 코드를 조정해야 한다.
- auto_coach/enabled는 INTEGER 기반이다. BOOLEAN 전환 시 enabled=1 등의 조건과 저장 값을 함께 수정한다.
- REAL의 정밀도, PK/UNIQUE/FK, ON DELETE CASCADE 및 인덱스를 명시적으로 비교한다.
- PostgreSQL은 SQLite보다 자료형을 엄격히 검사한다. 누락·중복·잘못된 시간대와 기존 데이터의 제약 위반을 이관 전에 확인한다.
- PRAGMA secure_delete와 PostgreSQL VACUUM은 같은 보안 삭제 기능이 아니다. 복구 기록과 보관 기간을 포함해 삭제 정책을 다시 정의한다.

## 연결을 기존 서비스에 적용하기 전 통과해야 할 검증

1. 마이그레이션으로 빈 PostgreSQL DB에 20개 테이블·제약·인덱스 생성.
2. 소유자별 기록 격리, 기존 로그인, 키 회수·만료, 계정 삭제 회귀 검사.
3. 동시에 들어온 동기화·수정·삭제·AI 한도 요청의 중복/경합 검사.
4. 서버·DB 재시작과 절전 후 연결 실패·복구 검사. 자동으로 SQLite에 저장하지 않을 것.
5. 기존 HTTP·JSON 응답과 웹·Android·iOS 계약 유지.
6. 데이터 이관은 실제 계정·DB가 준비된 뒤 별도 승인 범위에서 수행. 원본 SQLite와 사용자 데이터는 Git에 넣지 않을 것.

## 이번 단계의 테스트 범위

테스트는 합성 DATABASE_URL, 모의 psycopg.connect, 임시 SQLite DB만 사용한다.
새 드라이버가 없으면 드라이버 의존 테스트는 건너뛰며 기존 SQLite 테스트 실행을 막지 않는다.
기존 27개 건강앱 테스트와 새 연결·설정·비밀값 비노출·SQLite 격리 테스트를 함께 실행한다.
실제 Neon 접속, TLS 협상, PostgreSQL 쿼리/마이그레이션의 정상 동작을 검증한 결과는 아니다.

이번 실행 결과: 기존 건강앱/계정 테스트 27개와 신규 PostgreSQL 기반/SQLite 격리 테스트 19개,
총 46개가 모두 통과했다. 테스트 환경은 Windows, Python 3.15.2, Psycopg 3.3.8이다.
실제 PostgreSQL·Neon 연결 및 외부 AI 호출은 차단한 상태로 확인했다.


공식 참고:
- https://www.psycopg.org/psycopg3/docs/basic/install.html
- https://www.psycopg.org/psycopg3/docs/api/connections.html
- https://www.psycopg.org/psycopg3/docs/api/conninfo.html
- https://neon.com/docs/connect/connection-pooling
