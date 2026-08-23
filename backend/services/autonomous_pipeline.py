# -*- coding: utf-8 -*-
"""
Autonomous Background Pipeline Service (雲端多小說並行無人值守自主創作服務)
在 Hugging Face 後端以多執行緒守護架構運行，支援同時觸發多本小說平行全自動生成。
具備自動重試防卡死機制 (Auto-Retry with Exponential Backoff) 與即時總監對話通報。
"""

import threading
import time
import datetime
from typing import Dict, Any, List, Optional

from backend import persistence as db
from backend.services.hf_sync import async_backup, backup_database
from backend.generation.routing.router import execute_generation_task


class NovelPipelineTask:
    """單本小說的自主生成任務狀態實例"""

    def __init__(self, novel_id: str, novel_title: str):
        self.novel_id = novel_id
        self.novel_title = novel_title
        self.is_running = False
        self.stop_requested = False
        self.current_stage = "idle"
        self.current_chapter = 0
        self.total_chapters = 0
        self.progress_percent = 0
        self.status_message = "等待啟動"
        self.logs: List[Dict[str, str]] = []
        self.error: Optional[str] = None
        self.start_time: Optional[str] = None
        self.last_heartbeat: str = datetime.datetime.now().strftime("%H:%M:%S")
        self.worker_thread: Optional[threading.Thread] = None

    def log(self, message: str, level: str = "info"):
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        self.last_heartbeat = now_str
        entry = {"time": now_str, "msg": message, "level": level}
        self.logs.append(entry)
        if len(self.logs) > 100:
            self.logs = self.logs[-100:]
        print(f"[AutoPipeline][{self.novel_title}][{now_str}] {message}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "novel_id": self.novel_id,
            "novel_title": self.novel_title,
            "is_running": self.is_running,
            "current_stage": self.current_stage,
            "current_chapter": self.current_chapter,
            "total_chapters": self.total_chapters,
            "progress_percent": self.progress_percent,
            "status_message": self.status_message,
            "logs": list(self.logs),
            "error": self.error,
            "start_time": self.start_time,
            "last_heartbeat": self.last_heartbeat,
        }


class AutonomousPipelineManager:
    """多小說並行無人值守管理器 (單例模式)"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AutonomousPipelineManager, cls).__new__(cls)
                cls._instance._init_state()
            return cls._instance

    def _init_state(self):
        self.tasks: Dict[str, NovelPipelineTask] = {}

    def get_status(self, novel_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            active_list = [t.to_dict() for t in self.tasks.values() if t.is_running]
            
            # 若指定 novel_id 且存在該任務
            if novel_id and novel_id in self.tasks:
                res = self.tasks[novel_id].to_dict()
                res["active_tasks_count"] = len(active_list)
                res["active_tasks"] = active_list
                return res

            # 若未指定或找不到指定小說，優先回傳任一正在運行的任務
            if active_list:
                res = dict(active_list[0])
                res["active_tasks_count"] = len(active_list)
                res["active_tasks"] = active_list
                return res

            # 若有已存在的歷史任務，回傳最近一個
            if self.tasks:
                last_task = list(self.tasks.values())[-1]
                res = last_task.to_dict()
                res["active_tasks_count"] = 0
                res["active_tasks"] = []
                return res

            # 全空閒狀態
            return {
                "is_running": False,
                "novel_id": None,
                "novel_title": "",
                "current_stage": "idle",
                "current_chapter": 0,
                "total_chapters": 0,
                "progress_percent": 0,
                "status_message": "等待啟動",
                "logs": [],
                "error": None,
                "start_time": None,
                "active_tasks_count": 0,
                "active_tasks": [],
            }

    def start_pipeline(self, novel_id: str, prompt: str = "", max_chapters: int = 5) -> Dict[str, Any]:
        with self._lock:
            if novel_id in self.tasks and self.tasks[novel_id].is_running:
                return {
                    "status": "already_running",
                    "novel_id": novel_id,
                    "novel_title": self.tasks[novel_id].novel_title,
                    "message": f"小說《{self.tasks[novel_id].novel_title}》已有自主生成任務在背景運行中",
                }

            novel = db.get_novel(novel_id)
            if not novel:
                return {"status": "error", "message": f"找不到小說 (ID: {novel_id})"}

            task = NovelPipelineTask(novel_id, novel.get("title", "未命名小說"))
            task.is_running = True
            task.stop_requested = False
            task.start_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            task.status_message = "🚀 雲端無人值守生成啟動中..."
            task.log(f"啟動小說《{task.novel_title}》的雲端無人值守全自動創作任務")

            self.tasks[novel_id] = task

            worker = threading.Thread(
                target=self._run_autonomous_flow,
                args=(task, prompt, max_chapters),
                daemon=True,
            )
            task.worker_thread = worker
            worker.start()

            active_count = len([t for t in self.tasks.values() if t.is_running])
            return {
                "status": "started",
                "novel_id": novel_id,
                "novel_title": task.novel_title,
                "active_tasks_count": active_count,
                "message": f"小說《{task.novel_title}》雲端自主創作任務已在背景成功啟動！(當前共 {active_count} 本並行寫作中)",
            }

    def stop_pipeline(self, novel_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            if novel_id:
                if novel_id not in self.tasks or not self.tasks[novel_id].is_running:
                    return {"status": "not_running", "message": "該小說目前沒有正在運行的任務"}
                task = self.tasks[novel_id]
                task.stop_requested = True
                task.status_message = "🛑 正在等待當前步驟完成後中止..."
                task.log("使用者請求中止本小說的雲端自主生成任務", level="warn")
                return {"status": "stopping", "novel_id": novel_id, "message": f"已發送中止請求，小說《{task.novel_title}》將於當前章節完成後安全停止"}
            else:
                running_tasks = [t for t in self.tasks.values() if t.is_running]
                if not running_tasks:
                    return {"status": "not_running", "message": "目前沒有任何正在運行的任務"}
                for t in running_tasks:
                    t.stop_requested = True
                    t.status_message = "🛑 正在等待當前步驟完成後中止..."
                    t.log("使用者請求全域中止雲端任務", level="warn")
                return {"status": "stopping", "message": f"已對所有 {len(running_tasks)} 本正在生成的小說發送中止請求"}

    def _execute_stage_with_retry(
        self,
        task: NovelPipelineTask,
        stage: str,
        task_type: str,
        instruction: str,
        user_prompt: str,
        scope: str = "global",
        target: Optional[Dict[str, Any]] = None,
        extra_body: Optional[Dict[str, Any]] = None,
        max_retries: int = 5,
    ) -> Any:
        """具備指數退避自動重試與防卡死機制的 Stage 執行器"""
        last_exc = None
        for attempt in range(1, max_retries + 1):
            if task.stop_requested:
                return None
            try:
                payload = {
                    "novel_id": task.novel_id,
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
                if not resp or not resp.ok:
                    err_detail = resp.error if resp else "Empty response returned from generation router"
                    raise RuntimeError(err_detail)
                return resp

            except Exception as exc:
                last_exc = exc
                if attempt >= max_retries or task.stop_requested:
                    raise last_exc
                delay = min(25, 3 * attempt)
                task.log(f"⚠️ [{stage}] 執行波動 ({exc})，將於 {delay} 秒後進行第 {attempt}/{max_retries} 次自動重試...", level="warn")
                time.sleep(delay)

        raise last_exc or RuntimeError(f"Stage {stage} failed after {max_retries} retries")

    def _run_autonomous_flow(self, task: NovelPipelineTask, initial_prompt: str, max_chapters: int):
        novel_id = task.novel_id
        try:
            # 1. 檢查並生成世界觀
            if task.stop_requested: return
            wb = db.get_latest_worldbuilding(novel_id)
            if not wb or not wb.get("content"):
                task.current_stage = "worldview"
                task.progress_percent = 5
                task.status_message = "正在由總監規劃宏觀世界觀與核心設定..."
                task.log("開始生成宏觀世界觀設定...")
                self._execute_stage_with_retry(
                    task=task,
                    stage="worldview",
                    task_type="generate",
                    instruction="請為本小說構建完整的世界觀設定、力量體系與時代背景",
                    user_prompt=initial_prompt or "請根據小說核心構想設計世界觀",
                )
                task.log("✅ 世界觀設定已完成並持久化！")
                db.save_chat_message(novel_id, "assistant", "🌍 **【總監通報】** 世界觀設定與力量體系已規劃完成並存入數據庫！", message_type="chat")
                async_backup(reason=f"Auto flow [{task.novel_title}]: worldview finished")

            # 2. 檢查並生成主要角色設定
            if task.stop_requested: return
            chars = db.get_latest_characters(novel_id)
            if not chars or not chars.get("parsed_data"):
                task.current_stage = "characters"
                task.progress_percent = 15
                task.status_message = "正在設計核心主角群與配角人設檔案..."
                task.log("開始生成角色設定...")
                self._execute_stage_with_retry(
                    task=task,
                    stage="characters",
                    task_type="generate",
                    instruction="請設計立體豐富的主角、主要配角與反派角色設定",
                    user_prompt=initial_prompt or "請根據世界觀塑造核心角色",
                )
                task.log("✅ 角色設定已完成並持久化！")
                db.save_chat_message(novel_id, "assistant", "👥 **【總監通報】** 核心主角群與配角人設檔案已設計完成！", message_type="chat")
                async_backup(reason=f"Auto flow [{task.novel_title}]: characters finished")

            # 3. 檢查並編織全局伏筆
            if task.stop_requested: return
            seeds = db.get_foreshadowing_seeds(novel_id)
            if not seeds:
                task.current_stage = "foreshadowing"
                task.progress_percent = 25
                task.status_message = "正在編織全局懸念與長線伏筆網絡..."
                task.log("開始編織全書伏筆網絡...")
                self._execute_stage_with_retry(
                    task=task,
                    stage="foreshadowing",
                    task_type="generate",
                    instruction="請為全書埋設貫穿全局的重大懸念與分卷伏筆",
                    user_prompt="設計核心主線伏筆",
                )
                task.log("✅ 伏筆網絡已編織完成！")
                db.save_chat_message(novel_id, "assistant", "🕸️ **【總監通報】** 全局懸念與長線伏筆網絡已編織完成！", message_type="chat")

            # 4. 檢查並規劃分卷結構
            if task.stop_requested: return
            vols = db.get_volumes(novel_id)
            if not vols:
                task.current_stage = "volumes"
                task.progress_percent = 35
                task.status_message = "正在規劃全書分卷大綱與高潮節奏..."
                task.log("開始規劃分卷架構...")
                self._execute_stage_with_retry(
                    task=task,
                    stage="volumes",
                    task_type="generate",
                    instruction="請規劃全書分卷架構，包含各卷核心矛盾、起承轉合與終局高潮",
                    user_prompt="規劃分卷大綱",
                )
                task.log("✅ 分卷架構規劃完成！")
                db.save_chat_message(novel_id, "assistant", "📚 **【總監通報】** 全書分卷結構與高潮節奏已規劃就緒！", message_type="chat")
                async_backup(reason=f"Auto flow [{task.novel_title}]: volumes finished")

            # 5. 檢查並規劃篇卷骨架 (各章節細綱)
            if task.stop_requested: return
            plot_data = db.get_stitched_plot(novel_id)
            planned_chapters = plot_data.get("chapters", []) if plot_data else []
            if not planned_chapters:
                task.current_stage = "volume_skeleton"
                task.progress_percent = 45
                task.status_message = "正在生成第一卷的逐章詳細情節骨架..."
                task.log("開始生成篇卷章節骨架細綱...")
                self._execute_stage_with_retry(
                    task=task,
                    stage="volume_skeleton",
                    task_type="generate",
                    instruction="請詳細規劃各章的情節要點、視角人物、場景與伏筆回收點",
                    user_prompt="生成逐章詳細細綱",
                )
                task.log("✅ 章節細綱骨架規劃完成！")
                db.save_chat_message(novel_id, "assistant", "📝 **【總監通報】** 各章節詳細情節骨架與細綱已生成完畢！", message_type="chat")
                plot_data = db.get_stitched_plot(novel_id)
                planned_chapters = plot_data.get("chapters", []) if plot_data else []

            # 6. 逐章撰寫與精修 (智慧接續未完成之章節)
            total_target = len(planned_chapters) if planned_chapters else max_chapters
            if total_target <= 0:
                total_target = max_chapters or 10

            task.total_chapters = total_target
            task.log(f"進入正文寫作流水線，全書共規劃 {total_target} 章節")

            # 讀取目前資料庫已存在且有內容的章節
            existing_db_chapters = db.get_chapters(novel_id)
            written_indices = {int(c.get("chapter_index") or 0) for c in existing_db_chapters if c.get("content") and len(c.get("content", "").strip()) > 50}

            for ch_idx in range(1, total_target + 1):
                if task.stop_requested:
                    task.log(f"任務已安全停止於第 {ch_idx - 1} 章", level="warn")
                    break

                task.current_chapter = ch_idx
                base_pct = 50 + int((ch_idx - 1) / total_target * 45)
                task.progress_percent = base_pct

                # 若該章節已被撰寫過，後端智慧直接略過並接續下一章
                if ch_idx in written_indices:
                    task.log(f"第 {ch_idx} 章已存在完整內容，跳過並接續下一章。")
                    continue

                # (1) 正文寫作 (含 5 次自動重試)
                task.current_stage = f"writer_ch{ch_idx}"
                task.status_message = f"✍️ 正在由 Writer Agent 撰寫第 {ch_idx}/{total_target} 章正文..."
                task.log(f"開始撰寫第 {ch_idx} 章正文...")

                self._execute_stage_with_retry(
                    task=task,
                    stage="writer",
                    task_type="generate",
                    scope="chapter",
                    target={"chapter_index": ch_idx},
                    instruction=f"請根據大綱撰寫第 {ch_idx} 章的完整故事正文，著重視角、心理、對白與感官細節",
                    user_prompt=f"撰寫第 {ch_idx} 章",
                )
                task.log(f"第 {ch_idx} 章初稿撰寫完成！")

                # (2) 編輯精修 (含 5 次自動重試)
                if task.stop_requested: break
                task.current_stage = f"editor_ch{ch_idx}"
                task.status_message = f"🔍 正在由 Editor Agent 精修第 {ch_idx}/{total_target} 章文字與修辭..."
                task.log(f"開始對第 {ch_idx} 章進行潤色與精修...")

                self._execute_stage_with_retry(
                    task=task,
                    stage="editor",
                    task_type="refine",
                    scope="chapter",
                    target={"chapter_index": ch_idx},
                    instruction=f"請對第 {ch_idx} 章進行修辭優化、節奏微調與行文潤色",
                    user_prompt=f"精修第 {ch_idx} 章",
                )
                task.log(f"✅ 第 {ch_idx} 章精修完成並已存入資料庫！")
                db.save_chat_message(
                    novel_id,
                    "assistant",
                    f"✍️ **【總監通報】** 第 {ch_idx} 章正文已由 Writer 撰寫並經 Editor 潤色精修完成，已成功入庫！\n- 進度：第 {ch_idx}/{total_target} 章 ({task.progress_percent}%)",
                    message_type="chat"
                )

                # (3) 每完成一章即時同步至私有 Dataset
                async_backup(reason=f"Auto flow [{task.novel_title}]: Chapter {ch_idx} completed")
                time.sleep(1)

            if not task.stop_requested:
                task.progress_percent = 100
                task.current_stage = "completed"
                task.status_message = f"🎉 雲端無人值守生成圓滿完成！全書 {task.total_chapters} 章已全數就緒。"
                task.log(f"🎉 創作任務大功告成！所有內容已完整備份至私有雲端 Dataset。")
                db.save_chat_message(novel_id, "assistant", f"🎉 **【總監通報】** 小說全書 {task.total_chapters} 章全自動創作已圓滿完成！所有正文已安全備份至私有雲端 Dataset。", message_type="chat")
                backup_database(reason=f"Auto flow [{task.novel_title}]: all completed", force=True)

        except Exception as exc:
            err_msg = str(exc)
            task.error = err_msg
            task.current_stage = "error"
            task.status_message = f"❌ 執行中斷: {err_msg}"
            task.log(f"執行出錯: {err_msg}", level="error")
        finally:
            task.is_running = False
            task.stop_requested = False


# 全域單例管理器
autonomous_manager = AutonomousPipelineManager()
