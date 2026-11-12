import {NextResponse} from "next/server";

// Server runtime setting; never expose this as a NEXT_PUBLIC build variable.
export function isDemoOnly() {
  return process.env.DALJAM_DEMO_ONLY === "1";
}

export function demoBlockedResponse() {
  return NextResponse.json({detail: {
    code: "demo_only",
    message: "체험 버전에서는 회원가입·로그인·업로드·건강앱 연결을 제공하지 않습니다. 가상 기록으로 둘러봐 주세요.",
  }}, {status: 403, headers: {"Cache-Control": "no-store"}});
}
