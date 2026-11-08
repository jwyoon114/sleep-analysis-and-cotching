$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $env:JAVA_HOME -and (Test-Path 'C:\Program Files\Android\Android Studio\jbr')) { $env:JAVA_HOME = 'C:\Program Files\Android\Android Studio\jbr' }
if (-not $env:JAVA_HOME) { throw 'Install Android Studio with SDK 36. Set JAVA_HOME to its jbr folder or JDK 17+.' }
$env:Path = (Join-Path $env:JAVA_HOME 'bin') + ';' + $env:Path
$version = '8.11.1'
$tools = Join-Path $PSScriptRoot '.tools'
$gradle = Join-Path $tools "gradle-$version\bin\gradle.bat"
if (-not (Test-Path -LiteralPath $gradle)) {
 New-Item -ItemType Directory -Path $tools -Force | Out-Null
 $zip = Join-Path $tools "gradle-$version-bin.zip"
 Invoke-WebRequest "https://services.gradle.org/distributions/gradle-$version-bin.zip" -OutFile $zip
 $expected = (Invoke-RestMethod "https://services.gradle.org/distributions/gradle-$version-bin.zip.sha256").Trim()
 if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected.ToLowerInvariant()) { throw 'Gradle checksum mismatch.' }
 Expand-Archive -LiteralPath $zip -DestinationPath $tools -Force
}
& $gradle wrapper --gradle-version $version
if ($LASTEXITCODE -ne 0) { throw 'Gradle setup failed.' }
& $gradle :app:assembleDebug
if ($LASTEXITCODE -ne 0) { throw 'Android build failed. Check Android Studio and SDK 36.' }
Write-Host 'APK: app\build\outputs\apk\debug\app-debug.apk'
