# -*- coding: utf-8 -*-
"""
Story Engine 2.0 Narrative Auditor (Director 2.0 敘事推理核心)
八大核心診斷維度 + 四大補充維度

核心準則：
1. Rubric 用來發現長程結構性問題，而不是規定故事必須長成某一種形式。
2. 不要求每章完整 Five Commandments，不要求每章強行 Value Shift。
3. 學會「何時什麼都不用改」(NO_ACTION_REQUIRED) — 安靜章、過渡章、探索章皆是健康的節奏呼吸。
4. 辨識長程結構重複 (Conflict Novelty) 與能力無代價萬能解 (Ability Constraints)。
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from backend import persistence as db
from backend.services.narrative.conflict_ledger import ConflictLedger
from backend.services.narrative.setting_registry import SettingRegistry


class NarrativeAuditor:
    """提供 Director 2.0 的全面敘事推理與診斷能力。"""

    # 常見 AI 模板化動作與口癖
    GESTURE_REUSE_PATTERNS = [
        (r"嘴角(?:微微)?勾起(?:一抹)?(?:冷笑|笑意|弧度|譏諷)", "嘴角勾起笑意/冷笑"),
        (r"眼神(?:深處)?閃過(?:一抹|一絲)?(?:冷冽|寒芒|異色|讚賞)", "眼神閃過異色/冷冽"),
        (r"不知死活的螻蟻|區區螻蟻|區區賤民", "反派臉譜化辱罵台詞"),
        (r"這不可能[！!]|你怎麼可能[！!]", "反派公式化驚呼"),
        (r"倒吸一[口口]涼氣", "旁觀者震驚模板"),
        (r"空氣(?:彷彿|瞬間)?凝固", "氛圍定型化描寫"),
    ]

    @classmethod
    def audit_chapter_prose(
        cls,
        novel_id: str,
        chapter_index: int,
        prose_text: str,
        current_outline: Optional[Dict[str, Any]] = None,
        candidate_conflict_sig: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        對單章正文進行長程敘事診斷。
        回傳包含 overall_action, dimension_results, recommendations 的診斷物件。
        """
        outline = current_outline or {}
        scene_func = outline.get("scene_function", "progression")
        findings: List[Dict[str, Any]] = []

        # -----------------------------------------------------------------
        # 維度 1: voice_integrity & gesture_reuse (語言與動作重複診斷)
        # -----------------------------------------------------------------
        gesture_hits = []
        for pat, label in cls.GESTURE_REUSE_PATTERNS:
            matches = re.findall(pat, prose_text)
            if matches:
                gesture_hits.append(f"{label} (出現 {len(matches)} 次)")

        if len(gesture_hits) >= 2:
            findings.append({
                "dimension": "voice_integrity",
                "severity": "watch" if len(gesture_hits) <= 2 else "warning",
                "evidence": "、".join(gesture_hits),
                "recommendation": "偵測到多處高頻套路動作或反派模板對白，建議替換為角色獨特之微動作、具體物象或富有次文本的語言交鋒。",
                "action_required": len(gesture_hits) > 3,
            })

        # -----------------------------------------------------------------
        # 維度 2: conflict_novelty (長程衝突因果重複診斷)
        # -----------------------------------------------------------------
        if candidate_conflict_sig:
            rep_check = ConflictLedger.check_long_range_repetition(
                novel_id, candidate_conflict_sig, exclude_chapter=chapter_index
            )
            if rep_check.get("has_repetition"):
                matches = rep_check["matches"]
                first_m = matches[0]
                findings.append({
                    "dimension": "conflict_novelty",
                    "severity": "warning",
                    "evidence": f"與 {first_m['prior_chapter_range']} 因果模式高度相似 (相似度 {first_m['similarity']})：{', '.join(first_m['reasons'])}",
                    "recommendation": "此交鋒公式在過去章節已多次出現。建議本章將解決方式轉為：非暴力智鬥、體制合法漏洞、利益同盟交換，或讓主角承受真實的社會/情報代價。",
                    "action_required": True,
                })

        # -----------------------------------------------------------------
        # 維度 3: ability_constraints (超常能力代價與萬能解診斷)
        # -----------------------------------------------------------------
        # 若本章有重大戰鬥/反殺，但正文中毫無任何受創、消耗、暴露或道德兩難描寫
        if candidate_conflict_sig and candidate_conflict_sig.get("protagonist_strategy") in ("asymmetric_wit", "rules_loophole", "direct_clash"):
            cost_desc = str(candidate_conflict_sig.get("cost") or "").strip().lower()
            if not cost_desc or cost_desc in ("無", "none", "零代價", "無代價"):
                # 檢查是否為無敵流
                profile = db.get_narrative_profile(novel_id)
                if profile.get("power_fantasy_level") != "absolute":
                    findings.append({
                        "dimension": "ability_constraints",
                        "severity": "watch",
                        "evidence": "主角動用高階破局手段後未體現任何能力冷卻、精神負擔、情報暴露或人際代價。",
                        "recommendation": "適度描寫動用底牌後的外部引力（如引起監察使警覺、魔能殘留難以掩蓋），維持故事危機感。",
                        "action_required": False,
                    })

        # -----------------------------------------------------------------
        # 維度 4: pacing_balance & breathing_space (節奏呼吸診斷)
        # -----------------------------------------------------------------
        # 辨識安靜章、過渡章、探索章
        is_breathing_scene = scene_func in ("recovery", "transition", "discovery", "reflection")
        if is_breathing_scene:
            # 這是健康的節奏沉澱，堅決不要求強制爆發衝突
            pass

        # -----------------------------------------------------------------
        # 決策收束 (Overall Decision)
        # -----------------------------------------------------------------
        critical_issues = [f for f in findings if f["severity"] == "critical"]
        warning_issues = [f for f in findings if f["severity"] == "warning" and f["action_required"]]
        watch_issues = [f for f in findings if f["severity"] in ("watch", "warning") and not f["action_required"]]

        if critical_issues:
            overall_action = "CRITICAL"
        elif warning_issues:
            overall_action = "REVISE"
        elif watch_issues:
            overall_action = "WATCH"
        else:
            # 如果是安靜章或無任何重大疑慮，判定為健全無須動作
            overall_action = "NO_ACTION_REQUIRED" if is_breathing_scene else "PASS"

        # 持久化診斷記錄
        for f in findings:
            db.add_narrative_audit(
                novel_id=novel_id,
                chapter_index=chapter_index,
                dimension=f["dimension"],
                severity=f["severity"],
                evidence=f["evidence"],
                recommendation=f["recommendation"],
                action_required=f["action_required"],
            )

        return {
            "chapter_index": chapter_index,
            "overall_action": overall_action,
            "scene_function": scene_func,
            "findings_count": len(findings),
            "findings": findings,
            "is_breathing_scene": is_breathing_scene,
            "summary": f"第 {chapter_index} 章診斷結論：[{overall_action}]。發現 {len(findings)} 項觀察點。"
        }
