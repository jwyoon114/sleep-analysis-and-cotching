"use client";

import {useEffect, useRef, useState} from "react";
import {Download, Smartphone, X} from "lucide-react";

const APK_URL = "/downloads/daljam-android.apk";

export default function PwaInstall() {
  const [native, setNative] = useState(false);
  const [open, setOpen] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const detectNative = () => setNative(Boolean(window.DaljamNative));
    detectNative();
    window.addEventListener("daljam-native-ready", detectNative);
    if ("serviceWorker" in navigator && window.isSecureContext) {
      navigator.serviceWorker.register("/sw.js", {scope: "/", updateViaCache: "none"}).catch(() => {});
    }
    return () => window.removeEventListener("daljam-native-ready", detectNative);
  }, []);

  useEffect(() => {
    if (open) dialog.current?.showModal();
    else dialog.current?.close();
  }, [open]);

  if (native) return null;

  return <>
    <div className="app-install-actions" aria-label="달잠 앱 설치">
      <a className="button primary app-download-button" href={APK_URL} download="daljam-android.apk" aria-describedby="apk-requirements">
        <Download size={16} aria-hidden="true"/> 갤럭시 앱 다운로드
      </a>
      <button type="button" ref={trigger} className="button secondary app-install-guide" onClick={() => setOpen(true)}>
        <Smartphone size={16} aria-hidden="true"/> 설치 안내
      </button>
      <small id="apk-requirements">테스트 버전 · Android 9 이상</small>
    </div>
    <dialog ref={dialog} className="pwa-dialog" aria-labelledby="app-install-title" onClose={() => {
      setOpen(false);
      trigger.current?.focus();
    }}>
      <button type="button" className="icon-button pwa-close" aria-label="설치 안내 닫기" onClick={() => setOpen(false)}>
        <X aria-hidden="true"/>
      </button>
      <h2 id="app-install-title">휴대폰에 달잠 설치하기</h2>
      <section aria-labelledby="galaxy-install-title">
        <h3 id="galaxy-install-title">갤럭시 · Android 앱</h3>
        <p><strong>테스트 버전 · Android 9 이상</strong></p>
        <p>APK를 내려받아 열고 Android의 설치 안내를 따라 주세요. 필요한 경우 다운로드에 사용한 브라우저에 이 앱을 설치할 권한을 허용하세요.</p>
        <p>달잠에 로그인한 뒤 삼성 헬스의 Health Connect 수면 공유를 켜세요. 달잠의 건강앱 연결에서 삼성 헬스를 선택하고, 수면 읽기와 서버 전송에 동의하면 앱을 열어 기록을 동기화할 수 있어요.</p>
        <a className="button primary app-download-button" href={APK_URL} download="daljam-android.apk">
          <Download size={16} aria-hidden="true"/> 갤럭시 앱 다운로드
        </a>
      </section>
      <section aria-labelledby="iphone-install-title">
        <h3 id="iphone-install-title">iPhone · iPad</h3>
        <p>Safari에서 달잠을 열고 공유 메뉴 → <strong>홈 화면에 추가</strong>를 선택하세요. ‘웹 앱으로 열기’가 표시되면 켠 뒤 추가하세요.</p>
        <p>Apple 건강 기록은 지원하는 수면 JSON으로 내보낸 뒤 달잠의 <strong>수면 기록 추가</strong>에서 가져오세요. 홈 화면 웹앱에서는 HealthKit 직접 자동 연결을 지원하지 않아요.</p>
      </section>
      <p>웹앱과 수면 동기화에는 인터넷 연결이 필요해요. 휴대폰 푸시 알림은 현재 지원하지 않아요.</p>
      <button type="button" className="button secondary full" onClick={() => setOpen(false)}>확인했어요</button>
    </dialog>
  </>;
}
