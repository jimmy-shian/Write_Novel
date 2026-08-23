# -*- coding: utf-8 -*-
"""
Autonomous Background Pipeline Service (雲端無人值守自主創作服務)
在 Hugging Face 後端以守護執行緒運行完整的長篇小說生成工作流，
使用者可完全關閉瀏覽器與電腦，後端自動逐階段、逐章節調度 Agent 並定時持久化至 Dataset。
"""

import threading
import time
import datetime
from typing import Dict, Any, List, Optional

from backend import persistence as db
from backend.services.hf_sync import async_backup, backup_database
from backend.generation.routing.router import execute_generation_task


class AutonomousPipelineManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AutonomousPipelineManager, cls).__new__(cls)
                cls._instance._init_state()
            return cls._instance

    def _init_state(self):
        self.is_running = False
        self.stop_requested = False
        self.novel_id: Optional[str] = None
        self.novel_title: str = ""
        self.current_stage: str = "idle"
        self.current_chapter: int = 0
        self.total_chapters: int = 0
        self.progress_percent: int = 0
        self.status_message: str = "等待啟動"
        self.logs: List[Dict[str, str]] = []
        self.error: Optional[str] = None
        self.start_time: Optional[str] = None
        self.worker_thread: Optional[threading.Thread] = None

    def _log(self, message: str, level: str = "info"):
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        entry = {"time": now_str, "msg": message, "level": level}
        self.logs.append(entry)
        if len(self.logs) > 100:
            self.logs = self.logs[-100:]
        print(f"[AutonomousPipeline] [{now_str}] {message}")

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "is_running": self.is_running,
                "novel_id": self.novel_id,
                "novel_title": self.novel_title,
                "current_stage": self.current_stage,
                "current_chapter": self.current_chapter,
                "total_chapters": self.total_chapters,
                "progress_percent": self.progress_percent,
                "status_message": self.status_message,
                "logs": list(self.logs),
                "error": self.error,
                "start_time": self.start_time,
            }

    def start_pipeline(self, novel_id: str, prompt: str = "", max_chapters: int = 5) -> Dict[str, Any]:
        with self._lock:
            if self.is_running:
                return {"status": "already_running", "message": "已有自主生成任務在背景運行中"}

            novel = db.get_novel(novel_id)
            if not novel:
                return {"status": "error", "message": f"找不到小說 (ID: {novel_id})"}

            self._init_state()
            self.is_running = True
            self.stop_requested = False
            self.novel_id = novel_id
            self.novel_title = novel.get("title", "未命名小說")
            self.start_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.status_message = "🚀 雲端無人值守生成啟動中..."
            self._log(f"啟動小說《{self.novel_title}》的雲端無人值守全自動創作任務")

            self.worker_thread = threading.Thread(
                target=self._run_autonomous_flow,
                args=(novel_id, prompt, max_chapters),
                daemon=True,
            )
            self.worker_thread.start()

            return {
                "status": "started",
                "novel_id": novel_id,
                "novel_title": self.novel_title,
                "message": "雲端自主創作任務已在背景成功啟動！您可以隨時關閉網頁。",
            }

    def stop_pipeline(self) -> Dict[str, Any]:
        with self._lock:
            if not self.is_running:
                return {"status": "not_running", "message": "目前沒有正在運行的任務"}
            self.stop_requested = True
            self.status_message = "🛑 正在等待當前步驟完成後中止..."
            self._log("使用者請求中止雲端自主生成任務", level="warn")
            return {"status": "stopping", "message": "已發送中止請求，將於當前章節完成後安全停止"}

    def _execute_stage(self, stage: str, task_type: str, instruction: str, user_prompt: str, scope: str = "global", target: Optional[Dict[str, Any]] = None, extra_body: Optional[Dict[str, Any]] = None) -> Any:
        payload = {
            "novel_id": self.novel_id,
            "task_type": task_type,
            "stage": stage,
            "scope": scope,
            "target": target or {},
            "context_mode": "full",
            "instruction": instruction,
            "user_prompt": user_prompt,
            "options": {
                "stream": False,
                "save_to_db": True,
                "auto_accept": True,
            },
            "frontend_state": {},
        }
        if extra_body:
            payload.update(extra_body)

        resp = execute_generation_task(payload)
        if not resp.ok:
            raise RuntimeError(f"Stage {stage} execution failed: {resp.error}")
        return resp

    def _run_autonomous_flow(self, novel_id: str, initial_prompt: str, max_chapters: int):
        try:
            # 1. 檢查並生成世界觀
            if self.stop_requested: return
            wb = db.get_latest_worldbuilding(novel_id)
            if not wb or not wb.get("content"):
                self.current_stage = "worldview"
                self.progress_percent = 5
                self.status_message = "正在由總監規劃宏觀世界觀與核心設定..."
                self._log("開始生成宏觀世界觀設定...")
                self._execute_stage(
                    stage="worldview",
                    task_type="generate",
                    instruction="請為本小說構建完整的世界觀設定、力量體系與時代背景",
                    user_prompt=initial_prompt or "請根據小說核心構想設計世界觀",
                )
                self._log("✅ 世界觀設定已完成並持久化！")
                db.save_chat_message(novel_id, "assistant", "🌍 **【總監通報】** 世界觀設定與力量體系已規劃完成並存入數據庫！", message_type="chat")
                async_backup(reason="Autonomous flow: worldview finished")

            # 2. 檢查並生成主要角色設定
            if self.stop_requested: return
            chars = db.get_latest_characters(novel_id)
            if not chars or not chars.get("parsed_data"):
                self.current_stage = "characters"
                self.progress_percent = 15
                self.status_message = "正在設計核心主角群與配角人設檔案..."
                self._log("開始生成角色設定...")
                self._execute_stage(
                    stage="characters",
                    task_type="generate",
                    instruction="請設計立體豐富的主角、主要配角與反派角色設定",
                    user_prompt=initial_prompt or "請根據世界觀塑造核心角色",
                )
                self._log("✅ 角色設定已完成並持久化！")
                db.save_chat_message(novel_id, "assistant", "👥 **【總監通報】** 核心主角群與配角人設檔案已設計完成！", message_type="chat")
                async_backup(reason="Autonomous flow: characters finished")

            # 3. 檢查並編織全局伏筆
            if self.stop_requested: return
            seeds = db.get_foreshadowing_seeds(novel_id)
            if not seeds:
                self.current_stage = "foreshadowing"
                self.progress_percent = 25
                self.status_message = "正在編織全局懸念與長線伏筆網絡..."
                self._log("開始編織全書伏筆網絡...")
                self._execute_stage(
                    stage="foreshadowing",
                    task_type="generate",
                    instruction="請為全書埋設貫穿全局的重大懸念與分卷伏筆",
                    user_prompt="設計核心主線伏筆",
                )
                self._log("✅ 伏筆網絡已編織完成！")
                db.save_chat_message(novel_id, "assistant", "🕸️ **【總監通報】** 全局懸念與長線伏筆網絡已編織完成！", message_type="chat")

            # 4. 檢查並規劃分卷結構
            if self.stop_requested: return
            vols = db.get_volumes(novel_id)
            if not vols:
                self.current_stage = "volumes"
                self.progress_percent = 35
                self.status_message = "正在規劃全書分卷大綱與高潮節奏..."
                self._log("開始規劃分卷架構...")
                self._execute_stage(
                    stage="volumes",
                    task_type="generate",
                    instruction="請規劃全書分卷架構，包含各卷核心矛盾、起承轉合與終局高潮",
                    user_prompt="規劃分卷大綱",
                )
                self._log("✅ 分卷架構規劃完成！")
                db.save_chat_message(novel_id, "assistant", "📚 **【總監通報】** 全書分卷結構與高潮節奏已規劃就緒！", message_type="chat")
                async_backup(reason="Autonomous flow: volumes finished")

            # 5. 檢查並規劃篇卷骨架 (各章節細綱)
            if self.stop_requested: return
            plot_data = db.get_stitched_plot(novel_id)
            planned_chapters = plot_data.get("chapters", []) if plot_data else []
            if not planned_chapters:
                self.current_stage = "volume_skeleton"
                self.progress_percent = 45
                self.status_message = "正在生成第一卷的逐章詳細情節骨架..."
                self._log("開始生成篇卷章節骨架細綱...")
                self._execute_stage(
                    stage="volume_skeleton",
                    task_type="generate",
                    instruction="請詳細規劃各章的情節要點、視角人物、場景與伏筆回收點",
                    user_prompt="生成逐章詳細細綱",
                )
                self._log("✅ 章節細綱骨架規劃完成！")
                db.save_chat_message(novel_id, "assistant", "📝 **【總監通報】** 各章節詳細情節骨架與細綱已生成完畢！", message_type="chat")
                plot_data = db.get_stitched_plot(novel_id)
                planned_chapters = plot_data.get("chapters", []) if plot_data else []

            # 6. 逐章撰寫與精修 (智慧接續未完成之章節)
            total_target = len(planned_chapters) if planned_chapters else max_chapters
            if total_target <= 0:
                total_target = max_chapters or 10

            self.total_chapters = total_target
            self._log(f"進入正文寫作流水線，全書共規劃 {total_target} 章節")

            # 讀取目前資料庫已存在且有內容的章節
            existing_db_chapters = db.get_chapters(novel_id)
            written_indices = {int(c.get("chapter_index") or 0) for c in existing_db_chapters if c.get("content") and len(c.get("content", "").strip()) > 50}

            for ch_idx in range(1, total_target + 1):
                if self.stop_requested:
                    self._log(f"任務已安全停止於第 {ch_idx - 1} 章", level="warn")
                    break

                self.current_chapter = ch_idx
                base_pct = 50 + int((ch_idx - 1) / total_target * 45)
                self.progress_percent = base_pct

                # 若該章節已被撰寫過，後端智慧直接略過並接續下一章
                if ch_idx in written_indices:
                    self._log(f"第 {ch_idx} 章已存在完整內容，跳過並接續下一章。")
                    continue

                # (1) 正文寫作
                self.current_stage = f"writer_ch{ch_idx}"
                self.status_message = f"✍️ 正在由 Writer Agent 撰寫第 {ch_idx}/{total_target} 章正文..."
                self._log(f"開始撰寫第 {ch_idx} 章正文...")

                self._execute_stage(
                    stage="writer",
                    task_type="generate",
                    scope="chapter",
                    target={"chapter_index": ch_idx},
                    instruction=f"請根據大綱撰寫第 {ch_idx} 章的完整故事正文，著重視角、心理、對白與感官細節",
                    user_prompt=f"撰寫第 {ch_idx} 章",
                )
                self._log(f"第 {ch_idx} 章初稿撰寫完成！")

                # (2) 編輯精修
                if self.stop_requested: break
                self.current_stage = f"editor_ch{ch_idx}"
                self.status_message = f"🔍 正在由 Editor Agent 精修第 {ch_idx}/{total_target} 章文字與修辭..."
                self._log(f"開始對第 {ch_idx} 章進行潤色與精修...")

                self._execute_stage(
                    stage="editor",
                    task_type="refine",
                    scope="chapter",
                    target={"chapter_index": ch_idx},
                    instruction=f"請對第 {ch_idx} 章進行修辭優化、節奏微調與行文潤色",
                    user_prompt=f"精修第 {ch_idx} 章",
                )
                self._log(f"✅ 第 {ch_idx} 章精修完成並已存入資料庫！")
                db.save_chat_message(
                    novel_id,
                    "assistant",
                    f"✍️ **【總監通報】** 第 {ch_idx} 章正文已由 Writer 撰寫並經 Editor 潤色精修完成，已成功入庫！\n- 進度：第 {ch_idx}/{total_target} 章 ({self.progress_percent}%)",
                    message_type="chat"
                )

                # (3) 每完成一章即時同步至私有 Dataset
                async_backup(reason=f"Autonomous flow: Chapter {ch_idx} completed")
                time.sleep(2)

            if not self.stop_requested:
                self.progress_percent = 100
                self.current_stage = "completed"
                self.status_message = f"🎉 雲端無人值守生成圓滿完成！全書 {self.total_chapters} 章已全數就緒。"
                self._log(f"🎉 創作任務大功告成！所有內容已完整備份至私有雲端 Dataset。")
                db.save_chat_message(novel_id, "assistant", f"🎉 **【總監通報】** 小說全書 {self.total_chapters} 章全自動創作已圓滿完成！所有正文已安全備份至私有雲端 Dataset。", message_type="chat")
                backup_database(reason="Autonomous flow: all completed", force=True)

        except Exception as exc:
            err_msg = str(exc)
            self.error = err_msg
            self.current_stage = "error"
            self.status_message = f"❌ 執行中斷: {err_msg}"
            self._log(f"執行出錯: {err_msg}", level="error")
        finally:
            self.is_running = False
            self.stop_requested = False


# 全域單例管理器
autonomous_manager = AutonomousPipelineManager()
