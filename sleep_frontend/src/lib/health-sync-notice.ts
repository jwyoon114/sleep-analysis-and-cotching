type SyncCounts = {
  added_sessions: number;
  updated_sessions: number;
  ignored_incomplete: number;
};

// The distributed Android bridge rejects empty reads with this text and
// repeats it in status.error. Recognize that existing contract without
// classifying permission, network, or server failures as empty reads.
const androidEmptyRead = "접근 가능한 수면 기록이 없어요. 건강앱의 기록과 권한을 확인해 주세요.";

export function healthSyncIssue(platform: "android" | "ios" | undefined, message?: string): {
  role: "status" | "alert";
  text: string;
} | null {
  if (!message) return null;
  if (platform === "android" && message === androidEmptyRead) {
    return {role:"status", text:"선택한 건강앱 출처에서 읽을 수 있는 수면 기록이 없어요."};
  }
  return {role:"alert", text:message};
}

export function healthSyncMessage(result: SyncCounts) {
  const saved = result.added_sessions > 0 || result.updated_sessions > 0;
  const savedMessage = "새 수면 기록을 가져와 분석했어요.";
  if (result.ignored_incomplete > 0) {
    const excluded = "분석할 수면 단계가 없는 기록 " + result.ignored_incomplete + "건은 분석에서 제외했어요.";
    return saved ? savedMessage + " " + excluded : excluded;
  }
  return saved ? savedMessage : "확인을 마쳤어요. 새로 분석해 저장한 수면 기록은 없어요.";
}
