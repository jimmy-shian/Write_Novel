# -*- coding: utf-8 -*-
"""AI Novel Factory - Electron sidecar 無頭後端入口 (僅包裝用)

由 Electron main process 啟動：
    AI_Novel_Factory_Backend.exe --port 8000

特性：
- 不開啟瀏覽器、不讀取 stdin（Electron 負責開視窗）
- DB / gold_rules 路徑由環境變數決定：
    DB_PATH        -> 預設 <專案>/data/novel_factory.db
    GOLD_RULES_DIR -> 預設 <專案>/backend/data/gold_rules
  Electron 版會把兩者都指向 %USERPROFILE%\\.ai-novel-factory，
  dev / start.bat / HF 行為完全不變。
"""
import argparse
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Novel Factory headless backend (Electron sidecar)")
    parser.add_argument("--host", default=os.environ.get("APP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("APP_PORT", "8000")))
    args = parser.parse_args()

    print(f"[backend] starting on http://{args.host}:{args.port}", flush=True)
    print(f"[backend] DB_PATH={os.environ.get('DB_PATH', '<default>')}", flush=True)
    print(f"[backend] GOLD_RULES_DIR={os.environ.get('GOLD_RULES_DIR', '<default>')}", flush=True)

    import uvicorn
    from backend.app import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
