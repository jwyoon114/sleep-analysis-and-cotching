import {ArrowRight, FileJson, HeartPulse, Images} from "lucide-react";
import type {InstallPlatform} from "@/lib/install-platform";
import type {AndroidConnection} from "./health-connect";
import {InstallHelpButton} from "./pwa-install";

const androidDescription: Record<AndroidConnection, string> = {
  checking: "이 휴대폰의 Health Connect 연결을 확인하고 있어요.",
  connected: "Health Connect가 연결되어 있어요. 삼성 헬스의 수면 기록과 읽기 권한을 확인해 보세요.",
  disconnected: "삼성 헬스의 수면 기록을 가져오려면 Health Connect를 연결해 주세요.",
  unavailable: "이 휴대폰에서 Health Connect를 사용할 수 없어요. 설치·업데이트와 기기 지원 여부를 확인해 주세요.",
  error: "Health Connect 연결 상태를 확인하지 못했어요. 건강 데이터 연결에서 다시 확인해 주세요.",
};

type Props = {
  connection: AndroidConnection;
  platform: InstallPlatform;
  onUpload: () => void;
  onGuide: () => void;
  onHealth: () => void;
};

export default function HomeDataConnection({connection, platform, onUpload, onGuide, onHealth}: Props) {

  return <section className="dashboard-card dashboard-connection-card" aria-labelledby="home-connection-title">
    <header className="dashboard-card-title">
      <span className="dashboard-card-icon"><HeartPulse size={19} aria-hidden="true"/></span>
      <h2 id="home-connection-title">수면 기록 연결하기</h2>
    </header>
    {platform === "native" ? <p role="status">{androidDescription[connection]}</p>
      : platform === "ios" ? <p>Health Export Kit에서 수면 기록을 JSON으로 저장한 뒤 달잠으로 가져올 수 있어요.</p>
      : platform === "android" ? <p>삼성 헬스 자동 연결은 달잠 Android 앱에서 사용할 수 있어요. 수면 기록 파일이 있다면 여기서 바로 가져올 수 있어요.</p>
      : <p>지원하는 수면 기록 파일을 가져오면 나의 수면 시간과 흐름을 볼 수 있어요.</p>}
    <div className="dashboard-connection-actions">
      {platform === "native" && <button type="button" className="button primary" onClick={onHealth}>
        {connection === "disconnected" ? "Health Connect 연결하기" : "Health Connect 확인"}<ArrowRight size={16} aria-hidden="true"/>
      </button>}
      {platform === "ios" && <button type="button" className="button primary" aria-haspopup="dialog" onClick={event=>{
        event.currentTarget.focus({preventScroll:true});
        onGuide();
      }}>
        <Images size={16} aria-hidden="true"/>사진으로 따라 하기
      </button>}
      <button type="button" className={`button ${platform === "native" || platform === "ios" ? "secondary" : "primary"}`} aria-haspopup="dialog" onClick={event=>{
        event.currentTarget.focus({preventScroll:true});
        onUpload();
      }}>
        <FileJson size={16} aria-hidden="true"/>{platform === "ios" ? "JSON 파일 가져오기" : "수면 기록 파일 가져오기"}
      </button>
      {platform === "android" && <InstallHelpButton/>}
    </div>
  </section>;
}
