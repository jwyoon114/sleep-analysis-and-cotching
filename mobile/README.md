# 달잠 건강앱 자동 연결

기존 웹 화면을 휴대폰 앱 안에서 열고, 휴대폰이 허용한 수면 데이터만 읽어 서버에 전송합니다. 별도의 내보내기 앱이나 파일 업로드는 필요하지 않습니다.

## 사용자 흐름
1. 달잠 안드로이드 또는 아이폰 앱을 설치합니다.
2. 첫 실행 때 달잠 서버의 HTTPS 주소를 입력하고 기존 계정으로 로그인합니다.
3. 대시보드의 '건강앱 자동 연결'에서 수면 읽기 권한을 허용하고 기록 출처 하나를 선택합니다.
4. 이후 앱을 열면 자동 동기화합니다. 운영체제와 권한이 허용하면 백그라운드에서도 확인합니다.
5. AI 조언 자동 생성을 켜면 새 기록이 들어왔을 때 가장 최신 기록의 조언을 생성합니다. 서버 API 키와 사용 한도가 필요합니다.

## 서버 준비
기존 설치는 변경된 웹 화면을 다시 빌드하고 앱을 재실행해야 합니다. Python 의존성을 추가하지 않았습니다.

- 웹 준비는 ../sleep_frontend/README.md를 따릅니다. 웹을 빌드한 뒤 sleep_frontend 폴더에서 ..\.venv\Scripts\python.exe -B launch_web.py --backend-project ..로 루트 Python API와 웹을 실행합니다. 현재 저장소에는 START.cmd가 없습니다.
- 휴대폰 공유 도구의 임시 HTTPS 주소로 개발 확인할 수 있습니다. 주소가 바뀌면 앱의 '서버 변경'으로 다시 연결해야 합니다.
- 지속적인 사용에는 고정 HTTPS 주소와 켜져 있는 서버가 필요합니다. PC가 꺼지면 동기화와 AI 조언이 지연됩니다.
- 건강앱 연결 키는 180일 유효하며 연결 해제·재연결·계정 정보 변경·계정 삭제 시 기존 키가 무효화됩니다. 만료 시 다시 연결합니다.
- 기존 웹 로그인 유효기간은 24시간입니다. 웹 로그인이 만료되어도 휴대폰의 연결 키가 유효하면 백그라운드 기록 동기화는 계속됩니다. 리포트를 보려면 다시 로그인할 수 있습니다.

## 안드로이드 앱 빌드
1. Android Studio와 Android SDK 36을 설치합니다. JDK 17 이상이 필요합니다.
2. 이 폴더의 android를 Android Studio에서 엽니다.
3. SDK 위치를 안내에 따라 지정하거나 android/local.properties의 sdk.dir에 설정합니다.
4. Windows에서 android/BUILD_ANDROID.cmd를 실행합니다. 공식 Gradle 배포본과 SHA-256을 확인해 빌드합니다.
5. 생성된 android/app/build/outputs/apk/debug/app-debug.apk를 테스트 휴대폰에 설치합니다.
6. 삼성헬스 설정에서 Health Connect로 수면 데이터를 공유하도록 허용하고, 달잠에도 수면 읽기를 허용합니다.
Android 9 이상 및 지원되는 Health Connect가 필요합니다. Android 13 이하에서는 Health Connect 설치가 필요할 수 있고, 백그라운드 읽기를 지원하지 않는 기기에서는 앱을 열 때 가져옵니다.

## Mac이 없는 경우

`CLOUD_BUILD.md`의 수동 클라우드 빌드 설정을 사용할 수 있습니다. 아이폰 시뮬레이터 코드 확인과 실제 아이폰 설치는 서로 다른 단계이며, TestFlight 배포에는 Apple 개발자 등록과 서명이 필요합니다. 현재 클라우드 작업을 실행하거나 외부에 소스를 업로드하지 않았습니다.

## 아이폰 앱 빌드
Mac, Xcode, 실제 아이폰, HealthKit 사용이 가능한 서명 설정이 필요합니다. Windows에서 아이폰 설치 파일을 빌드할 수 없습니다.
1. mobile/ios 폴더를 Mac으로 복사합니다.
2. XcodeGen을 설치한 뒤 ios 폴더에서 xcodegen generate를 실행합니다.
3. 생성된 Daljam.xcodeproj를 Xcode에서 열고 Signing & Capabilities에서 팀과 실제 사용할 Bundle Identifier를 설정합니다.
4. HealthKit 및 HealthKit Background Delivery 권한을 확인하고 실제 아이폰에서 빌드·실행합니다.
5. 건강앱의 수면 읽기를 허용합니다. 실제 수면 데이터가 있어야 출처가 표시됩니다.

## 데이터 처리
- 최초 및 이후 동기화에서 접근 가능한 최근 30일 수면 기록을 가져옵니다. 운영체제의 기록 접근 범위 제한을 따릅니다.
- 출처 하나를 선택해 여러 앱이 같은 수면을 기록한 경우의 중복 합산을 줄입니다.
- 폭넓은 '수면' 표본과 세부 수면 단계가 겹치면 세부 단계가 우선하며 같은 시간을 두 번 세지 않습니다.
- 현지 정오부터 다음 정오까지 한 수면 기록으로 묶습니다. 낮잠이 같은 묶음에 포함될 수 있으며, 사이의 빈 구간은 미기록으로 처리합니다.
- 수면 단계가 없는 Health Connect 세션과 Apple의 '침대에 있음' 표본을 실제 수면으로 가정하지 않습니다.
- 같은 날의 수정 데이터는 기존 자동 분석을 갱신합니다. 기존 AI 조언은 생성 당시 기록을 기준으로 하며 수정 후 다시 생성할 수 있습니다.
- 달잠에서 삭제한 기록은 자동으로 복원하지 않습니다. Health Connect 원본에서 사라진 기록은 완전한 비어 있지 않은 스냅샷에서 확인된 경우 휴지통으로 이동합니다. Apple 건강은 제한된 읽기 권한과 원본 삭제를 구분할 수 없어 원본의 삭제를 자동 반영하지 않습니다. 달잠에서 기록을 별도로 삭제할 수 있습니다.
- 읽기 권한 거부와 기록 없음이 구분되지 않는 경우가 있어 빈 조회 결과로 기존 기록을 삭제하지 않습니다.
- 전송 실패 시 연결 키만 기기의 Keychain/Android Keystore에 보관하고 다음 실행 또는 백그라운드 작업에서 다시 읽어 보냅니다. 원본 건강 파일을 기기에 별도 저장하지 않습니다.
- 연결 키는 서버에 해시로 저장하고 건강앱 동기화에만 허용합니다. HTTPS와 지정된 서버 출처에서만 네이티브 연결을 허용합니다.
- 일반 웹 브라우저/PWA에서는 휴대폰 건강 데이터를 직접 읽지 않습니다.

## 확인 범위
현재 저장소의 루트 Python API 및 sleep_frontend 네이티브 브리지와 호환되는 경로와 메시지를 정적으로 확인합니다.
이번 통합에서 기존 JDK 21, Android SDK 36, Gradle 8.11.1과 캐시를 사용해 :app:assembleDebug 오프라인 빌드가 성공했습니다(33개 작업).
생성 APK의 서명과 minSdk 28/targetSdk 36 및 수면 읽기 권한을 확인했습니다. 테스트용 디버그 APK이며 배포용 서명은 구성하지 않았습니다.
Android/iOS 브리지 JavaScript의 5개 메서드 요청·응답과 오류 처리 검사도 통과했습니다. 실제 휴대폰 건강 데이터를 읽는 검사는 아닙니다.
iOS는 Windows에서 Info.plist, HealthKit 권한, XcodeGen 설정과 리소스 경로만 정적으로 확인하며 Swift/Xcode 빌드 성공을 의미하지 않습니다.
실제 휴대폰에서의 권한 요청·수면 읽기·백그라운드 전송은 별도 확인이 필요합니다.

## 프로젝트 생성과 서명
Android Gradle 설정과 BUILD_ANDROID.cmd는 원본을 유지했습니다. Gradle wrapper 파일은 원본에 없으며 빌드 스크립트가 공식 Gradle을 준비한 뒤 생성합니다.
iOS에는 project.yml이 있으며 Mac에서 xcodegen generate로 실제 Daljam.xcodeproj를 생성합니다. 생성된 프로젝트를 가짜 파일로 대체하지 않습니다.
개발 팀, 실제 앱 식별자 등록, 배포용 인증서·프로비저닝·릴리스 서명 및 스토어용 앱 아이콘 구성은 원본에 포함되지 않았습니다.
이 통합에서는 개인 인증서나 기존 서명 키를 복사하지 않습니다.
수동 클라우드 빌드용 .github/workflows/mobile-build.yml을 함께 포함하며, 외부 업로드나 클라우드 실행은 수행하지 않습니다.

공식 참고:
- https://developer.samsung.com/health/blog/en/accessing-samsung-health-data-through-health-connect
- https://developer.android.com/health-and-fitness/health-connect/read-data
- https://developer.apple.com/documentation/healthkit/authorizing-access-to-health-data
