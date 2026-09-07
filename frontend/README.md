# 🎨 AI Novel Factory - Frontend (React + TypeScript + OpenDesign)

本目錄為 **AI Novel Factory (v4.0.0)** 現代化前端單頁應用程式（SPA），採用 **React 18 + Vite + TypeScript** 構建，落實 **OpenDesign** 極簡暗黑無 Emoji 設計系統。

---

## 📁 目錄結構

```
frontend/
├── dist/                         # npm run build 輸出的生產發布包 (FastAPI 自動掛載)
├── index.html                    # 應用程式入口 HTML (嚴格 0 處 inline styles)
├── package.json                  # 前端相依設定
├── tsconfig.json                 # TypeScript 編譯器配置 (包含 @/ 路徑別名)
├── vite.config.ts                # Vite 構建配置 (base: './', /api 代理)
└── src/
    ├── main.tsx                  # React 應用程式掛載進入點
    ├── App.tsx                   # 根容器元件 (4 欄式網格 + 行動抽屜切換)
    ├── api/                      # 後端 API 客戶端
    │   ├── client.ts             # 基礎 fetch 封裝 (含平台 Base URL 解析)
    │   ├── novels.ts             # 小說與章節 CRUD
    │   ├── temporal.ts           # Graphiti 時序記憶圖譜與切片端點
    │   ├── terms.ts              # 故事專用術語庫 (Glossary)
    │   ├── proposals.ts          # 草稿提案與 Diff 套用
    │   ├── generation.ts         # SSE 串流任務與自主寫作管線
    │   └── settings.ts           # 系統參數與動態模型探索
    ├── components/
    │   ├── common/               # OpenDesign 基礎元件 (Button, Badge, StatusDot, CopyCard, ModelChip, Modal, Icons)
    │   ├── layout/               # 佈局元件 (ActivityRail, ExplorerDrawer, WorkspaceHeader, BottomDock, MobileNav)
    │   ├── editor/               # 正文畫布 (EditorPane), 差異對比器 (DiffViewer), 提案收件箱 (ProposalInbox)
    │   ├── graph/                # 時序記憶面板 (TemporalGraphBoard)
    │   ├── copilot/              # AI 導演總控室 (CopilotDrawer)
    │   └── settings/             # 設定對話框 (SettingsModal), 術語庫對話框 (TermsModal)
    ├── config/
    │   └── version.ts            # 單一事實來源版本號 (引用根目錄 version.json)
    ├── hooks/
    │   ├── useNovel.ts           # 小說與章節狀態機、Dirty Check、自動儲存
    │   ├── useTemporalGraph.ts   # Graphiti 時序切片資料快取與操作
    │   └── useProposals.ts       # 草稿提案與 Diff 審閱狀態機
    ├── platform/
    │   └── index.ts              # 平台抽象層 (Web, Android APK, Desktop)
    ├── styles/
    │   └── opendesign.css        # OpenDesign 完整樣式系統 (嚴格禁止 Inline Styles)
    └── utils/
        ├── diff.ts               # 自製 LCS 行級差異對比演算法
        └── clipboard.ts          # 1-Click 一鍵複製工具 (無 Inline Styles)
```

---

## 🛠️ 開發與構建指令

```powershell
# 1. 安裝相依套件
npm install

# 2. 本地開發伺服器 (包含 HMR 熱重載)
npm run dev

# 3. 類型檢查與生產環境構建
npm run build
```

---

## 📐 設計與編碼守則

1. **嚴格禁止 Inline Styles**：
   - 嚴格禁止在 JSX 或 HTML 元素使用 `style={{...}}` 或 `style="..."`。
   - 所有版面間距、色彩、字體大小與動態狀態均必須透過 `opendesign.css` 的 CSS 類別控制。
2. **無 Emoji 政策**：
   - 介面禁止使用卡通 Emoji，統一使用輕量向量 SVG（`components/common/Icons.tsx`）與 6px 狀態指示圓點（`StatusDot`）。
3. **平台解耦與 APK 打包相容**：
   - 所有資源相對引用（`base: './'`），相容於 Capacitor / Cordova 容器封裝為 Android APK。
   - 透過 `platform/index.ts` 取得或設定後端 API 地址。
