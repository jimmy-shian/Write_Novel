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
DEFAULT_MAX_FIX_ROUNDS = 5

DIMENSION_LABELS = {
    "voice_integrity": "語言/口癖/動作重複",
    "opening_repetition": "開篇套路與跨章重複",
    "meta_narrative_leak": "破壁元敘事/大綱標籤洩漏",
    "conflict_novelty": "長程因果套路重複",
    "ability_constraints": "超常能力邊界/代價缺失",
    "terms_compliance": "術語庫專有名詞合規",
    "temporal_graph_compliance": "時序圖譜世界線一致性",
    "pacing_balance": "節奏呼吸與沉澱",
}


def build_fix_instructions(
    targets: List[Dict[str, Any]],
    banned_hits: Optional[List[Dict[str, Any]]] = None,
) -> str:
    lines = ["【總監 2.0 敘事診斷定向修正】以下為本章已被確認的問題，請針對性重寫，其餘優秀段落保留："]
    has_causal = any(a.get("dimension") in ("conflict_novelty", "ability_constraints") for a in targets)
    has_voice = any(a.get("dimension") == "voice_integrity" for a in targets)
    for a in targets:
        label = DIMENSION_LABELS.get(a.get("dimension", ""), a.get("dimension", ""))
        lines.append(f"- [{label}] 佐證：{a.get('evidence', '')}")
        lines.append(f"  改法：{a.get('recommendation', '')}")
    if banned_hits:
        lines.append("【精確命中之禁用原文段落】")
        for h in banned_hits[:10]:
            lines.append(f"- 第 {h.get('paragraph_index', 1)} 段：『{h.get('matched_sentence', '')}』[{h.get('pattern_label', '')}]")
    lines.append("注意：只修正上述問題點，不得改變本章大綱事件、人物立場與伏筆走向。")
    if has_causal:
        lines.append("紅線：必須實質更換情節因果鏈與主角博弈方式；嚴禁僅在策略名詞上做近義詞替換蒙混；若診斷指出代價缺失，必須補寫具體的能力冷卻、資源消耗、體能透支或代價暴露後果。")
    if has_voice:
        lines.append("紅線：嚴格刪除或替換所有標記之禁用句與套路動作，出現禁用句即判失敗。")
    return "\n".join(lines)


def build_director_user_instruction(
    novel_id: str,
    chapter_index: int,
    targets: List[Dict[str, Any]],
    reaudit_findings: Optional[List[Dict[str, Any]]] = None,
    banned_hits: Optional[List[Dict[str, Any]]] = None,
    round_idx: int = 1,
) -> str:
    """
    總監指令合成：把敘事引擎的診斷與建議（含上一輪「引擎重審」的殘留 findings 與正文精確命中錨點）
    交給總監 LLM，由總監產生一段給 Writer 與 Editor 的「user 修正指令」，具體說明內文要怎麼改。
    LLM 失敗或離線時降級回確定性模板 build_fix_instructions，永不拋錯。
    """
    fallback = build_fix_instructions(targets, banned_hits=banned_hits)
    try:
        from backend.common.llm import call_llm

        engine_lines: List[str] = []
        for a in targets:
            label = DIMENSION_LABELS.get(a.get("dimension", ""), a.get("dimension", ""))
            sev = a.get("severity", "warning")
            dim = a.get("dimension", "")
            engine_lines.append(
                f"- [{label}/{sev}] 維度：{dim} | 佐證：{a.get('evidence', '')}\n  引擎建議：{a.get('recommendation', '')}"
            )
        if reaudit_findings:
            engine_lines.append(f"【引擎重審（上一輪第 {max(1, round_idx - 1)} 輪修正後殘留觀察，必須一併處置）】")
            for f in reaudit_findings[:5]:
                label = DIMENSION_LABELS.get(f.get("dimension", ""), f.get("dimension", ""))
                engine_lines.append(
                    f"- [{label}/{f.get('severity', '')}] 佐證：{f.get('evidence', '')}"
                    f"\n  引擎建議：{f.get('recommendation', '')}"
                )
        if banned_hits:
            engine_lines.append("【正文精確命中之禁用原文與位置（請針對性重寫）】")
            for h in banned_hits[:10]:
                ctx = h.get("context_20chars", "")
                ctx_str = f"（前後文：…{ctx}…）" if ctx else ""
                engine_lines.append(
                    f"- 第 {h.get('paragraph_index', 1)} 段：『{h.get('matched_sentence', '')}』[標籤：{h.get('pattern_label', '')}]{ctx_str}"
                )

        # 注入開頭/結尾上下文與前章開頭（用於開篇去重與結尾收束）
        try:
            ch_row = db.get_latest_chapter(novel_id, chapter_index)
            cur_text = (ch_row.get("content") or "").strip() if ch_row else ""
            if cur_text:
                engine_lines.append(f"【本章當前開篇 100 字】：{cur_text[:100]}")
                engine_lines.append(f"【本章當前結尾 100 字】：{cur_text[-100:]}")
            if chapter_index > 1:
                prev_row = db.get_latest_chapter(novel_id, chapter_index - 1)
                prev_text = (prev_row.get("content") or "").strip() if prev_row else ""
                if prev_text:
                    engine_lines.append(f"【前一章開篇 100 字（本章開篇切入必須與之去重）】：{prev_text[:100]}")
        except Exception:
            pass

        # 注入衝突簽名脈絡（若有）
        try:
            recent_sigs = db.get_conflict_signatures(novel_id, limit=4, max_chapter=chapter_index - 1)
            if recent_sigs:
                sig_summaries = [
                    f"第{s['chapter_start']}章[壓迫:{s.get('pressure_type')}->主角策略:{s.get('protagonist_strategy')}->結果:{s.get('outcome')}]"
                    for s in recent_sigs
                ]
                engine_lines.append(f"【近 4 章因果策略簽名】：{'; '.join(sig_summaries)}")
        except Exception:
            pass

        if not engine_lines:
            return fallback

        system_prompt = (
            "你是小說創作流水線的總監（Director）。敘事引擎（Narrative Auditor）已完成離線診斷，"
            "你的任務是把引擎的診斷與建議，轉寫成一段給 Writer 與 Editor 的「修正指令」："
            "具體、可執行、逐點說明情節因果與內文要怎麼改，輸出必須包含：\n"
            "1.【禁用原文逐條】：列出必須刪除替換的套路句與段落位置。\n"
            "2.【位置與替換方向】：說明開篇、結尾、微動作或對白之替換方式。\n"
            "3.【策略與代價重寫要求】：若涉及因果問題，說明新的破局手段與支付代價。\n"
            "4.【紅線】：不得改變本章核心大綱主旨、人物立場與伏筆走向。\n"
            "只輸出指令本文本身（繁體中文），不要 JSON、不要標題、不要客套話。"
        )
        user_prompt = (
            f"第 {chapter_index} 章敘事引擎診斷與建議如下：\n"
            + "\n".join(engine_lines)
            + "\n\n請據此產生給 Writer 與 Editor 的 user 修正指令（600 字內，逐點列改法）。"
        )
        instruction = (call_llm("copilot", system_prompt, user_prompt) or "").strip()
        if not instruction:
            return fallback

        # 紅線條件化附加，避免過度修正或約束洩漏
        has_causal = any(a.get("dimension") in ("conflict_novelty", "ability_constraints") for a in targets)
        has_voice = any(a.get("dimension") == "voice_integrity" for a in targets)

        if "不得改變本章大綱" not in instruction:
            instruction += "\n注意：只修正上述問題點，不得改變本章大綱事件、人物立場與伏筆走向。"
        if has_causal and "因果鏈" not in instruction:
            instruction += "\n紅線：必須實質更換情節因果鏈與主角博弈方式，嚴禁僅做策略名詞同義替換蒙混；若指出代價缺失，必須補寫具體的能力冷卻、資源消耗或情報暴露後果。"
        if has_voice and ("禁用" not in instruction and "套路" not in instruction):
            instruction += "\n紅線：嚴格刪除或替換所有標記之禁用句與套路動作，出現禁用句即判失敗。"

        return instruction
    except Exception:
        return fallback


def fix_chapter_from_audits(
    novel_id: str,
    chapter_index: int,
    audit_ids: Optional[List[str]] = None,
    reaudit_findings: Optional[List[Dict[str, Any]]] = None,
    round_idx: int = 1,
) -> Dict[str, Any]:
    """執行閉環修正（Writer 重構因果 -> Editor 定點手術/潤色 -> 衝突簽名更新 -> 總監評斷），
    回傳 status success / no_change，並附 reaudit。

    reaudit_findings：上一輪引擎重審的 findings（含建議），會一併納入給總監合成 user 指令。
    round_idx：當前修正輪次。round_idx >= 2 時跳過 Writer，僅由 Editor 精準定點手術。
    """
    from backend.agents.chapter_writer.runner import run_chapter_writer
    from backend.agents.editor.runner import run_editor_agent
    from backend.services.narrative.conflict_ledger import ConflictLedger
    from backend.services.narrative.narrative_auditor import extract_banned_hits

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
    banned_hits = extract_banned_hits(before_content)
    has_causal = any(a.get("dimension") in ("conflict_novelty", "ability_constraints") for a in targets)

    # 步驟 1: 引擎診斷 + 精確命中錨點 + 上一輪重審建議 → 總監 LLM 合成修正指令
    user_instruction = build_director_user_instruction(
        novel_id,
        chapter_index,
        targets,
        reaudit_findings=reaudit_findings,
        banned_hits=banned_hits,
        round_idx=round_idx,
    )

    # 步驟 2: 總監優先級重點分流 (Priority-Based Agent Routing)
    # 根據缺陷維度精準分派：
    # - 若涉及核心因果、能力代價或主線任務（P0 級問題）：由 Writer 重新推演因果與情節架構（打破 round_idx==1 的死鎖，只要因果未解就由 Writer 負責根本解決）。
    # - 純微觀語言、口癖、開篇切入或微調（P1/P2 級問題）：由 Editor 進行定點手術潤色，專注語法與調理，不碰因果。
    should_run_writer = has_causal
    current_spans = banned_hits

    if should_run_writer:
        try:
            writer_gen = run_chapter_writer(
                novel_id,
                chapter_index,
                user_prompt=user_instruction,
                stream=False,
                fix_mode=True,
                fix_targets=targets,
                banned_hits=banned_hits,
            )
            for _ in writer_gen:
                pass
            w_row = db.get_latest_chapter(novel_id, chapter_index)
            if w_row and (w_row.get("content") or "").strip():
                w_content = w_row["content"]
                w_hits = extract_banned_hits(w_content)
                if w_hits:
                    current_spans = w_hits
        except TypeError:
            try:
                writer_gen = run_chapter_writer(
                    novel_id,
                    chapter_index,
                    user_prompt=user_instruction,
                )
                for _ in writer_gen:
                    pass
            except Exception as e:
                print(f"[WARN] run_chapter_writer fallback in fix loop notice: {e}")
        except Exception as e:
            print(f"[WARN] run_chapter_writer in fix loop notice: {e}")

    # 步驟 3: Editor 職責邊界收斂——專注語句、語法、口癖剔除與文風調理
    # 若上一階段執行了 Writer，Editor 進行最後的語言拋光；若未跑 Writer，則由 Editor 進行定點微創手術
    try:
        editor_gen = run_editor_agent(
            novel_id,
            chapter_index,
            edit_instructions=user_instruction,
            stream=False,
            fix_mode=True,
            fix_spans=current_spans,
        )
        for _ in editor_gen:
            pass
    except TypeError:
        try:
            editor_gen = run_editor_agent(
                novel_id,
                chapter_index,
                edit_instructions=user_instruction,
            )
            for _ in editor_gen:
                pass
        except Exception as e:
            print(f"[WARN] run_editor_agent fallback in fix loop notice: {e}")
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
                novel_id, chapter_index, reaudit_findings=prev_reaudit_findings, round_idx=rnd,
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
        "rounds_used": len(rounds),
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
