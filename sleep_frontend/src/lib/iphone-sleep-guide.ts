type GuideArea = readonly [left: number, top: number, width: number, height: number];

type GuideStep = {
  title: string;
  description: string;
  photo: string;
  alt: string;
  highlights: readonly GuideArea[];
  formatNotes?: readonly string[];
};

export const HEALTH_EXPORT_KIT_APP_STORE = "https://apps.apple.com/kr/app/health-export-kit/id6762845329";

// When replacing an image, update its highlight rectangles as percentages of the crop.
export const IPHONE_SLEEP_STEPS: readonly GuideStep[] = [
  {
    title: "앱에서 내보내기 시작",
    description: "App Store에서 Lunium AB의 Health Export Kit를 설치하고 앱에서 Start new export를 누르세요.",
    photo: "start",
    alt: "Health Export Kit의 Start new export 버튼",
    highlights: [[6, 12, 88, 69]],
  },
  {
    title: "수면 분석 선택",
    description: "Sleep에서 Sleep Analysis만 켜고 Continue를 누르세요. 권한을 묻는 경우 수면 읽기를 허용해 주세요.",
    photo: "sleep-analysis",
    alt: "Sleep Analysis가 켜진 상태와 화면 아래 Continue 버튼",
    highlights: [[12, 42, 84, 22], [1, 72, 98, 26]],
  },
  {
    title: "내보낼 기간 선택",
    description: "Last 7 days 또는 필요한 기간을 선택하고 Continue를 누르세요.",
    photo: "period",
    alt: "Last 7 days가 선택된 상태와 Continue 버튼",
    highlights: [[1, 4, 49, 47], [1, 58, 98, 38]],
  },
  {
    title: "JSON으로 내보내기",
    description: "Format에서 JSON을 고른 뒤 Export를 누르세요. Sleep Analysis만 선택했다면 일반 내보내기부터 시도해 보세요.",
    photo: "json-format",
    alt: "오른쪽 JSON 형식과 하단 Export 버튼",
    highlights: [[50, 2, 49, 60], [1, 69, 98, 27]],
    formatNotes: [
      "달잠은 수면 세션과 단계가 들어 있는 Health Export Kit JSON v2를 읽어요. Verbose 옵션의 원본 표본은 달잠이 읽을 수 있는 v2 배열 구조일 때 지원해요.",
      "요약 표본 오류가 나면 Sleep Analysis만 선택해 다시 내보내세요. 날짜가 모호하다면 하루 범위로 다시 시도해 보세요. Apple 건강 앱의 XML·ZIP은 지원하지 않아요.",
    ],
  },
  {
    title: "완료 화면에서 저장",
    description: "Export complete 화면에서 오른쪽 Save를 누르면 iPhone 공유 메뉴가 열려요.",
    photo: "save-export",
    alt: "Export complete 제목과 오른쪽 Save 버튼",
    highlights: [[50, 44, 49, 49]],
  },
  {
    title: "파일 앱에 저장",
    description: "공유 메뉴에서 파일에 저장을 누르세요. 나중에 찾기 쉬운 폴더를 고르고 저장하세요.",
    photo: "save-to-files",
    alt: "iPhone 공유 메뉴의 파일에 저장 항목",
    highlights: [[1, 6, 98, 89]],
  },
  {
    title: "달잠에 수면 기록 가져오기",
    description: "저장한 .json 파일을 선택하고, 달잠에서 분석하고 내 기록에 저장을 누르세요.",
    photo: "daljam-upload",
    alt: "달잠의 수면 파일 선택 영역과 분석하고 내 기록에 저장 버튼",
    highlights: [[1, 1, 98, 45], [1, 86, 98, 13]],
  },
];
