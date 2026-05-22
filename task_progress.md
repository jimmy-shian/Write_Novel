# app.js 簡化任務清單

## 第一階段：導入模組支援
- [ ] 修改 index.html 為 ES module 模式
- [ ] 在 app.js 頂部添加 imports 語句（導入所有已拆分模組）
- [ ] 刪除 app.js 中重複的 state 定義（1-30行）
- [ ] 刪除 app.js 中重複的 el 定義（35-121行）
- [ ] 刪除 app.js 中重複的 showToast 定義（126-132行）
- [ ] 刪除 app.js 中重複的 requestAPI 定義（890-910行）
- [ ] 刪除 app.js 中重複的 streamAPI 定義（914-967行）

## 第二階段：移除 utils 重複函式
- [ ] 刪除 parseWorldviewJSON（重複，utils.js 已有）
- [ ] 刪除 showCustomConfirm（重複，utils.js 已有）
- [ ] 刪除 stripBulletPrefix（重複，utils.js 已有）
- [ ] 刪除 formatDate（重複，utils.js 已有）
- [ ] 刪除 parseWorldviewSeeds（重複，utils.js 已有）
- [ ] 刪除 parseCoreTheme, parseCoreConflict, parseWorldSetting, parseThreeActStructure, parseOverallOutline, parseCharacterWavePlan, parseKeyTurningPoints（重複，utils.js 已有）

## 第三階段：移除 renderers 重複函式
- [ ] 刪除 renderActiveTab（重複，renderers.js 已有）
- [ ] 刪除 renderWorldviewTab（重複，renderers.js 已有）
- [ ] 刪除 renderWorldviewSections（重複，renderers.js 已有）
- [ ] 刪除 renderWorldviewSection（重複，renderers.js 已有）
- [ ] 刪除 renderCharactersTab（重複，renderers.js 已有）
- [ ] 刪除 renderPlotTab（重複，renderers.js 已有）
- [ ] 刪除 renderWriterTab（重複，renderers.js 已有）
- [ ] 刪除 selectWriterChapter（重複，renderers.js 已有）
- [ ] 刪除 renderActiveChapter（重複，renderers.js 已有）
- [ ] 刪除 renderChatMessages（重複，renderers.js 已有）
- [ ] 刪除 appendChatMessage（重複，renderers.js 已有）

## 第四階段：移除 novelLifecycle 重複函式
- [ ] 刪除 loadNovels（重複，novelLifecycle.js 已有）
- [ ] 刪除 loadNovelDetails（重複，novelLifecycle.js 已有）
- [ ] 刪除 clearWorkspace（重複，novelLifecycle.js 已有）
- [ ] 刪除 renderNovelsList（重複，novelLifecycle.js 已有）

## 第五階段：移除 settings 重複函式
- [ ] 刪除 loadSettings（重複，settings.js 已有）
- [ ] 刪除 loadAgentConfigFields（重複，settings.js 已有）
- [ ] 刪除 saveCurrentAgentSettings（重複，settings.js 已有）

## 第六階段：移除 pipeline 重複函式
- [ ] 檢查 executePipelineStage（是否與 pipeline.js 相同）
- [ ] 檢查 writeAllChaptersSequentially（是否與 pipeline.js 相同）
- [ ] 刪除重複的管道相關函式（如果已移到 pipeline.js）

## 第七階段：移除 agentProcessing 重複函式
- [ ] 刪除 showAgentProcessingIndicator（重複，agentProcessing.js 已有）
- [ ] 刪除 hideAgentProcessingIndicator（重複，agentProcessing.js 已有）
- [ ] 刪除 hideAllAgentProcessingIndicators（重複，agentProcessing.js 已有）

## 第八階段：清理剩餘全域函式
- [ ] 移至 EMB.中學模組刪除或移動未分類的輔助函式
- [ ] 確認所有 DOM 事件監聽器的绑定仍正確
- [ ] 驗證.module導入沒有 Circular Dependency 問題

## 第九階段：測試與驗證
- [ ] 檢查瀏覽器 Console 是否有錯誤
- [ ] 驗證所有功能仍正常运行
- [ ] 確認檔案大小顯著減小