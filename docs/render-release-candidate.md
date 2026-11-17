# 달잠 운영 배포 후보 확인 절차

아이콘 수정 PR #3이 포함된 운영 기준 `76d5103` 위에 최종 UI 통합 변경을 검증한다. APK는 아이콘 수정 커밋 `6ed5254`의 0.1.1-icon-test(versionCode 2)를 보존한다. 기존 0.1.0 APK와 서명이 다르므로 기존 설치 사용자는 별도 재설치 안내를 따른다. 검증용 `codex/ui-release-validation` 브랜치는 운영 배포 브랜치가 아니며 이 문서는 배포 완료를 의미하지 않는다. 배포에 사용할 SHA는 최종 CI 및 승인 결과와 함께 확인한다.

## Render 환경 확인

| 항목 | 후보 설정 |
| --- | --- |
| 서비스 | 기존 Render Docker 웹 서비스, `Dockerfile.production` |
| 상태 확인 | `GET /api/ready` |
| DB | `SLEEP_DB_BACKEND=postgresql`, Render 비밀 환경변수 `DATABASE_URL` |
| 웹 | `DALJAM_ENV=production`, `DALJAM_DEMO_ONLY=0`, `DALJAM_PUBLIC_ORIGIN=https://daljam.onrender.com` |
| 코칭·알림 | `COACHING_ENGINE=rules`, `SLEEP_DESKTOP_ALARMS=0` |
| 백업 정책 | `DALJAM_BACKUP_POLICY=render-pitr-3d-v1` — 실제 PITR 3일, Render 논리 export 보관 7일 |
| 런타임 | Render가 주는 `PORT`, supervisor가 설정하는 `SLEEP_API_URL=http://127.0.0.1:8011` |

담당자는 Render Dashboard에서 연결 브랜치·배포 SHA·자동 배포 설정, 실제 웹 서비스와 PostgreSQL의 컴퓨트 플랜, PostgreSQL 주 버전·리전, 워크스페이스 요금제를 확인한다. 저장소 Blueprint는 웹 Starter와 DB Basic 256MB를 명시한다. 실제 계약 플랜은 이 파일로 확인할 수 없다. 온보딩과 계획에는 추가 환경변수가 필요 없으며, rules 모드는 OpenAI 키 없이 동작한다.

유료 PostgreSQL의 시점 복구(PITR) 기간은 워크스페이스 Hobby 3일, Pro 이상 7일이다. 현재 운영 Recovery 화면의 확인값은 **3일**이므로 후보 정책을 이에 맞춘다. 대시보드의 논리 export 보관 7일은 PITR과 별개다. 정책 환경변수는 운영자의 확인 표시이며 공급자 상태를 자동 검증하거나 복구 기간을 늘리지 않는다. 다운로드한 백업과 복원 검증 데이터는 Git/CI에 넣지 않으며 운영자가 접근을 제한하고 원본 백업 생성 시각부터 **최대 7일 이내**에 별도로 폐기한다. 운영 정책 또는 실제 기간이 달라지면 배포를 중단하고 재검토한다. [Render PostgreSQL 복구와 백업](https://render.com/docs/postgresql-backups)

기존 운영 이미지의 정책 값은 7일 계약이므로 **현재 서버를 새 3일 값으로 재시작하지 않는다**. 최종 승인 후 새 코드 배포와 함께 `DALJAM_BACKUP_POLICY` 변경을 적용한다. Dashboard에서는 Save only와 배포 실행을 구분하고, `DATABASE_URL` 등 다른 환경변수는 보존한다. 로컬 render.yaml 수정은 실제 운영 설정을 변경하지 않는다. 이 파일을 새 Blueprint로 적용하거나 중복 서비스를 생성하지 않는다.

## 배포 후보의 Linux 검증

**Release safety rehearsal**은 후보·최종 통합 및 검증용 `codex/ui-release-validation` 브랜치에 Push하면 표준 Ubuntu 24.04 러너에서 실행된다. 공식 PGDG 저장소의 PostgreSQL **18**을 명시적으로 설치하고 루프백·TLS 시험 클러스터만 사용한다. 후보 이미지, 아이콘 PR #3 이후의 운영 이미지, 그 운영 이미지에 새 마이그레이션 카탈로그와 `production_policy.py`·`backup_policy.py`만 포함한 호환 이미지를 검증한다. 기존 이미지 거부 검사는 기존 7일 계약으로 실행해 정책 오류와 스키마 오류를 구분한다. 후보와 호환 이미지 양쪽의 APK를 검증한다.

모든 검사 통과 시 테스트한 후보·호환 이미지 자체를 `docker save`로 저장하고 `images.tar.gz`와 `manifest.json`만 Actions artifact로 남긴다. 운영 DB 덤프·실제 사용자 데이터·실행 컨테이너·DB 볼륨은 포함하지 않는다. manifest는 최종 커밋, 기존 운영 SHA, 이미지 ID, APK 및 tar SHA-256을 연결한다. CI artifact 보관은 **1일**이며, 운영 반영 전 담당자가 다운로드하고 해시를 검증해 별도 보관해야 한다. artifact 만료 전 로컬 보관이 확인되지 않으면 롤백 이미지 확보 완료로 보지 않는다. 이 workflow는 Render 배포·환경변수 수정·패키지 레지스트리 게시를 하지 않는다.

이미지 보관 파일은 Linux Docker 호스트에서 `gzip -dc images.tar.gz | docker load`로 가져올 수 있다. manifest의 `images.rollback.tag`와 `images.rollback.id`를 대조한다. Render의 현재 서비스는 Git 기반이므로 로컬 tar를 Dashboard에 직접 지정할 수 없다. 이를 위해 `deploy/rollback-source.json`에 기록된 별도 복구 브랜치 `codex/rollback-compatible-20261117`와 SHA의 소스를 직접 빌드해 호환 이미지를 검증한다. 현재 운영 `76d5103`에서 새 SQL·manifest·정책 두 모듈만 추가한 복구 소스다. 비상 시에는 승인받아 Render 연결 브랜치를 이 복구 브랜치로 변경하고 기록된 SHA와 정책 값으로 배포한다. 소스 재빌드이므로 보관 이미지와 비트 단위로 같은 이미지가 생성된다고 보장하지는 않는다. 실제 공급자 설정 변경은 이 CI가 수행하지 않는다. 일반 Rollback 버튼으로 구버전 이미지만 되돌리지 않는다.

Linux Docker 호스트에서 실행하려면 Python 가상환경을 만들고 PostgreSQL 서버 및 클라이언트 도구, OpenSSL을 준비한다. 아래 명령에서 `DALJAM_TEST_RELEASE_DOCKER=1`을 빼면 논리 백업·복원과 호환 API만 검증한다.

    python -m pip install -r requirements-server.txt httpx
    export DALJAM_TEST_POSTGRES_BIN="$(pg_config --bindir)"
    DALJAM_TEST_RELEASE_DOCKER=1 python -B -m unittest discover -s tests -p test_release_recovery.py -v

배포 대상 SHA에서 이미지 빌드, `/api/ready`, 온보딩·계획 API, APK 무결성, SIGTERM 종료 코드 0, 재시작 후 데이터 보존, 필수 환경변수 누락 시 종료를 확인한다. 운영 DB와 러너의 PostgreSQL 주 버전이 다르면 운영과 같은 주 버전으로 업그레이드와 복구를 다시 검증한다.

## 운영 DB 백업 및 검증

1. 담당자가 접근을 승인받은 환경에서 배포 직전 기준 시각을 UTC로 기록한다. 쓰기 중단 시간을 정하고 마지막 정상 쓰기 시각도 함께 기록한다.
2. Render Recovery 화면의 **Create export**를 사용하거나 승인된 백업 호스트에서 PostgreSQL 클라이언트로 TLS 논리 백업을 만든다. `pg_dump --format=custom --file=<보호된 경로>`로 백업 파일을 만들 수 있다. 접속 정보는 승인된 비밀 변수나 권한이 제한된 자격 증명 파일로 주입한다. URL·비밀번호를 명령 기록, 스크린샷, GitHub에 남기지 않는다.
3. 백업을 접근 권한이 제한된 암호화 저장소에 보관한다. 크기와 SHA-256을 기록하고 `pg_restore --list`로 목록을 확인한다. 보관과 폐기 일정은 서비스의 데이터 삭제·백업 정책에 맞춘다.
4. 별도 빈 DB에서 `pg_restore --exit-on-error --single-transaction`으로 복원한다. 운영용 원본과 복구 대상의 이름·계정을 먼저 확인한다. 마이그레이션 버전·체크섬, 핵심 테이블 행 수, 대표 데이터의 무결성, 승인된 테스트 계정의 로그인·기록·코칭 조회를 검증한다. 실데이터 복원본의 접근도 운영 DB와 같은 수준으로 제한한다.
5. 백업과 복원 검증을 마친 시각을 기록한다. 백업 이후 쓰기가 생겼다면 복구 시점부터 연결 전환까지의 변경분을 별도로 대조할 절차를 정한다. 과거 백업의 복원 검증만으로 최신 운영 데이터까지 보장하지 않는다. 배포 직전 최종 백업 기준과 점검·쓰기 중단 시간을 승인받는다.

## 배포 순서와 점검

1. 최신 운영 브랜치와 최종 PR의 차이 및 CI 결과를 확인한다. 운영 브랜치가 검증 기준인 `76d5103` 이후 변경됐다면 새 기준에서 통합과 호환 이미지 검증을 다시 진행한다.
2. 운영 DB의 마이그레이션 이력이 `0001_initial_schema.sql`과 `0002_account_consents.sql`인지 확인한다. 이력이 다르면 실제 이력과 같은 격리 DB에서 다시 리허설한다.
3. 백업 검증과 승인된 Linux 및 실기기 검수를 마치고 점검 시간에 지정된 SHA를 배포한다. 기존 인스턴스와 신규 인스턴스의 동시 가동을 전제로 무중단을 약속할 수 없다.
4. `deploy/supervisor.py`는 서버 두 개를 시작하기 전에 기존 버전·체크섬을 검증하고 `0003_account_personalization.sql` → `0004_morning_plans.sql`을 한 트랜잭션에서 적용한다. 실패 시 서버 시작을 중단한다.
5. 배포 직후 상태와 앱을 확인한다.
   - `/api/ready`와 `/api/sleep/health`가 200을 반환하는지 확인한다. readiness는 DB 연결을 포함한다. [Render 상태 확인](https://render.com/docs/health-checks)
   - 승인된 합성 검수 계정으로 로그인·온보딩, `/api/sleep/auth/personalization`, `/api/sleep/alarms`, `/api/sleep/plans`, JSON 가져오기·중복 검증, 코칭 이력과 바텀시트를 확인한다. 비인증 요청은 401이어야 한다.
   - `/downloads/daljam-android.apk`가 200이며 **9,714,838바이트**, SHA-256 `95d84e979b72d1f150c59c0cdb33a6d70fa63e0adbeba05ab57a64c699eae05e`인지 확인한다.
   - Galaxy에서 APK 설치·업데이트, Health Connect 권한, 삼성 헬스 출처, 명시적 동의 후 동기화를 확인한다. iPhone Safari와 홈 화면 웹앱에서 설치 안내, JSON 파일 선택·분석, safe-area와 바텀시트, 이전 서비스 워커의 오프라인 안내 갱신을 확인한다. iPhone은 JSON 수동 가져오기 방식이며 휴대폰 알림은 미지원이다.

## 장애 대응 및 복구 선택

배포 실패 시 UTC 장애 시각과 증상을 기록하고 추가 배포를 보류한다. HTTP 상태, 시작 로그의 오류 종류, 적용된 DB 버전과 체크섬을 확인한다. SQL, 이력 행, 기존 테이블을 보존한다. 복구 도중 추가 쓰기가 유실될 수 있으면 쓰기를 먼저 중단한다.

| 방법 | 예상 중단 범위 | 데이터 영향 | 비용과 검증 |
| --- | --- | --- | --- |
| 이전 기능의 호환 이미지 | 이미지 재배포·기동·검수 시간. 사전 빌드로 단축 가능 | 동일 DB의 0003·0004 데이터 보존. 이전 UI에서는 새 기능 사용이 중단됨 | DB 추가 생성 없음. 실제 운영 기준 코드에 0001–0004 SQL·manifest 및 새 production_policy.py·backup_policy.py를 포함하고 Linux에서 로그인·기록·알람 쓰기 확인 |
| 논리 백업을 별도 DB에 복원 | 빈 DB 준비, 복원, 데이터 대조, 연결 전환 | 백업 이후 쓰기가 복구 대상에 없음. 기존 인스턴스를 보존해 변경분 대조 | 별도 DB 컴퓨트·스토리지 및 백업 보관·전송 비용 가능. 복원과 앱 검증 필요 |
| Render PITR | 별도 인스턴스 프로비저닝과 로그 재생, 검수·전환 | 선택한 시점 이후 쓰기가 복구 대상에 없음. 현재 시각 10분 이내는 복구 시점으로 선택 불가 | 복구 인스턴스의 컴퓨트·스토리지 및 7일 보존을 위한 플랜 비용 가능. 실제 복구 기간·권한과 연결 전환 검증 필요 |

마이그레이션 자체가 실패해 트랜잭션이 롤백됐다면 이력을 확인한 후 원인을 고친다. 0003·0004가 이미 커밋된 경우 구버전 manifest는 더 많은 이력 행을 만나면 무결성 검사를 통과하지 못한다. Render의 서비스 롤백은 DB 복구를 수행하지 않는다. DB가 건강하고 앱에만 문제가 있다면 사전 검증한 호환 이미지 또는 수정 배포를 우선한다. [Render 서비스 롤백](https://render.com/docs/rollbacks)

DB 복구가 필요하면 별도 인스턴스에서 계정·기록·코칭·이력을 검증한 뒤 연결을 전환한다. 원래 인스턴스를 보존해 복구 기준 이후 쓰기를 대조하고 검수 후 쓰기를 재개한다. 운영 중단 시간은 실제 데이터 크기와 검수 시간으로 산정한다. 추가 비용이 드는 복구 인스턴스 생성·요금제 변경·별도 유료 테스트는 담당자의 승인을 받고 진행한다. [Render PostgreSQL 복구와 백업](https://render.com/docs/postgresql-backups) · [Render 요금표](https://render.com/pricing)
