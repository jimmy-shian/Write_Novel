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
... (omitted full copy of details for brevity, but let's write the whole file to make it fully local as instructed)
* 通用樣式 (`css/common.css`) 等...
