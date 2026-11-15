# 달잠 운영 배포 후보 확인 절차

운영 기준 `9bc1d25`에서 기능 선행 커밋을 모두 포함하는 `f202117`을 반영하고, APK PR #2의 `e2c5ebf`를 별도 worktree에서 통합했다. 실제 배포에 사용할 SHA는 이 문서가 포함된 검증 브랜치의 최종 커밋으로 확인한다. 운영 담당자는 PR #2와 기능 변경이 최종 트리에 각각 한 번만 포함되었는지 검토한다.

## 환경 확인

| 항목 | 후보 설정 |
| --- | --- |
| 서비스 | 기존 Render Docker 웹 서비스, `Dockerfile.production` |
| 상태 확인 | `GET /api/ready` |
| DB | `SLEEP_DB_BACKEND=postgresql`, Render 비밀 환경변수로 관리하는 `DATABASE_URL` |
| 웹 | `DALJAM_ENV=production`, `DALJAM_DEMO_ONLY=0`, `DALJAM_PUBLIC_ORIGIN=https://daljam.onrender.com` |
| 코칭·알림 | `COACHING_ENGINE=rules`, `SLEEP_DESKTOP_ALARMS=0` |
| 백업 정책 | `DALJAM_BACKUP_POLICY=render-pitr-7d-v1`은 실제 복구 기간이 정책과 일치하는지 먼저 확인 |
| 런타임 | Render가 주는 `PORT`와 supervisor가 구성하는 루프백 API 주소 `http://127.0.0.1:8011` |

온보딩과 계획에는 추가 환경변수가 필요 없다. `rules` 모드에는 OpenAI 키가 필요 없다. `DATABASE_URL`의 실제 값과 계정·건강 데이터는 커밋, 명령 출력과 검수 자료에서 제외한다.

Render PITR 문서상 복구 기간은 작업공간 요금제에 따라 Hobby 3일 또는 Pro 이상 7일이다. 서비스와 DB가 유료라는 정보만으로 실제 복구 기간을 확인할 수 없다. 운영 담당자가 Recovery 화면에서 복구 가능 기간과 기점을 확인한다. [Render PostgreSQL 복구와 백업](https://render.com/docs/postgresql-backups)

## 배포 전 준비 및 순서

1. 운영 브랜치와 PR #2 상태를 다시 조회하고 서버 담당자의 승인으로 통합 순서를 확정한다. 자동 배포 설정과 운영 브랜치 연결을 확인한다.
2. 운영 DB의 마이그레이션 버전·체크섬을 비밀 연결 정보 없이 확인한다. 기대 이전 버전은 `0001_initial_schema.sql`, `0002_account_consents.sql`이다. 적용 이력이 다르면 격리 복사본에서 실제 이력에 맞춰 다시 리허설한다.
3. 배포 직전 복구 기준 시각을 기록하고, 정책에 맞는 접근 통제된 백업과 복구 검증을 완료한다. 아래 복구 절차를 검토하고 쓰기 중단 시간과 복구 여부를 결정할 담당자를 정한다.
4. 배포 후보의 Linux 컨테이너 빌드와 실제 기기 테스트를 마친 뒤 운영 담당자가 승인된 SHA를 수동 배포한다. 기존 컨테이너는 DB에 자신보다 새 버전이 있으면 DB 연결을 거부한다. 기존 프로세스와 신규 프로세스의 동시 가동을 전제로 무중단이라고 판단하지 말고 점검 시간을 잡는다.
5. `deploy/supervisor.py`가 API와 Next.js를 시작하기 전에 실행한다. 기대 적용 순서는 `0003_account_personalization.sql` → `0004_morning_plans.sql`이다. 기존 버전·체크섬을 검증하고, 추가 마이그레이션을 한 트랜잭션에서 적용하며, 실패한 경우 서버 시작을 중단한다.
6. 헤더와 본문에 비밀이 없는지 보면서 배포 직후 확인한다.
   - `/api/ready`와 `/api/sleep/health`의 200 응답. HTTP 준비 검사는 DB 연결을 포함한다. [Render 상태 확인](https://render.com/docs/health-checks)
   - 합성 검수 계정으로 로그인·온보딩 완료 상태와 `/api/sleep/auth/personalization`, `/api/sleep/alarms`, `/api/sleep/plans` 확인. 인증 없는 요청은 401.
   - 합성 JSON의 첫 분석 및 재업로드 중복 확인, 기록과 코칭 이력, 오늘·다음 기상일 계획과 바텀시트 확인.
   - `/downloads/daljam-android.apk` 200, 9,678,311바이트와 SHA-256 `9fc36065fb61dff9be62ab958628b4d3215d25987a8d97fec690b47e89c96a38`. 기존 PWA 설치 사용자의 오프라인 안내 갱신 확인.
   - 실제 Galaxy에서 APK 설치 및 업데이트, Health Connect 권한과 삼성 헬스 출처, 명시적 동의 후 동기화. 실제 iPhone Safari 및 홈 화면 웹앱에서 설치 안내, JSON 파일 선택·분석, safe-area 및 바텀시트 조작. 웹앱의 iPhone 사용 방식은 JSON 수동 가져오기이며 모바일 알림은 미지원이다.

## 복구

- 마이그레이션 실패로 트랜잭션이 롤백됐으면 DB 이력과 변경 여부를 먼저 확인하고 원인을 고친다. SQL이나 이력 행을 수동으로 삭제해 시작 조건을 맞추지 않는다.
- `0003`·`0004` 커밋 후에는 이전 이미지가 새 DB 이력을 거부한다. 앱만 롤백해야 하면 기존 코드와 최신 manifest를 포함한 복구 이미지를 격리 DB에서 먼저 검증하거나 수정 배포를 준비한다. Render의 서비스 롤백은 DB 복구를 수행하지 않는다. [Render 서비스 롤백](https://render.com/docs/rollbacks)
- DB 복구가 필요하면 Render에서 배포 전 시점으로 별도 인스턴스를 복구한다. 계정, 기록, 코칭, 마이그레이션 이력과 승인된 서비스 설정을 확인한 후 운영 담당자가 연결을 전환한다. 배포 후 접수된 쓰기가 있다면 원래 인스턴스를 보존하고 누락 가능 데이터를 검토한다. [Render PostgreSQL 복구와 백업](https://render.com/docs/postgresql-backups)
