# -*- coding: utf-8 -*-
"""
Story Engine 2.0 Conflict Signature Ledger
長程因果特徵帳本與結構性重複檢測器

核心原則：
- 不比較字面詞彙相似度，而是比較「因果模式」(Causal Pattern)。
- 辨識典型套路循環：[強權施壓 -> 主角裝弱 -> 對方低估 -> 規則漏洞/金手指 -> 敵人震驚 -> 零代價離場]。
- 支援 100~500 章長程檢索，預防長篇小說中期開始的模式僵化。
"""

import json
from typing import Any, Dict, List, Optional, Tuple

from backend import persistence as db
from backend.common.config import CONFLICT_SIMILARITY_WARNING_THRESHOLD, LONG_RANGE_CONFLICT_CHECK_WINDOW


class ConflictLedger:
    """管理長篇小說衝突因果特徵並診斷結構性套路重複。"""

    # LLM 歸一化用的封閉分類（與 Graphiti Extractor 共用，保證相似度比對吃到
    # 枚舉字串而非自由文本；未知值允許原樣寫入，相似度函數仍可處理）。
    PRESSURE_TYPES = (
        "oppression", "suppression", "blockade", "humiliation",
        "assassination", "frame_up", "legal_strangulation", "manipulation",
        "emotional_coercion", "exclusion", "other",
    )
    PROTAGONIST_STRATEGIES = (
        "play_dumb_or_weak", "asymmetric_wit", "rules_loophole",
        "direct_clash", "strategic_retreat", "negotiation",
        "investigation", "damage_control", "recuperation",
        "groundwork", "adaptive_response", "payoff_execution",
    )
    OUTCOMES = (
        "public_shock", "uneasy_truce", "costly_victory", "setback",
        "escape", "reversal", "progression", "revelation",
    )

    @staticmethod
    def record_signature(
        novel_id: str,
        chapter_start: int,
        chapter_end: int,
        pressure_type: str,
        protagonist_strategy: str,
        outcome: str,
        initiator: Optional[str] = None,
        antagonist_goal: Optional[str] = None,
        power_used: Optional[str] = None,
        twist_mechanism: Optional[str] = None,
        cost: Optional[str] = None,
        emotional_effect: Optional[str] = None,
        setting_used: Optional[str] = None,
    ) -> Dict[str, Any]:
        """記錄一筆衝突特徵到持久化帳本"""
        return db.add_conflict_signature(
            novel_id=novel_id,
            chapter_start=chapter_start,
            chapter_end=chapter_end,
            pressure_type=pressure_type,
            protagonist_strategy=protagonist_strategy,
            outcome=outcome,
            initiator=initiator,
            antagonist_goal=antagonist_goal,
            power_used=power_used,
            twist_mechanism=twist_mechanism,
            cost=cost,
            emotional_effect=emotional_effect,
            setting_used=setting_used,
        )

    @staticmethod
    def calculate_causal_similarity(sig_a: Dict[str, Any], sig_b: Dict[str, Any]) -> Tuple[float, List[str]]:
        """
        比對兩筆衝突的因果模式相似度（0.0 ~ 1.0）
        回傳 (score, match_reasons)
        """
        match_reasons = []
        score = 0.0

        # 1. 壓迫手段相似度 (權重 0.25)
        p_a = str(sig_a.get("pressure_type") or sig_a.get("underlying_cause") or "").strip().lower()
        p_b = str(sig_b.get("pressure_type") or sig_b.get("underlying_cause") or "").strip().lower()
        if p_a and p_b and (
            p_a == p_b
            or (len(p_a) >= 2 and len(p_b) >= 2 and (p_a in p_b or p_b in p_a))
            or ("壓迫" in p_a and "壓迫" in p_b)
            or ("打壓" in p_a and "打壓" in p_b)
            or ("封鎖" in p_a and "封鎖" in p_b)
        ):
            score += 0.25
            match_reasons.append(f"壓迫手段同質：皆涉及「{p_a}」與「{p_b}」")

        # 2. 主角應對策略相似度 (權重 0.35 - 最關鍵的套路指標)
        s_a = str(sig_a.get("protagonist_strategy") or "").strip().lower()
        s_b = str(sig_b.get("protagonist_strategy") or "").strip().lower()
        if s_a and s_a == s_b:
            score += 0.35
            match_reasons.append(f"主角解題策略同質：皆為「{s_a}」")
        elif ("裝傻" in s_a or "play_dumb" in s_a or "無賴" in s_a) and ("裝傻" in s_b or "play_dumb" in s_b or "無賴" in s_b):
            score += 0.30
            match_reasons.append("主角均採取裝傻/偽裝弱者以尋求反殺之相同套路")

        # 3. 結果與代價相似度 (權重 0.25)
        o_a = str(sig_a.get("outcome") or sig_a.get("resolution_archetype") or "").strip().lower()
        o_b = str(sig_b.get("outcome") or sig_b.get("resolution_archetype") or "").strip().lower()
        c_a = str(sig_a.get("cost") or "").strip().lower()
        c_b = str(sig_b.get("cost") or "").strip().lower()
        if o_a and o_b and (
            o_a == o_b
            or (len(o_a) >= 2 and len(o_b) >= 2 and (o_a in o_b or o_b in o_a))
            or ("shock" in o_a and "shock" in o_b)
            or ("震驚" in o_a and "震驚" in o_b)
        ):
            score += 0.15
            match_reasons.append(f"結局模式同質：皆為「{o_a}」與「{o_b}」")
        if (not c_a or "無" in c_a or "none" in c_a or "零代價" in c_a) and (not c_b or "無" in c_b or "none" in c_b or "零代價" in c_b):
            score += 0.10
            match_reasons.append("雙方均為零代價完美破局，缺乏實質挫折或代價承擔")

        # 4. 所用力量/破局機制相似度 (權重 0.15)
        pw_a = str(sig_a.get("power_used") or sig_a.get("turning_tactic") or "").strip().lower()
        pw_b = str(sig_b.get("power_used") or sig_b.get("turning_tactic") or "").strip().lower()
        if pw_a and pw_b and (pw_a == pw_b or ("secret_power" in pw_a and "secret_power" in pw_b)):
            score += 0.15
            match_reasons.append(f"動用之破局手段重複：皆依靠「{pw_a}」")

        return min(1.0, score), match_reasons

    @classmethod
    def check_long_range_repetition(
        cls,
        novel_id: str,
        candidate_sig: Dict[str, Any],
        window: int = LONG_RANGE_CONFLICT_CHECK_WINDOW,
        threshold: float = CONFLICT_SIMILARITY_WARNING_THRESHOLD,
        exclude_chapter: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        在過去 window 章的衝突特徵中，檢索是否有高度相似的因果模式。
        exclude_chapter：審計本章時排除本章自己的簽名，避免自己跟自己比出 1.0。
        回傳診斷報告字典。
        """
        history = db.get_conflict_signatures(novel_id, limit=window)
        if exclude_chapter is not None:
            try:
                ex = int(exclude_chapter)
                history = [
                    h for h in history
                    if not (int(h.get("chapter_start") or 0) <= ex <= int(h.get("chapter_end") or h.get("chapter_start") or 0))
                ]
            except Exception:
                pass
        if not history:
            return {"has_repetition": False, "max_similarity": 0.0, "matches": []}

        matches = []
        max_sim = 0.0
        for item in history:
            sim, reasons = cls.calculate_causal_similarity(candidate_sig, item)
            if sim >= threshold:
                cs, ce = int(item['chapter_start']), int(item['chapter_end'])
                chap_range = f"第 {cs} 章" if cs == ce else f"第 {cs}-{ce} 章"
                matches.append({
                    "prior_chapter_range": chap_range,
                    "initiator": item.get("initiator"),
                    "similarity": round(sim, 2),
                    "reasons": reasons,
                    "prior_summary": f"壓迫: {item.get('pressure_type')} | 策略: {item.get('protagonist_strategy')} | 結果: {item.get('outcome')}",
                })
            if sim > max_sim:
                max_sim = sim

        return {
            "has_repetition": len(matches) > 0,
            "max_similarity": round(max_sim, 2),
            "match_count": len(matches),
            "matches": matches[:3], # 取最相似的前3項
        }

    @classmethod
    def extract_signature_from_chapter(
        cls,
        novel_id: str,
        chapter_index: int,
        outline_hint: Optional[Dict[str, Any]] = None,
        prose_text: Optional[str] = None,
        outline: Optional[Dict[str, Any]] = None,
        llm_signature: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """從章節大綱 hint + 正文啟發式提取一筆可持久化的衝突簽名 dict。

        優先級：llm_signature（Graphiti Extractor 同次 LLM 歸一化結果，枚舉值）
        ＞ outline_hint ＞ scene_function 映射＋正文關鍵字（全離線 fallback）。
        保證永不拋錯，管線可安全呼叫。
        回傳 dict 相容 ``db.add_conflict_signature(dict)``（含 novel_id /
        chapter_start / chapter_end / chapter_index 與因果欄位）。
        """
        llm_sig = llm_signature if isinstance(llm_signature, dict) else {}
        hint = outline_hint if isinstance(outline_hint, dict) else {}
        ol = outline if isinstance(outline, dict) else {}
        # outline_hint 有時直接就是整章 outline（pipeline 舊寫法），合併備援
        if not hint and ol:
            hint = ol
        prose = prose_text if isinstance(prose_text, str) else ""

        def _pick(*keys: str) -> str:
            for src in (llm_sig, hint, ol):
                for k in keys:
                    v = src.get(k)
                    if v is None:
                        continue
                    if isinstance(v, list):
                        v = "、".join(str(x) for x in v if str(x).strip())
                    s = str(v).strip()
                    if s and s not in ("{}", "[]", "無", "none", "null"):
                        return s
            return ""

        def _clip(s: str, n: int = 60) -> str:
            s = str(s or "").strip()
            return s[:n] if len(s) > n else s

        # -- 1. 壓迫類型 --------------------------------------------------
        pressure = _pick("pressure_type", "underlying_cause", "scene_conflict")
        if not pressure:
            pressure = _clip(
                _pick("chapter_summary", "scene_goal", "scene_beats") or "衝突推進"
            ) or "衝突推進"

        # -- 2. 主角策略 --------------------------------------------------
        strategy = _pick("protagonist_strategy")
        if not strategy:
            scene_func = str(
                hint.get("scene_function") or ol.get("scene_function") or ""
            ).lower()
            func_map = {
                "setup": "groundwork",
                "escalation": "adaptive_response",
                "confrontation": "direct_clash",
                "discovery": "investigation",
                "decision": "rules_loophole",
                "consequence": "damage_control",
                "recovery": "recuperation",
                "transition": "recuperation",
                "reflection": "recuperation",
                "payoff": "payoff_execution",
                "progression": "adaptive_response",
            }
            strategy = "adaptive_response"
            for key, val in func_map.items():
                if key in scene_func:
                    strategy = val
                    break
            # 正文關鍵字微調（裝傻/律法/智鬥等高頻套路優先標記，利於去重）
            if any(k in prose for k in ("裝傻", "示弱", "扮豬吃虎", "藏拙")):
                strategy = "play_dumb_or_weak"
            elif any(k in prose for k in ("律法", "規則漏洞", "漏洞", "條例")):
                strategy = "rules_loophole"
            elif any(k in prose for k in ("佈局", "設局", "計中計", "借刀")):
                strategy = "asymmetric_wit"
            elif any(k in prose for k in ("撤退", "暫避", "退走", "隱忍")):
                strategy = "strategic_retreat"
            elif any(k in prose for k in ("結盟", "交易", "談判", "妥協")):
                strategy = "negotiation"

        # -- 3. 結果 ------------------------------------------------------
        outcome = _pick("outcome", "resolution_archetype", "scene_outcome")
        if not outcome:
            outcome = _clip(
                _pick("story_state_after", "scene_turn", "chapter_summary") or "推進"
            ) or "推進"

        # -- 4. 其餘欄位 --------------------------------------------------
        initiator = _pick("initiator", "opponent")
        if not initiator:
            active = hint.get("characters_active") or ol.get("characters_active") or []
            if isinstance(active, str):
                active = [c.strip() for c in active.replace("，", ",").replace("、", ",").split(",") if c.strip()]
            if isinstance(active, list) and len(active) >= 2:
                initiator = str(active[1])[:20]
            elif isinstance(active, list) and active:
                initiator = "對立勢力"
            else:
                initiator = "對立勢力"

        antagonist_goal = _pick("antagonist_goal", "escalation_mechanism", "scene_conflict")
        power_used = _pick("power_used", "turning_tactic", "twist_mechanism")
        twist = _pick("twist_mechanism", "turning_tactic", "scene_turn")
        cost = _pick("cost", "cost_paid")
        emotional = _pick("emotional_effect", "emotional_tone")
        setting_used = _pick("setting_used")
        if not setting_used:
            su = hint.get("setting_usage", ol.get("setting_usage"))
            if isinstance(su, list) and su:
                first = su[0]
                setting_used = first.get("system_name") if isinstance(first, dict) else str(first)
            elif isinstance(su, dict) and su.get("system_name"):
                setting_used = str(su["system_name"])
            elif isinstance(su, str) and su.strip():
                setting_used = su.strip()

        ch_idx = int(chapter_index or 1)
        return {
            "novel_id": novel_id,
            "chapter_start": ch_idx,
            "chapter_end": ch_idx,
            "chapter_index": ch_idx,
            "initiator": initiator or "對立勢力",
            "antagonist_goal": antagonist_goal or None,
            "pressure_type": pressure,
            "protagonist_strategy": strategy,
            "power_used": power_used or None,
            "twist_mechanism": twist or None,
            "outcome": outcome,
            "cost": cost or None,
            "emotional_effect": emotional or None,
            "setting_used": (str(setting_used).strip() or None) if setting_used else None,
        }

    @classmethod
    def build_anti_repetition_prompt_snippet(
        cls,
        novel_id: str,
        current_chapter: int,
    ) -> str:
        """為 WriterContextBuilder 產生乾淨且富啟發性的長程去套路化提示詞"""
        recent = db.get_conflict_signatures(novel_id, limit=4)
        if not recent:
            return ""

        lines = ["### ⚠️【長程衝突因果防重複指引 (Conflict Novelty Guard)】"]
        lines.append("- **近幾次已使用之衝突與破局模式**（本章請主動避開相同因果公式）：")
        for r in recent:
            c_range = f"第 {r['chapter_start']}-{r['chapter_end']} 章" if r['chapter_start'] != r['chapter_end'] else f"第 {r['chapter_start']} 章"
            cost_str = f"，付出了代價「{r['cost']}」" if r.get("cost") and r["cost"] not in ("無", "none") else "（零代價反殺）"
            lines.append(f"  * {c_range}：{r.get('initiator', '敵人')}發起【{r.get('pressure_type', '施壓')}】 -> 主角採取【{r.get('protagonist_strategy', '應對')}】 -> 結果【{r.get('outcome', '解決')}】{cost_str}")

        lines.append("- **創作演繹建議**：")
        lines.append("  * 避免再次採用「敵人上門挑釁 -> 主角裝傻示弱 -> 主角金手指一擊必殺 -> 敵人驚駭」的公式化閉環。")
        lines.append("  * 鼓勵探索：資訊迷霧偵錯、多方利益斡旋、體制規則合法博弈、同伴救援背叛抉擇、主動出擊佈局，或讓主角承受真實的情報暴露與社會後果。")

        return "\n".join(lines)
