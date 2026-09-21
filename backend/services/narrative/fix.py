# -*- coding: utf-8 -*-
"""
Story Engine 2.0 閉環修正服務（Audit → Editor Fix Loop）
把指定章節的未處置敘事診斷拼成編輯指示，呼叫 Editor 重寫正文；
成功存下新版後自動 resolve 本次餵入的診斷，並對新正文重跑離線審計。

支援「修到好」閉環：fix_chapter_until_pass 會反覆執行
「Editor 重寫 → resolve → 引擎(Narrative Auditor)重審 → 總監硬性校驗(evaluate_output)」，
直到審計判決進入通過態（PASS / WATCH / NO_ACTION_REQUIRED）或觸發安全上限。
WATCH 為觀察級，僅靠下一章寫作上下文約束，不需動用 Editor。

呼叫方有二：
1. 全自動流水線（autonomous_pipeline 2.7）：審計判 REVISE/CRITICAL 時自動修到通過。
2. 單章輔助 API（narrative routes fix-chapter）：手動按鈕（單輪）。
"""

from typing import Any, Dict, List, Optional

from backend import persistence as db
from backend.common.llm import call_llm
from backend.services.narrative.narrative_auditor import NarrativeAuditor

# 審計判決視為「通過」的集合：PASS=健全、NO_ACTION_REQUIRED=安靜呼吸章、
# WATCH=觀察級（留給下一章上下文約束，不動用 Editor）
PASS_ACTIONS = {"PASS", "NO_ACTION_REQUIRED", "WATCH"}

# 「修到好」的安全上限：無人值守流水線不可無限迴圈燒 LLM 配額；
# 達上限仍未通過時保留原稿與殘留診斷，交由看板處置與下一章約束。
DEFAULT_MAX_FIX_ROUNDS = 3

DIMENSION_LABELS = {
    "voice_integrity": "語言/口癖/動作重複",
    "conflict_novelty": "長程因果套路重複",
    "ability_constraints": "超常能力邊界/代價缺失",
    "pacing_balance": "節奏呼吸與沉澱",
}


def build_fix_instructions(targets: List[Dict[str, Any]]) -> str:
    lines = ["【總監 2.0 敘事診斷定向修正】以下為本章已被確認的問題，請針對性重寫，其餘優秀段落保留："]
    for a in targets:
        label = DIMENSION_LABELS.get(a.get("dimension", ""), a.get("dimension", ""))
        lines.append(f"- [{label}] 佐證：{a.get('evidence', '')}")
        lines.append(f"  改法：{a.get('recommendation', '')}")
    lines.append("注意：只修正上述問題點，不得改變本章大綱事件、人物立場與伏筆走向。")
    return "\n".join(lines)


def build_director_user_instruction(
    novel_id: str,
    chapter_index: int,
    targets: List[Dict[str, Any]],
    reaudit_findings: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    總監指令合成：把敘事引擎的診斷與建議（含上一輪「引擎重審」的殘留 findings）
    交給總監 LLM，由總監產生一段給 Editor 的「user 修正指令」，具體說明內文要怎麼改。
    LLM 失敗或離線時降級回確定性模板 build_fix_instructions，永不拋錯。
    """
    fallback = build_fix_instructions(targets)
    try:
        from backend.common.llm import call_llm

        engine_lines: List[str] = []
        for a in targets:
            label = DIMENSION_LABELS.get(a.get("dimension", ""), a.get("dimension", ""))
            engine_lines.append(
                f"- [{label}] 佐證：{a.get('evidence', '')}\n  引擎建議：{a.get('recommendation', '')}"
            )
        if reaudit_findings:
            engine_lines.append("【引擎重審（上一輪修正後）殘留觀察，必須一併處置】")
            for f in reaudit_findings:
                label = DIMENSION_LABELS.get(f.get("dimension", ""), f.get("dimension", ""))
                engine_lines.append(
                    f"- [{label}/{f.get('severity', '')}] 佐證：{f.get('evidence', '')}"
                    f"\n  引擎建議：{f.get('recommendation', '')}"
                )
        if not engine_lines:
            return fallback

        system_prompt = (
            "你是小說創作流水線的總監（Director）。敘事引擎（Narrative Auditor）已完成離線診斷，"
            "你的任務是把引擎的診斷與建議，轉寫成一段給 Writer（正文寫作作家）與 Editor 的「修正指令」："
            "具體、可執行、逐點說明情節因果與內文要怎麼改（例如：打破公式化套路、換掉重複的主角破局策略、"
            "為強力破局補上實質代價與外部引力、替換模板化動作為角色獨特微動作等），"
            "並嚴守紅線：不得改變本章核心大綱主旨、人物立場與伏筆走向。"
            "只輸出指令本文本身（繁體中文），不要 JSON、不要標題、不要客套話。"
        )
        user_prompt = (
            f"第 {chapter_index} 章敘事引擎診斷與建議如下：\n"
            + "\n".join(engine_lines)
            + "\n\n請據此產生給 Writer 與 Editor 的 user 修正指令（300 字內，逐點列改法）。"
        )
        instruction = (call_llm("copilot", system_prompt, user_prompt) or "").strip()
        if not instruction:
            return fallback
        # 紅線附註一律保留，避免 LLM 合成時遺漏
        if "不得改變本章大綱" not in instruction:
            instruction += "\n注意：只修正上述問題點，不得改變本章大綱事件、人物立場與伏筆走向。"
        return instruction
    except Exception:
        return fallback


def fix_chapter_from_audits(
    novel_id: str,
    chapter_index: int,
    audit_ids: Optional[List[str]] = None,
    reaudit_findings: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """執行閉環修正（Writer 重寫 -> Editor 潤色 -> 衝突簽名更新 -> 總監評斷），
    回傳 status success / no_change，並附 reaudit。

    reaudit_findings：上一輪引擎重審的 findings（含建議），會一併納入給總監合成 user 指令。
    """
    from backend.agents.chapter_writer.runner import run_chapter_writer
    from backend.agents.editor.runner import run_editor_agent
    from backend.services.narrative.conflict_ledger import ConflictLedger

    ch_row = db.get_latest_chapter(novel_id, chapter_index)
    if not ch_row or not (ch_row.get("content") or "").strip():
        raise ValueError(f"第 {chapter_index} 章尚無正文內容")

    audits = db.get_narrative_audits(novel_id, chapter_index=chapter_index, limit=50)
    targets = [a for a in audits if not a.get("resolved")]
    if audit_ids:
        wanted = set(audit_ids)
        targets = [a for a in targets if a.get("id") in wanted]
    if not targets:
        raise ValueError(f"第 {chapter_index} 章目前無未處置的敘事診斷")

    before_content = ch_row.get("content") or ""
    # 步驟 1: 引擎診斷 + 上一輪重審建議 → 總監 LLM 合成修正指令
    user_instruction = build_director_user_instruction(
        novel_id, chapter_index, targets, reaudit_findings=reaudit_findings,
    )

    # 步驟 2: Writer 重寫正文（因果模式與破局策略在此階段徹底重構）
    try:
        writer_gen = run_chapter_writer(
            novel_id, chapter_index,
            user_prompt=user_instruction, stream=False,
        )
        for _ in writer_gen:
            pass
    except Exception as e:
        print(f"[WARN] run_chapter_writer in fix loop notice: {e}")

    # 步驟 3: Editor 接手潤色（精修語言美感、去除模板動作與口癖）
    try:
        editor_gen = run_editor_agent(
            novel_id, chapter_index,
            edit_instructions=user_instruction, stream=False,
        )
        for _ in editor_gen:
            pass
    except Exception as e:
        print(f"[WARN] run_editor_agent in fix loop notice: {e}")

    after_row = db.get_latest_chapter(novel_id, chapter_index)
    after_content = (after_row.get("content") or "") if after_row else ""
    changed = bool(after_content.strip()) and after_content.strip() != before_content.strip()

    resolved_ids: List[str] = []
    if changed:
        for a in targets:
            try:
                if db.resolve_narrative_audit(a["id"]):
                    resolved_ids.append(a["id"])
            except Exception:
                continue

    reaudit = None
    if changed and after_content.strip():
        try:
            outline = None
            try:
                from backend.services import narrative_memory
                outline = narrative_memory.get_chapter_outline(novel_id, chapter_index)
            except Exception:
                outline = None

            # 步驟 4: 基於改寫後的新正文與大綱，重新提取本章衝突簽名並更新帳本！
            new_sig = ConflictLedger.extract_signature_from_chapter(
                novel_id=novel_id,
                chapter_index=chapter_index,
                outline=outline,
                prose_text=after_content,
            )
            try:
                ConflictLedger.record_signature(
                    novel_id=novel_id,
                    chapter_start=new_sig.get("chapter_start", chapter_index),
                    chapter_end=new_sig.get("chapter_end", chapter_index),
                    pressure_type=new_sig.get("pressure_type", "衝突推進"),
                    protagonist_strategy=new_sig.get("protagonist_strategy", "adaptive_response"),
                    outcome=new_sig.get("outcome", "推進"),
                    initiator=new_sig.get("initiator"),
                    antagonist_goal=new_sig.get("antagonist_goal"),
                    power_used=new_sig.get("power_used"),
                    twist_mechanism=new_sig.get("twist_mechanism"),
                    cost=new_sig.get("cost"),
                    emotional_effect=new_sig.get("emotional_effect"),
                    setting_used=new_sig.get("setting_used"),
                )
            except Exception as e:
                print(f"[WARN] Failed to record updated signature in fix loop: {e}")

            # 步驟 5: 總監評斷（以新簽名重跑 NarrativeAuditor 審查）
            reaudit = NarrativeAuditor.audit_chapter_prose(
                novel_id=novel_id, chapter_index=chapter_index,
                prose_text=after_content, current_outline=outline,
                candidate_conflict_sig=new_sig,
            )
        except Exception as exc:
            print(f"[WARN] Reaudit in fix loop failed: {exc}")
            reaudit = None

    return {
        "status": "success" if changed else "no_change",
        "novel_id": novel_id,
        "chapter_index": chapter_index,
        "fixed_count": len(resolved_ids),
        "resolved_audit_ids": resolved_ids,
        "reaudit": reaudit,
    }


def fix_chapter_until_pass(
    novel_id: str,
    chapter_index: int,
    max_rounds: int = DEFAULT_MAX_FIX_ROUNDS,
    log_fn=None,
) -> Dict[str, Any]:
    """
    閉環「修到好」：反覆 Editor 重寫 → resolve → 引擎重審 → 總監硬性校驗，
    直到 Narrative Auditor 判決進入 PASS_ACTIONS 通過態，或觸發安全上限。

    回傳：
    {
        "status": "passed" | "max_rounds" | "no_change" | "failed",
        "novel_id", "chapter_index",
        "rounds": [每輪 {round, status, fixed_count, reaudit}],
        "final_action": 最後一次審計判決（無審計時為 None）,
        "total_fixed": 累計處置診斷數,
        "final_reaudit": 最後一次重審結果,
        "director_check": 最後一次總監硬性校驗（evaluate_output）結果或 None,
    }
    """
    rounds: List[Dict[str, Any]] = []
    total_fixed = 0
    final_reaudit: Optional[Dict[str, Any]] = None
    director_check: Optional[Dict[str, Any]] = None
    status = "failed"
    # 上一輪引擎重審的 findings：下一輪納入給總監，合成更精準的 user 修正指令
    prev_reaudit_findings: Optional[List[Dict[str, Any]]] = None

    def _log(msg: str, level: str = "info"):
        if log_fn:
            try:
                log_fn(msg, level)
            except Exception:
                pass

    for rnd in range(1, max(1, max_rounds) + 1):
        try:
            fix_res = fix_chapter_from_audits(
                novel_id, chapter_index, reaudit_findings=prev_reaudit_findings,
            )
        except ValueError as ve:
            # 無正文或無未處置診斷：視為無事可修
            _log(f"第 {chapter_index} 章閉環修正中止（第 {rnd} 輪）：{ve}")
            status = "no_change"
            break
        except Exception as exc:
            _log(f"第 {chapter_index} 章閉環修正異常（第 {rnd} 輪）：{exc}", "warn")
            status = "failed"
            break

        round_entry = {
            "round": rnd,
            "status": fix_res.get("status"),
            "fixed_count": fix_res.get("fixed_count", 0),
            "reaudit": fix_res.get("reaudit"),
        }
        rounds.append(round_entry)
        total_fixed += fix_res.get("fixed_count", 0)
        reaudit = fix_res.get("reaudit") or {}
        final_reaudit = reaudit or final_reaudit
        final_action = reaudit.get("overall_action")
        # 引擎重審的殘留建議 → 下一輪交給總監併入 user 指令
        prev_reaudit_findings = reaudit.get("findings") or None

        # Editor 認為無需改動：原文保留，繼續迴圈只會空轉
        if fix_res.get("status") != "success":
            status = "no_change"
            _log(f"第 {chapter_index} 章第 {rnd} 輪 Editor 未產生新版（原文保留），閉環中止")
            break

        # 引擎重審通過：再過一道總監硬性校驗（content 長度/占位標記/紅線）
        if final_action in PASS_ACTIONS:
            director_check = _run_director_check(novel_id, chapter_index)
            if director_check and not director_check.get("passed", True):
                # 硬性校驗未過（如正文過短）：視同未通過，繼續下一輪
                _log(
                    f"第 {chapter_index} 章第 {rnd} 輪引擎判 [{final_action}]，"
                    f"但總監硬性校驗未過：{director_check.get('message', '')}",
                    "warn",
                )
                status = "max_rounds" if rnd >= max(1, max_rounds) else "retrying"
            else:
                status = "passed"
                _log(f"✅ 第 {chapter_index} 章閉環通過：引擎判 [{final_action}]，總監校驗通過（共 {rnd} 輪）")
                break
        else:
            # 仍為 REVISE / CRITICAL：若還有輪次則繼續修
            status = "max_rounds" if rnd >= max(1, max_rounds) else "retrying"
            if status != "retrying":
                _log(
                    f"第 {chapter_index} 章閉環達修復上限（{max_rounds} 輪），最終判決 [{final_action}]；"
                    "殘留診斷保留待看板處置與下一章約束",
                    "warn",
                )
            else:
                _log(f"第 {chapter_index} 章第 {rnd} 輪重審仍為 [{final_action}]，繼續閉環修正...")

    return {
        "status": status,
        "novel_id": novel_id,
        "chapter_index": chapter_index,
        "rounds": rounds,
        "final_action": (final_reaudit or {}).get("overall_action"),
        "total_fixed": total_fixed,
        "final_reaudit": final_reaudit,
        "director_check": director_check,
    }


def _run_director_check(novel_id: str, chapter_index: int) -> Optional[Dict[str, Any]]:
    """總監硬性校驗：evaluate_output('editor') 含正文長度/占位標記/敘事紅線，純離線零 LLM。"""
    try:
        from backend.services.director.tool_registry.evaluator import evaluate_output

        ch_row = db.get_latest_chapter(novel_id, chapter_index)
        content = (ch_row.get("content") or "") if ch_row else ""
        if not content.strip():
            return None
        payload = {
            "novel_id": novel_id,
            "chapter_index": chapter_index,
            "content": content,
        }
        return evaluate_output(
            stage_name="editor",
            output_content=payload.get("content") or "",
            novel_id=novel_id,
        )
    except Exception:
        return None
