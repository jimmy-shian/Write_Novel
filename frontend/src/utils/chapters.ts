/**
 * 章節名稱解析共用工具。
 * 與 ExplorerDrawer 的 displayChapters 合併邏輯保持一致：
 * 分卷細綱 (volumes.chapters_outline) > 全書大綱 (plot.chapters) > 已撰寫章節 (chapters.title)
 * 並去除「第 N 章：」前綴，避免上方區塊顯示重複編號。
 */

export interface ChapterTitleSource {
  volumes?: any[];
  plot?: any;
  chapters?: Array<{ chapter_index: number; title?: string }>;
}

export function stripChapterNumberPrefix(rawTitle: string): string {
  if (!rawTitle) return '';
  const trimmed = String(rawTitle).trim();
  if (!trimmed) return '';
  const cleaned = trimmed.replace(/^第\s*\d+\s*章([：:・\s]*)/, '').trim();
  return cleaned || trimmed;
}

export function getChapterTitle(
  detail: ChapterTitleSource | null | undefined,
  chapterIndex: number,
): string {
  if (!detail || !chapterIndex || chapterIndex <= 0) return '';

  // 1. 分卷細綱優先（與左側導航目錄 same source）
  if (Array.isArray(detail.volumes)) {
    for (const vol of detail.volumes) {
      const outlines = Array.isArray((vol as any)?.chapters_outline)
        ? (vol as any).chapters_outline
        : Array.isArray((vol as any)?.chapters)
          ? (vol as any).chapters
          : [];
      for (const ch of outlines) {
        const chNum = Number(ch?.chapter_index);
        if (chNum === chapterIndex) {
          const raw = ch?.chapter_title || ch?.title || '';
          const clean = stripChapterNumberPrefix(raw);
          // 若細綱本身就是「第 X 章」泛稱，視為無自訂名稱
          if (clean && clean !== `第 ${chapterIndex} 章`) return clean;
          if (raw && raw.trim() && raw.trim() !== `第 ${chapterIndex} 章`) {
            return stripChapterNumberPrefix(raw);
          }
          // 找到編號但無自訂名稱，仍繼續看 plot/chapters 是否有更具體的名稱
          break;
        }
      }
    }
  }

  // 2. 全書大綱 plot.chapters
  const plotChapters = (detail.plot as any)?.chapters;
  if (Array.isArray(plotChapters)) {
    for (const ch of plotChapters) {
      const chNum = Number(ch?.chapter_index);
      if (chNum === chapterIndex) {
        const raw = ch?.chapter_title || ch?.title || '';
        const clean = stripChapterNumberPrefix(raw);
        if (clean && clean !== `第 ${chapterIndex} 章`) return clean;
        break;
      }
    }
  }

  // 3. 已撰寫章節自帶 title
  if (Array.isArray(detail.chapters)) {
    const found = detail.chapters.find((c) => Number(c?.chapter_index) === chapterIndex);
    const raw = (found?.title || '').trim();
    if (raw) {
      const clean = stripChapterNumberPrefix(raw);
      if (clean && clean !== `第 ${chapterIndex} 章`) return clean;
    }
  }

  return '';
}
