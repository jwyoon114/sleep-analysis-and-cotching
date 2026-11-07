# 달잠 무료 공개 서버 준비

구성: Render Free의 Next.js + FastAPI 한 서버, Neon Free PostgreSQL.
PC를 꺼도 고정 HTTPS 주소로 접속할 수 있지만 무료 한도·절전으로 지연·중단이 가능합니다.
실제 배포 완료 전에는 공개 주소가 생성되지 않습니다.

## 배포 순서

1. Render와 Neon에 무료 가입합니다. 유료 요금제·카드 등록은 진행하지 않습니다.
2. Neon Free 프로젝트에 새 DB를 만듭니다. 기존 PC의 수면 기록을 업로드하지 않습니다.
3. `python cloud_deploy/free/build_bundle.py`로 배포 파일을 만듭니다.
4. `cloud_deploy/artifacts/free-release/`의 세 파일을 GitHub 저장소 루트에 올립니다.
   `render.yaml`, `Dockerfile.cloud`, `daljam-cloud-source.zip`입니다.
5. Render에서 해당 저장소로 Blueprint를 만들고 **Free**인지 확인합니다.
6. Render의 비공개 환경변수 `DATABASE_URL`에 Neon 연결 문자열을 입력합니다.
   `sslmode=require` 이상이 필요합니다. 연결 문자열은 GitHub·채팅에 올리지 않습니다.
7. 빌드 후 발급된 HTTPS 주소에서 회원가입·로그인·예제 파일 분석·기록 조회를 확인합니다.
   서버를 재배포한 뒤에도 예제 기록이 남는지 확인합니다.
8. 휴대폰으로 주소를 열고 Safari/Chrome의 홈 화면 추가 기능을 사용합니다.

## 저장과 기능

- DATABASE_URL이 없거나 DB에 연결하지 못하면 서버 시작을 중단합니다. 임시 SQLite로 저장하지 않습니다.
- 기존 PC 프로그램은 DATABASE_URL 없이 기존 SQLite 파일을 계속 사용합니다.
- 클라우드에는 새 계정으로 가입합니다. 계정별로 기록 접근을 제한합니다.
- 백업은 Neon의 현재 요금제·복구 설정에 따릅니다. 로컬 앱의 30일 백업 정책이 적용되지 않습니다.
- 앱에서 영구 삭제해도 제공자 복구 이력에는 제공자의 정책에 따라 남을 수 있습니다.
- PC 알람 소리는 공개 서버에서 지원하지 않습니다. 휴대폰 네이티브 알람도 아닙니다.
- 건강 기록을 처리하므로 공개 운영 전 개인정보 처리 안내와 실제 운영자의 문의처를 준비해야 합니다.

## AI 코칭

무료 호스팅과 OpenAI API 비용은 별도입니다. 기본 배포에는 API 키를 넣지 않습니다.
키 없이도 파일 분석·그래프·기록 저장은 가능합니다.
API 사용을 원할 때 운영자가 Render의 비공개 `OPENAI_API_KEY`와 `OPENAI_MODEL`을 설정합니다.
앱의 일일 한도는 동시 요청도 DB에서 검사하지만 과금 상한 자체를 보장하지는 않습니다.
운영자가 설정 전 API 결제·할당량을 확인해야 합니다.

## 제한과 검증

Render Free는 유휴 상태에서 절전되고 로컬 파일은 보존되지 않습니다.
Neon Free도 사용 한도와 절전이 있습니다. 지속적인 가용성은 보장되지 않습니다.
Docker 전체 빌드와 실제 PostgreSQL 통합 검증은 해당 환경 연결 후 완료해야 합니다.
실제 수면 기록 대신 동봉된 예제 데이터를 사용합니다.

공식 문서: https://render.com/docs/free · https://neon.com/pricing
