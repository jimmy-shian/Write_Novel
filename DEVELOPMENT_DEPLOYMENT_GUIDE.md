# 📖 AI Novel Factory 開發與多分支部署守則

本專案採用嚴謹的「多分支解耦架構」，實現**本機純淨開發**、**雲端算力與無人值守後端**、以及 **GitHub Pages 前端靜態發布**三者完全解耦。

---

## 🏛️ 一、 分支職責架構一覽

| 分支名稱 | 角色定位 | 部署目標 | 核心職責與內容 |
| :--- | :--- | :--- | :--- |
| **`master`** | **本機標準版** | 本地開發環境 (Local) | • 純本機 FastAPI + SQLite + 前端靜態伺服器。<br>• 保持最純淨的本地開發環境，不包含雲端入口與部署雜訊。<br>• 本地開發、測試、修復 Bug 主要在此分支進行。 |
| **`feat/cloud-hybrid-deployment`** | **雲端混合部署版** | Hugging Face Spaces (後端) | • 包含 `autonomous_pipeline.py` 雲端無人值守引擎。<br>• 包含 Hugging Face Dataset 逐章自動持久化備份。<br>• 包含 Space 算力入口 `app.py`、CORS 與 `/gradio_api/novel` API 路由。<br>• 此分支為 Hugging Face Space 後端運行的真實代碼源。 |
| **`gh-pages`** | **前端展示發布版** | GitHub Pages (前端) | • 由 `docs/`（即最新 `frontend/static`）自動拆分發布。<br>• 託管於 `https://jimmy-shian.github.io/Write_Novel/`。<br>• 純靜態前端，作為創作看板、閱讀器與無人值守觸發介面。<br>• 透過通用伺服器設定連接個人的 Hugging Face Space 後端。 |

---

## 🔄 二、 當 `master` 修改後，如何同步更新所有分支？

### 🌟 方式 A：一鍵全自動同步腳本（強烈推薦）

當您在 `master` 完成代碼修改與本地測試後，直接在終端機執行：

```powershell
C:\Users\Administrator\venv\Scripts\python.exe scripts/sync_deployment.py
```

腳本會全自動安全執行以下 5 大步驟：
1. **[Step 1]** 確保 `master` 乾淨：將 `frontend/static` 複製覆蓋到 `docs/`，提交並推送到 `origin/master`。
2. **[Step 2]** 切換至 `feat/cloud-hybrid-deployment`：將 `master` 最新變更合併進來，推送到 `origin/feat/cloud-hybrid-deployment`。
3. **[Step 3]** 發布 GitHub Pages：透過 `git subtree split` 將 `docs/` 強制推送到 `origin/gh-pages`。
4. **[Step 4]** 部署 Hugging Face Space：將包含 `app.py`、`autonomous_pipeline.py` 的雲端後端完整代碼上傳至 Space。
5. **[Step 5]** 安全切回 `master` 分支：確保日常開發環境始終保持在乾淨的 `master` 上。

---

### 🛠️ 方式 B：手動標準流程

如果需要手動分步操作，請依照下列標準順序：

```powershell
# 1. 在 master 分支更新 docs/ 並推送
git checkout master
python -c "import shutil, os; shutil.rmtree('docs', ignore_errors=True); shutil.copytree('frontend/static', 'docs')"
git add -A && git commit -m "chore: sync frontend to docs"
git push origin master

# 2. 切換至 feat/cloud-hybrid-deployment 分支並合併 master
git checkout feat/cloud-hybrid-deployment
git merge master
git push origin feat/cloud-hybrid-deployment

# 3. 發布至 gh-pages 前端
git subtree split --prefix docs -b gh-pages-auto-sync
git push -f origin gh-pages-auto-sync:gh-pages
git branch -D gh-pages-auto-sync

# 4. 部署至 Hugging Face Space (botsz/WriteNovel)
python -c "from huggingface_hub import HfApi, os; HfApi(token=os.getenv('HF_TOKEN')).upload_folder(folder_path='.', repo_id='botsz/WriteNovel', repo_type='space', ignore_patterns=['.git/**', 'data/*.db*', 'tests/**', 'scratch/**'])"

# 5. 切回 master 分支
git checkout master
```

---

## 🧠 三、 雲端無人值守生成 (Autonomous Pipeline) 設計核心

1. **後端大腦自主判斷與接續**：
   * 前端不干預任何階段的推進邏輯。
   * 後端收到啟動指令後，AI 總監會**自動檢查小說進度**：
     * 若無世界觀 ➔ 自動規劃世界觀。
     * 若無角色 ➔ 自動設計角色。
     * 若無伏筆/分卷/細綱 ➔ 自動規劃全套結構。
     * 若已存在第 1~N 章 ➔ **智慧跳過已完成章節，接續撰寫後續章節**。
     * 每章撰寫並經編輯精修後，**自動即時備份至私有 Dataset**。
2. **前端純粹作為即時看板**：
   * 點擊「☁️ 雲端無人值守」直接一鍵觸發，無需輸入任何繁瑣參數。
   * 右下角浮動進度看板每 3 秒自動向後端查詢狀態，即時動態入庫顯示。
   * 使用者可隨時關閉瀏覽器與電腦，後端背景持續自主創作。
3. **總監對話與章節編輯器即時連動**：
   * 後端無人值守引擎每完成一個創作階段（世界觀、角色、伏筆、分卷、細綱骨架）與每一章正文潤色，都會主動向 `chat_memory` 寫入總監巡檢通報。
   * 前端輪詢到章節或階段推進時，自動切換焦點章節、刷新正文編輯器，並重繪右側「Co-pilot 小說總監」對話紀錄，達成完全即時動態看台效果。

