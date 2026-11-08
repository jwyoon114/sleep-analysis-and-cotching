# Daljam 웹앱 개발

이 폴더는 Next.js 웹 화면이며 Python API는 저장소 루트의 api.py입니다.
기존 로그인, 파일 분석, 수면 그래프, 과거 기록, AI 코칭, 비교, 휴지통, PC 알람, PWA와 건강앱 연결 화면을 포함합니다.

## 설치와 검사

프로젝트 루트에서 Python 환경을 준비합니다.

    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements-mobile.txt

이 폴더에서 Node.js가 연결된 PowerShell을 사용합니다.

    npm.cmd ci
    npx.cmd next typegen
    npm.cmd run typecheck
    npm.cmd run build

node_modules, .next, next-env.d.ts는 설치 및 검사 과정에서 재생성합니다.
기존 test:timeline 명령에 대응하는 테스트 파일은 원본 폴더와 PWA ZIP에 없으므로 별도 복원이 필요합니다.

## 실행

이 폴더에서 다음 명령을 실행합니다.

    ..\.venv\Scripts\python.exe -B launch_web.py --backend-project ..

웹은 http://127.0.0.1:3000, Python API는 http://127.0.0.1:8011입니다.
다른 프로젝트가 이 포트를 사용 중이면 먼저 해당 실행을 종료해야 합니다.
웹 서버만 개발 모드로 실행하려면 Python API를 저장소 루트에서 실행한 뒤 여기에서 npm.cmd run dev를 사용합니다.

웹 API는 서버의 SLEEP_API_URL을 사용하며 기본값은 http://127.0.0.1:8011입니다.
브라우저의 /api/sleep/... 요청이 루트 Python API의 같은 경로로 전달됩니다.
건강앱 연결은 /api/sleep/watch/health/connection, 네이티브 기록 전송은 /api/mobile/health-sync를 사용합니다.
API 키나 개인 기록을 웹 소스와 public 폴더에 넣지 않습니다.

## 휴대폰과 건강앱

일반 웹/PWA는 동기화된 기록 조회와 연결 해제를 제공하며, 건강 데이터 읽기는 별도의 Daljam 네이티브 앱이 담당합니다.
네이티브 앱과 연결하려면 접근 가능한 HTTPS 주소가 필요합니다.
휴대폰 공유가 필요한 경우에만 share_phone.py --backend-project ..를 명시적으로 실행합니다.
공유 도구는 tools/download-cloudflared.ps1에서 받고 기존 SHA-256 검증을 거칩니다.
이 소스 통합 작업에서는 외부 공유나 바탕화면 바로가기 설치를 실행하지 않습니다.
