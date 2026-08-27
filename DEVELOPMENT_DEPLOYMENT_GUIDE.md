# 📖 AI Novel Factory 開發與雲端部署守則

本專案採用精簡高效的單一主分支架構（Single Mainstream Architecture），主分支 `master` 即為全功能唯一代碼源（Single Source of Truth），同時支援**本機獨立開發**、**Hugging Face Spaces 雲端無人值守後端**、以及 **GitHub Pages 前端靜態託管**。

---

## 🏛️ 一、 分支架構與職責一覽

| 分支名稱 | 角色定位 | 部署目標 | 核心職責與內容 |
| :--- | :--- | :--- | :--- |
| **`master`** | **唯一主分支 (Source of Truth)** | • 本地開發環境 (Local)<br>• GitHub 核心代碼庫<br>• Hugging Face Spaces (後端) | • 包含本機 FastAPI / Gradio 雙入口與 SQLite 資料庫。<br>• 包含 `autonomous_pipeline.py` 雲端無人值守自主創作引擎。<br>• 包含 Hugging Face Storage Bucket 零 Commit 原地持久化同步。<br>• 所有開發、測試、修復與雲端後端部署皆由此分支直接驅動。 |
| **`gh-pages`** | **前端靜態託管發布版** | GitHub Pages (前端網站) | • 由 `docs/`（即最新 `frontend/static`）自動拆分發布。<br>• 託管於 `https://jimmy-shian.github.io/Write_Novel/`。<br>• 純靜態前端，作為小說創作面板、閱讀器與無人值守看台。<br>• 透過通用伺服器設定連接個人的 Hugging Face Space 後端。 |

---

## 🔄 二、 一鍵全自動同步與發布流程

### 🌟 一鍵全自動同步腳本（強烈推薦）

當您在 `master` 完成代碼修改與本地測試後，直接在終端機執行：

```powershell
C:\Users\Administrator\venv\Scripts\python.exe scripts/sync_deployment.py
```

腳本會全自動安全執行以下 3 大步驟：
1. **[Step 1] 同步前端至 docs/ 並推送到 GitHub master**：將 `frontend/static` 完整複製覆蓋至 `docs/`，提交並推送至 `origin/master`。
2. **[Step 2] 發布至 GitHub Pages**：透過 `git subtree split` 將 `docs/` 自動推送到 `origin/gh-pages` 分支。
3. **[Step 3] 部署至 Hugging Face Space**：透過 Hugging Face API 將後端代碼完整同步至 `botsz/WriteNovel` Space。

---

### 🛠️ 手動標準發布流程

如果需要手動分步操作，請依照下列標準順序：

```powershell
# 1. 在 master 分支更新 docs/ 並推送至 GitHub
git checkout master
python -c "import shutil, os; shutil.rmtree('docs', ignore_errors=True); shutil.copytree('frontend/static', 'docs')"
git add docs/ frontend/static/
git commit -m "【文件】同步前端資源至 docs/ 發布目錄"
git push origin master

# 2. 發布至 GitHub Pages (gh-pages)
git subtree split --prefix docs -b gh-pages-auto-sync
git push -f origin gh-pages-auto-sync:gh-pages
git branch -D gh-pages-auto-sync

# 3. 部署最新代碼至 Hugging Face Space (botsz/WriteNovel)
python -c "from huggingface_hub import HfApi, os; HfApi(token=os.getenv('HF_TOKEN')).upload_folder(folder_path='.', repo_id='botsz/WriteNovel', repo_type='space', ignore_patterns=['.git/**', 'data/**', '*.db*', '_archive/**', 'tests/**', 'scratch/**'])"
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
     * 平常寫作**毫秒級寫入本地 SQLite**，全書完成時自動原地同步至 Hugging Face Storage Bucket。
2. **前端純粹作為即時看板**：
   * 點擊「☁️ 雲端無人值守」直接一鍵觸發，無需輸入任何繁瑣參數。
   * 右下角浮動進度看板每 3 秒自動向後端查詢狀態，即時動態入庫顯示。
   * 使用者可隨時關閉瀏覽器與電腦，後端背景持續自主創作。
3. **總監對話與章節編輯器即時連動**：
   * 後端無人值守引擎每完成一個創作階段與每一章正文潤色，都會主動向 `chat_memory` 寫入總監巡檢通報。
   * 前端輪詢到進度推進時，自動切換焦點章節、刷新正文編輯器，並重繪右側「Co-pilot 小說總監」對話紀錄，達成完全即時動態看台效果。
4. **多小說平行並行創作支援**：
   * 後端管理員（`AutonomousPipelineManager`）採用多執行緒實例架構（`NovelPipelineTask`）。
   * 使用者可切換至不同小說點擊「☁️ 雲端無人值守」，後端將同時在背景平行運算多本小說，互不干擾。
5. **雲端網路防卡死與自動重試機制 (Auto-Retry with Backoff)**：
   * 引擎內建指數退避重試機制（每階段/每章節最高 5 次自動重試），遇到短暫連線波動或 API 限制時自動休眠並接續重試，徹底解決單篇生成卡死停頓問題。
