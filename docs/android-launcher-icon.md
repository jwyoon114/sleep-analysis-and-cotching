# Android 런처 아이콘 적용

웹앱의 기존 `sleep_frontend/public/icons/app-512.png` 원본을 그대로 사용한다.
Manifest의 일반/원형 앱 아이콘, 기본 비트맵, Android 8+ 적응형 아이콘,
Android 13+ 테마 아이콘을 지정한다. 갤럭시 Android 15는 v33 리소스를 사용한다.

APK를 다시 빌드해야 설치된 앱 아이콘이 바뀐다. 웹사이트 아이콘 변경이나
APK 다운로드 서버 재시작만으로 이미 설치된 APK의 아이콘은 변경되지 않는다.

현재 공개 APK는 `app.daljam.mobile.test`, versionCode 1,
versionName `0.1.0-user-test`이며 저장소 Android 프로젝트의 applicationId와 다르다.
현재 공개 인증서의 SHA-256은 다음과 같다.

`6a7ddef7a465b8ed8e45e617688e40bb0d15292def8c8b201f077998f9a5e7c1`

일반적인 업데이트에는 같은 applicationId와 서명 키가 필요하다.
원래 서명 키를 찾지 못해 사용자가 기존 테스트 앱 삭제 후 재설치 방식을 승인했다.
새 APK는 같은 applicationId, versionCode 2, versionName `0.1.1-icon-test`를 사용한다.
키나 비밀번호는 Git, 채팅, 빌드 로그에 포함하지 않는다.

원본 APK SHA-256은 `9fc36065fb61dff9be62ab958628b4d3215d25987a8d97fec690b47e89c96a38`다.
Apktool 3.0.3의 `decode --no-src`로 원본 실행 코드를 보존한 채 리소스만 해제하고,
`mobile/android/tools/apply-test-apk-icons.py <decoded-directory>`로 아이콘과 버전을 적용했다.
새 키로 서명하기 전후 원본의 classes*.dex 및 assets 전체가 같은지 검사했다.
Android 리소스 컴파일, zipalign, apksigner v3 검증 및 독립 v2 내용 다이제스트 검사를 수행했다.
정식 소스 Gradle 빌드를 수행한 것으로 표현하지 않는다.

새 APK SHA-256: `95d84e979b72d1f150c59c0cdb33a6d70fa63e0adbeba05ab57a64c699eae05e`

새 APK 크기: 9,714,838 bytes.

새 서명 인증서 SHA-256: `55d03d7ed757433cd9c54e34e96c3cce19469ece7640fc28bc38de83dd66f71d`

개인 키는 사용자 홈의 `.android/daljam-test-signing`에 두고 Windows 사용자 및 SYSTEM만
읽도록 권한을 제한했다. 비밀번호는 Windows 사용자 DPAPI로 암호화해 같은 전용 폴더에
보관한다. 이 폴더를 Git에 올리지 않는다. 향후에는 이 새 키를 보존해야 하며, 키 파일과
DPAPI 파일을 다른 PC에 복사하는 것만으로 비밀번호 복구를 보장하지 않는다.

재설치 시 휴대폰 로그인·연결 설정은 초기화되며 건강앱 권한과 전송 동의를 다시 설정한다.
서버 계정과 수면 기록은 유지한다. 이 변경은 API·DB·건강앱 권한을 수정하지 않는다.
실제 갤럭시 설치·아이콘 표시·Health Connect 동기화는 사용자의 기기에서 확인해야 한다.
