# -*- coding: utf-8 -*-
"""
Autonomous Background Pipeline Service (雲端多小說並行無人值守自主創作服務)
在 Hugging Face 後端以多執行緒守護架構運行，支援同時觸發多本小說平行全自動生成。
具備自動重試防卡死機制 (Auto-Retry with Exponential Backoff) 與即時總監對話通報。
"""

import json
import threading
import time
import datetime
from typing import Dict, Any, List, Optional, Callable, Union

from backend import persistence as db
from backend.services.hf_sync import async_backup, backup_database
from backend.generation.routing.router import execute_generation_task
from backend.services.graphiti.extractor import ChapterFactExtractor
from backend.common.config import (
    VOLUME_SKELETON_BATCH_SIZE,
    MIN_VOLUME_COUNT,
    MIN_FORESHADOWING_SEEDS,
    MIN_KEY_TURNING_POINTS,
    RETRY_MULTIPLIER,
    FINAL_QUALITY_GATE_RETRIES,
    MIN_WRITER_DRAFT_LENGTH,
)
from backend.schemas.validation import split_consecutive_batches
from backend.common.refusal_filter import is_refusal_or_disclaimer
from backend.agents.director.runner import get_director_decision_sync
from backend.services.foreshadowing.chapter_math import get_volume_chapter_range


class PipelineHaltedException(Exception):
    """Raised when Director decides to halt autonomous execution (WAIT_USER or FINISH)."""

    def __init__(self, action: str, reason: str = ""):
        self.action = (action or "").upper().strip()
        self.reason = reason or ""
        super().__init__(f"Pipeline halted by Director: {self.action} ({self.reason})")


class StageRedirectException(Exception):
    """Raised when Director or pipeline decides to redirect flow to another stage."""

    def __init__(self, target_stage: str, reason: str = "", agent_prompt: str = ""):
        self.target_stage = target_stage
        self.reason = reason
        self.agent_prompt = agent_prompt
        super().__init__(f"Stage redirected to {target_stage}: {reason}")


class ChapterHaltedException(Exception):
    """Raised when Director or pipeline decides to halt current chapter (HALT_CHAPTER)."""

    def __init__(self, reason: str = ""):
        self.reason = reason
        super().__init__(f"Chapter halted: {reason}")


RETRY_POLICY = {
    "writer": 3 * RETRY_MULTIPLIER,
    "editor": 3 * RETRY_MULTIPLIER,
    "final_quality_gate": FINAL_QUALITY_GATE_RETRIES,
    "graph_extraction": 1 * RETRY_MULTIPLIER,
}


def classify_pipeline_error(err_msg: str) -> str:
    err = str(err_msg or "").strip()
    if "EDITOR_MISSING_INPUT" in err or "prose not found for editing" in err or "prose is empty or too short" in err:
        return "EDITOR_MISSING_INPUT"
    if any(k in err for k in (
        "拒答", "免責聲明", "UNAUTHENTICATED", "Unauthorized", "401", "Connection refused",
        "Cookie 是否過期", "Read timed out", "TimeoutError", "連線被拒", "API Key"
    )):
        return "INFRA_ERROR"
    if "Empty response" in err or "content 不可為空" in err or "為空" in err:
        return "EMPTY_OUTPUT"
    if "長度不足" in err or "too short" in err:
        return "SHORT_OUTPUT"
    if "時序" in err or "temporal" in err.lower() or "穿幫" in err or "復活" in err:
        return "TEMPORAL_ERROR"
    if "場景地點漂移" in err or "房號" in err or "漂移" in err:
        return "SCENE_DRIFT"
    if any(k in err for k in ("世界線", "因果", "矛盾", "大綱", "canon")):
        return "CANON_ERROR"
    return "QUALITY_ERROR"


class NovelPipelineTask:
    """單本小說的自主生成任務狀態實例"""

    def __init__(self, novel_id: str, novel_title: str = ""):
        self._lock = threading.RLock()
        self.novel_id = novel_id
        self.novel_title = novel_title or novel_id
        self.is_running = False
        self.stop_requested = False
        self.current_stage = "idle"
        self.current_chapter = 0
        self.total_chapters = 0
        self.progress_percent = 0
        self.status_message = "等待啟動"
        self.logs: List[Dict[str, str]] = []
        self.log_seq = 0
        self.error: Optional[str] = None
        self.start_time: Optional[str] = None
        self.last_heartbeat: str = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S")
        self.worker_thread: Optional[threading.Thread] = None
        # 可觀測性指標
        self.stage_retry_counts: Dict[str, int] = {}
        self.stage_redirect_count: int = 0
        self.last_error_type: Optional[str] = None
        self.same_error_repeat_count: int = 0

    def log(self, message: str, level: str = "info"):
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S")
        with self._lock:
            self.last_heartbeat = now_str
            # seq 為單調遞增序號：即使 logs 因記憶體上限被截斷 (-100)，
            # 前端仍可靠 seq 精準增量同步，不會因長度凍結而漏接日誌
            self.log_seq += 1
            entry = {"seq": self.log_seq, "time": now_str, "msg": message, "level": level}
            self.logs.append(entry)
            if len(self.logs) > 100:
                self.logs = self.logs[-100:]
        try:
            print(f"[AutoPipeline][{self.novel_title}][{now_str}] {message}")
        except Exception:
            try:
                safe_msg = message.encode("ascii", errors="backslashreplace").decode("ascii")
                print(f"[AutoPipeline][{now_str}] {safe_msg}")
            except Exception:
                pass

    def finish(self, status_message: str = "創作完成"):
        with self._lock:
            self.is_running = False
            self.current_stage = "completed"
            self.progress_percent = 100
            self.status_message = status_message
            self.log(status_message, level="info")

    def fail(self, error_message: str):
        with self._lock:
            self.is_running = False
            self.error = error_message
            self.current_stage = "error"
            self.status_message = f"❌ 執行中斷: {error_message}"
            self.log(f"執行出錯: {error_message}", level="error")

    def get_logs(self, since_seq: int = 0) -> List[Dict[str, Any]]:
        with self._lock:
            if since_seq <= 0:
                return list(self.logs)
            return [entry for entry in self.logs if entry.get("seq", 0) > since_seq]

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "novel_id": self.novel_id,
                "novel_title": self.novel_title,
                "is_running": self.is_running,
                "running": self.is_running,
                "current_stage": self.current_stage,
                "current_chapter": self.current_chapter,
                "total_chapters": self.total_chapters,
                "progress_percent": self.progress_percent,
                "status_message": self.status_message,
                "logs": list(self.logs),
                "log_seq": self.log_seq,
                "error": self.error,
                "stop_requested": self.stop_requested,
                "start_time": self.start_time,
                "last_heartbeat": self.last_heartbeat,
            }


GenerationTaskState = NovelPipelineTask


class AutonomousPipelineManager:
    """多小說並行無人值守管理器 (單例模式)"""
    _instance = None
    _lock = threading.Lock()
    execute_generation_task = staticmethod(execute_generation_task)

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
            
            # 若有指定 novel_id
            if novel_id:
                if novel_id in self.tasks:
                    res = self.tasks[novel_id].to_dict()
                    res["active_tasks_count"] = len(active_list)
                    res["active_tasks"] = active_list
                    return res
                # 該小說未曾運行任務，回傳空閒/未運行狀態，同時附帶目前背景正在運行的任務列表
                return {
                    "is_running": False,
                    "running": False,
                    "novel_id": novel_id,
                    "novel_title": "",
                    "current_stage": "idle",
                    "current_chapter": 0,
                    "total_chapters": 0,
                    "progress_percent": 0,
                    "status_message": "未運行",
                    "logs": [],
                    "log_seq": 0,
                    "error": None,
                    "start_time": None,
                    "active_tasks_count": len(active_list),
                    "active_tasks": active_list,
                }

            # 若未指定 novel_id (全域查詢)，優先回傳任一正在運行的任務
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
                "running": False,
                "novel_id": None,
                "novel_title": "",
                "current_stage": "idle",
                "current_chapter": 0,
                "total_chapters": 0,
                "progress_percent": 0,
                "status_message": "等待啟動",
                "logs": [],
                "log_seq": 0,
                "error": None,
                "start_time": None,
                "active_tasks_count": 0,
                "active_tasks": [],
            }

    get_task_status = get_status

    def start_pipeline(self, novel_id: str, prompt: str = "", max_chapters: int = 5) -> Dict[str, Any]:
        with self._lock:
            # 檢查先前任務是否真正在執行
            if novel_id in self.tasks:
                existing_task = self.tasks[novel_id]
                if existing_task.is_running:
                    # 檢查背景執行緒是否仍存活，若已終止則自我修復重設狀態
                    if existing_task.worker_thread and not existing_task.worker_thread.is_alive():
                        print(f"[AutoPipeline] Task for {novel_id} was marked running but thread is dead. Resetting...")
                        existing_task.is_running = False
                        try:
                            db.release_pipeline_lock(novel_id)
                        except Exception:
                            pass
                    else:
                        return {
                            "status": "already_running",
                            "success": True,
                            "novel_id": novel_id,
                            "novel_title": existing_task.novel_title,
                            "message": f"小說《{existing_task.novel_title}》已有自主生成任務在背景運行中",
                        }

            novel = db.get_novel(novel_id)
            if not novel:
                return {"status": "error", "success": False, "message": f"找不到小說 (ID: {novel_id})"}

            # 啟動前清理可能殘留的 SQLite 鎖定
            try:
                db.release_pipeline_lock(novel_id)
            except Exception:
                pass

            effective_prompt = prompt.strip() if (prompt and prompt.strip()) else (novel.get("pipeline_prompt") or "").strip()

            task = NovelPipelineTask(novel_id, novel.get("title", "未命名小說"))
            task.is_running = True
            task.stop_requested = False
            task.start_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            task.status_message = "🚀 雲端無人值守生成啟動中..."
            task.log(f"啟動小說《{task.novel_title}》的雲端無人值守全自動創作任務")

            self.tasks[novel_id] = task

            worker = threading.Thread(
                target=self._run_autonomous_flow,
                args=(task, effective_prompt, max_chapters),
                daemon=True,
            )
            task.worker_thread = worker
            worker.start()

            active_count = len([t for t in self.tasks.values() if t.is_running])
            return {
                "status": "started",
                "success": True,
                "novel_id": novel_id,
                "novel_title": task.novel_title,
                "active_tasks_count": active_count,
                "message": f"小說《{task.novel_title}》雲端自主創作任務已在背景成功啟動！(當前共 {active_count} 本並行寫作中)",
            }

    def stop_pipeline(self, novel_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            if novel_id:
                # 無論記憶體是否有活躍任務，皆主動清理該小說的 SQLite 鎖定
                try:
                    db.release_pipeline_lock(novel_id)
                except Exception:
                    pass

                if novel_id not in self.tasks or not self.tasks[novel_id].is_running:
                    return {"status": "not_running", "success": False, "message": "該小說目前沒有正在運行的任務"}
                task = self.tasks[novel_id]
                task.stop_requested = True
                task.status_message = "🛑 正在等待當前步驟完成後中止..."
                task.log("使用者請求中止本小說的雲端自主生成任務", level="warn")
                return {"status": "stopping", "success": True, "novel_id": novel_id, "message": f"已發送中止請求，小說《{task.novel_title}》將於當前步驟完成後安全停止"}
            else:
                running_tasks = [t for t in self.tasks.values() if t.is_running]
                if not running_tasks:
                    return {"status": "not_running", "success": False, "message": "目前沒有任何正在運行的任務"}
                for t in running_tasks:
                    t.stop_requested = True
                    t.status_message = "🛑 正在等待當前步驟完成後中止..."
                    t.log("使用者請求全域中止雲端任務", level="warn")
                return {"status": "stopping", "success": True, "message": f"已對所有 {len(running_tasks)} 本正在生成的小說發送中止請求"}

    def execute_generation_task(self, payload: Dict[str, Any]) -> Any:
        return execute_generation_task(payload)

    def _execute_stage_with_retry(
        self,
        task: NovelPipelineTask,
        stage: str = "writer",
        task_type: Union[str, Dict[str, Any]] = "generate",
        instruction: Union[str, Callable[[], bool]] = "",
        user_prompt: str = "",
        scope: str = "global",
        target: Optional[Dict[str, Any]] = None,
        extra_body: Optional[Dict[str, Any]] = None,
        verify_fn: Optional[Callable[[], bool]] = None,
        max_retries: int = 20,
        stage_name: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Any:
        """具備指數退避自動重試、防卡死機制與實質資料庫校驗的 Stage 執行器"""
        if stage_name:
            stage = stage_name
        if payload and isinstance(payload, dict):
            if not target:
                target = payload
            elif isinstance(target, dict):
                target.update(payload)
        # 兼容彈性參數呼叫（例如 (task, stage, target_dict, verify_fn, max_retries=...)）
        if isinstance(task_type, dict):
            target = task_type
            task_type = "generate"
            if callable(instruction):
                verify_fn = instruction
                instruction = ""
        elif callable(instruction) and verify_fn is None:
            verify_fn = instruction
            instruction = ""

        # 階段型上限：未特別傳入特定 max_retries 時使用 RETRY_POLICY
        if max_retries == 20 or max_retries is None:
            max_retries = RETRY_POLICY.get(stage, 3 * RETRY_MULTIPLIER)

        last_exc = None
        for attempt in range(1, max_retries + 1):
            if task.stop_requested:
                return None
            try:
                ch_target = target.get("chapter_index") if isinstance(target, dict) else None
                payload = {
                    "novel_id": task.novel_id,
                    "task_type": task_type,
                    "stage": stage,
                    "scope": scope,
                    "target": target or {},
                    "chapter_index": ch_target,
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

                exec_fn = getattr(self, "execute_generation_task", execute_generation_task)
                resp = exec_fn(payload)
                if not resp or not getattr(resp, "ok", False):
                    err_detail = getattr(resp, "error", None) if resp else "Empty response returned from generation router"
                    raise RuntimeError(err_detail or "Generation task execution failed")

                # 實質校驗：確認該階段所需的成品已真正寫入資料庫
                if verify_fn and not verify_fn():
                    diag_suffix = ""
                    try:
                        if stage in ("geometry", "macro_semantic", "character_semantic", "cross_relation"):
                            stats = db.get_geometry_stats(task.novel_id) if hasattr(db, "get_geometry_stats") else {}
                            diag_suffix = (
                                f"（幾何診斷：nodes={stats.get('node_count', '?')}/filled={stats.get('filled_nodes', '?')}，"
                                f"threads={stats.get('thread_count', '?')}/filled={stats.get('filled_threads', '?')}，"
                                f"edges={stats.get('edge_count', '?')}/filled={stats.get('filled_edges', '?')}，"
                                f"volumes_filled={stats.get('filled_volumes', '?')}）"
                            )
                    except Exception:
                        pass
                    raise RuntimeError(f"階段 [{stage}] 執行結束，但資料庫實質校驗未通過（未持久化實質資料）。{diag_suffix}")

                return resp

            except (StageRedirectException, ChapterHaltedException, PipelineHaltedException):
                raise
            except Exception as exc:
                last_exc = exc
                if stage in ("chapter", "writer") and target and target.get("chapter_index"):
                    try:
                        db.rollback_or_purge_chapter(task.novel_id, int(target["chapter_index"]))
                        task.log(f"🧹 已清除第 {target['chapter_index']} 章未通過或異常之草稿，準備重試...", level="warn")
                    except Exception:
                        pass

                err_clean = str(exc).strip()
                error_type = classify_pipeline_error(err_clean)
                ch_idx_for_director = target.get("chapter_index") if isinstance(target, dict) else None
                vol_idx_for_director = target.get("volume_index") if isinstance(target, dict) else None
                # 同一錯誤只應在同一 stage、同一章內累計；不能把上一章或另一個
                # stage 的錯誤串在一起，否則會誤觸發 HUMAN_REVIEW。
                error_key = f"{stage}:{ch_idx_for_director}:{error_type}"

                # 指標更新
                task.stage_retry_counts[stage] = task.stage_retry_counts.get(stage, 0) + 1
                if error_key == task.last_error_type:
                    task.same_error_repeat_count += 1
                else:
                    task.same_error_repeat_count = 1
                task.last_error_type = error_key

                cur_content = ""
                if ch_idx_for_director:
                    try:
                        cur_ch = db.get_chapter(task.novel_id, ch_idx_for_director)
                        cur_content = (cur_ch.get("content") or "").strip() if cur_ch else ""
                    except Exception:
                        pass

                # 第四階段：EDITOR_MISSING_INPUT 不可重試 Editor，直接導向 Writer
                if stage == "editor" and error_type == "EDITOR_MISSING_INPUT":
                    task.stage_redirect_count += 1
                    task.log(f"🚨 [Editor 缺失正文] 第 {ch_idx_for_director} 章正文缺失或過短，停止 Editor 重試，直接導向 Writer！", level="warn")
                    missing_input_prompt = "正文缺失或過短，請完整撰寫本章故事正文。"
                    try:
                        decision = get_director_decision_sync(
                            novel_id=task.novel_id,
                            current_stage="writer",
                            user_prompt=(
                                f"第 {ch_idx_for_director} 章 Editor 前置檢查發現正文缺失或過短。"
                                "請依本書世界觀、相關角色 Bible、本章大綱及前後章脈絡，"
                                "提出 Writer 可直接執行的完整正文補寫方向，確保不新增設定矛盾。"
                            ),
                            chapter_index=ch_idx_for_director,
                            volume_index=vol_idx_for_director,
                            extra_context=(
                                f"Editor 缺稿錯誤：{err_clean}\n"
                                f"目前資料庫正文長度：{len(cur_content)} 字。"
                            ),
                        )
                        if decision:
                            missing_input_prompt = str(
                                decision.get("agent_prompt") or decision.get("hint") or missing_input_prompt
                            ).strip()
                        task.log(f"🎬 [Director 缺稿修正方向] 第 {ch_idx_for_director} 章：{missing_input_prompt[:400]}")
                    except Exception as director_exc:
                        task.log(f"⚠️ Editor 缺稿時 Director 診斷失敗，使用明確 Writer 補稿指示：{director_exc}", level="warn")
                    retry_log_data = {
                        "chapter": ch_idx_for_director,
                        "stage": stage,
                        "attempt": attempt,
                        "error_type": error_type,
                        "director_action": "REDIRECT",
                        "target_stage": "writer",
                        "content_length": len(cur_content),
                        "stage_retry_count": task.stage_retry_counts[stage],
                        "stage_redirect_count": task.stage_redirect_count,
                        "same_error_repeat_count": task.same_error_repeat_count,
                    }
                    task.log(f"📊 [重試結構化日誌] {json.dumps(retry_log_data, ensure_ascii=False)}", level="warn")
                    raise StageRedirectException(
                        target_stage="writer",
                        reason="Editor 前置檢查失敗：正文不存在或過短，停止 Editor 重試並回到 Writer。",
                        agent_prompt=missing_input_prompt,
                    )

                # 同一章同一錯誤連續出現時，記錄並加強下一次 Director 指令，
                # 不直接轉 HUMAN_REVIEW。自主流水線的人工入口是使用者再次按下
                # 流水線，而不是在這裡強制中斷；真正的停止仍由 retry 上限控制。
                if task.same_error_repeat_count >= 2 and error_type != "INFRA_ERROR":
                    task.log(
                        f"⚠️ [同一錯誤連續重複 {task.same_error_repeat_count} 次] 階段 [{stage}] "
                        f"錯誤 [{error_type}]，交由 Director 自主換方案修正，不中斷流水線。",
                        level="warn",
                    )
                    retry_log_data = {
                        "chapter": ch_idx_for_director,
                        "stage": stage,
                        "attempt": attempt,
                        "error_type": error_type,
                        "director_action": "FORCE_SELF_CORRECTION",
                        "target_stage": None,
                        "content_length": len(cur_content),
                        "stage_retry_count": task.stage_retry_counts[stage],
                        "stage_redirect_count": task.stage_redirect_count,
                        "same_error_repeat_count": task.same_error_repeat_count,
                    }
                    task.log(f"📊 [重試結構化日誌] {json.dumps(retry_log_data, ensure_ascii=False)}", level="warn")
                    instruction = (
                        f"【Director 強制換方案】同一問題已連續出現 {task.same_error_repeat_count} 次。"
                        f"請不要重複上一個方案，直接採用另一種可執行修正：{err_clean}。\n"
                        + (f"原始任務指引：{instruction}" if instruction else "")
                    )

                if attempt >= max_retries or task.stop_requested:
                    raise last_exc

                is_infra_error = (error_type == "INFRA_ERROR")
                if is_infra_error:
                    # ── 基建類錯誤：跳過 Director LLM 呼叫，直接指數退避重試 ──
                    director_prescription = (
                        f"【總監診斷處方箋（第 {attempt + 1} 次連線環境診斷）】\n"
                        f"檢測到上游模型通訊或身分驗證異常：{err_clean}。\n"
                        f"此為模型連線/登入憑證問題（非創作大綱或情節邏輯錯誤）。請檢查模型服務端、API Key 或 WebChat2Local Cookie 是否正常。"
                    )
                    if instruction:
                        instruction = f"{director_prescription}\n原始任務指引：{instruction}"
                    else:
                        instruction = director_prescription
                    delay = min(15, 2 * attempt)
                    task.log(
                        f"🩺 [基建異常] [{stage}] 連線/憑證問題，將於 {delay} 秒後進行第 {attempt + 1}/{max_retries} 次重試：{exc}",
                        level="warn",
                    )
                    time.sleep(delay)
                    continue

                # ── 內容/品質類錯誤：調用真正的 Director Agent 做智慧決策 ──
                task.log(
                    f"🎬 [Director 決策介入] [{stage}] 第 {attempt}/{max_retries} 次產出未達標（類型: {error_type}），"
                    f"正在調用 Director Agent 進行智慧決策...",
                    level="warn",
                )

                director_extra = (
                    f"【自主流程重試上下文 — 第 {attempt}/{max_retries} 次重試】\n"
                    f"階段: {stage}\n"
                    f"錯誤類型: {error_type}\n"
                    f"錯誤原因: {err_clean}\n"
                    f"原始任務指引: {instruction or '(無)'}\n"
                    f"請以真實使用者身份，根據圖譜引擎、角色聖經、大綱等上下文，"
                    f"決定如何修正此 agent 的生成。支援回傳 action: RETRY_SAME_STAGE / REDIRECT / HALT_CHAPTER / WAIT_USER，"
                    f"並可在 target_stage (如 'writer') 與 agent_prompt 中給出精確指示。"
                )

                try:
                    decision = get_director_decision_sync(
                        novel_id=task.novel_id,
                        current_stage=stage,
                        user_prompt=user_prompt or f"自主流程 {stage} 階段重試決策",
                        chapter_index=ch_idx_for_director,
                        volume_index=vol_idx_for_director,
                        extra_context=director_extra,
                    )
                except Exception as dir_exc:
                    task.log(
                        f"⚠️ Director 決策呼叫異常（退回文字處方箋模式）：{dir_exc}",
                        level="warn",
                    )
                    decision = None

                if decision and isinstance(decision, dict):
                    action = str(decision.get("action") or "").upper().strip()
                    target_stage = str(decision.get("target_stage") or "").lower().strip()
                    task.log(
                        f"🎬 [Director 決策結果] action={action}, target_stage={target_stage or stage}, "
                        f"reason={str(decision.get('reason', '(無)'))[:120]}",
                    )

                    retry_log_data = {
                        "chapter": ch_idx_for_director,
                        "stage": stage,
                        "attempt": attempt,
                        "error_type": error_type,
                        "director_action": action,
                        "target_stage": target_stage or stage,
                        "content_length": len(cur_content),
                        "stage_retry_count": task.stage_retry_counts[stage],
                        "stage_redirect_count": task.stage_redirect_count,
                        "same_error_repeat_count": task.same_error_repeat_count,
                    }
                    task.log(f"📊 [重試結構化日誌] {json.dumps(retry_log_data, ensure_ascii=False)}", level="warn")

                    # 第二階段：HALT_CHAPTER 停止本章並保留草稿
                    if action == "HALT_CHAPTER":
                        task.log(
                            f"🛑 [Director 決策中止] Director 判定 HALT_CHAPTER，停止本章流程。原因：{decision.get('reason', '(無)')}",
                            level="warn",
                        )
                        raise ChapterHaltedException(reason=decision.get("reason", "Director HALT_CHAPTER"))

                    # 自主流水線中，Director 本身就是「使用者代理」。
                    # WAIT_USER 不應把整條任務停在等待真人輸入；把它轉成
                    # Director 自主裁決後的修正重試。只有 FINISH 仍代表整體完成。
                    if action == "WAIT_USER":
                        self_resolve_prompt = (
                            decision.get("agent_prompt")
                            or decision.get("hint")
                            or decision.get("reason")
                            or "請由總監自行選擇最符合既有世界觀、角色聖經與大綱的方案，完成本階段修正。"
                        )
                        task.log(
                            f"🧠 [Director 自主裁決] 收到 WAIT_USER，改由 Director 自行完成修正，不中斷流水線："
                            f"{str(decision.get('reason', '(無)'))[:180]}",
                            level="warn",
                        )
                        try:
                            db.save_chat_message(
                                task.novel_id,
                                "director",
                                f"🧠 **【Director 自主裁決取代 WAIT_USER】**\n"
                                f"- 階段: {stage}\n"
                                f"- 原因: {decision.get('reason', '(無)')}\n"
                                f"- 自主修正: {self_resolve_prompt}",
                                message_type="director",
                            )
                        except Exception:
                            pass
                        instruction = (
                            f"【Director 自主裁決修正指令】\n{self_resolve_prompt}\n"
                            "不得等待使用者、不得輸出 WAIT_USER；請直接完成可執行的內容修正。\n"
                            + (f"原始任務指引：{instruction}" if instruction else "")
                        )
                        # 若 Director 同時提供合法 target_stage，沿用下面的 REDIRECT
                        # 路由；否則保持目前 stage 重試。
                        if target_stage and target_stage != stage:
                            action = "REDIRECT"

                    # Director 判斷整體任務已完成 → 提前結束重試
                    if action == "FINISH":
                        task.log(
                            f"🛑 [Director 決策中止] Director 判定 FINISH，"
                            f"提前中止重試。原因：{decision.get('reason', '(無)')}",
                            level="warn",
                        )
                        try:
                            db.save_chat_message(
                                task.novel_id,
                                "director",
                                f"🛑 **【Director 判定完成，中止重試】**\n"
                                f"- 階段: {stage}\n"
                                f"- 決策: {action}\n"
                                f"- 原因: {decision.get('reason', '(無)')}\n"
                                f"- 提示: {decision.get('hint', '(無)')}",
                                message_type="director",
                            )
                        except Exception:
                            pass
                        raise PipelineHaltedException(action=action, reason=decision.get("reason", ""))

                    # 第二階段：REDIRECT 真正改變 stage
                    if action == "REDIRECT" or (target_stage and target_stage != stage):
                        if stage == "editor" and target_stage == "writer":
                            task.stage_redirect_count += 1
                            task.log(f"🔀 [Director 路由切換] 結束 Editor 重試，真正重定向至 Writer 階段！原因：{decision.get('reason')}")
                            raise StageRedirectException(
                                target_stage="writer",
                                reason=decision.get("reason", "Director 決定打回 Writer"),
                                agent_prompt=decision.get("agent_prompt") or decision.get("hint") or "",
                            )
                        elif stage == "writer" and target_stage == "editor":
                            if len(cur_content) >= MIN_WRITER_DRAFT_LENGTH:
                                task.stage_redirect_count += 1
                                task.log(f"🔀 [Director 路由切換] Writer 劇情底稿可供編輯（{len(cur_content)} 字），推進至 Editor 階段")
                                raise StageRedirectException(
                                    target_stage="editor",
                                    reason=decision.get("reason", "初稿合格，推進至 Editor"),
                                    agent_prompt=decision.get("agent_prompt") or "",
                                )
                            else:
                                task.log(f"⚠️ Writer 底稿未達最低可編輯長度（< {MIN_WRITER_DRAFT_LENGTH} 字），不允許提早 REDIRECT 至 Editor，繼續在 Writer 修正", level="warn")

                    # Director 決策動態拆章
                    if action == "SPLIT_CHAPTER_OUTLINE":
                        split_plan = decision.get("split_plan") or {}
                        split_chapters = split_plan.get("chapters") or []
                        target_ch = decision.get("chapter_index") or ch_idx_for_director
                        if target_ch and split_chapters:
                            from backend.persistence.repositories.volumes import split_and_expand_chapter_outline
                            try:
                                split_res = split_and_expand_chapter_outline(task.novel_id, target_ch, split_chapters)
                                task.log(
                                    f"✂️ [Director 拆章完成] 第 {target_ch} 章已動態拆分為 {len(split_chapters)} 章，"
                                    f"總章數 +{split_res.get('delta', len(split_chapters) - 1)}"
                                )
                            except Exception as sp_exc:
                                task.log(f"⚠️ [Director 拆章失敗]: {sp_exc}", level="warn")

                    # Director 提供修正指令 → 注入到下一輪 instruction
                    agent_prompt = decision.get("agent_prompt") or decision.get("hint") or ""
                    if agent_prompt:
                        director_instruction = (
                            f"【Director Agent 第 {attempt + 1} 次智慧修正指令】\n"
                            f"{agent_prompt}\n"
                            f"（修正原因：{decision.get('reason', err_clean)}）"
                        )
                    else:
                        director_instruction = (
                            f"【Director Agent 第 {attempt + 1} 次定向修正】\n"
                            f"上一輪產出未達標準，核心病灶：{err_clean}。\n"
                            f"請針對上述問題進行重點修正，確保符合規範約束與結構自洽。"
                        )

                    if instruction:
                        instruction = f"{director_instruction}\n原始任務指引：{instruction}"
                    else:
                        instruction = director_instruction

                else:
                    # Director 呼叫失敗或無法解析 → fallback 到舊的文字處方箋
                    task.log(
                        f"⚠️ Director 決策無法解析，退回文字處方箋模式。",
                        level="warn",
                    )
                    director_prescription = (
                        f"【總監診斷處方箋（第 {attempt + 1} 次定向重點修正）】\n"
                        f"上一輪產出未達標準，核心病灶：{err_clean}。\n"
                        f"請針對上述問題進行重點修正，確保符合規範約束與結構自洽。"
                    )
                    if instruction:
                        instruction = f"{director_prescription}\n原始任務指引：{instruction}"
                    else:
                        instruction = director_prescription

                delay = min(15, 2 * attempt)
                task.log(
                    f"🩺 [Director 修正處方箋已就緒] 將於 {delay} 秒後進行第 {attempt + 1}/{max_retries} 次修正：{exc}",
                    level="warn",
                )
                time.sleep(delay)

        raise last_exc or RuntimeError(f"Stage {stage} failed after {max_retries} retries")

    def _run_autonomous_flow(self, task: NovelPipelineTask, initial_prompt: str, max_chapters: int):
        novel_id = task.novel_id
        try:
            # 1. 檢查並生成世界觀
            if task.stop_requested: return
            self._phase_worldview(task, novel_id, initial_prompt)

            # 1.5 拓樸先行：長篇規模、動態多幕與初始因果藍圖
            if task.stop_requested: return
            self._phase_narrative_scale_and_blueprint(task, novel_id)

            # 2. 檢查並生成主要角色設定（陣營梯隊導向群像：各陣營 5-10 人，全書至少 15+ 位）
            if task.stop_requested: return
            self._phase_characters(task, novel_id, initial_prompt)

            # 3. 檢查並編織全局伏筆與關鍵轉折 (目標各達 MIN 保底條數)
            if task.stop_requested: return
            self._phase_foreshadowing(task, novel_id)

            # 4. 檢查並規劃分卷結構
            if task.stop_requested: return
            vols = self._phase_volumes(task, novel_id)

            # 4.5-4.8 敘事幾何骨架與宏觀/角色/跨距語義填充
            if task.stop_requested: return
            self._phase_geometry_semantics(task, novel_id)

            # 5. 檢查並規劃全部分卷骨架 (各章節細綱 - 確保每卷皆 100% 具備細綱)
            if task.stop_requested: return
            vols = self._phase_volume_skeletons(task, novel_id, vols)
            if task.stop_requested: return

            # 5.5 角色一致性與名冊完整性防呆校驗 (防止正文角色性格盲猜或反派立場翻轉)
            self._phase_character_roster_guard(task, novel_id, vols)

            # 6. 逐章撰寫與精修 (智慧接續未完成之章節)
            vols, total_target, written_rows, written_indices = self._prepare_chapter_pipeline(task, novel_id)
            for ch_idx in range(1, total_target + 1):
                if task.stop_requested:
                    task.log(f"任務已安全停止於第 {ch_idx - 1} 章", level="warn")
                    break

                task.current_chapter = ch_idx
                base_pct = 50 + int((ch_idx - 1) / total_target * 45)
                task.progress_percent = base_pct

                # 若該章節已被撰寫過，檢查 Editor 是否曾成功收尾：
                # 上次精修失敗（failed）或只有 Writer 初稿（version==1 且無 Editor 驗收記錄）
                # 的章節不可直接跳過，必須跳過 Writer、僅重試 Editor 及後續流程。
                editor_retry_only = False
                if ch_idx in written_indices:
                    if _chapter_needs_editor_retry(novel_id, ch_idx, written_rows.get(ch_idx)):
                        editor_retry_only = True
                        task.log(f"第 {ch_idx} 章初稿仍在、但上次精修未完成，跳過 Writer、僅重試 Editor 及後續流程...")
                    else:
                        task.log(f"第 {ch_idx} 章已存在完整內容，跳過並接續下一章。")
                        continue

                vols, stopped_before_editor = self._write_single_chapter(
                    task, novel_id, vols, ch_idx, total_target, written_rows, editor_retry_only
                )
                if stopped_before_editor:
                    break
                if vols and self._is_volume_end(vols, ch_idx):
                    self._reconcile_foreshadowing_debts(task, novel_id, max_chapter=ch_idx)

            # (2.8) 卷末零 LLM 伏筆回收對帳：每卷寫完後 Python 快速對帳
            self._reconcile_foreshadowing_debts(task, novel_id)

            finale_ok, finale_issues = _audit_final_volume_lock(novel_id)
            if not finale_ok:
                task.current_stage = "completion_locked"
                task.status_message = "⚠️ 終卷對帳未通過，完成狀態已鎖定。"
                task.log(
                    "⚠️ [終卷結局鎖] 零 LLM 對帳未通過：" + "；".join(finale_issues[:8]),
                    level="warn",
                )
                return

            self._finalize_completion(task, novel_id)

        except PipelineHaltedException as halt_exc:
            self._handle_pipeline_halt(task, halt_exc)
            return
        except Exception as exc:
            self._handle_pipeline_failure(task, novel_id, exc)
        finally:
            with task._lock:
                task.is_running = False
                task.stop_requested = False
            try:
                db.release_pipeline_lock(novel_id)
            except Exception as e:
                print(f"[WARN] Failed to release pipeline lock for novel {novel_id}: {e}")

    def _phase_worldview(self, task: NovelPipelineTask, novel_id: str, initial_prompt: str):
        """步驟 1/1.5：檢查並生成世界觀，同步設定體系並執行 Setting Audit A 審計。"""
        # 1. 檢查並生成世界觀
        if not _is_worldview_ready(novel_id):
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
                verify_fn=lambda: _is_worldview_ready(novel_id),
            )
            task.log("✅ 世界觀設定已完成並持久化！")
            db.save_chat_message(novel_id, "assistant", "🌍 **【系統進度】** 世界觀設定與力量體系已規劃完成並存入數據庫！", message_type="pipeline")
        else:
            task.log("世界觀設定已就緒，跳過生成。")

        # 1.5 世界觀設定體系同步與 Setting Audit A 審計
        try:
            from backend.agents.setting_auditor import run_setting_audit
            from backend.services.narrative import SettingRegistry
            SettingRegistry.sync_systems_from_worldview(novel_id)
            audit_a = run_setting_audit(novel_id, "worldview")
            task.log(f"⚙️ [Setting Audit A] 世界觀設定與力量體系註冊完成 (審計結果: {audit_a.get('overall_decision')})")
        except Exception as sa_exc:
            task.log(f"⚠️ Setting Audit A 執行異常 (非致命): {sa_exc}", level="warn")

    def _phase_narrative_scale_and_blueprint(self, task: NovelPipelineTask, novel_id: str):
        """步驟 1.5：長篇規格與動態多幕架構 + 初始敘事拓樸藍圖 (Topological-First Blueprint)"""
        planning_blueprint = db.get_planning_blueprint(novel_id) if hasattr(db, "get_planning_blueprint") else None
        if not planning_blueprint or planning_blueprint.get("state") != "planning_blueprint":
            task.current_stage = "planning_blueprint"
            task.progress_percent = 12
            task.status_message = "正在建構全書長篇規格、動態多幕與初始敘事拓樸藍圖..."
            task.log("開始構建拓樸先行藍圖 (Planning Blueprint & Dynamic Acts)...")
            from backend.generation.modules.blueprint_planner import generate_planning_blueprint
            bp = generate_planning_blueprint(novel_id)
            from backend.generation.core.gates import evaluate_stage_rigid_gate
            blueprint_gate = evaluate_stage_rigid_gate("planning_blueprint", novel_id)
            if not blueprint_gate.passed:
                raise RuntimeError("規劃拓樸藍圖驗收未通過：" + "；".join(blueprint_gate.defects))
            task.log(f"✅ 初始敘事拓樸藍圖已建立並持久化（{len(bp.nodes)} 個里程碑節點、{len(bp.threads)} 條敘事線、{len(bp.edges)} 條因果邊）！")
            db.save_chat_message(
                novel_id,
                "assistant",
                f"🗺️ **【系統進度】** 全書初始敘事拓樸藍圖（Planning Blueprint）已建立！涵蓋 {bp.scale_spec.act_count} 幕架構與 {len(bp.nodes)} 個里程碑節點，奠定宏觀因果骨架。",
                message_type="pipeline",
            )
        else:
            task.log("初始敘事拓樸藍圖已就緒，跳過生成。")

    def _phase_characters(self, task: NovelPipelineTask, novel_id: str, initial_prompt: str):
        """步驟 2：檢查並分段生成主要角色設定（陣營梯隊導向群像）。"""
        if not _are_characters_ready(novel_id, min_count=15):
            task.current_stage = "characters"
            task.progress_percent = 15
            task.status_message = "正在分段設計各陣營高層核心與中堅骨幹群像檔案（各陣營 5-10 位）..."
            task.log("開始分段生成各陣營角色設定（梯隊分段累加，全書目標 15-30+ 位）...")
            self._execute_stage_with_retry(
                task=task,
                stage="characters",
                task_type="generate",
                instruction="請根據世界觀各陣營架構，分段梯隊設計豐富立體的主角、主要配角、反派與各大陣營代表角色（每陣營 5-10 位）",
                user_prompt=initial_prompt or "請根據世界觀塑造各陣營核心角色與勢力群像",
                verify_fn=lambda: _are_characters_ready(novel_id, min_count=15),
            )
            task.log("✅ 各陣營角色設定已分段完成並持久化！")
            db.save_chat_message(novel_id, "assistant", "👥 **【系統進度】** 各陣營高層領袖與中堅骨幹人設檔案已分段梯隊設計完成！", message_type="pipeline")
        else:
            task.log("各陣營角色設定已就緒，跳過生成。")

    def _phase_foreshadowing(self, task: NovelPipelineTask, novel_id: str):
        """步驟 3：檢查並編織全局伏筆與關鍵轉折（目標各達 MIN 保底條數）。"""
        if not _are_seeds_ready(novel_id, min_count=MIN_FORESHADOWING_SEEDS):
            task.current_stage = "foreshadowing_seeds"
            task.progress_percent = 22
            task.status_message = f"正在分段編織全局懸念與長線伏筆網絡（目標 {MIN_FORESHADOWING_SEEDS}+ 條）..."
            task.log(f"開始編織全書伏筆網絡（分批累加生成至 {MIN_FORESHADOWING_SEEDS}+ 條）...")
            self._execute_stage_with_retry(
                task=task,
                stage="foreshadowing",
                task_type="generate",
                instruction=f"[BATCH: foreshadowing_seeds] 請為全書埋設貫穿全局的重大懸念與分卷伏筆（目標累加至 {MIN_FORESHADOWING_SEEDS}+ 條）",
                user_prompt="設計核心主線伏筆",
                verify_fn=lambda: _are_seeds_ready(novel_id, min_count=MIN_FORESHADOWING_SEEDS),
            )
            task.log(f"✅ 伏筆網絡已編織完成（{MIN_FORESHADOWING_SEEDS}+ 條）！")
            db.save_chat_message(novel_id, "assistant", f"🕸️ **【系統進度】** 全局懸念與長線伏筆網絡已編織完成（{MIN_FORESHADOWING_SEEDS}+ 條）！", message_type="pipeline")
        else:
            task.log(f"全書伏筆網絡已就緒（>= {MIN_FORESHADOWING_SEEDS} 條），跳過生成。")

        if task.stop_requested: return
        if not _are_turning_points_ready(novel_id, min_count=MIN_KEY_TURNING_POINTS):
            task.current_stage = "foreshadowing_turns"
            task.progress_percent = 28
            task.status_message = f"正在規劃核心關鍵轉折點（與已確立之伏筆網絡聯動，目標 {MIN_KEY_TURNING_POINTS}+ 條）..."
            task.log(f"開始規劃全書核心關鍵轉折點（與 {MIN_FORESHADOWING_SEEDS}+ 條伏筆網絡深度聯動）...")
            self._execute_stage_with_retry(
                task=task,
                stage="foreshadowing",
                task_type="generate",
                instruction=f"[BATCH: key_turning_points] 請為全書規劃核心關鍵轉折點與重大逆轉事件，呼應並引爆伏筆網絡（目標累加至 {MIN_KEY_TURNING_POINTS}+ 條）",
                user_prompt="設計核心關鍵轉折點",
                verify_fn=lambda: _are_turning_points_ready(novel_id, min_count=MIN_KEY_TURNING_POINTS),
            )
            task.log(f"✅ 關鍵轉折點已規劃完成（{MIN_KEY_TURNING_POINTS}+ 條）！")
            db.save_chat_message(novel_id, "assistant", f"🎭 **【系統進度】** 全書核心關鍵轉折點已分段組合規劃就緒（{MIN_KEY_TURNING_POINTS}+ 條，與伏筆閉環聯動）！", message_type="pipeline")
        else:
            task.log(f"全書關鍵轉折點已就緒（>= {MIN_KEY_TURNING_POINTS} 條），跳過生成。")

        # 3.5 實體與伏筆拓樸硬綁定 (Entity & Foreshadowing ID Binding)
        try:
            from backend.generation.modules.entity_binder import bind_entities_and_foreshadowings
            bindings = bind_entities_and_foreshadowings(novel_id)
            task.log(f"🔗 [實體拓樸綁定] 已成功將 {len(bindings)} 條伏筆種子綁定至角色、陣營與幕次節點，並持久化！")
        except Exception as bind_err:
            task.log(f"⚠️ [實體拓樸綁定提示] 略過：{bind_err}")

    def _phase_volumes(self, task: NovelPipelineTask, novel_id: str) -> List[Dict[str, Any]]:
        """步驟 4：檢查並規劃分卷結構，回傳分卷列表（無分卷時 raise RuntimeError）。"""
        if not _are_volumes_ready(novel_id):
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
                verify_fn=lambda: _are_volumes_ready(novel_id),
            )
            task.log("✅ 分卷架構規劃完成！")
            db.save_chat_message(novel_id, "assistant", "📚 **【系統進度】** 全書分卷結構與高潮節奏已規劃就緒！", message_type="pipeline")
            async_backup(reason=f"Auto flow [{task.novel_title}]: volumes finished")
        else:
            task.log("分卷架構已就緒，跳過生成。")

        vols = db.get_volumes(novel_id)
        if not vols:
            raise RuntimeError("分卷結構尚未生成成功，無法繼續後續流程。")
        return vols

    def _phase_geometry_semantics(self, task: NovelPipelineTask, novel_id: str):
        """步驟 4.5-4.8：敘事幾何骨架與宏觀/角色/跨距語義填充。"""
        # 4.5 敘事幾何骨架 (Geometry-First):純程式碼零 LLM 消耗，
        # 在分卷確定後、細綱與正文之前先鋪設全書拓撲 (長距伏筆/多線合流/主題對比邊)，
        # 後續 volume_skeleton / writer 才能遵照拓撲架構生成。
        if not _is_geometry_ready(novel_id):
            task.current_stage = "geometry"
            task.progress_percent = 37
            task.status_message = "正在鋪設全書敘事幾何骨架 (長距伏筆/多線合流/主題對比)..."
            task.log("開始生成敘事幾何骨架 (Geometry-First, 純程式零 LLM)...")
            self._execute_stage_with_retry(
                task=task,
                stage="geometry",
                task_type="generate",
                instruction="請根據已確立的分卷架構鋪設全書敘事幾何骨架 (Motif 拓撲編織)",
                user_prompt="生成全書敘事幾何骨架",
                verify_fn=lambda: _is_geometry_ready(novel_id),
            )
            task.log("✅ 敘事幾何骨架已鋪設完成並持久化！")
            db.save_chat_message(novel_id, "assistant", "🧭 **【系統進度】** 全書敘事幾何骨架 (長距伏筆/多線合流/主題對比邊) 已鋪設完成，後續細綱與正文將遵照拓撲架構生成！", message_type="pipeline")
        else:
            task.log("敘事幾何骨架已就緒，跳過生成。")

        # 4.6 宏觀語義填充 (Macro Semantic): 為幾何篇卷與線程注入故事主題、衝突核心與具體劇本線索
        if task.stop_requested: return
        if not _is_macro_semantic_ready(novel_id):
            task.current_stage = "macro_semantic"
            task.progress_percent = 38
            task.status_message = "正在填充宏觀幾何語義 (篇卷主題/核心衝突/線程懸念)..."
            task.log("開始填充宏觀敘事語義 (Pass 1 & Pass 2: 篇卷與線程主題)...")
            self._execute_stage_with_retry(
                task=task,
                stage="macro_semantic",
                task_type="generate",
                instruction="請為幾何篇卷與線程填充宏觀故事主題、衝突核心與具體劇本線索",
                user_prompt="填充宏觀幾何語義",
                verify_fn=lambda: _is_macro_semantic_ready(novel_id),
            )
            task.log("✅ 宏觀幾何語義已填充完成！")
            db.save_chat_message(novel_id, "assistant", "🎨 **【系統進度】** 全書宏觀故事主題與幾何線程懸念已填充完成！", message_type="pipeline")
        else:
            task.log("宏觀幾何語義已就緒，跳過生成。")

        # 4.7 角色幾何語義填充 (Character Semantic): 將人物綁定至幾何角色弧線並注入心境轉折抉擇
        if task.stop_requested: return
        if not _is_character_semantic_ready(novel_id):
            task.current_stage = "character_semantic"
            task.progress_percent = 39
            task.status_message = "正在綁定角色幾何弧線與關鍵心境位移 (Pass 3)..."
            task.log("開始填充角色幾何語義 (角色人物綁定與心境轉折抉擇)...")
            self._execute_stage_with_retry(
                task=task,
                stage="character_semantic",
                task_type="generate",
                instruction="請將角色聖經人物綁定至幾何角色弧線，並填充關鍵心境位移與代價抉擇",
                user_prompt="綁定角色弧線與心境位移",
                verify_fn=lambda: _is_character_semantic_ready(novel_id),
            )
            task.log("✅ 角色幾何語義已填充完成！")
            db.save_chat_message(novel_id, "assistant", "🎭 **【系統進度】** 角色人物已綁定至幾何弧線，關鍵心境轉變與抉擇已注入！", message_type="pipeline")
        else:
            task.log("角色幾何語義已就緒，跳過生成。")

        # 4.8 跨距關聯邊語義填充 (Cross Relation): 為幾何跨距 Motif 邊注入因果關係與碰撞動機
        if task.stop_requested: return
        if not _is_cross_relation_ready(novel_id):
            task.current_stage = "cross_relation"
            task.progress_percent = 40
            task.status_message = "正在為跨距 Motif 邊注入因果關係與碰撞動機 (Pass 4)..."
            task.log("開始填充跨線關聯語義 (Motif 邊因果與碰撞理由)...")
            self._execute_stage_with_retry(
                task=task,
                stage="cross_relation",
                task_type="generate",
                instruction="請為幾何跨距 Motif 邊注入因果關係、多線碰撞矛盾與哲學對照理由",
                user_prompt="填充跨線關聯語義",
                verify_fn=lambda: _is_cross_relation_ready(novel_id),
            )
            task.log("✅ 跨線關聯語義已填充完成！")
            db.save_chat_message(novel_id, "assistant", "🔗 **【系統進度】** 跨距 Motif 關聯因果與碰撞動機已注入完畢！", message_type="pipeline")
        else:
            task.log("跨線關聯語義已就緒，跳過生成。")

    def _phase_volume_skeletons(
        self,
        task: NovelPipelineTask,
        novel_id: str,
        vols: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """步驟 5：逐卷檢查並分批規劃全部分卷章節骨架細綱，回傳更新後的分卷列表。"""
        for v_idx, vol in enumerate(vols, start=1):
            if task.stop_requested: return
            vol_idx = int(vol.get("volume_index") or v_idx)
            vol_title = vol.get("title", f"第 {vol_idx} 卷")
            missing_chapters = db.volume_missing_chapter_indexes(vols, vol_idx)
            if missing_chapters:
                batches = split_consecutive_batches(missing_chapters, batch_size=VOLUME_SKELETON_BATCH_SIZE)
                total_batches = len(batches)
                task.current_stage = f"volume_skeleton_vol{vol_idx}"
                task.log(f"開始規劃第 {vol_idx} 卷【{vol_title}】章節骨架細綱（缺失 {len(missing_chapters)} 章，後端自主拆分為 {total_batches} 批次生成）...")

                for b_idx, batch_chs in enumerate(batches, start=1):
                    if task.stop_requested: return
                    b_start, b_end = min(batch_chs), max(batch_chs)
                    b_count = len(batch_chs)
                    batch_progress = 40 + int(((v_idx - 1 + (b_idx / total_batches)) / len(vols)) * 10)
                    task.progress_percent = min(50, batch_progress)
                    task.status_message = f"正在生成第 {vol_idx}/{len(vols)} 卷【{vol_title}】第 {b_start}-{b_end} 章骨架細綱 (批次 {b_idx}/{total_batches})..."
                    task.log(f"開始生成第 {vol_idx} 卷【{vol_title}】章節骨架細綱 (批次 {b_idx}/{total_batches}: 第 {b_start}-{b_end} 章，共 {b_count} 章)...")

                    self._execute_stage_with_retry(
                        task=task,
                        stage="volume_skeleton",
                        task_type="generate",
                        target={
                            "volume_index": vol_idx,
                            "batch_indexes": batch_chs,
                            "start_chapter": b_start,
                            "end_chapter": b_end,
                        },
                        instruction=f"請規劃第 {vol_idx} 卷（{vol_title}）第 {b_start} 至第 {b_end} 章的情節骨架細綱（批次 {b_idx}/{total_batches}），緊密承接前文既有章節",
                        user_prompt=f"生成第 {vol_idx} 卷第 {b_start}-{b_end} 章詳細骨架",
                        verify_fn=lambda v=vol_idx, chs=batch_chs: _are_batch_chapters_ready(novel_id, v, chs),
                    )
                    task.log(f"✅ 第 {vol_idx} 卷【{vol_title}】第 {b_start}-{b_end} 章骨架細綱已完成！")

                task.log(f"🎉 第 {vol_idx} 卷【{vol_title}】全卷章節細綱骨架規劃完成！")
                try:
                    from backend.agents.setting_auditor import run_setting_audit
                    audit_b = run_setting_audit(novel_id, "skeleton", {"volume_index": vol_idx})
                    task.log(f"⚙️ [Setting Audit B] 第 {vol_idx} 卷骨架設定與因果合理性審計完成 (結果: {audit_b.get('overall_decision')})")
                except Exception as sb_exc:
                    task.log(f"⚠️ Setting Audit B 執行異常 (非致命): {sb_exc}", level="warn")
                vols = db.get_volumes(novel_id)

        db.save_chat_message(novel_id, "assistant", "📝 **【系統進度】** 全書所有分卷詳細情節骨架與細綱已全數生成完畢！", message_type="pipeline")
        async_backup(reason=f"Auto flow [{task.novel_title}]: all volume skeletons finished")
        return vols

    def _phase_character_roster_guard(
        self,
        task: NovelPipelineTask,
        novel_id: str,
        vols: List[Dict[str, Any]],
    ):
        """步驟 5.5：角色一致性與名冊完整性防呆校驗。"""
        try:
            char_data = db.get_latest_characters(novel_id)
            existing_names = set()
            if char_data and char_data.get("parsed_data"):
                parsed = char_data["parsed_data"]
                ch_list = parsed.get("characters", []) if isinstance(parsed, dict) else (parsed if isinstance(parsed, list) else [])
                for c in ch_list:
                    if isinstance(c, dict) and c.get("name"):
                        existing_names.add(str(c["name"]).strip())

            # 收集全書已規劃章節大綱中活躍的角色
            missing_char_cards = []
            GENERIC_IGNORE = {
                "主角", "群眾", "眾人", "路人", "守衛", "衛兵", "NPC", "某人", "乘客", "掌櫃", "店小二",
                "殺手", "刺客", "弟子", "長老", "侍衛", "管家", "僕人", "士兵", "隨從", "黑衣人", "無名氏"
            }
            for vol in vols:
                ch_outline = vol.get("chapters_outline") or []
                if isinstance(ch_outline, str):
                    try:
                        ch_outline = json.loads(ch_outline)
                    except Exception:
                        ch_outline = []
                for ch in ch_outline:
                    if not isinstance(ch, dict):
                        continue
                    act = ch.get("characters_active") or []
                    if isinstance(act, str):
                        act = [a.strip() for a in act.replace("，", ",").replace("、", ",").split(",") if a.strip()]
                    for name in act:
                        name_clean = str(name).strip()
                        if not name_clean or len(name_clean) > 15 or name_clean in GENERIC_IGNORE:
                            continue
                        if name_clean not in existing_names:
                            ch_i = ch.get("chapter_index", 1)
                            missing_char_cards.append({
                                "name": name_clean,
                                "role": "大綱出場角色",
                                "personality": "行事符合大綱情節脈絡，具備明確立場與動機",
                                "motivation": f"於第 {ch_i} 章登場推動主線",
                                "first_appearance_chapter": ch_i,
                            })
                            existing_names.add(name_clean)

            if missing_char_cards:
                added = db.append_or_merge_characters(novel_id, missing_char_cards)
                task.log(f"💡 [角色一致性守護] 偵測到大綱活躍角色尚未立卡，已自動合流補齊 {len(added)} 位：{', '.join(added)}")
                db.save_chat_message(
                    novel_id,
                    "assistant",
                    f"🛡️ **【角色庫合流防呆通報】** 正文寫作啟動前，已自動補齊大綱中出場的 {len(added)} 位角色卡：{', '.join(added)}，杜絕正文盲猜與立場偏離！",
                    message_type="chat"
                )
        except Exception as e:
            task.log(f"⚠️ 角色庫完整性檢查發生異常（非致命）：{e}", level="warn")

    def _prepare_chapter_pipeline(
        self,
        task: NovelPipelineTask,
        novel_id: str,
    ):
        """步驟 6 前置：取得分卷/細綱並盤點已寫章節，回傳 (vols, total_target, written_rows, written_indices)。"""
        vols = db.get_volumes(novel_id)
        if not vols:
            raise RuntimeError("分卷結構尚未就緒，無法進入正文撰寫流水線。")
        plot_data = db.get_stitched_plot(novel_id)
        planned_chapters = plot_data.get("chapters", []) if plot_data else []
        if not planned_chapters:
            raise RuntimeError("全書章節細綱尚未就緒，無法進入正文撰寫流水線。")

        total_target = len(planned_chapters)
        task.total_chapters = total_target
        task.log(f"進入正文寫作流水線，全書共規劃 {total_target} 章節")

        existing_db_chapters = db.get_chapters(novel_id)
        written_rows = {
            int(c.get("chapter_index") or 0): c
            for c in existing_db_chapters
            if c.get("content")
            and len(c.get("content", "").strip()) >= 50
            and not is_refusal_or_disclaimer(c.get("content", ""))
        }
        written_indices = set(written_rows.keys())
        return vols, total_target, written_rows, written_indices

    def _write_single_chapter(
        self,
        task: NovelPipelineTask,
        novel_id: str,
        vols: List[Dict[str, Any]],
        ch_idx: int,
        total_target: int,
        written_rows: Dict[int, Dict[str, Any]],
        editor_retry_only: bool,
    ):
        """步驟 6 內層：單章狀態機（Writer -> Writer Gate -> Editor -> Final Gate -> Graph）。

        回傳 (更新後 vols, stopped_before_editor)；stopped_before_editor 為 True 時呼叫端須中止章節迴圈。
        """
        # 確保該章所屬的卷具備骨架
        curr_vol_idx = db.get_chapter_volume_index(vols, ch_idx) if vols else None
        vols = self._ensure_chapter_volume_skeleton(task, novel_id, vols, ch_idx, curr_vol_idx)

        # 即使是 Editor-only recovery，也必須先重新跑 Writer Gate。
        # 否則舊的短稿、拒答稿或時序壞稿可能直接繞過硬性驗收。
        current_state = "WRITER_GATE" if editor_retry_only else "WRITER"
        writer_retries = 0
        # 外層 Writer 嘗試維持原有倍率上限；每輪均攜帶 Director 定向修正指示。
        max_writer_retries = 3 * RETRY_MULTIPLIER
        director_eval = {}
        writer_repair_instruction = ""
        last_writer_failure = ""

        while not task.stop_requested:
            if current_state == "WRITER":
                if writer_retries >= max_writer_retries:
                    failure_reason = last_writer_failure or "; ".join(director_eval.get("issues") or []) or "Writer 未產出可驗收正文"
                    task.log(
                        f"🚫 第 {ch_idx} 章 Writer 已完成 {writer_retries} 輪定向修正仍未通過，標記 writer_failed：{failure_reason}",
                        level="error",
                    )
                    try:
                        db.save_director_review_status(
                            novel_id=novel_id,
                            stage_name="writer",
                            status="writer_failed",
                            block_name=f"chapter_{ch_idx}",
                            volume_index=curr_vol_idx,
                            chapter_index=ch_idx,
                            reason=f"Writer 定向修正達到上限 {max_writer_retries} 輪：{failure_reason}",
                            decision_json=director_eval or {"error": failure_reason},
                        )
                    except Exception:
                        pass
                    return vols, False

                writer_retries += 1
                try:
                    self._run_writer_for_chapter(
                        task, novel_id, ch_idx, total_target, False, written_rows,
                        repair_instruction=writer_repair_instruction,
                    )
                    current_state = "WRITER_GATE"
                except StageRedirectException as redirect_exc:
                    if redirect_exc.target_stage == "editor":
                        current_state = "EDITOR"
                    else:
                        current_state = "WRITER"
                except ChapterHaltedException:
                    task.log(f"🛑 第 {ch_idx} 章 Writer 流程終止（HALT_CHAPTER），保留草稿", level="warn")
                    return vols, False
                except PipelineHaltedException:
                    raise
                except Exception as writer_exc:
                    last_writer_failure = str(writer_exc)
                    writer_repair_instruction = (
                        "上一輪 Writer 生成或存檔失敗，請依錯誤原因採用不同生成方式，並確認產出完整正文且確實寫入章節資料：\n"
                        + last_writer_failure
                    )
                    task.log(
                        f"⚠️ 第 {ch_idx} 章 Writer 本輪呼叫失敗（定向輪次 {writer_retries}/{max_writer_retries}）：{writer_exc}；將重新執行 Writer。",
                        level="warn",
                    )
                    current_state = "WRITER"

            elif current_state == "WRITER_GATE":
                director_eval = self._run_director_chapter_gate(task, novel_id, ch_idx, curr_vol_idx)
                if director_eval.get("writer_failed") or not director_eval.get("passed", False):
                    writer_repair_instruction = str(director_eval.get("repair_instruction") or "")
                    last_writer_failure = "; ".join(director_eval.get("issues") or []) or "Writer Gate 未通過"
                    task.log(
                        f"🚫 [Writer Gate 失敗] 第 {ch_idx} 章未通過驗收，不進入 Editor；"
                        f"將帶著 Director 定向指示回到 Writer（第 {writer_retries}/{max_writer_retries} 輪）：{last_writer_failure}",
                        level="error",
                    )
                    current_state = "WRITER"
                    continue
                current_state = "EDITOR"

            elif current_state == "EDITOR":
                editor_result = self._run_editor_for_chapter(task, novel_id, ch_idx, total_target, curr_vol_idx, director_eval)
                if editor_result == "REDIRECT_TO_WRITER":
                    task.log(f"🔀 [狀態機路由] Editor 指示重定向至 Writer，第 {ch_idx} 章重新寫作！", level="warn")
                    current_state = "WRITER"
                    continue
                elif editor_result == "HALT_CHAPTER":
                    task.log(f"🛑 [狀態機路由] 第 {ch_idx} 章暫停（HALT_CHAPTER），保留草稿並跳出本章", level="warn")
                    return vols, False
                elif editor_result == "FAILED":
                    task.log(f"⚠️ 第 {ch_idx} 章 Editor 精修失敗，已保留 Writer 初稿，略過後續門禁進入下一章", level="warn")
                    return vols, False
                else:  # PASS
                    task.log(f"✅ 第 {ch_idx} 章精修完成並已存入資料庫！")
                    current_state = "FINAL_GATE"

            elif current_state == "FINAL_GATE":
                final_passed = self._run_final_quality_gate(task, novel_id, ch_idx, curr_vol_idx)
                if not final_passed:
                    # 未通過最終品質閘門的正文不得進入長期記憶，避免污染
                    # temporal graph、術語庫與下一章的上下文。
                    task.log(
                        f"🚫 第 {ch_idx} 章 Final Gate 未通過，跳過圖譜抽取並保留人工檢視狀態。",
                        level="error",
                    )
                    return vols, False
                current_state = "GRAPH_EXTRACTION"

            elif current_state == "GRAPH_EXTRACTION":
                # (2.5) 同步提取時序事實與動態圖譜 (Graphiti Temporal Graph)
                graph_res: Dict[str, Any] = {}
                ch_text = ""
                graph_failed = False
                try:
                    task.log(f"🧠 正在為第 {ch_idx} 章同步提取時序記憶圖譜事實...")
                    ch_obj = db.get_chapter(novel_id, ch_idx)
                    ch_text = (ch_obj.get("content") or "") if ch_obj else ""
                    if ch_text and len(ch_text.strip()) > 50:
                        graph_res = ChapterFactExtractor.process_chapter_prose(
                            novel_id=novel_id,
                            chapter_index=ch_idx,
                            chapter_text=ch_text,
                            agent_name="copilot",
                        ) or {}
                        facts_added = graph_res.get("facts_added", 0)
                        terms_created = graph_res.get("terms_created", 0)
                        terms_updated = graph_res.get("terms_updated", 0)
                        task.log(f"✅ 第 {ch_idx} 章時序記憶抽取完成 (新增 {facts_added} 條世界線動態事實，術語庫新增 {terms_created}/更新 {terms_updated})")
                except Exception as g_exc:
                    graph_failed = True
                    task.log(f"⚠️ 第 {ch_idx} 章時序記憶提取異常 (安全跳過不阻礙後續寫作): {g_exc}", level="warn")
                    try:
                        db.save_chat_message(
                            novel_id,
                            "assistant",
                            f"⚠️ 第 {ch_idx} 章正文已完成，但時序記憶尚未同步；後續章節不得假設本章圖譜已更新。",
                            message_type="pipeline",
                        )
                    except Exception as log_exc:
                        task.log(f"⚠️ 記錄圖譜同步失敗通知時發生異常：{log_exc}", level="warn")

                # (2.6) 註冊衝突簽名與長程敘事因果審計
                try:
                    self._run_narrative_diagnostics(task, novel_id, vols, ch_idx, graph_res, ch_text)
                except Exception as n_exc:
                    task.log(f"⚠️ 第 {ch_idx} 章長程敘事診斷異常 (安全跳過不阻礙): {n_exc}", level="warn")

                db.save_chat_message(
                    novel_id,
                    "assistant",
                    f"✍️ **【章節完成進度】** 第 {ch_idx} 章正文已由 Writer 撰寫並經 Editor 潤色精修完成，已成功入庫！"
                    f"\n- 進度：第 {ch_idx}/{total_target} 章 ({task.progress_percent}%)"
                    f"\n- 時序記憶：{'待同步' if graph_failed else '已同步'}",
                    message_type="pipeline",
                )
                time.sleep(0.5)
                break

        return vols, False

    def _ensure_chapter_volume_skeleton(
        self,
        task: NovelPipelineTask,
        novel_id: str,
        vols: List[Dict[str, Any]],
        ch_idx: int,
        curr_vol_idx: Optional[int],
    ) -> List[Dict[str, Any]]:
        """確保該章所屬的卷具備骨架細綱，缺失時即時補生成並回傳更新後的分卷列表。"""
        if curr_vol_idx:
            missing_in_curr = db.volume_missing_chapter_indexes(vols, curr_vol_idx)
            if ch_idx in missing_in_curr:
                task.log(f"第 {ch_idx} 章所屬第 {curr_vol_idx} 卷缺失該章細綱，正在補充生成第 {curr_vol_idx} 卷骨架...")
                self._execute_stage_with_retry(
                    task=task,
                    stage="volume_skeleton",
                    task_type="generate",
                    target={"volume_index": int(curr_vol_idx)},
                    instruction=f"請詳細規劃第 {curr_vol_idx} 卷各章的情節要點、視角人物、場景與伏筆回收點",
                    user_prompt=f"生成第 {curr_vol_idx} 卷詳細細綱",
                    verify_fn=lambda v=int(curr_vol_idx): _has_volume_skeleton(novel_id, v),
                )
                vols = db.get_volumes(novel_id)
        return vols

    def _run_writer_for_chapter(
        self,
        task: NovelPipelineTask,
        novel_id: str,
        ch_idx: int,
        total_target: int,
        editor_retry_only: bool,
        written_rows: Dict[int, Dict[str, Any]],
        repair_instruction: str = "",
    ) -> bool:
        """(1) 正文寫作：沿用既有初稿或呼叫 Writer Agent 撰寫（含自動重試與驗證）。"""
        if editor_retry_only:
            existing_draft = (written_rows.get(ch_idx) or {}).get("content") or ""
            task.current_stage = f"writer_ch{ch_idx}_reused"
            task.log(f"第 {ch_idx} 章沿用既有初稿（{len(existing_draft.strip())} 字），直接進入總監審查與精修...")
        else:
            task.current_stage = f"writer_ch{ch_idx}"
            task.status_message = f"✍️ 正在由 Writer Agent 撰寫第 {ch_idx}/{total_target} 章正文..."
            task.log(f"開始撰寫第 {ch_idx} 章正文...")

            writer_instruction = (
                f"【Writer Gate 定向修正】\n{repair_instruction}\n\n"
                if repair_instruction else ""
            ) + f"請根據大綱撰寫第 {ch_idx} 章可供 Editor 擴寫的劇情底稿，確保事件因果、角色行動與關鍵對白完整；環境、衣著、表情與感官細節由 Editor 擴寫"
            self._execute_stage_with_retry(
                task=task,
                stage="writer",
                task_type="generate",
                scope="chapter",
                target={"chapter_index": ch_idx},
                instruction=writer_instruction,
                user_prompt=f"撰寫第 {ch_idx} 章",
                verify_fn=lambda c=ch_idx: _is_chapter_written(novel_id, c),
                max_retries=3,
            )
            task.log(f"第 {ch_idx} 章初稿撰寫完成！")

    def _run_director_chapter_gate(
        self,
        task: NovelPipelineTask,
        novel_id: str,
        ch_idx: int,
        curr_vol_idx: Optional[int],
    ) -> Dict[str, Any]:
        """(1.5) 總監章節品質與時空一致性審查 (Director Quality Gate)。"""
        director_eval: Dict[str, Any] = {}
        try:
            from backend.services.director.tool_registry.evaluator import evaluate_output
            ch_draft = db.get_chapter(novel_id, ch_idx)
            draft_content = (ch_draft.get("content") or "").strip() if ch_draft else ""
            if not draft_content or len(draft_content) < 50:
                director_eval = {
                    "passed": False,
                    "critical_drift": True,
                    "issues": ["content 不可為空：正文未生成或長度不足 50 字"],
                }
            else:
                director_eval = evaluate_output(
                    stage_name="writer",
                    output_content=draft_content,
                    novel_id=novel_id,
                    chapter_index=ch_idx,
                )

            eval_passed = director_eval.get("passed", False)
            is_critical = director_eval.get("critical_drift", False)
            eval_issues = director_eval.get("issues", [])

            hard_writer_issues = [
                issue for issue in eval_issues
                if issue.startswith((
                    "content 不可為空",
                    "content 長度不足",
                    "content 含占位或系統標記",
                    "content 包含 AI 拒答",
                    "content 包含元敘事",
                    "【場景地點漂移】",
                    "【時間連續性矛盾】",
                    "【開篇定型模板重複】",
                    "【敘事診斷紅線",
                ))
            ]

            if hard_writer_issues and not task.stop_requested:
                task.log(f"🚨 [總監章節硬性攔截] 第 {ch_idx} 章需先修正：{'; '.join(hard_writer_issues)}。", level="warn")
                director_prompt = ""
                try:
                    director_decision = get_director_decision_sync(
                        novel_id=novel_id,
                        current_stage="writer",
                        user_prompt=(
                            f"審查第 {ch_idx} 章 Writer 初稿。Python 硬性驗收已指出："
                            + "；".join(hard_writer_issues)
                            + "。請查閱完整世界觀、相關角色 Bible、本章及前後章大綱、正文和連續性資料，"
                            "給 Writer 可直接執行、逐項對應缺陷的修正指示。不得只重述錯誤，也不得改動已確立的角色動機或事件因果。"
                        ),
                        chapter_index=ch_idx,
                        volume_index=curr_vol_idx,
                        extra_context=(
                            "【Python 驗收事實，必須逐項消除】\n- "
                            + "\n- ".join(hard_writer_issues)
                            + f"\n\n【目前正文】\n{draft_content[:24000]}"
                        ),
                    )
                    if director_decision:
                        director_prompt = str(
                            director_decision.get("agent_prompt")
                            or director_decision.get("hint")
                            or ""
                        ).strip()
                        if director_prompt:
                            task.log(f"🎬 [Director Writer 修正方向] 第 {ch_idx} 章：{director_prompt[:500]}")
                except Exception as director_exc:
                    task.log(f"⚠️ Writer Gate Director 診斷失敗，採用明確驗收修正指示：{director_exc}", level="warn")

                db.save_chat_message(
                    novel_id,
                    "director",
                    f"🚨 **【總監審查打回 - 第 {ch_idx} 章】**\n硬性驗收缺陷：\n- " + "\n- ".join(hard_writer_issues)
                    + (f"\n\nDirector 修正方向：\n{director_prompt}" if director_prompt else ""),
                    message_type="director"
                )
                fix_instruction = (
                    f"【總監剛性修正指示】\nPython 驗收缺陷：\n- "
                    + "\n- ".join(hard_writer_issues)
                    + "\n"
                    + (f"\n【Director 根據世界觀、角色 Bible 與大綱給出的修正方向】\n{director_prompt}\n" if director_prompt else "")
                    + "\n請依每項缺陷實際改寫正文，維持已確認的世界觀、角色動機、事件因果與大綱。"
                )
                scene_places = []
                for issue in hard_writer_issues:
                    if issue.startswith("【場景地點漂移】") and "「" in issue and "」" in issue:
                        scene_places.append(issue.split("「", 1)[1].split("」", 1)[0])
                if scene_places:
                    fix_instruction += (
                        "\n【場景地點明確修正】請在正文第一段前 500 字內，逐字寫出大綱指定地標："
                        + "、".join(dict.fromkeys(scene_places))
                        + "。並用角色當下看見、聽見或觸及的細節自然帶出，不能只在提示或章名中出現。"
                    )
                try:
                    self._execute_stage_with_retry(
                        task=task,
                        stage="writer",
                        task_type="generate",
                        scope="chapter",
                        target={"chapter_index": ch_idx},
                        instruction=fix_instruction,
                        user_prompt=f"修正時空漂移重寫第 {ch_idx} 章",
                        verify_fn=lambda c=ch_idx: _is_chapter_written(novel_id, c),
                        max_retries=1,
                    )
                    # 重新獲取修復後的內容並再次快速校驗
                    ch_draft = db.get_chapter(novel_id, ch_idx)
                    draft_content = (ch_draft.get("content") or "").strip() if ch_draft else ""
                    director_eval = evaluate_output(
                        stage_name="writer",
                        output_content=draft_content,
                        novel_id=novel_id,
                        chapter_index=ch_idx,
                    )
                    eval_passed = director_eval.get("passed", False)
                    eval_issues = director_eval.get("issues", [])
                    hard_writer_issues = [
                        issue for issue in eval_issues
                        if issue.startswith((
                            "content 不可為空",
                            "content 長度不足",
                            "content 含占位或系統標記",
                            "content 包含 AI 拒答",
                            "content 包含元敘事",
                            "【場景地點漂移】",
                            "【時間連續性矛盾】",
                            "【開篇定型模板重複】",
                            "【敘事診斷紅線",
                        ))
                    ]
                except Exception as fix_exc:
                    task.log(f"❌ Writer 定向修正失敗：{fix_exc}", level="error")
                    eval_passed = False
                    hard_writer_issues.append(f"Writer 重寫失敗：{fix_exc}")
                    director_eval["repair_instruction"] = fix_instruction

            # Writer gate owns structural/continuity blockers. Descriptive and stylistic
            # findings remain attached for Editor, whose job is to turn the draft into prose.
            if hard_writer_issues:
                director_eval["passed"] = False
                director_eval["writer_failed"] = True
                director_eval["repair_instruction"] = fix_instruction if 'fix_instruction' in locals() else "；".join(hard_writer_issues)
                task.log(f"🚫 [Writer Gate 失敗] 第 {ch_idx} 章 Writer 修正未通過驗收，停止進入 Editor：{'; '.join(hard_writer_issues or eval_issues)}", level="error")
                try:
                    db.save_director_review_status(
                        novel_id=novel_id,
                        stage_name="writer",
                        status="writer_failed",
                        block_name=f"chapter_{ch_idx}",
                        volume_index=curr_vol_idx,
                        chapter_index=ch_idx,
                        reason="; ".join(hard_writer_issues or eval_issues),
                        decision_json=director_eval,
                    )
                except Exception as d_db_exc:
                    task.log(f"⚠️ 總監審查記錄持久化異常: {d_db_exc}", level="warn")
                return director_eval

            try:
                db.save_director_review_status(
                    novel_id=novel_id,
                    stage_name="writer",
                    status="passed",
                    block_name=f"chapter_{ch_idx}",
                    volume_index=curr_vol_idx,
                    chapter_index=ch_idx,
                    reason="; ".join(eval_issues) if eval_issues else "總監校驗通過",
                    decision_json=director_eval,
                )
            except Exception:
                pass
            if eval_issues:
                director_eval["editor_handoff_issues"] = list(eval_issues)
            task.log(f"✅ [Writer Gate 通過] 第 {ch_idx} 章劇情底稿符合硬性因果與連續性要求，交由 Editor 擴寫精修。")
            director_eval["passed"] = True
            director_eval["writer_failed"] = False
            return director_eval
        except Exception as d_exc:
            task.log(f"⚠️ 總監章節審查異常: {d_exc}", level="warn")
            return {"passed": False, "writer_failed": True, "error": str(d_exc)}

    def _run_editor_for_chapter(
        self,
        task: NovelPipelineTask,
        novel_id: str,
        ch_idx: int,
        total_target: int,
        curr_vol_idx: Optional[int],
        director_eval: Dict[str, Any],
    ) -> str:
        """(2) 編輯精修：前置正文檢查，成功回傳 'PASS'；重定向回傳 'REDIRECT_TO_WRITER'；HALT 回傳 'HALT_CHAPTER'；失敗回傳 'FAILED'。"""
        # 第一階段：先擋掉 Editor 空稿
        chapter = db.get_latest_chapter(novel_id, ch_idx)
        content = (chapter.get("content") or "").strip() if chapter else ""
        if len(content) < 50:
            task.log(
                f"🚨 Editor 前置檢查失敗：第 {ch_idx} 章正文不存在或過短（{len(content)} < 50 字），停止 Editor 重試並回到 Writer。",
                level="warn",
            )
            return "REDIRECT_TO_WRITER"

        task.current_stage = f"editor_ch{ch_idx}"
        task.status_message = f"🔍 正在由 Editor Agent 精修第 {ch_idx}/{total_target} 章文字與修辭..."
        task.log(f"開始對第 {ch_idx} 章進行潤色與精修...")

        editor_instruction = f"請對第 {ch_idx} 章進行修辭優化、節奏微調與行文潤色"
        if director_eval and director_eval.get("issues"):
            editor_instruction += f"，並特別注意消弭總監提示之問題：{'; '.join(director_eval['issues'][:3])}"

        try:
            self._execute_stage_with_retry(
                task=task,
                stage="editor",
                task_type="refine",
                scope="chapter",
                target={"chapter_index": ch_idx},
                instruction=editor_instruction,
                user_prompt=f"精修第 {ch_idx} 章",
                verify_fn=lambda c=ch_idx: _is_chapter_written(novel_id, c),
            )
            return "PASS"
        except StageRedirectException as redirect_exc:
            if redirect_exc.target_stage == "writer":
                task.log(f"🔀 [Director 路由] Editor 收到重定向指示：回到 Writer 階段（{redirect_exc.reason}）", level="warn")
                return "REDIRECT_TO_WRITER"
            raise redirect_exc
        except ChapterHaltedException as halt_exc:
            task.log(f"🛑 [Director 路由] Editor 收到章節中止指示：{halt_exc.reason}", level="warn")
            return "HALT_CHAPTER"
        except Exception as editor_exc:
            # Editor 精修失敗不可中斷整條管線：Writer 初稿已保留，
            # 記一筆 failed 驗收供下次重啟時僅重試 Editor，然後繼續下一章。
            task.log(
                f"⚠️ 第 {ch_idx} 章精修失敗（已達重試上限）：{editor_exc}；"
                f"已保留 Writer 初稿，下次重啟將僅重試 Editor，流程繼續下一章...",
                level="warn",
            )
            try:
                db.save_director_review_status(
                    novel_id=novel_id,
                    stage_name="editor",
                    status="failed",
                    block_name=f"chapter_{ch_idx}",
                    volume_index=curr_vol_idx,
                    chapter_index=ch_idx,
                    reason=f"Editor 精修異常失敗，已保留初稿待重試：{editor_exc}",
                    decision_json={"chapter_index": ch_idx, "error": str(editor_exc)},
                )
            except Exception as eval_save_exc:
                task.log(f"⚠️ Editor 失敗記錄儲存失敗：{eval_save_exc}", level="warn")
            try:
                db.save_chat_message(
                    novel_id,
                    "assistant",
                    f"⚠️ **【章節精修失敗通報】** 第 {ch_idx} 章 Writer 初稿已保留，"
                    f"Editor 精修失敗原因：{editor_exc}。下次啟動將自動僅重試 Editor，流程已繼續下一章。",
                    message_type="pipeline",
                )
            except Exception:
                pass
            return "FAILED"

    def _run_final_quality_gate(
        self,
        task: NovelPipelineTask,
        novel_id: str,
        ch_idx: int,
        curr_vol_idx: Optional[int],
    ):
        """Editor 後的確定性品質閘門：最多三次定向修訂並保留最終驗收狀態。"""
        from backend.services.director.tool_registry.evaluator import evaluate_output
        final_editor_eval = {}
        repair_failures = []
        for quality_attempt in range(FINAL_QUALITY_GATE_RETRIES):
            ch_final = db.get_chapter(novel_id, ch_idx)
            final_content = (ch_final.get("content") or "") if ch_final else ""
            final_editor_eval = evaluate_output(
                stage_name="editor",
                output_content=final_content,
                novel_id=novel_id,
                chapter_index=ch_idx,
            ) if final_content else {"passed": False, "issues": ["Editor 後正文為空"]}
            if final_editor_eval.get("passed"):
                break
            final_issues = final_editor_eval.get("issues") or []
            if quality_attempt >= FINAL_QUALITY_GATE_RETRIES - 1 or task.stop_requested:
                break
            task.log(
                f"⚠️ [Editor 後品質閘門] 第 {ch_idx} 章第 {quality_attempt + 1} 次驗收未通過，定向修訂：{'; '.join(final_issues[:8])}",
                level="warn",
            )
            from backend.agents.editor.runner import run_editor_agent
            try:
                director_prompt = ""
                try:
                    director_decision = get_director_decision_sync(
                        novel_id=novel_id,
                        current_stage="editor",
                        user_prompt=(
                            f"審查第 {ch_idx} 章 Editor 後正文。Python Final Gate 已指出："
                            + "；".join(final_issues[:12])
                            + "。請結合本書世界觀、相關角色 Bible、本章大綱與正文，"
                            "在 agent_prompt 中提出逐項可執行的修訂方向，指出應改的位置與做法，"
                            "維持角色動機、因果與大綱事件。"
                        ),
                        chapter_index=ch_idx,
                        volume_index=curr_vol_idx,
                        extra_context=(
                            "【Python Final Gate 缺陷】\n- "
                            + "\n- ".join(final_issues[:12])
                            + f"\n\n【目前正文】\n{final_content[:24000]}"
                        ),
                    )
                    if director_decision:
                        director_prompt = str(
                            director_decision.get("agent_prompt")
                            or director_decision.get("hint")
                            or ""
                        ).strip()
                    if director_prompt:
                        task.log(f"🎬 [Director Final Gate 修正方向] 第 {ch_idx} 章：{director_prompt[:500]}")
                    else:
                        task.log(f"⚠️ 第 {ch_idx} 章 Final Gate Director 未提供 agent_prompt，改用明確缺陷指令。", level="warn")
                except Exception as director_exc:
                    task.log(f"⚠️ 第 {ch_idx} 章 Final Gate Director 診斷失敗：{director_exc}；改用明確缺陷指令。", level="warn")

                repair_lines = [
                    "【總監驗收返修工單】請直接修改正文並逐項消除以下缺陷；不要只回覆處理方式。保留事件因果、角色事實與大綱，不得新增矛盾情節。"
                ]
                if director_prompt:
                    repair_lines.append(f"【Director 依本書設定與本章脈絡給出的修正方向】\n{director_prompt}")
                if repair_failures:
                    repair_lines.append(
                        "【前次返修未生效】前次輸出未被採用，原因如下："
                        + "；".join(repair_failures[-2:])
                        + "。本輪必須產出與原稿有實質差異的完整正文，且不得引入新的套路句。"
                    )
                for issue in final_issues[:12]:
                    if "場景氛圍提醒" in issue:
                        scene_anchor = ""
                        try:
                            from backend.services import narrative_memory
                            chapter_outline = narrative_memory.get_chapter_outline(novel_id, ch_idx) or {}
                            scene_anchor = str(
                                chapter_outline.get("scene_setting")
                                or chapter_outline.get("location")
                                or ""
                            ).strip()
                        except Exception:
                            pass
                        directive = (
                            (f"場景錨點為「{scene_anchor}」。" if scene_anchor else "依本章大綱的場景錨點，")
                            + "在正文開篇前 500 字內實際補入具體環境感官描寫"
                            "（例如光線、聲音、氣味、溫度或觸感，選擇符合場景者），讓讀者能形成場景畫面；"
                            "第一段須明確讓讀者辨認場景錨點，並讓感官細節由角色正在做的事自然帶出；"
                            "不要只改同義詞，也不要把說明寫在正文之外。"
                        )
                    elif "場景細節提醒" in issue:
                        directive = (
                            "依本章大綱的場景長描述，在正文第一段補入能辨識場景的具體元素，"
                            "並自然融入角色當下的觀察或動作。"
                        )
                    elif "content 長度不足" in issue:
                        directive = (
                            "將正文擴寫至至少 1200 字，透過場景、人物動作表情、心理與感官描寫補足；"
                            "保留所有既有事件，不得灌水或重複。"
                        )
                    else:
                        directive = "依缺陷描述實際修正正文，修改位置與方式須能通過同一項驗收。"
                    repair_lines.append(f"- 驗收缺陷：{issue}\n  必須執行：{directive}")
                repair_instruction = "\n".join(repair_lines)
                before_chapter = db.get_latest_chapter(novel_id, ch_idx) or {}
                before_content = (before_chapter.get("content") or "").strip()
                editor_gen = run_editor_agent(
                    novel_id,
                    ch_idx,
                    edit_instructions=repair_instruction,
                    stream=False,
                    fix_mode=True,
                )
                editor_errors = []
                for chunk in editor_gen:
                    if not isinstance(chunk, str):
                        continue
                    for event_line in chunk.splitlines():
                        event_line = event_line.strip()
                        if not event_line.startswith("data:"):
                            continue
                        try:
                            event = json.loads(event_line[5:].strip())
                        except (TypeError, ValueError):
                            continue
                        if isinstance(event, dict) and event.get("type") == "error":
                            editor_errors.append(str(event.get("message") or "Editor 回報修訂失敗"))
                if editor_errors:
                    raise RuntimeError("；".join(editor_errors[:3]))
                after_chapter = db.get_latest_chapter(novel_id, ch_idx) or {}
                after_content = (after_chapter.get("content") or "").strip()
                if not after_content or after_content == before_content:
                    raise RuntimeError("Editor 已完成呼叫，但章節正文沒有更新；停止重送相同修訂工單")
            except Exception as fix_exc:
                failure_text = f"Final Gate 修訂失敗：{fix_exc}"
                repair_failures.append(failure_text)
                # 保留本輪驗收缺陷，讓下一輪能重新評估目前正文並繼續修訂。
                # 單次 Editor 拒絕或 no_change 不應中止整個 Final Gate。
                final_editor_eval = dict(final_editor_eval or {})
                final_editor_eval["passed"] = False
                final_editor_eval["issues"] = list(final_issues[:12]) + [failure_text]
                task.log(f"⚠️ 第 {ch_idx} 章 Final Gate 修訂呼叫失敗：{fix_exc}", level="warn")
                if "停止重送相同修訂工單" in str(fix_exc):
                    break
                continue
        passed = bool(final_editor_eval.get("passed"))
        if final_editor_eval and not passed:
            remaining = final_editor_eval.get("issues") or []
            task.log(
                f"🚫 [Editor 後品質閘門未通過] 第 {ch_idx} 章已修訂至上限，保留章節供人工檢視：{'; '.join(remaining[:8])}",
                level="error",
            )
        try:
            db.save_director_review_status(
                novel_id,
                stage_name="editor",
                status="passed" if final_editor_eval.get("passed") else "revise",
                block_name=f"chapter_{ch_idx}",
                volume_index=curr_vol_idx,
                chapter_index=ch_idx,
                reason="; ".join(final_editor_eval.get("issues") or []) or "Editor 後硬性品質驗收通過",
                decision_json=final_editor_eval,
            )
        except Exception as eval_save_exc:
            task.log(f"⚠️ Editor 後品質驗收記錄儲存失敗：{eval_save_exc}", level="warn")
        if final_editor_eval and not passed:
            task.log(
                f"⚠️ 第 {ch_idx} 章未通過 Editor 後品質驗收；草稿已保留並標記為待人工檢視，流程繼續下一章："
                + "; ".join((final_editor_eval.get("issues") or [])[:8]),
                level="error",
            )
        return passed

    def _run_narrative_diagnostics(
        self,
        task: NovelPipelineTask,
        novel_id: str,
        vols: List[Dict[str, Any]],
        ch_idx: int,
        graph_res: Dict[str, Any],
        ch_text: str,
    ):
        """(2.6-2.7) 註冊衝突簽名、記錄設定調用、長程敘事審計與閉環自修至通過。"""
        from backend.services.narrative import ConflictLedger, SettingRegistry, NarrativeAuditor
        outline = None
        for v in vols:
            for c in (v.get("chapters_outline") or []):
                if isinstance(c, dict) and c.get("chapter_index") == ch_idx:
                    outline = c
                    break
            if outline:
                break

        hint = outline.get("conflict_signature_hint") if isinstance(outline, dict) else None
        if not isinstance(hint, dict) or not hint:
            # hint 缺失時直接用整章 outline 兜底提取，保證不斷鏈
            hint = outline if isinstance(outline, dict) else None
        # LLM 歸一化簽名優先（同次圖譜提取順帶），失敗則離線啟發式兜底
        llm_sig = (graph_res or {}).get("conflict_signature") or {}
        if not isinstance(llm_sig, dict):
            llm_sig = {}
        sig_dict = ConflictLedger.extract_signature_from_chapter(
            novel_id=novel_id,
            chapter_index=ch_idx,
            outline_hint=hint,
            prose_text=ch_text,
            outline=outline if isinstance(outline, dict) else None,
            llm_signature=llm_sig or None,
        )
        # 冪等：同章已登記則跳過，避免重跑管線產生重複簽名
        existing_sigs = db.get_conflict_signatures(novel_id, limit=500)
        already = any(
            int(s.get("chapter_start") or 0) <= ch_idx <= int(s.get("chapter_end") or s.get("chapter_start") or 0)
            for s in existing_sigs
        )
        sig_row = None
        if not already:
            sig_row = ConflictLedger.record_signature(
                novel_id=novel_id,
                chapter_start=sig_dict["chapter_start"],
                chapter_end=sig_dict["chapter_end"],
                pressure_type=sig_dict["pressure_type"],
                protagonist_strategy=sig_dict["protagonist_strategy"],
                outcome=sig_dict["outcome"],
                initiator=sig_dict.get("initiator"),
                antagonist_goal=sig_dict.get("antagonist_goal"),
                power_used=sig_dict.get("power_used"),
                twist_mechanism=sig_dict.get("twist_mechanism"),
                cost=sig_dict.get("cost"),
                emotional_effect=sig_dict.get("emotional_effect"),
                setting_used=sig_dict.get("setting_used"),
            )
        else:
            sig_row = next(
                (
                    s for s in existing_sigs
                    if int(s.get("chapter_start") or 0) <= ch_idx <= int(s.get("chapter_end") or s.get("chapter_start") or 0)
                ),
                sig_dict,
            )

        # setting_usage 可能是 list[str] / list[dict] / dict / str，四種全吃
        def _iter_setting_names(su):
            if su is None:
                return
            if isinstance(su, str):
                if su.strip():
                    yield su.strip()
                return
            if isinstance(su, dict):
                if su.get("system_name"):
                    yield str(su["system_name"]).strip()
                elif su.get("name"):
                    yield str(su["name"]).strip()
                return
            if isinstance(su, list):
                for item in su:
                    if isinstance(item, dict):
                        nm = item.get("system_name") or item.get("name")
                        if nm and str(nm).strip():
                            yield str(nm).strip()
                    elif isinstance(item, str) and item.strip():
                        yield item.strip()

        # 大綱點名 + LLM 實際調用 + 簽名指名，三路合併去重後記 usage
        _llm_settings = (graph_res or {}).get("setting_usage") or []
        if not isinstance(_llm_settings, list):
            _llm_settings = []
        _seen_names: set = set()
        _all_su = []
        if outline and outline.get("setting_usage"):
            _all_su.append(outline["setting_usage"])
        _all_su.extend(_llm_settings)
        if sig_row and sig_row.get("setting_used"):
            _all_su.append(str(sig_row["setting_used"]))
        for _su_item in _all_su:
            for sys_name in _iter_setting_names(_su_item):
                if sys_name in _seen_names:
                    continue
                _seen_names.add(sys_name)
                ok = SettingRegistry.record_system_usage(
                    novel_id=novel_id,
                    system_name=sys_name,
                    chapter_index=ch_idx,
                )
                if not ok:
                    # 大綱點名了但運作庫沒這個實體：自動補登後再記一次，
                    # 否則 usage_count 永遠是 0。
                    try:
                        db.upsert_setting_system(
                            novel_id=novel_id,
                            name=sys_name,
                            setting_type="generic",
                            mechanism=f"第 {ch_idx} 章劇情調用之世界觀設定",
                            cost="動用該設定須承擔相應代價",
                            boundary="受世界法則與環境條件約束",
                        )
                        SettingRegistry.record_system_usage(
                            novel_id=novel_id,
                            system_name=sys_name,
                            chapter_index=ch_idx,
                        )
                    except Exception:
                        pass
        audit_res = NarrativeAuditor.audit_chapter_prose(
            novel_id=novel_id,
            chapter_index=ch_idx,
            prose_text=ch_text,
            current_outline=outline,
            candidate_conflict_sig=sig_row or sig_dict,
        )
        task.log(f"📊 [Narrative Auditor 2.0] 第 {ch_idx} 章敘事因果診斷完成: [{audit_res.get('overall_action')}]")

        # (2.7b) 標題章號硬檢驗：正文首行若含「第X章」，X 必須等於 ch_idx
        try:
            import re as _re
            _ch_num_map = {
                '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
                '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
                '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15,
                '十六': 16, '十七': 17, '十八': 18, '十九': 19, '二十': 20,
            }
            _first_line = (ch_text or "").strip().split("\n")[0]
            _title_match = _re.search(r'第([\d一二三四五六七八九十百千零]+)[章回]', _first_line)
            if _title_match:
                _title_num_str = _title_match.group(1)
                try:
                    _title_num = int(_title_num_str)
                except ValueError:
                    _title_num = _ch_num_map.get(_title_num_str, -1)
                if _title_num > 0 and _title_num != ch_idx:
                    task.log(
                        f"⚠️ 第 {ch_idx} 章標題章號不一致：正文標題寫「第{_title_num_str}章」，"
                        f"但實際章節索引為 {ch_idx}。已標記待修正。",
                        level="warn",
                    )
        except Exception:
            pass

        # (2.7) 閉環自修「修到好」：判 REVISE/CRITICAL 即反覆
        # 「Editor 重寫 → resolve → 引擎重審 → 總監硬性校驗」，
        # 直到 Narrative Auditor 判決進入通過態（PASS/WATCH/安靜章）
        # 或觸發安全上限（預設 3 輪，防止無人值守無限燒 LLM 配額）；
        # 達上限的殘留診斷保留給看板處置與下一章上下文約束，不阻礙流水線。
        if audit_res.get("overall_action") in ("REVISE", "CRITICAL") and not task.stop_requested:
            try:
                from backend.services.narrative.fix import fix_chapter_until_pass as _auto_fix_loop
                task.log(
                    f"🛠️ 第 {ch_idx} 章診斷為 [{audit_res.get('overall_action')}]，"
                    "啟動閉環修正（修到總監/引擎評斷通過為止）..."
                )
                fix_res = _auto_fix_loop(novel_id, ch_idx, log_fn=task.log)
                reaudit = fix_res.get("final_reaudit") or {}
                loop_status = fix_res.get("status")
                if loop_status == "passed":
                    task.log(
                        f"✅ 第 {ch_idx} 章閉環修正通過（{len(fix_res.get('rounds', []))} 輪、"
                        f"累計處置 {fix_res.get('total_fixed', 0)} 筆診斷，"
                        f"最終判決: [{reaudit.get('overall_action', fix_res.get('final_action'))}]）"
                    )
                elif loop_status == "no_change":
                    task.log(
                        f"⚠️ 第 {ch_idx} 章閉環修正中止（Editor 未產生新版，原文保留；"
                        f"最終判決: [{reaudit.get('overall_action', '?')}]）",
                        level="warn",
                    )
                else:
                    task.log(
                        f"⚠️ 第 {ch_idx} 章閉環修正達安全上限仍為 "
                        f"[{reaudit.get('overall_action', fix_res.get('final_action'))}]；"
                        f"殘留 {fix_res.get('total_fixed', 0)} 筆已處置診斷，"
                        "其餘待看板處置與下一章約束",
                        level="warn",
                    )
                # 修正後正文已變：刷新本章文字供後續圖譜/日誌使用
                try:
                    _fixed_row = db.get_chapter(novel_id, ch_idx)
                    if _fixed_row and (_fixed_row.get("content") or "").strip():
                        ch_text = _fixed_row["content"]
                except Exception:
                    pass
            except Exception as fix_exc:
                task.log(f"⚠️ 第 {ch_idx} 章自動修正異常 (保留原稿繼續): {fix_exc}", level="warn")

    @staticmethod
    def _is_volume_end(vols: List[Dict[str, Any]], chapter_index: int) -> bool:
        """Return whether a chapter is the last planned chapter of its volume."""
        try:
            return any(
                int(chapter_index) == get_volume_chapter_range(vols, int(volume.get("volume_index") or 0))[1]
                for volume in vols or []
            )
        except Exception:
            return False

    def _reconcile_foreshadowing_debts(self, task: NovelPipelineTask, novel_id: str, max_chapter: Optional[int] = None):
        """(2.8) 卷末零 LLM 伏筆回收對帳，並驗證 payoff 的正文證據。"""
        try:
            from backend.services.foreshadowing.blueprint import (
                get_global_foreshadowing_blueprint,
                verify_foreshadowing_payoff,
            )
            _blueprint = get_global_foreshadowing_blueprint(novel_id)
            if _blueprint:
                _alloc = _blueprint.get("foreshadowing_allocations", [])
                _seeds = db.get_foreshadowing_seeds(novel_id)
                _chapters_written = set()
                try:
                    _all_ch = db.get_all_chapters_latest(novel_id)
                    _chapters_written = {
                        int(c.get("chapter_index", 0)) for c in _all_ch
                        if (c.get("content") or "").strip()
                    }
                except Exception:
                    pass
                _overdue = []
                _unverified = []
                for _idx, _pair in enumerate(_alloc):
                    if isinstance(_pair, (list, tuple)) and len(_pair) >= 2:
                        _plant_ch, _payoff_ch = int(_pair[0]), int(_pair[1])
                        if max_chapter is not None and _payoff_ch > max_chapter:
                            continue
                        if _payoff_ch in _chapters_written and _plant_ch in _chapters_written:
                            _payoff_row = db.get_chapter(novel_id, _payoff_ch)
                            _seed = _seeds[_idx] if _idx < len(_seeds) else None
                            _verified = verify_foreshadowing_payoff(
                                _seed, (_payoff_row or {}).get("content", "")
                            )
                            if _verified is False:
                                _unverified.append(f"FS{_idx+1:03d}(payoff={_payoff_ch})")
                        elif _plant_ch in _chapters_written and _payoff_ch not in _chapters_written:
                            if _payoff_ch <= max(_chapters_written, default=0):
                                _overdue.append(f"FS{_idx+1:03d}(plant={_plant_ch}, payoff={_payoff_ch})")
                if _overdue:
                    task.log(
                        f"📋 [伏筆對帳] 發現 {len(_overdue)} 條伏筆疑似逾期未收：{', '.join(_overdue[:10])}"
                        + (f"...等共 {len(_overdue)} 條" if len(_overdue) > 10 else ""),
                        level="warn",
                    )
                if _unverified:
                    task.log(
                        f"📋 [伏筆實質回收] 發現 {len(_unverified)} 條 payoff 章缺少 seed 關鍵詞證據：{', '.join(_unverified[:10])}"
                        + (f"...等共 {len(_unverified)} 條" if len(_unverified) > 10 else ""),
                        level="warn",
                    )
        except Exception as _fsh_exc:
            task.log(f"⚠️ 伏筆回收對帳異常 (安全跳過): {_fsh_exc}", level="warn")

    def _finalize_completion(self, task: NovelPipelineTask, novel_id: str):
        """全書完成收尾：更新任務狀態、通報並強制雲端備份。"""
        if not task.stop_requested:
            task.progress_percent = 100
            task.current_stage = "completed"
            task.status_message = f"🎉 雲端無人值守生成圓滿完成！全書 {task.total_chapters} 章已全數就緒。"
            task.log(f"🎉 創作任務大功告成！所有內容已完整備份至私有雲端 Dataset。")
            db.save_chat_message(novel_id, "assistant", f"🎉 **【創作完成通報】** 小說全書 {task.total_chapters} 章全自動創作已圓滿完成！所有正文已安全備份至私有雲端 Dataset。", message_type="pipeline")
            backup_database(reason=f"Auto flow [{task.novel_title}]: all completed", force=True)

    def _handle_pipeline_halt(self, task: NovelPipelineTask, halt_exc: PipelineHaltedException):
        """處理 Director 的 WAIT_USER / FINISH 中止訊號。"""
        with task._lock:
            task.is_running = False
            if halt_exc.action == "WAIT_USER":
                task.current_stage = f"{task.current_stage}_wait_user"
                task.status_message = f"⏸️ 等待使用者介入: {halt_exc.reason}"
                task.log(f"⏸️ 流水線已由 Director 暫停等待使用者：{halt_exc.reason}", level="warn")
            elif halt_exc.action == "FINISH":
                task.current_stage = "completed"
                task.progress_percent = 100
                task.status_message = "🎉 創作已由 Director 判定圓滿完成！"
                task.log("🎉 Director 判定全書創作已完成！", level="info")

    def _handle_pipeline_failure(self, task: NovelPipelineTask, novel_id: str, exc: Exception):
        """處理非中止類例外：標記任務失敗並通報。"""
        err_msg = str(exc)
        task.fail(err_msg)
        try:
            db.save_chat_message(novel_id, "assistant", f"⚠️ **【系統通報】** 雲端自主創作任務異常中斷：{err_msg}", message_type="chat")
        except Exception:
            pass


# =============================================================================
# 終卷離線對帳與實質校驗輔助函數
# =============================================================================

def _iter_finale_keywords(value):
    """只讀取明確標成完成承諾的欄位，避免把舊章綱敘述誤當硬性條件。"""
    if isinstance(value, str):
        text = value.strip()
        if text:
            yield text
    elif isinstance(value, dict):
        for key in ("keyword", "name", "title"):
            if value.get(key):
                yield from _iter_finale_keywords(value[key])
        for key in ("keywords", "items"):
            if isinstance(value.get(key), (list, tuple, set)):
                for item in value[key]:
                    yield from _iter_finale_keywords(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_finale_keywords(item)


def _audit_final_volume_lock(novel_id: str):
    """完成前零 LLM 對帳；沒有新欄位的舊資料保持相容並直接通過。"""
    try:
        volumes = db.get_volumes(novel_id) or []
        if not volumes:
            return True, []
        final_volume = max(volumes, key=lambda item: int(item.get("volume_index", 0)))
        volume_index = int(final_volume.get("volume_index", 0))
        start_ch, end_ch = db.get_volume_chapter_range(volumes, volume_index)
        chapters = db.get_chapters_latest_range(novel_id, start_ch, end_ch)
        prose = "\n".join(str(ch.get("content") or "") for ch in chapters)
        issues = []

        # 終卷新增 temporal entities 必須在終卷正文留下可追溯名稱。
        for entity in db.get_entities(novel_id) or []:
            name = str(entity.get("name") or "").strip()
            created_ch = entity.get("created_chapter")
            if name and created_ch is not None and int(created_ch) >= start_ch and name not in prose:
                issues.append(f"新增命名實體「{name}」未在終卷正文出現")

        # 終卷明確新增法則同樣要求正文落名；舊版純文字或空欄位不加新約束。
        rules = final_volume.get("parsed_applicable_rules")
        if not rules and final_volume.get("applicable_rules"):
            raw_rules = final_volume["applicable_rules"]
            try:
                rules = json.loads(raw_rules) if isinstance(raw_rules, str) else raw_rules
            except (TypeError, ValueError):
                rules = []
        for rule in rules or []:
            rule_name = rule.get("name") or rule.get("rule_name") if isinstance(rule, dict) else ""
            rule_name = str(rule_name or "").strip()
            if rule_name and rule_name not in prose:
                issues.append(f"終卷新增法則「{rule_name}」未在正文落實")

        # 只驗證明確的承諾欄位，兼容既有只含 summary/chapters_outline 的資料。
        outlines = final_volume.get("chapters_outline") or []
        if isinstance(outlines, str):
            try:
                outlines = json.loads(outlines)
            except (TypeError, ValueError):
                outlines = []
        promise_keys = (
            "promise_keywords", "completion_keywords", "required_keywords",
            "ending_keywords", "volume_promises",
        )
        promises = []
        for outline in outlines if isinstance(outlines, list) else []:
            if not isinstance(outline, dict):
                continue
            for key in promise_keys:
                promises.extend(_iter_finale_keywords(outline.get(key)))
        seen = set()
        for promise in promises:
            promise = promise.strip()
            if promise and promise not in seen:
                seen.add(promise)
                if promise not in prose:
                    issues.append(f"卷承諾關鍵詞「{promise}」未在終卷正文回收")

        return not issues, issues
    except Exception as exc:
        # 對帳本身不可讓舊資料或缺欄位造成假完成；錯誤只鎖完成，不呼叫 LLM。
        return False, [f"對帳資料異常：{exc}"]


# =============================================================================
# 實質校驗輔助函數 (Substantive Validation Helpers)
# =============================================================================

def _is_worldview_ready(novel_id: str) -> bool:
    wb = db.get_latest_worldbuilding(novel_id)
    if not wb or not wb.get("content"):
        return False
    try:
        parsed = db.parse_worldview_to_json(wb["content"])
        if not isinstance(parsed, dict):
            return False
        # 需確保 theme、worldview 或 macro_outline 具備實質故事文本 (>= 20 字)
        theme_val = (parsed.get("theme") or "").strip()
        wv_val = (parsed.get("worldview") or "").strip()
        macro_val = (parsed.get("macro_outline") or "").strip()
        return bool(len(theme_val) >= 20 or len(wv_val) >= 20 or len(macro_val) >= 20)
    except Exception:
        return False


def _are_characters_ready(novel_id: str, min_count: int = 2) -> bool:
    char_data = db.get_latest_characters(novel_id)
    if not char_data:
        return False
    candidates = []
    if char_data.get("json_data"):
        try:
            candidates.append(json.loads(char_data.get("json_data") or "{}"))
        except Exception:
            pass
    if char_data.get("parsed_data") is not None:
        candidates.append(char_data.get("parsed_data"))

    placeholder_names = {
        "新登場的次要角色", "待補充", "暫無", "placeholder", "新角色", "路人", 
        "客棧老闆", "符合人設說話風格", "todo", "新登場次要角色"
    }

    for parsed in candidates:
        if isinstance(parsed, dict):
            chars = parsed.get("characters", [])
        elif isinstance(parsed, list):
            chars = parsed
        else:
            chars = []
        if isinstance(chars, list) and len(chars) > 0:
            valid_chars = [
                c for c in chars
                if isinstance(c, dict)
                and (c.get("name") or "").strip()
                and not any(pn in (c.get("name") or "").lower() for pn in placeholder_names)
            ]
            if len(valid_chars) >= min_count:
                return True
    return False


def _are_seeds_ready(novel_id: str, min_count: int = 5) -> bool:
    seeds = db.get_foreshadowing_seeds(novel_id)
    return bool(seeds and len(seeds) >= min_count)


def _are_turning_points_ready(novel_id: str, min_count: int = 5) -> bool:
    turns = db.get_key_turning_points(novel_id) if hasattr(db, "get_key_turning_points") else []
    return bool(turns and len(turns) >= min_count)


def _are_volumes_ready(novel_id: str) -> bool:
    vols = db.get_volumes(novel_id)
    return bool(vols and len(vols) >= MIN_VOLUME_COUNT)


def _is_geometry_ready(novel_id: str) -> bool:
    try:
        stats = db.get_geometry_stats(novel_id)
        return bool(stats and int(stats.get("node_count") or 0) > 0)
    except Exception:
        return False


def _is_geometry_semantic_ready(novel_id: str, kind: str) -> bool:
    """共用幾何語義就緒檢查 (kind: macro / character / cross)。"""
    try:
        stats = db.get_geometry_stats(novel_id)
        if not stats or int(stats.get("node_count") or 0) == 0:
            return False
        if kind == "macro":
            if int(stats.get("filled_threads") or 0) > 0 or int(stats.get("filled_volumes") or 0) > 0:
                return True
        elif kind == "character":
            if int(stats.get("filled_nodes") or 0) > 0:
                return True
        elif kind == "cross":
            if int(stats.get("edge_count") or 0) == 0:
                return True
            if int(stats.get("filled_edges") or 0) > 0:
                return True
        graph_loader = getattr(db, "load_geometry_graph", None)
        if not callable(graph_loader):
            return False
        g = graph_loader(novel_id)
        if not g:
            return False
        if kind == "macro":
            return any(v.semantic for v in g.volumes.values())
        if kind == "character":
            return any(t.semantic and "character_binding" in t.semantic for t in g.threads.values())
        return bool(g.edges) and any(e.semantic for e in g.edges)
    except Exception:
        return False


def _is_macro_semantic_ready(novel_id: str) -> bool:
    return _is_geometry_semantic_ready(novel_id, "macro")


def _is_character_semantic_ready(novel_id: str) -> bool:
    return _is_geometry_semantic_ready(novel_id, "character")


def _is_cross_relation_ready(novel_id: str) -> bool:
    return _is_geometry_semantic_ready(novel_id, "cross")


def _has_volume_skeleton(novel_id: str, volume_index: int) -> bool:
    vols = db.get_volumes(novel_id)
    if not vols:
        return False
    target_vol = next((v for v in vols if int(v.get("volume_index") or 0) == int(volume_index)), None)
    if not target_vol:
        return False
    missing = db.volume_missing_chapter_indexes(vols, volume_index)
    return len(missing) == 0


def _are_batch_chapters_ready(novel_id: str, volume_index: int, batch_indexes: List[int]) -> bool:
    vols = db.get_volumes(novel_id)
    if not vols:
        return False
    target_vol = next((v for v in vols if int(v.get("volume_index") or 0) == int(volume_index)), None)
    if not target_vol:
        return False
    chapters = target_vol.get("chapters_outline") or []
    if isinstance(chapters, str):
        try:
            chapters = json.loads(chapters)
        except Exception:
            chapters = []
    if not isinstance(chapters, list):
        return False
    existing_indexes = {int(c.get("chapter_index", 0)) for c in chapters if isinstance(c, dict) and c.get("chapter_index")}
    return set(batch_indexes).issubset(existing_indexes)



def _is_chapter_written(novel_id: str, chapter_index: int) -> bool:
    chapters = db.get_chapters(novel_id)
    for c in chapters:
        if int(c.get("chapter_index") or 0) == chapter_index:
            content = (c.get("content") or "").strip()
            if len(content) >= 50 and not is_refusal_or_disclaimer(content):
                return True
    return False


def _chapter_needs_editor_retry(novel_id: str, chapter_index: int, chapter_row=None) -> bool:
    """判斷已寫章節是否需要「跳過 Writer、僅重試 Editor」。

    需要重試的兩種情況（皆代表 Editor 從未成功收尾）：
    1. 最近一次 Editor 驗收記錄為 failed（本次新增的失敗標記）。
    2. 無任何 Editor 驗收記錄、且章節只有 version==1（僅 Writer 初稿，
       Editor 從未成功存檔；成功精修必定會存新版本）。
    已有 passed / revise / warning 記錄，或 version>=2 的舊章節，視為已完成，不重試。
    """
    try:
        get_status = getattr(db, "get_chapter_editor_review_status", None)
        review = get_status(novel_id, int(chapter_index)) if callable(get_status) else None
    except Exception:
        review = None
    if isinstance(review, dict):
        status = str(review.get("status") or "").strip().lower()
        if status == "failed":
            return True
        if status in ("passed", "revise", "warning"):
            return False
    # 無 Editor 驗收記錄：用版本數判斷是否只有 Writer 初稿
    try:
        version = None
        if isinstance(chapter_row, dict):
            version = chapter_row.get("version")
        if version is None:
            latest = db.get_chapter(novel_id, int(chapter_index))
            version = (latest or {}).get("version")
        if version is not None and int(version) <= 1:
            return True
    except Exception:
        pass
    return False


# 全域單例管理器
autonomous_manager = AutonomousPipelineManager()
