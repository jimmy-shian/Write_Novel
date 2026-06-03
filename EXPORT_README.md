# 小說資料匯出工具使用說明

## 📦 檔案說明

本專案提供兩方面的資料匯出功能：

| 檔案 | 說明 |
|------|------|
| `export_novel.py` | Python 命令列工具，可從資料庫直接提取並匯出小說 |
| `小说数据导出说明.md` | 技術文件，說明後端 API 與前端整合方案 |

---

## 🚀 快速開始

### 1. 檢查可用小說

```bash
python export_novel.py --list
```

輸出範例：
```
共找到 2 部小說：
--------------------------------------------------------------------------------
ID: abc123-def456
  標題: 天衍九州：斬仙路
  題材: 仙俠
  風格: 史詩宏大
  建立時間: 2025-04-01 10:30:00
```

### 2. 匯出小說

```bash
# 匯出為 TXT（純文字）
python export_novel.py --novel-id abc123-def456

# 匯出為 Markdown（結構化）
python export_novel.py --novel-id abc123-def456 --format markdown

# 自訂輸出檔名
python export_novel.py --novel-id abc123-def456 --output ./ novels/我的小說.txt
```

---

## 📝 匯出內容說明

### TXT 格式
```
《天衍九州：斬仙路》
題材：仙俠
風格基調：史詩宏大
=========================================

【第 1 章：修仙路啟】

正文內容...

-----------------------------------------

【第 2 章：靈根測試】

正文內容...
```

### Markdown 格式
```markdown
# 《天衍九州：斬仙路》

- **題材**: 仙俠
- **風格基調**: 史詩宏大

---

## 📖 世界觀與核心設定

{世界構設定內容}

---

## 👥 角色聖經 (Character Bible)

{"characters": [...]}  // JSON 格式

---

## 🗺️ 劇情章節大綱

{"chapters": [...]}  // JSON 格式

---

## 📝 小說完整正文

### 第 1 章：修仙路啟

正文內容...
```

---

## 🔧 技術細節

### 資料來源

此工具直接讀取 SQLite 資料庫（`novel_factory.db`），從以下表格提取資料：

- `novels` - 小說基本資訊
- `worldbuilding` - 世界觀（最新版本）
- `characters` - 角色聖經（最新版本）
- `plot_chapters` - 劇情大綱
- `chapters` - 正文章節
- `volumes` - 篇卷規劃

### 資料收集邏輯

`get_full_novel_data()` 函數複刻了 FastAPI 端點 `GET /api/novels/{novel_id}` 的邏輯，確保匯出內容與 Web 界面看到的完全一致。

### 編碼處理

- 所有檔案使用 **UTF-8 編碼**，確保中文正確顯示
- 檔名會清理非法字元（如 `\/:*?"<>|`）

---

## 🖥️ 前端整合方案

### 現有 API

Web 後端已提供以下 API 端點：

```
GET /api/novels/{novel_id}/export?format=txt
GET /api/novels/{novel_id}/export?format=markdown
```

### 前端調用範例

```javascript
function exportNovel(novelId, format = 'txt') {
  const url = `/api/novels/${novelId}/export?format=${format}`;
  
  // 方法 1: 直接開啟新分頁（瀏覽器會自動下載）
  window.open(url, '_blank');
  
  // 方法 2: 建立隱藏連結並點擊
  const link = document.createElement('a');
  link.href = url;
  link.download = '';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// 使用
exportNovel(state.currentNovelId, 'markdown');
```

### 建議 UI 位置

在 `static/index.html` 的 Writer 標籤頁 `writer-top-bar` 區域新增「匯出小說」按鈕，旁边的 directive：

```html
<div class="button-group">
  <!-- 現有按鈕 -->
  <button id="btn-write-chapter" ...>AI 撰寫本章正文</button>
  <button id="btn-edit-chapter" ...>AI 編輯優化本章</button>
  <button id="btn-prose-save" ...>保存 prose</button>
  
  <!-- 新增匯出按鈕 -->
  <button id="btn-export-novel" class="btn btn-ghost btn-sm">
    <svg>...</svg>
    <span>匯出小說</span>
  </button>
</div>
```

---

## 🐛 常見問題

### Q1: 執行時出現「找不到模組 db」
**A**：請確保在專案根目錄執行，`export_novel.py` 會自動將當前目錄加入 Python 路徑。

### Q2: 匯出檔名亂碼？
**A**：檔案已使用 UTF-8 編碼，請用正確的編輯器開啟（如 VS Code、Notepad++）。

### Q3: 小說 ID 如何取得？
**A**：執行 `python export_novel.py --list` 查看所有小說及其 ID。

### Q4: 可以批量匯出所有小說嗎？
**A**：目前需個別執行。可修改腳本支援批量，或使用 Web API 批次處理。

---

## 📊 匯出功能對照表

| 功能 | Web API | Python 工具 |
|------|---------|------------|
| 列出小說 | ❌ | ✅ (`--list`) |
| 匯出 TXT | ✅ | ✅ (`--format txt`) |
| 匯出 Markdown | ✅ | ✅ (`--format markdown`) |
| 自訂檔名 | ❌ | ✅ (`--output`) |
| 直接下載 | ✅ (瀏覽器) | ✅ (本地檔案) |

---

## 🔄 更新紀錄

- **2025-04-06** - 初版發行
  - 支援 TXT 和 Markdown 格式
  - 命令行參數完整功能
  - 包含世界觀、角色、大綱、正文

---

## 📄 授權

本工具為專案內部使用，授權遵循專案主體 license。