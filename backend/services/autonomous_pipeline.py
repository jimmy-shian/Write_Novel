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
)
from backend.schemas.validation import split_consecutive_batches
from backend.common.refusal_filter import is_refusal_or_disclaimer


class NovelPipelineTask:
    """單本小說的自主生成任務狀態實例"""

    def __init__(self, novel_id: str, novel_title: str = ""):
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
        self.last_heartbeat: str = datetime.datetime.now().strftime("%H:%M:%S")
        self.worker_thread: Optional[threading.Thread] = None

    def log(self, message: str, level: str = "info"):
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
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

    def to_dict(self) -> Dict[str, Any]:
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
            task.start_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
        max_retries: int = 5,
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
                    raise RuntimeError(f"階段 [{stage}] 執行結束，但資料庫實質校驗未通過（未持久化實質資料）。")

                return resp

            except Exception as exc:
                last_exc = exc
                if stage in ("chapter", "writer") and target and target.get("chapter_index"):
                    try:
                        db.rollback_or_purge_chapter(task.novel_id, int(target["chapter_index"]))
                        task.log(f"🧹 已清除第 {target['chapter_index']} 章未通過或異常之草稿，準備重試...", level="warn")
                    except Exception:
                        pass
                if attempt >= max_retries or task.stop_requested:
                    raise last_exc

                # 總監介入出具診斷處方箋，取代盲目次數重試
                err_clean = str(exc).strip()
                is_infra_error = any(k in err_clean for k in (
                    "拒答", "免責聲明", "UNAUTHENTICATED", "Unauthorized", "401", "Connection refused",
                    "Cookie 是否過期", "Read timed out", "TimeoutError", "連線被拒", "API Key"
                ))
                if is_infra_error:
                    director_prescription = (
                        f"【總監診斷處方箋（第 {attempt + 1} 次連線環境診斷）】\n"
                        f"檢測到上游模型通訊或身分驗證異常：{err_clean}。\n"
                        f"此為模型連線/登入憑證問題（非創作大綱或情節邏輯錯誤）。請檢查模型服務端、API Key 或 WebChat2Local Cookie 是否正常。"
                    )
                else:
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
                task.log(f"🩺 [總監出具修正處方箋] 針對 [{stage}] 出具定向修復指導，將於 {delay} 秒後進行第 {attempt + 1}/{max_retries} 次重點修正：{exc}", level="warn")
                time.sleep(delay)

        raise last_exc or RuntimeError(f"Stage {stage} failed after {max_retries} retries")

    def _run_autonomous_flow(self, task: NovelPipelineTask, initial_prompt: str, max_chapters: int):
        novel_id = task.novel_id
        try:
            # 1. 檢查並生成世界觀
            if task.stop_requested: return
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

            # 2. 檢查並生成主要角色設定（陣營梯隊導向群像：各陣營 5-10 人，全書至少 15+ 位）
            if task.stop_requested: return
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

            # 3. 檢查並編織全局伏筆與關鍵轉折 (目標各達 MIN 保底條數)
            if task.stop_requested: return
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

            # 4. 檢查並規劃分卷結構
            if task.stop_requested: return
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

            # 4.5 敘事幾何骨架 (Geometry-First):純程式碼零 LLM 消耗，
            # 在分卷確定後、細綱與正文之前先鋪設全書拓撲 (長距伏筆/多線合流/主題對比邊)，
            # 後續 volume_skeleton / writer 才能遵照拓撲架構生成。
            if task.stop_requested: return
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

            # 5. 檢查並規劃全部分卷骨架 (各章節細綱 - 確保每卷皆 100% 具備細綱)
            if task.stop_requested: return
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

            # 5.5 角色一致性與名冊完整性防呆校驗 (防止正文角色性格盲猜或反派立場翻轉)
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

            # 6. 逐章撰寫與精修 (智慧接續未完成之章節)
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

                # 確保該章所屬的卷具備骨架
                curr_vol_idx = db.get_chapter_volume_index(vols, ch_idx) if vols else None
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

                # (1) 正文寫作 (含 5 次自動重試與驗證)
                # editor_retry_only 時沿用既有初稿，不重寫、不覆蓋，直接進入總監審查與精修。
                if editor_retry_only:
                    existing_draft = (written_rows.get(ch_idx) or {}).get("content") or ""
                    task.current_stage = f"writer_ch{ch_idx}_reused"
                    task.log(f"第 {ch_idx} 章沿用既有初稿（{len(existing_draft.strip())} 字），直接進入總監審查與精修...")
                else:
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
                        verify_fn=lambda c=ch_idx: _is_chapter_written(novel_id, c),
                    )
                    task.log(f"第 {ch_idx} 章初稿撰寫完成！")

                # (1.5) 總監章節品質與時空一致性審查 (Director Quality Gate)
                director_eval: Dict[str, Any] = {}
                try:
                    from backend.services.director.tool_registry.evaluator import evaluate_output
                    ch_draft = db.get_chapter(novel_id, ch_idx)
                    draft_content = (ch_draft.get("content") or "") if ch_draft else ""
                    if draft_content and len(draft_content.strip()) >= 50:
                        director_eval = evaluate_output(
                            stage_name="writer",
                            output_content=draft_content,
                            novel_id=novel_id,
                            chapter_index=ch_idx,
                        )
                        eval_passed = director_eval.get("passed", False)
                        is_critical = director_eval.get("critical_drift", False)
                        eval_issues = director_eval.get("issues", [])

                        # 儲存真實總監評審記錄至 director_reviews 表
                        try:
                            db.save_director_review_status(
                                novel_id=novel_id,
                                stage_name="writer",
                                status="passed" if eval_passed else ("revise" if is_critical else "warning"),
                                block_name=f"chapter_{ch_idx}",
                                volume_index=curr_vol_idx,
                                chapter_index=ch_idx,
                                reason="; ".join(eval_issues) if eval_issues else "總監校驗通過",
                                decision_json=director_eval,
                            )
                        except Exception as d_db_exc:
                            task.log(f"⚠️ 總監審查記錄持久化異常: {d_db_exc}", level="warn")

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
                            # Hard content/canon errors must be revised before Editor;
                            # stylistic hits are passed to Editor for targeted repair.
                            task.log(f"🚨 [總監章節硬性攔截] 第 {ch_idx} 章需先修正：{'; '.join(hard_writer_issues)}。", level="warn")
                            db.save_chat_message(
                                novel_id,
                                "director",
                                f"🚨 **【總監審查打回 - 第 {ch_idx} 章】**\n檢測到背景設定或時空存在嚴重漂移：\n- " + "\n- ".join(eval_issues) + "\n\n正在指示 Writer 重新對齊大綱時空重寫...",
                                message_type="director"
                            )
                            # 進行定向重寫 (最多重試 2 次)
                            fix_instruction = (
                                f"【總監剛性修正指示】：上一版草稿未通過硬性內容驗收：\n"
                                f"{'; '.join(hard_writer_issues)}\n"
                                f"請逐項修正，維持已確認的大綱因果與故事事實，重寫第 {ch_idx} 章正文。"
                            )
                            self._execute_stage_with_retry(
                                task=task,
                                stage="writer",
                                task_type="generate",
                                scope="chapter",
                                target={"chapter_index": ch_idx},
                                instruction=fix_instruction,
                                user_prompt=f"修正時空漂移重寫第 {ch_idx} 章",
                                verify_fn=lambda c=ch_idx: _is_chapter_written(novel_id, c),
                                max_retries=2,
                            )
                            # 重新獲取修復後的內容並再次快速校驗
                            ch_draft = db.get_chapter(novel_id, ch_idx)
                            draft_content = (ch_draft.get("content") or "") if ch_draft else ""
                            director_eval = evaluate_output(
                                stage_name="writer",
                                output_content=draft_content,
                                novel_id=novel_id,
                                chapter_index=ch_idx,
                            )
                        elif eval_issues:
                            task.log(f"⚠️ [總監審查備註] 第 {ch_idx} 章存在輕微建議或用詞提醒：{'; '.join(eval_issues)}，將交由 Editor 潤色時修訂。")
                        else:
                            task.log(f"✅ [總監審查通過] 第 {ch_idx} 章背景設定、時空連續性與實體錨點完全合規！")
                            db.save_chat_message(
                                novel_id,
                                "director",
                                f"🎬 **【總監審查通過 - 第 {ch_idx} 章】**\n- 審查狀態：完全合規\n- 時空一致性：符合大綱要求\n- 實體與術語：無違規漂移",
                                message_type="director"
                            )
                except Exception as d_exc:
                    task.log(f"⚠️ 總監章節審查執行異常 (非致命，繼續後續流程): {d_exc}", level="warn")

                # (2) 編輯精修 (含 5 次自動重試與驗證)
                if task.stop_requested: break
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
                    continue
                task.log(f"✅ 第 {ch_idx} 章精修完成並已存入資料庫！")

                # Final deterministic quality gate after Editor has had a chance to
                # repair the draft. Retry targeted editing twice; preserve the
                # final failed status instead of silently calling it fully clean.
                final_editor_eval = {}
                for quality_attempt in range(3):
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
                    if quality_attempt >= 2 or task.stop_requested:
                        break
                    task.log(
                        f"⚠️ [Editor 後品質閘門] 第 {ch_idx} 章第 {quality_attempt + 1} 次驗收未通過，定向修訂：{'; '.join(final_issues[:8])}",
                        level="warn",
                    )
                    from backend.agents.editor.runner import run_editor_agent
                    editor_gen = run_editor_agent(
                        novel_id,
                        ch_idx,
                        edit_instructions=(
                            "請依下列硬性驗收問題修正正文，必須保留既有事件因果與角色事實；"
                            "重寫命中句的敘事方式，不可只替換同義詞：\n- "
                            + "\n- ".join(final_issues[:12])
                        ),
                        stream=False,
                        fix_mode=True,
                    )
                    for _ in editor_gen:
                        pass
                if final_editor_eval and not final_editor_eval.get("passed"):
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
                if final_editor_eval and not final_editor_eval.get("passed"):
                    task.log(
                        f"⚠️ 第 {ch_idx} 章未通過 Editor 後品質驗收；草稿已保留並標記為待人工檢視，流程繼續下一章："
                        + "; ".join((final_editor_eval.get("issues") or [])[:8]),
                        level="error",
                    )

                # (2.5) 同步提取時序事實與動態圖譜 (Graphiti Temporal Graph)
                # 同次 LLM 順帶歸一化衝突簽名 + 設定調用（Story Engine 搭便車，零額外呼叫）
                graph_res: Dict[str, Any] = {}
                try:
                    task.log(f"🧠 正在為第 {ch_idx} 章同步提取時序記憶圖譜事實...")
                    ch_obj = db.get_chapter(novel_id, ch_idx)
                    ch_text = (ch_obj.get("content") or "") if ch_obj else ""
                    if ch_text and len(ch_text.strip()) > 50:
                        graph_res = ChapterFactExtractor.process_chapter_prose(
                            novel_id=novel_id,
                            chapter_index=ch_idx,
                            chapter_text=ch_text,
                            agent_name="copilot"
                        ) or {}
                        facts_added = graph_res.get("facts_added", 0)
                        terms_created = graph_res.get("terms_created", 0)
                        terms_updated = graph_res.get("terms_updated", 0)
                        task.log(f"✅ 第 {ch_idx} 章時序記憶抽取完成 (新增 {facts_added} 條世界線動態事實，術語庫新增 {terms_created}/更新 {terms_updated})")
                except Exception as g_exc:
                    task.log(f"⚠️ 第 {ch_idx} 章時序記憶提取異常 (安全跳過不阻礙後續寫作): {g_exc}", level="warn")

                # (2.6) 註冊衝突簽名 (Conflict Signature) 與長程敘事因果審計 (Narrative Auditor)
                try:
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
                except Exception as n_exc:
                    task.log(f"⚠️ 第 {ch_idx} 章長程敘事診斷異常 (安全跳過不阻礙): {n_exc}", level="warn")

                db.save_chat_message(
                    novel_id,
                    "assistant",
                    f"✍️ **【章節完成進度】** 第 {ch_idx} 章正文已由 Writer 撰寫並經 Editor 潤色精修完成，已成功入庫！\n- 進度：第 {ch_idx}/{total_target} 章 ({task.progress_percent}%)",
                    message_type="pipeline"
                )
                # (3) 本地 DB 已寫入，不進行每章雲端 commit 備份以避免空間爆滿
                time.sleep(0.5)

            # (2.8) 卷末零 LLM 伏筆回收對帳：每卷寫完後 Python 快速對帳
            try:
                from backend.services.foreshadowing.blueprint import get_global_foreshadowing_blueprint
                _blueprint = get_global_foreshadowing_blueprint(novel_id)
                if _blueprint:
                    _alloc = _blueprint.get("foreshadowing_allocations", [])
                    _total_T = _blueprint.get("T", 0)
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
                    for _idx, _pair in enumerate(_alloc):
                        if isinstance(_pair, (list, tuple)) and len(_pair) >= 2:
                            _plant_ch, _payoff_ch = int(_pair[0]), int(_pair[1])
                            # 若 payoff 章已寫完但尚無回收紀錄，標記逾期
                            if _payoff_ch in _chapters_written and _plant_ch in _chapters_written:
                                # 此處為簡易對帳；未來可細化為實際檢查正文中 FSID 是否出現
                                pass
                            elif _plant_ch in _chapters_written and _payoff_ch not in _chapters_written:
                                if _payoff_ch <= max(_chapters_written, default=0):
                                    _overdue.append(f"FS{_idx+1:03d}(plant={_plant_ch}, payoff={_payoff_ch})")
                    if _overdue:
                        task.log(
                            f"📋 [伏筆對帳] 發現 {len(_overdue)} 條伏筆疑似逾期未收：{', '.join(_overdue[:10])}"
                            + (f"...等共 {len(_overdue)} 條" if len(_overdue) > 10 else ""),
                            level="warn",
                        )
            except Exception as _fsh_exc:
                task.log(f"⚠️ 伏筆回收對帳異常 (安全跳過): {_fsh_exc}", level="warn")

            if not task.stop_requested:
                task.progress_percent = 100
                task.current_stage = "completed"
                task.status_message = f"🎉 雲端無人值守生成圓滿完成！全書 {task.total_chapters} 章已全數就緒。"
                task.log(f"🎉 創作任務大功告成！所有內容已完整備份至私有雲端 Dataset。")
                db.save_chat_message(novel_id, "assistant", f"🎉 **【創作完成通報】** 小說全書 {task.total_chapters} 章全自動創作已圓滿完成！所有正文已安全備份至私有雲端 Dataset。", message_type="pipeline")
                backup_database(reason=f"Auto flow [{task.novel_title}]: all completed", force=True)

        except Exception as exc:
            err_msg = str(exc)
            task.error = err_msg
            task.current_stage = "error"
            task.status_message = f"❌ 執行中斷: {err_msg}"
            task.log(f"執行出錯: {err_msg}", level="error")
            try:
                db.save_chat_message(novel_id, "assistant", f"⚠️ **【系統通報】** 雲端自主創作任務異常中斷：{err_msg}", message_type="chat")
            except Exception:
                pass
        finally:
            task.is_running = False
            task.stop_requested = False
            try:
                db.release_pipeline_lock(novel_id)
            except Exception as e:
                print(f"[WARN] Failed to release pipeline lock for novel {novel_id}: {e}")


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
