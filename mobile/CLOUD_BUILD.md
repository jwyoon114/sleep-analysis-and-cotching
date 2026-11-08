# Mac 없이 휴대폰 앱 빌드하기

이 설정은 GitHub Actions의 안드로이드·Mac 환경에서 실행하는 수동 빌드 작업입니다. 로컬에 파일을 추가한 것만으로 외부 업로드나 빌드가 시작되지는 않습니다.

## 준비한 범위
- 갤럭시: 테스트용 APK 생성 작업
- 아이폰: 시뮬레이터용 앱을 컴파일해 소스 오류를 확인하는 작업
- 아이폰 실기기 설치와 TestFlight 배포: Apple 서명 설정을 추가해야 하며 현재 작업에 포함되어 있지 않습니다.

## 사용 방법
1. 현재 저장소에서 mobile 폴더와 .github/workflows/mobile-build.yml을 함께 관리합니다.
2. 모바일 소스 패키지의 mobile 폴더와 .github 폴더를 저장소에 올립니다. 루트 data, backend/data, .venv, .runtime, .env, API 키 또는 실제 건강 기록은 올리지 않습니다.
3. GitHub Actions에서 Daljam mobile build를 선택하고 Run workflow로 실행합니다.
4. android 또는 both로 실행한 경우 성공한 작업의 Artifacts에서 테스트용 APK를 내려받습니다.
5. ios 작업은 Mac이 없어도 Swift 코드를 컴파일할 수 있게 하지만, 생성 결과는 아이폰에 설치하는 파일이 아닙니다.

## 아이폰 실기기 설치
TestFlight로 배포하려면 Apple Developer Program 계정과 App Store Connect 앱 등록, 앱 식별자·HealthKit 권한·인증서·프로비저닝 프로파일 등 서명 구성이 필요합니다.
이 정보를 사용해 Mac 클라우드 작업에서 기기용 빌드와 TestFlight 업로드를 설정할 수 있습니다. 개발자 계정의 비밀번호나 인증서 개인 키를 채팅 또는 소스 파일에 넣지 않습니다. 빌드 서비스의 비밀값 보관 기능을 사용합니다.
현재 어떤 GitHub 저장소에도 코드를 올리거나 클라우드 작업을 실행하지 않았습니다.

공식 참고:
- https://docs.github.com/en/actions/concepts/runners/github-hosted-runners
- https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds
