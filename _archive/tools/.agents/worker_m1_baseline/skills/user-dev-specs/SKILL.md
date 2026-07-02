---
name: user-dev-specs
description: Specifications for Windows environments, Python UTF-8 single-file tests, CSS clean architecture, and Codex background/theme visual standards.
---

# 使用者開發與網頁架構規範說明書 (Custom Web & Python Development Specs)

當觸發此 Skill 時，AI 助理必須嚴格遵守以下所有規則與開發偏好：

---

## 🛠️ 1. 系統環境與執行規範 (System & Environment Specs)
* **純 Windows PowerShell 環境**：
  * 所有終端機指令必須相容於 Windows。**嚴禁使用任何 Linux 特有指令**（例如：`ls`, `grep`, `rm -rf`, `export` 等）。
  * 請改用 Windows/PowerShell 等效指令（如：`Get-ChildItem`, `Select-String`, `Remove-Item` 等）。
* **路徑處理**：
  * 使用 Windows 格式反斜線 `\` 作為路徑分隔符，或在 Python 中使用 `pathlib.Path` 以確保跨平台路徑相容性。
* **指定 Python 解譯器**：
  * 執行 Python 腳本或相關命令時，強制使用：
    ```
    C:\Users\user\venv\Scripts\python.exe
    ```
* **強制 UTF-8 編碼**：
  * **所有中文字串與檔案讀寫一律強制使用 `utf-8` 編碼**。
  * 開啟/讀寫檔案時必須明確宣告 `encoding='utf-8'`，嚴防 Windows 系統預設 `cp950`（ANSI）所導致的編碼報錯。

---

## 🧪 2. 測試與開發驗證規範 (Testing & Quality Assurance)
* **單一測試檔案整合**：
  * 所有測試邏輯必須整合在**「單一 Python 檔案」**之內。
  * 執行該測試檔案一次，必須完整測試並驗證系統的所有功能，禁止將測試拆分成多個檔案，或要求分批多次執行。

---

## 🎨 3. 網頁 CSS 與 HTML 架構規範 (CSS Architecture & Refactoring)
進行網頁前端開發或 CSS 重構時，必須遵循以下清晰的模組化結構：

### 📁 3.1 樣式檔目錄結構
* **通用樣式 (`css/common.css`)**：
  * 存放所有頁面共用的樣式。
  * 包含：CSS Reset、body 基礎字體與排版、色彩變數、全域按鈕、表單樣式、Header、Footer、Container 以及通用 Utility classes。
* **個別頁面樣式 (`css/<page_name>.css`)**：
  * 每個 HTML 頁面必須有對應的專用 CSS 檔案。
    * 例如：`index.html` ➡️ `css/index.css`；`about.html` ➡️ `css/about.css`。
  * 個別頁面 CSS 只放該頁面專屬的樣式，**嚴禁**將單一頁面的特殊樣式寫入 `common.css`。

### 🏷️ 3.2 HTML 作用域限制與 Clean HTML
* **頁面作用域 (Page Scope)**：
  * 為了防範 CSS 衝突，請在個別頁面 CSS 中使用 body 上的頁面作用域 class 作為限定選擇器。
  * 新增頁面作用域 class 時，必須保留原本 body 上已有的 class。
    * *正確示範*：`<body class="dark-mode page-about">`
* **移除 Inline & Internal Styles**：
  * HTML 中**不應出現**任何標籤上的行內樣式 (`style="..."`) 與頁面內嵌樣式區塊 (`<style>...</style>`)。所有樣式必須乾淨地抽離至 CSS 檔中。

### 📱 3.3 響應式網頁設計 (RWD)
* `common.css` 與各別頁面 CSS 均需完整包含響應式設計（RWD）。
* 至少需以 Media Queries 整理出三個層次的斷點：
  1. 桌機版 (Desktop)
  2. 平板版 (Tablet)
  3. 手機版 (Mobile)（手機版各主要網格、卡片元件應自動轉換為單欄 100% 寬度直排）

### ⚡ 3.4 JavaScript 動態樣式規範
* **Class 優先原則**：
  * 原本由 JavaScript 動態控制 `style` 的行為（如元素位置、旋轉、過渡動畫等），必須**優先改用** CSS Class、`data-*` 屬性、CSS Animation 或 CSS Layout 來控制。
  * 僅在完全無法避免的極端動態座標計算時（如拼圖塊座標、3D Transform 實時位移等），才列為例外並於文件中標註說明。

### 📁 3.5 漸進式重構 (Deprecated 流程)
* 重構期間**不可直接刪除**任何舊有的 CSS 檔案。
* 完成搬移、修改引用並完整測試後，先將舊檔案標記為 `deprecated`。
* 再次確認沒有任何畫面與引用異常後，方可提出正式刪除建議。

---

## 🎭 4. Codex 視覺主題與背景裝飾系統規範 (Codex Themes & Visual Specs)
依據 Codex 設計開發紀錄，網頁在實作各產業類別背景與動態視覺系統時，必須嚴格遵守以下裝飾與層級規範：

### 🌌 4.1 產業別背景主題系統 (Category Background Theme)
* **避免過度格式化與方正**：
  * 避免版面過度僵硬，需使用 CSS variables、pseudo-elements、gradient（漸層）、`color-mix` 以及低透明度紋理，為各產業別頁面（如農業、花藝、餐飲、殯葬、通訊、樂器、汽車美容等）實作專屬的背景氛圍。
* **背景裝飾的安全隔離**：
  * 背景元素僅作為純粹裝飾，必須標記 **`aria-hidden="true"`**。
  * 必須加上 **`pointer-events: none`**，以防裝飾圖層阻擋頁面正常的點擊或觸控交互。
  * **階層管理 (Z-Index)**：`.main-content`、`header`、`nav`、`footer` 的 `z-index` 階層必須高於 `.category-bg-decor`。

### 📱 4.2 行動端極致優化與 RWD 限制
* **防止水平溢出捲軸**：
  * 手機版寬度下，網頁**嚴禁出現任何水平捲軸**，在 RWD 媒體查詢中需對最外層容器（如 `#providers-grid`）施加 `overflow-x: hidden` 限制。
* **行動端降低背景複雜度**：
  * 行動裝置或觸控螢幕上，必須**停用或簡化**複雜的錯落式排列與懸浮 transform 動畫（例如：卡片 Hover 時的 `transform: none !important`），並隱藏非必要的裝飾背景圖案，以確保效能與可讀性。

### 📝 4.3 程式碼完整性與開發禮儀
* **保留原始註解**：
  * 在修改 HTML、CSS 與 JS 時，必須**完整保留原本既有的註解與被註解的程式碼**，不應隨意刪除使用者的歷史備忘。
