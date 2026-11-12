import SleepApp from "@/components/sleep-app";
import {isDemoOnly} from "@/lib/demo-mode";

export const dynamic = "force-dynamic";

export default function Page() {
  return <>
    {isDemoOnly() && <aside role="note" style={{padding:"12px 20px",background:"#f0ebfa",color:"#33264d",textAlign:"center",lineHeight:1.7}}>
      <strong>달잠 체험 버전 · 가상 기록</strong><br/>
      회원가입·로그인·파일 업로드·건강앱 연결·새 코칭 생성은 제공하지 않습니다. 실제 건강 정보를 입력하지 마세요.
      {" "}<a href="/?demo=1">체험 다시 열기</a>
    </aside>}
    <SleepApp />
  </>;
}
