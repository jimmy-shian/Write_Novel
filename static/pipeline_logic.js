/**
 * 純函式：統一 pipeline prompt 取值優先序
 * 優先序：使用者本次輸入 > state.pipelinePrompt > DB pipeline_prompt > default
 */
function getPipelinePrompt({ inputPrompt, statePrompt, dbPrompt, fallbackPrompt }) {
  const p =
    (inputPrompt || "").trim() ||
    (statePrompt || "").trim() ||
    (dbPrompt || "").trim() ||
    (fallbackPrompt || "").trim();
  return p;
}

/**
 * 檢查是否存在有效的章節大綱
 * @param {object} novelData - 小說資料物件
 * @returns {boolean} 如果所有卷都有包含實質內容的完整大綱則返回 true
 * 
 * 【Step 3 修復】修改檢查條件，確保每個章節除了有名稱外，
 * 必須含有實質的大綱核心內容（summary、content_flow 或 events），
 * 否則判定大綱未完工，強制退回大綱規劃階段。
 */
function hasValidChapterOutlines(novelData) {
  const volumes = novelData?.volumes || [];
  if (volumes.length === 0) return false;
  
  // 遍歷所有卷，嚴格檢查章節大綱是否包含實質內容
  return volumes.every(vol => {
    const chs = Array.isArray(vol.chapters_outline) 
      ? vol.chapters_outline 
      : JSON.parse(vol.chapters_outline || '[]');
    
    // 必須有章節存在
    if (!Array.isArray(chs) || chs.length === 0) return false;
    
    // 每個章節必須含有實質的大綱核心內容
    return chs.every(ch => ch.summary || ch.content_flow || ch.events);
  });
}

/**
 * 根據總監決策解析下一個階段
 * @param {object} decision - 總監決策物件，包含 action, target, hint 等屬性
 * @param {string} currentStage - 當前階段名稱：worldview, characters, plot, writer
 * @param {object} novelData - 可選的小說資料，用於進行章大綱檢查
 * @returns {string|null} 下一個階段名稱，如果應該停止則返回 null
 */
function resolveNextStageFromDecision(decision, currentStage, novelData) {
  const action = decision?.action;
  
    switch (action) {
    case 'CONTINUE':
      // 根據當前階段決定下一階段（四階段漏斗流）
      switch (currentStage) {
        case 'worldview':
          return 'characters';
        case 'characters':
          return 'volumes';
        case 'volumes':
          return 'volume_skeleton';
        case 'volume_skeleton':
        //   return 'foreshadowing_orchestration';
        // case 'foreshadowing_orchestration':
          return 'plot';
        case 'plot':
          return 'writer';
        case 'writer':
          return null; // 寫作階段完成
        default:
          return 'worldview'; // 預設從世界觀開始
      }
      
    case 'AUTO_REGENERATE':
      // 重新生成，保持當前階段
      return currentStage || 'worldview';
      
    case 'GO_BACK_TO_WORLDVIEW':
      return 'worldview';
      
    case 'GO_BACK_TO_CHARACTERS':
      return 'characters';
      
    case 'GO_BACK_TO_PLOT':
      return 'plot';
      
    case 'WRITE_ALL_CHAPTERS':
      return 'writer';
      
    case 'WAIT_USER':
    case 'FINISH':
      // 停止，等待用戶確認或任務完成
      return null;
      
    default:
      // 未知 action，返回 null 表示停止
      return null;
  }
}

module.exports = {
  getPipelinePrompt,
  resolveNextStageFromDecision,
};

