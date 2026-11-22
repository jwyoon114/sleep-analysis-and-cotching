const hidden = new Set(["수면 패턴", "기간별 수면 기록", "두 기간의 수면 흐름"]);
const headings = new Set(["선택 기록", "실천 제안", "데이터 한계"]);

export function coachingSections(body: string): {title: string; text: string}[] {
  return body.trim().split(/\r?\n\s*\r?\n/).flatMap(block => {
    const [first, ...lines] = block.split(/\r?\n/);
    const title = first.trim();
    if (hidden.has(title)) return [];
    if (headings.has(title)) {
      const text = lines.join("\n").trim();
      return text ? [{title, text}] : [];
    }
    return block.trim() ? [{title: "", text: block.trim()}] : [];
  });
}
