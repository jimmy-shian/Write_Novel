/**
 * 敘事推理刷新事件匯流排（SSOT）。
 *
 * 目的：每章內容生成後，Story Engine 2.0 要和前端正文一樣「同步更新顯示」，
 * 而不是只靠 3 秒輪詢慢慢追上。
 *
 * 使用方式：
 * - 章節正文變更處（App.tsx 單發生成 onDone / 自動管線 stageCompleted / 套用修訂）
 *   呼叫 `emitChapterContentUpdated(novelId, chapterIndex)`。
 * - `useNarrativeEngine` 訂閱此事件，收到屬於當前 novelId 的通知即靜默刷新。
 *
 * 為何不用 props drilling：NarrativeEngineBoard 深掛在 workspace-body 內，
 * 而生成邏輯在 App 頂層 + CopilotDrawer，事件匯流排是最薄的解耦層。
 */

export interface ChapterContentUpdatedDetail {
  novelId: string;
  chapterIndex?: number;
  reason: 'writer-done' | 'editor-done' | 'auto-pipeline' | 'proposal-applied' | 'audit-fix' | 'manual' | 'reset-content';
  at: number;
}

export const NARRATIVE_REFRESH_EVENT = 'nkust:chapter-content-updated';

export function emitChapterContentUpdated(
  novelId: string,
  reason: ChapterContentUpdatedDetail['reason'] = 'manual',
  chapterIndex?: number,
): void {
  if (!novelId) return;
  const detail: ChapterContentUpdatedDetail = {
    novelId,
    chapterIndex,
    reason,
    at: Date.now(),
  };
  window.dispatchEvent(new CustomEvent<ChapterContentUpdatedDetail>(NARRATIVE_REFRESH_EVENT, { detail }));
}

export function subscribeChapterContentUpdated(
  handler: (detail: ChapterContentUpdatedDetail) => void,
): () => void {
  const listener = (e: Event) => {
    const ce = e as CustomEvent<ChapterContentUpdatedDetail>;
    if (ce?.detail?.novelId) {
      handler(ce.detail);
    }
  };
  window.addEventListener(NARRATIVE_REFRESH_EVENT, listener);
  return () => window.removeEventListener(NARRATIVE_REFRESH_EVENT, listener);
}
