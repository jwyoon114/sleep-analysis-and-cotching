# 나의 수면 리포트

웨어러블 수면 기록을 분석하고 계정별 분석 결과와 AI 코칭을 보관하는 Python 서비스입니다.
현재 사용하는 방식은 **PC를 켜 두고 무료 임시 주소로 공유**하는 방식입니다.

## 포함 기능

- 수면 Markdown 및 지원 형식의 JSON 가져오기와 수면 단계별 요약
- 회원가입·로그인, 계정 편집·삭제
- 과거 분석·AI 코칭 조회, 휴지통·복원·영구 삭제
- 7일·30일 기간 비교, SQLite 백업 관리
- Windows 실행기와 Cloudflare 임시 HTTPS 공유 도구
- FastAPI 서버와 Flutter 모바일 앱 소스

## 구성

| 폴더 | 내용 |
| --- | --- |
| `mobile_backend` | 분석·계정·저장·코칭·API·테스트 |
| `streamlit_clock_update` | 현재 웹 화면 및 기존 시간 표시 관련 도구 |
| `desktop_launcher` | Windows 실행기 |
| `free_share` | 현재 선택한 무료 인터넷 공유 |
| `mobile_flutter` | 모바일 앱 소스와 프로젝트 생성 안내 |
| `cloud_deploy` | 선택 사항인 유료 호스팅 구성. 실행만으로 서버를 생성하지 않음 |
| `github_upload` | 개인정보를 제외한 소스 ZIP 생성 도구 |

## 다른 PC에서 실행

Python을 설치한 뒤 다음 파일들을 하나의 새 폴더로 복사합니다.

1. `mobile_backend`의 `api.py`, `health_records.py`, `json_sleep.py`, `export_times.py`, `health_export_kit.py`, `sleep_accounts.py`, `coaching_service.py`, `service_limits.py`, `history_service.py`, `backup_policy.py`, `requirements-mobile.txt`
2. `streamlit_clock_update`의 `app.py`, `apple_watch_ui.py`
3. Windows 실행기 사용 시 `desktop_launcher/launch_sleep_app.py`

해당 폴더에서 실행합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-mobile.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

새 PC에는 새 DB가 만들어집니다. 기존 계정·기록은 소스에 포함하지 않습니다.
AI 코칭에는 서버의 `OPENAI_API_KEY` 환경변수 또는 `.streamlit/secrets.toml` 설정이 필요하며 API 사용료가 별도로 발생합니다.
키 없이도 수면 기록 분석과 저장 기능을 사용할 수 있습니다.

무료 공유는 [안내](free_share/README.md)를 참고하세요. 설치 도구의 `-ProjectPath`에는 위 새 앱 폴더를 지정합니다.
공유 주소는 재연결할 때 바뀌며 PC 종료·절전 시 접속이 끊어집니다.

세부 기능은 [서버 안내](mobile_backend/README.md), 지원 입력은 [JSON 형식](mobile_backend/JSON_FORMAT.md), 모바일 빌드는 [Flutter 안내](mobile_flutter/README.md)를 참고하세요.
Flutter 소스는 실행 파일/APK로 빌드된 상태가 아닙니다. 일부 배포·검증 도구의 기본 경로는 기존 개발 PC를 기준으로 하므로 다른 PC에서는 경로를 변경해야 합니다.

## 소스 보관

API 키, 비밀번호 설정, 계정·수면 DB, 실제 건강 파일, 백업, 로그, 가상환경, 다운로드한 실행 파일은 업로드 대상이 아닙니다.
Cloudflare 실행 파일은 설치 도구로 공식 배포처에서 내려받습니다.
실제 데이터의 백업은 이 저장소와 별도로 관리하세요.

소스 ZIP 생성:

```powershell
python github_upload/build_source.py
```
