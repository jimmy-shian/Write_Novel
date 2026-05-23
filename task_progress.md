# 任務進度追蹤

## 問題：✍️ 分章寫作章節清單切換問題

### 問題描述
1. 切換章節時沒有正確顯示該章節內容
2. 串流的即時顯示會出現在文本框中（應該只在 AI 正在寫作該章節時顯示）

### 分析
從代碼分析發現兩個問題：

1. **pipeline.js 的 `writeAllChaptersSequentially` 函數**：
   - 串流回呼沒有檢查當前是否仍是活躍章節
   - 導致 AI 寫作舊章節時的串流內容被追加到當前選擇的新章節

2. **pipeline.js 的 `executePipelineStage` 函數**：
   - 同樣沒有對 `writer` 階段的串流進行章節活躍檢查

### 修復完成
- [x] 在 state.js 中新增 `currentlyWritingChapterIndex` 狀態追蹤
- [x] 在 pipeline.js 的 `writeAllChaptersSequentially` 中修改串流回呼，檢查是否為當前活躍章節
- [x] 在 pipeline.js 的 `executePipelineStage` 中為 writer 階段添加章節檢查
- [x] 在 renderers.js 的 `selectWriterChapter` 中添加保護邏輯

### 修改檔案
1. **static/state.js** - 新增 `currentlyWritingChapterIndex` 狀態
2. **static/pipeline.js** - 為所有 writer 階段串流添加章節檢查
3. **static/renderers.js** - 在 `selectWriterChapter` 中增強邏輯

### 修復邏輯說明
當用戶在 AI 寫作章節時切換到另一個章節：
1. `currentlyWritingChapterIndex` 追蹤正在寫作的章節索引
2. 串流回呼檢查 `state.currentlyWritingChapterIndex === chapterIndex` 才寫入
3. 如果用戶切換到其他章節，舊的串流內容不會被寫入新的章節
4. 當章節寫作完成或失敗時，清除 `currentlyWritingChapterIndex` 狀態