# Python 프로그램 실행 안내

저장소 루트의 `.py` 파일은 현재 사용하는 웨어러블 수면 분석·AI 코칭 프로그램입니다.
최근 추가한 분석 직후 시간별 수면 단계 그래프와 과거 기록 그래프가 포함되어 있습니다.
이 파일들과 `requirements-mobile.txt`를 같은 폴더에 두고 실행하세요.

## 설치 및 실행 (Windows, Python 3.11 이상)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-mobile.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

브라우저에 표시되는 주소로 접속하면 회원가입 후 사용할 수 있습니다.
새 PC에는 새 데이터베이스가 생성됩니다.
계정, 비밀번호, 실제 수면 기록, API 키는 소스에 포함하지 않습니다.
AI 코칭을 사용하려면 자신의 `OPENAI_API_KEY`를 서버 환경변수로 설정하세요.
AI 코칭에는 별도 API 사용료가 발생하며, 키 없이도 기록 분석과 저장은 가능합니다.

## 주요 파일

- `app.py`: 프로그램 시작
- `apple_watch_ui.py`: 분석·그래프·기록·계정 화면
- `health_records.py`, `json_sleep.py`: 기록 분석 및 저장
- `sleep_accounts.py`: 회원가입·로그인·계정 관리
- `coaching_service.py`: AI 코칭
- `history_service.py`, `backup_policy.py`: 기록·휴지통·백업 관리
- `api.py`: 모바일 및 웹 프론트엔드용 API
- `launch_sleep_app.py`, `share_sleep_app.py`: Windows 실행·무료 공유 도구

기존 ZIP은 이전 스냅샷입니다. 최신 Python 프로그램은 루트의 소스 파일을 사용하세요.
Next.js 프론트엔드와 Flutter 앱은 별도 프로젝트이며 이 Python 실행 절차에 필요하지 않습니다.
