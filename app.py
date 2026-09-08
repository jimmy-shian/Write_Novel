# -*- coding: utf-8 -*-
"""
Hugging Face Spaces 入口檔案 (Gradio SDK + ZeroGPU 相容)
提供小說工廠後端 RESTful API、雲端無人值守自主流水線 (Autonomous Pipeline) 與全域 CORS 跨網域存取。
前端由 GitHub Pages (https://jimmy-shian.github.io/Write_Novel/) 獨立託管。
"""

import os

try:
    import gradio as gr
    from gradio.routes import App
    HAS_GRADIO = hasattr(gr, "Blocks") and hasattr(App, "create_app")
except (ImportError, AttributeError):
    HAS_GRADIO = False

from starlette.routing import Mount
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from backend.services.hf_sync import get_sync_status, backup_database, restore_database, async_backup
from backend.services.autonomous_pipeline import autonomous_manager
from backend.app import api_router, api_routers, api_generation_task, get_static_dir, app as backend_app
import backend.persistence as db

# 雲端啟動時優先還原資料庫
restore_database(force=False)
db.db_init()

try:
    import spaces

    @spaces.GPU
    def _zero_gpu_worker(text: str = ""):
        return f"ZeroGPU Ready: {text}"
except ImportError:
    def _zero_gpu_worker(text: str = ""):
        return f"CPU Ready: {text}"

if HAS_GRADIO:
    # --- Hook Gradio App.create_app 注入 API 路由與最高優先級 ---
    _orig_create_app = App.create_app

    def _custom_create_app(*args, **kwargs):
        app = _orig_create_app(*args, **kwargs)

        # 0. 啟用全域 CORS 跨網域存取支援 (允許 GitHub Pages 呼叫)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # 1. 統一掛載靜態前端 (優先掛載 React dist)
        static_dir = get_static_dir()
        if static_dir and os.path.exists(static_dir):
            app.router.routes.insert(0, Mount("/novel_static", StaticFiles(directory=static_dir), name="novel_static"))

        # 2. 註冊單一真實來源 API 路由 (/api)
        app.include_router(api_router)

        # 3. 註冊雲端與歷史相容別名前綴 (/gradio_api/novel, /novel_api, /novel)
        for prefix in ["/gradio_api/novel", "/novel_api", "/novel"]:
            for sub_router in api_routers:
                app.include_router(sub_router, prefix=prefix)
            app.add_api_route(f"{prefix}/generation-task", api_generation_task, methods=["POST"])

        return app

    App.create_app = _custom_create_app

    # --- 建立 Gradio 後端服務入口與資訊面板 ---
    with gr.Blocks(title="AI Novel Factory 雲端算力中心", theme=gr.themes.Soft()) as demo:
        # 註冊 ZeroGPU 事件以通過啟動掃描校驗
        dummy_in = gr.Textbox(visible=False)
        dummy_out = gr.Textbox(visible=False)
        dummy_btn = gr.Button("ZeroGPU Init", visible=False)
        dummy_btn.click(fn=_zero_gpu_worker, inputs=dummy_in, outputs=dummy_out)

        gr.HTML(
            """
            <div style="background: linear-gradient(135deg, #1e1e2f 0%, #2d2b55 100%); padding: 28px; border-radius: 14px; margin-bottom: 20px; color: #fff; box-shadow: 0 8px 30px rgba(0,0,0,0.25);">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 20px;">
                    <div>
                        <h1 style="margin: 0 0 8px 0; font-size: 26px; font-weight: 700; color: #fff;">🌌 AI Novel Factory 雲端算力中心 (Backend Service)</h1>
                        <p style="margin: 0; font-size: 14px; color: #cbd5e1; line-height: 1.6;">
                            ⚡ 後端 API 服務運行中｜支援關閉瀏覽器與電腦，雲端自主全自動創作小說並同步持久化
                        </p>
                    </div>
                    <div>
                        <a href="https://jimmy-shian.github.io/Write_Novel/" target="_blank" style="background: #6366f1; color: #fff; padding: 12px 24px; border-radius: 10px; text-decoration: none; font-weight: 700; font-size: 16px; box-shadow: 0 4px 15px rgba(99,102,241,0.5); display: inline-flex; align-items: center; gap: 8px;">
                            🌐 開啟專屬 GitHub Pages 前端 ↗
                        </a>
                    </div>
                </div>
            </div>
            """
        )

        with gr.Tab("📊 即時背景生成監控 (Live Status)"):
            gr.Markdown(
                """
                > **💡 系統提示**：本頁面為純後端即時狀態監控看板。所有小說創作、大綱閱讀、章節檢視與一鍵無人值守生成，請直接至 [GitHub Pages 前端](https://jimmy-shian.github.io/Write_Novel/) 操作。
                """
            )
            auto_status_box = gr.JSON(value=autonomous_manager.get_status, label="當前雲端無人值守流水線執行狀態 (每 3 秒自動更新)", every=3)

        with gr.Tab("📖 系統架構與使用指南 (Guide)"):
            gr.Markdown(
                """
                ### 🏛️ 雲端小說工廠架構說明

                本系統採用 **前後端分離 ＋ 雲端無人值守自主創作** 架構：

                ```text
                [👤 使用者]
                    │ (1. 開啟網頁點擊「☁️ 雲端無人值守」)
                    ▼
                [🌐 GitHub Pages 前端] ──(呼叫 API)──> [⚡ Hugging Face Space 後端 (本伺服器)]
                    │                                           │
                    │ (2. 使用者可直接關閉網頁/關機)              │ (3. 背景守護執行緒自主調度 7 大 Agent)
                    │                                           ▼
                    │                                     [🤖 AI 總監自主流水線]
                    │                                      世界觀 ➔ 角色 ➔ 伏筆 ➔ 分卷 ➔ 細綱 ➔ 逐章寫作與精修
                    │                                           │
                    │ (4. 隨時打開網頁即時呈現)                   │ (5. 每完成一章自動持久化)
                    └───────────────────────────────────────────┴──> [💾 私有 Dataset 儲存庫]
                ```

                ---

                ### 🚀 快速上手流程

                1. **開啟前端頁面**：造訪 [https://jimmy-shian.github.io/Write_Novel/](https://jimmy-shian.github.io/Write_Novel/)
                2. **連線伺服器**：在前端填入本 Space 後端網址（`https://botsz-writenovel.hf.space`）。
                3. **啟動自主創作**：選定小說並點擊右上角 **`☁️ 雲端無人值守`**。
                4. **關閉電腦/瀏覽器**：雲端伺服器在背景全自動創作，每寫完一章自動存檔並備份至私有 Dataset。
                5. **隨時查看**：任何時候重新打開前端網頁，所有已完成的章節自動完整入庫呈現！

                ---

                ### 📡 核心 API 端點清單

                | 方法 | 端點路徑 | 說明 |
                | :---: | :--- | :--- |
                | `GET` | `/gradio_api/novel/novels` | 獲取雲端資料庫小說清單 |
                | `GET` | `/gradio_api/novel/pipeline/auto-status` | 獲取當前無人值守流水線執行進度與日誌 |
                | `POST` | `/gradio_api/novel/pipeline/auto-run` | 啟動雲端無人值守全自動小說創作任務 |
                | `POST` | `/gradio_api/novel/pipeline/auto-stop` | 安全中止當前背景生成任務 |
                | `GET` | `/gradio_api/novel/sync/status` | 檢查私有 Dataset 資料庫備份同步狀態 |
                """
            )

        with gr.Tab("💾 資料庫持久化狀態 (Storage Status)"):
            gr.Markdown("### 📦 私有 Dataset 資料庫即時備份狀態 (`botsz/writenovel-storage`)")
            sync_status_box = gr.JSON(value=get_sync_status, label="當前資料庫持久化狀態 (每 5 秒自動更新)", every=5)
else:
    app = backend_app
    demo = None

if __name__ == "__main__":
    port = int(os.environ.get("GRADIO_SERVER_PORT") or os.environ.get("PORT") or os.environ.get("APP_PORT") or 7860)
    if HAS_GRADIO and demo is not None:
        print(f"Launching AI Novel Factory Backend (Gradio Cloud Mode) on port {port}...")
        demo.launch(
            server_name="0.0.0.0",
            server_port=port,
            prevent_thread_lock=False,
        )
    else:
        import uvicorn
        print(f"Launching AI Novel Factory Backend (FastAPI Mode) on port {port}...")
        uvicorn.run(backend_app, host="0.0.0.0", port=port)
