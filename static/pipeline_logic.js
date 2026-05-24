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
 * 根據總監決策解析下一個階段
 * @param {object} decision - 總監決策物件，包含 action, target, hint 等屬性
 * @param {string} currentStage - 當前階段名稱：worldview, characters, plot, writer
 * @returns {string|null} 下一個階段名稱，如果應該停止則返回 null
 */
function resolveNextStageFromDecision(decision, currentStage) {
  const action = decision?.action;
  
    switch (action) {
    case 'CONTINUE':
      // 根據當前階段決定下一階段（四階段漏斗流）
      switch (currentStage) {
        case 'worldview':
          return 'characters';
        case 'characters':
          return 'plot';
        case 'plot':
          return 'volume_skeleton';  // 新增：Stage 2 簡易章綱
        case 'volume_skeleton':
          return 'foreshadowing_orchestration';  // 新增：Stage 3 伏筆編織
        case 'foreshadowing_orchestration':
          return 'writer';  // Stage 4 微觀細修完成後進入正文寫作
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