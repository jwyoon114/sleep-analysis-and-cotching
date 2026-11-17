"use client";

import {createContext, useContext, useEffect, useRef, useState, type ReactNode} from "react";
import {Download, Smartphone, X} from "lucide-react";
import {installPlatform, type InstallPlatform} from "@/lib/install-platform";

const APK_URL = "/downloads/daljam-android.apk";
const InstallHelp = createContext<((trigger: HTMLButtonElement) => void) | null>(null);

export function InstallHelpButton() {
  const show = useContext(InstallHelp);
  if (!show) return null;
  return <button type="button" className="text-button install-help-button" aria-haspopup="dialog" onClick={event => show(event.currentTarget)}>
    <Smartphone size={16} aria-hidden="true"/> 앱 설치 안내
  </button>;
}

export default function PwaInstall({children}: {children: ReactNode}) {
  const [device, setDevice] = useState<{platform: InstallPlatform; standalone: boolean} | null>(null);
  const [open, setOpen] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const displayMode = window.matchMedia("(display-mode: standalone)");
    const detect = () => {
      const platform = installPlatform(navigator, Boolean(window.DaljamNative));
      const standalone = displayMode.matches || (navigator as Navigator & {standalone?: boolean}).standalone === true;
      if (platform === "native") setOpen(false);
      setDevice({platform, standalone});
    };
    detect();
    window.addEventListener("daljam-native-ready", detect);
    displayMode.addEventListener("change", detect);
    if ("serviceWorker" in navigator && window.isSecureContext) {
      navigator.serviceWorker.register("/sw.js", {scope: "/", updateViaCache: "none"}).catch(() => {});
    }
    return () => {
      window.removeEventListener("daljam-native-ready", detect);
      displayMode.removeEventListener("change", detect);
    };
  }, []);

  useEffect(() => {
    const popup = dialog.current;
    if (open && popup && !popup.open) popup.showModal();
    else if (!open && popup?.open) popup.close();
  }, [open]);

  const showHelp = device && device.platform !== "native" ? (button: HTMLButtonElement) => {
    trigger.current = button;
    setOpen(true);
  } : null;
  const showAndroid = device && !device.standalone && (device.platform === "android" || device.platform === "web");
  const showApple = device?.platform === "ios" || device?.platform === "web" && !device.standalone;

  return <InstallHelp.Provider value={showHelp}>
    {children}
    <dialog ref={dialog} className="pwa-dialog install-help-dialog" aria-labelledby="app-install-title" onClose={() => {
      setOpen(false);
      trigger.current?.focus({preventScroll: true});
    }}>
      <button type="button" className="icon-button pwa-close" aria-label="설치 안내 닫기" onClick={() => setOpen(false)}>
        <X aria-hidden="true"/>
      </button>
      <h2 id="app-install-title">{device?.standalone ? "홈 화면 앱 이용 안내" : "달잠 앱 설치 안내"}</h2>
      {device?.standalone && <p>이미 홈 화면 앱으로 달잠을 이용하고 있어요.</p>}
      {showAndroid && <section aria-labelledby="galaxy-install-title">
        <h3 id="galaxy-install-title">갤럭시 · Android 앱</h3>
        <p id="apk-requirements"><strong>v0.1.1 아이콘 수정 테스트 버전 · Android 9 이상</strong></p>
        <p id="apk-reinstall">이전 v0.1.0 테스트 앱은 서명이 달라 삭제 후 다시 설치해야 해요. 휴대폰의 로그인·연결 설정이 초기화되므로 같은 계정으로 로그인하고 건강앱 권한과 연결을 다시 설정해 주세요. 서버에 저장된 계정과 수면 기록은 유지돼요.</p>
        <p>APK를 내려받아 열고 Android의 설치 안내를 따라 주세요. 필요한 경우 다운로드에 사용한 브라우저에 이 앱을 설치할 권한을 허용하세요.</p>
        <p>달잠에 로그인한 뒤 삼성 헬스의 Health Connect 수면 공유를 켜세요. 달잠의 건강앱 연결에서 삼성 헬스를 선택하고, 수면 읽기와 서버 전송에 동의하면 앱을 열어 기록을 동기화할 수 있어요.</p>
        <a className="button primary app-download-button" href={APK_URL} download="daljam-android.apk" aria-describedby="apk-requirements apk-reinstall">
          <Download size={16} aria-hidden="true"/> 갤럭시 앱 다운로드
        </a>
      </section>}
      {showApple && <section aria-labelledby="iphone-install-title">
        <h3 id="iphone-install-title">iPhone · iPad</h3>
        {!device?.standalone && <p>Safari에서 달잠을 열고 공유 메뉴 → <strong>홈 화면에 추가</strong>를 선택하세요. ‘웹 앱으로 열기’가 표시되면 켠 뒤 추가하세요.</p>}
        <p>Apple 건강 기록은 지원하는 수면 JSON으로 내보낸 뒤 달잠의 <strong>수면 기록 추가</strong>에서 가져오세요. 홈 화면 웹앱에서는 HealthKit 직접 자동 연결을 지원하지 않아요.</p>
      </section>}
      <p>웹앱과 수면 동기화에는 인터넷 연결이 필요해요. 휴대폰 푸시 알림은 현재 지원하지 않아요.</p>
      <button type="button" className="button secondary full" onClick={() => setOpen(false)}>확인했어요</button>
    </dialog>
  </InstallHelp.Provider>;
}
