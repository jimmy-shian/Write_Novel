# 📖 AI Novel Factory 開發、構建與雲端部署手則 (v4.0.0)

本專案採用精簡高效的單一主分支架構（Single Mainstream Architecture），主分支 `master` 即為全功能唯一代碼源（Single Source of Truth），同時支援**本機獨立開發**、**Hugging Face Spaces 雲端無人值守後端**、**GitHub Pages 前端發布**，以及 **Android APK 行動端打包**。

---

## 🏛️ 一、 分支與發布目標

| 部署目標 | 角色定位 | 核心職責與內容 |
| :--- | :--- | :--- |
| **`master`** | **唯一主分支 (Source of Truth)** | • 包含 FastAPI 後端、Graphiti 時序記憶圖譜與 SQLite 資料庫。<br>• 包含 `frontend/` (React + Vite + TypeScript) 源碼與 `dist/` 產物。<br>• 包含 `autonomous_pipeline.py` 雲端無人值守自主創作引擎。<br>• 包含 Hugging Face Storage Bucket 零 Commit 原地持久化同步。<br>• 所有開發、測試、修復皆由此分支直接驅動。 |
| **GitHub Pages** (`gh-pages`) | **前端靜態託管展示版** | • 由最新前端構建產物發布。<br>• 純靜態前端，作為小說創作面板、閱讀器與無人值守看台。<br>• 透過通用伺服器設定連接個人的 Hugging Face Space 後端。 |
| **Android APK** | **行動端離線/連線應用** | • 基於 `frontend/dist/` 打包之 Capacitor / Cordova 容器。<br>• 支援 Android 硬體返回鍵、觸控回饋與自訂遠端伺服器 API Base URL。 |

---

## 🔄 二、 標準前端構建與本地整合

在 v4.0.0 架構下，前端升級為 React 18 + Vite + TypeScript 應用：

### 1. 前端構建指令
```powershell
# 進入前端專案
cd frontend

# 安裝相依套件 (若未安裝)
npm install

# 編譯 TypeScript 並打包生產環境產物至 frontend/dist/
npm run build

# 返回專案根目錄
cd ..
```

### 2. 後端伺服器自動掛載機制
[`backend/app.py`](file:///c:/Users/Administrator/Desktop/Write_Novel/backend/app.py) 內建智能靜態資源解析邏輯：
```python
base_frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
dist_dir = os.path.join(base_frontend_dir, "dist")
legacy_static_dir = os.path.join(base_frontend_dir, "static")

static_dir = dist_dir if (os.path.exists(dist_dir) and os.path.exists(os.path.join(dist_dir, "index.html"))) else legacy_static_dir
```
- 若 `frontend/dist/` 存在，FastAPI 優先對外服務最新 React 應用。
- 若 `dist/` 不存在，自動備援降級為 `frontend/static/`。

---

## 📱 三、 Android APK 打包支援

前端架構具備良好的跨平台解耦設計（[`frontend/src/platform/index.ts`](file:///c:/Users/Administrator/Desktop/Write_Novel/frontend/src/platform/index.ts)）：

1. **相對路徑配置**：[`frontend/vite.config.ts`](file:///c:/Users/Administrator/Desktop/Write_Novel/frontend/vite.config.ts) 已配置 `base: './'`，所有 CSS、JS 與靜態資源均以相對路徑引入，相容於 `file:///` 協議。
2. **Capacitor 封裝範例**：
   ```powershell
   cd frontend
   npm install @capacitor/core @capacitor/cli @capacitor/android
   npx cap init "AI Novel Factory" "com.novel.factory" --web-dir "dist"
   npx cap add android
   npx cap sync
   npx cap open android
   ```
3. **動態後端對接**：在 Android APK 內部，使用者可於「系統設定」介面輸入遠端伺服器之 API Base URL，設定將自動存入設備端 LocalStorage，實現隨身隨地創作。

---

## ☁️ 四、 雲端無人值守生成 (Autonomous Pipeline) 設計核心

1. **後端大腦自主推進**：
   - 前端不涉入任何創作決策邏輯。
   - 後端收到啟動指令後，AI 總監自動檢查作品進度：
     - 若無世界觀 ➔ 自動規劃世界觀設定。
     - 若無角色 ➔ 自動規劃角色聖經。
     - 若無大綱 ➔ 自動規劃全套結構。
     - 逐章推進寫作、自動登錄時序記憶圖譜與評估反饋。
2. **斷線續寫與進度輪詢**：
   - 寫作進度即時寫入本地 SQLite，並向 Hugging Face Storage Bucket 進行安全同步。
   - 前端藉由 `/api/pipeline/auto-status` 每 3 秒輪詢一次狀態，即使關閉瀏覽器，後端持續自主創作。
3. **多小說平行並行創作**：
   - 後端 `AutonomousPipelineManager` 支援多執行緒實例，可同時在背景並行多部作品之創作。


---

## 🚀 五、 本地打包控制與 GitHub 遠端自動編譯

### 1. 本地打包 (uild_app.py)
`powershell
python build_app.py --target apk  # Android APK (mykey / 123456 永久固定簽名)
python build_app.py --target exe  # Windows 綠色免安裝可執行程式
`

### 2. GitHub Actions 遠端自動編譯發布
- 工作流路徑：.github/workflows/build_and_release.yml
- 當程式碼推送至 master 分支或建立發布標籤時，自動執行三階段建置：
  1. 執行 Pytest 全套自動化測試與前端打包。
  2. 構建並簽名 Android APK，發布為 Actions Artifact。
  3. 封裝 Windows 獨立執行程式 ZIP 壓縮包，發布為 Actions Artifact。
