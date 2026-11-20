type SyncCounts = {added_sessions:number; updated_sessions:number; ignored_incomplete:number};
export type HealthNotice = {role:"status"|"alert"; text:string; manual?:boolean};
export type HealthOperation = "read"|"sync"|"server"|"configure"|"disconnect";

const empty: HealthNotice = {
  role:"status", manual:true,
  text:"읽을 수 있는 수면 기록을 찾지 못했어요. 삼성 헬스의 Health Connect 동기화 상태를 확인하거나, 수면 시간을 직접 입력해 보세요.",
};
const appleEmpty: HealthNotice = {role:"status", manual:true, text:"읽을 수 있는 수면 기록을 찾지 못했어요. 건강 앱을 확인하거나 수면 시간을 직접 입력해 보세요."};
export const emptyHealthResult = (platform:"android"|"ios") => platform==="android" ? empty : appleEmpty;

export function healthIssue(operation:HealthOperation, message:unknown, platform?:"android"|"ios"):HealthNotice {
  const detail = typeof message === "string" ? message : "";
  if (platform === "android" && detail === "접근 가능한 수면 기록이 없어요. 건강앱의 기록과 권한을 확인해 주세요.") return empty;
  if (/수면 읽기 권한|수면 데이터 읽기 권한|READ_SLEEP/i.test(detail))
    return {role:"alert", manual:true, text:`${platform==="ios"?"건강 앱":"Health Connect"}의 수면 읽기 권한을 허용한 뒤 다시 확인해 주세요.`};
  if (/Health Connect를 설치하거나 업데이트/.test(detail))
    return {role:"alert", manual:true, text:"Health Connect를 설치하거나 업데이트한 뒤 다시 확인해 주세요."};
  if (/건강앱 (연결이 필요|연결이 만료|연결이 해제|연결을 다시 설정)|건강앱을 먼저 연결|연결이 만료|유효하지 않은.{0,10}연결/.test(detail))
    return {role:"alert", manual:true, text:"건강앱 연결을 다시 설정한 뒤 동기화해 주세요."};
  if (operation==="server" || /달잠 서버|서버에 연결|서버 연결|저장하지 못|데이터베이스를 사용할 수 없|건강 기록을 확인하세요|Unable to resolve host|Failed to connect|timeout|timed out/i.test(detail))
    return {role:"alert", manual:true, text:"달잠 서버에 수면 기록을 전송하거나 저장하지 못했어요. 인터넷을 확인한 뒤 다시 시도해 주세요."};
  if (operation==="read" || /readRecords|HealthConnectException|record read/i.test(detail))
    return {role:"alert", manual:true, text:"건강앱에서 수면 기록을 조회하지 못했어요. 권한과 연결 상태를 확인해 주세요."};
  if (operation==="disconnect") return {role:"alert", text:"건강앱 연결을 해제하지 못했어요. 잠시 뒤 다시 시도해 주세요."};
  if (operation==="configure") return {role:"alert", manual:true, text:"휴대폰에서 건강앱 연결을 완료하지 못했어요. 잠시 뒤 다시 시도해 주세요."};
  return {role:"alert", manual:true, text:"수면 기록을 동기화하지 못했어요. 건강앱 연결과 인터넷을 확인한 뒤 다시 시도해 주세요."};
}

export function healthSyncNotice(result:SyncCounts):HealthNotice {
  const saved = result.added_sessions + result.updated_sessions > 0;
  const summary = saved ? "건강앱이 연결되어 있고 수면 기록을 저장했어요." : "";
  if (result.ignored_incomplete > 0) {
    const excluded = `지원되는 수면 단계가 없는 기록 ${result.ignored_incomplete}건은 분석에서 제외했어요.`;
    return {role:"status", text:saved ? `${summary} ${excluded}` : excluded, manual:!saved};
  }
  return {role:"status", text:saved ? summary : "동기화를 확인했어요. 새로 저장하거나 갱신할 수면 기록이 없어요."};
}
