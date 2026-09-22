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
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from backend import persistence as db
from backend.services.narrative.conflict_ledger import ConflictLedger
from backend.services.narrative.setting_registry import SettingRegistry


class NarrativeAuditor:
    """提供 Director 2.0 的全面敘事推理與診斷能力。"""

    # 通用 AI 模板化微動作與臉譜化台詞（不綁定特定作品專有名詞）
    GESTURE_REUSE_PATTERNS = [
        (r"嘴角(?:微微)?勾起(?:一抹)?(?:冷笑|笑意|弧度|譏諷)", "嘴角勾起笑意/冷笑"),
        (r"眼神(?:深處)?閃過(?:一抹|一絲)?(?:冷冽|寒芒|異色|讚賞)", "眼神閃過異色/冷冽"),
        (r"不知死活的螻蟻|區區螻蟻|區區賤民", "反派臉譜化辱罵台詞"),
        (r"這不可能[！!]|你怎麼可能[！!]|這絕不可能", "反派公式化驚呼"),
        (r"倒吸一[口口]涼氣", "旁觀者震驚模板"),
        (r"空氣(?:彷彿|瞬間)?凝固", "氛圍定型化描寫"),
        (r"(?:指尖|手指|身軀)(?:微微)?顫抖", "感官堆疊模板（指尖/身軀顫抖）"),
        (r"命運的(?:齒輪|重量|天平|巨輪)", "抽象意象堆疊（命運的...）"),
        (r"(?:這一切|這場遊戲|這局棋)(?:，|,)?(?:才剛剛?開始|僅僅是個開始)", "公式化宣言句式"),
    ]

    # 通用抽象公式化結尾模式（預言/宣告/宏大抒情，而非現場實質情節動作）
    FORMULAIC_ENDING_PATTERNS = [
        (r"(?:風暴|暴風雨|波瀾|暗湧|序幕|帷幕|輪迴|變革|血雨腥風|動盪|深淵|黑暗).*?(?:拉開|落下|將至|降臨|展開|醞釀|到來|重啟|吞噬)", "宏大預言/風暴序幕套路結尾"),
        (r"(?:這|這一切|這場.*?)(?:，|,)?(?:只是|僅僅是|才剛剛?)(?:一個)?(?:開始|序曲|序幕)", "「這才剛剛開始」公式化懸念"),
        (r"等待著?(?:他|她|他們|這座.*?|整個.*?)(?:的)?(?:，|,)?(?:將是|又是).*?", "「等待著他的將是」宣告式收束"),
        (r"(?:命運|歷史).*?(?:齒輪|車輪|筆觸|天平).*?(?:轉動|落下|開啟|傾斜)", "命運齒輪抽象宏大宣告"),
    ]

    @classmethod
    def _check_ending_repetition(
        cls,
        novel_id: str,
        chapter_index: int,
        prose_text: str,
    ) -> Optional[Dict[str, Any]]:
        """動態檢測章節結尾是否陷入公式化宣告，或與近期章節連續出現同類收尾模式。"""
        if not prose_text or len(prose_text.strip()) < 200:
            return None

        ending_snippet = prose_text.strip()[-350:]
        cur_ending_hit = None
        for pat, label in cls.FORMULAIC_ENDING_PATTERNS:
            if re.search(pat, ending_snippet):
                cur_ending_hit = label
                break

        if not cur_ending_hit:
            return None

        # 檢查近期章節（前 1~3 章）結尾是否也有類似公式化收束
        consecutive_count = 1
        prev_ending_examples = []
        try:
            for prev_idx in range(max(1, chapter_index - 3), chapter_index):
                prev_ch = db.get_latest_chapter(novel_id, prev_idx)
                if prev_ch and (prev_ch.get("content") or "").strip():
                    prev_end = prev_ch["content"].strip()[-350:]
                    for pat, label in cls.FORMULAIC_ENDING_PATTERNS:
                        if re.search(pat, prev_end):
                            consecutive_count += 1
                            prev_ending_examples.append(f"第 {prev_idx} 章（{label}）")
                            break
        except Exception:
            pass

        # 若當前命中，且前 3 章已有同類收尾（連續 2 章以上）：升級為 WARNING 並強制修復！
        if consecutive_count >= 2:
            return {
                "dimension": "voice_integrity",
                "severity": "warning",
                "evidence": f"本章結尾命中「{cur_ending_hit}」；且近 3 章中已有 {', '.join(prev_ending_examples)} 採用同類公式化預言收尾。",
                "recommendation": "結尾嚴禁使用抽象命運預言或空洞懸念收束；必須切換為本場景的具體實質動作、即時危機爆發，或具備實質抉擇意義的現場懸念。",
                "action_required": True,
            }
        else:
            return {
                "dimension": "voice_integrity",
                "severity": "watch",
                "evidence": f"本章末尾出現公式化宣告式句式（{cur_ending_hit}）。",
                "recommendation": "建議章節結尾收束於角色具體動作或現場危機，避免每章固定以抽象預兆收尾。",
                "action_required": False,
            }

    @classmethod
    def _check_cross_chapter_motif_reuse(
        cls,
        novel_id: str,
        chapter_index: int,
        prose_text: str,
    ) -> Optional[Dict[str, Any]]:
        """動態檢查是否有特定非通用短語在相鄰章節高頻復現（物象或微動作去重）。"""
        if not prose_text or chapter_index <= 1:
            return None

        try:
            prev_ch = db.get_latest_chapter(novel_id, chapter_index - 1)
            if not prev_ch or not (prev_ch.get("content") or "").strip():
                return None
            prev_text = prev_ch["content"]

            cur_phrases = re.findall(r"[\u4e00-\u9fa5]{3,4}", prose_text)
            cur_counts = Counter(cur_phrases)

            COMMON_STOPWORDS = {
                "不知不覺", "與此同時", "與此相反", "不可思議", "毫不猶豫",
                "轉身離去", "搖了搖頭", "深吸一口", "點了點頭", "眉頭微皺",
                "就在這時", "下一瞬間", "片刻之後", "抬起頭來", "緩緩開口",
                "與此相關", "顯而易見", "無時無刻", "不由自主", "自言自語"
            }
            repeated_motifs = []
            for phrase, count in cur_counts.items():
                if count >= 3 and phrase not in COMMON_STOPWORDS:
                    prev_cnt = prev_text.count(phrase)
                    if prev_cnt >= 3:
                        repeated_motifs.append(f"「{phrase}」（本章 {count} 次，上章 {prev_cnt} 次）")

            if repeated_motifs:
                return {
                    "dimension": "voice_integrity",
                    "severity": "warning",
                    "evidence": f"偵測到特定物象或口癖短語跨章高頻復用：{', '.join(repeated_motifs[:3])}。",
                    "recommendation": "依據物象去重原則，嚴禁跨章節高頻復用單一固化物象或微動作，請更換為符合本章現場環境的新鮮感官描寫。",
                    "action_required": True,
                }
        except Exception:
            pass
        return None


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
        # 維度 1: voice_integrity & gesture_reuse (語言、動作與收尾重複診斷)
        # -----------------------------------------------------------------
        gesture_hits = []
        for pat, label in cls.GESTURE_REUSE_PATTERNS:
            matches = re.findall(pat, prose_text)
            if matches:
                gesture_hits.append(f"{label} (出現 {len(matches)} 次)")

        # 1a. 本章內的模板動作/口癖檢測（含跨章累犯升級）
        if len(gesture_hits) >= 1:
            recent_audits = []
            try:
                recent_audits = [
                    a for a in (db.get_narrative_audits(novel_id, unresolved_only=True, limit=20) or [])
                    if a.get("dimension") == "voice_integrity"
                    and a.get("chapter_index", 0) >= chapter_index - 3
                    and a.get("chapter_index", 0) < chapter_index
                ]
            except Exception:
                pass

            is_repeat_offense = len(recent_audits) >= 1
            sev = "warning" if (len(gesture_hits) >= 2 or is_repeat_offense) else "watch"
            act_req = len(gesture_hits) >= 3 or (len(gesture_hits) >= 2 and is_repeat_offense)

            note = f"（累犯升級：近 3 章內已有 {len(recent_audits)} 筆同類語言套路觀察）" if is_repeat_offense else ""
            findings.append({
                "dimension": "voice_integrity",
                "severity": sev,
                "evidence": "、".join(gesture_hits) + note,
                "recommendation": "偵測到高頻套路動作或定型描寫，建議替換為角色當前情境之獨特微動作、具體物象或富有次文本的語言交鋒。",
                "action_required": act_req,
            })

        # 1b. 動態公式化收尾檢測（非定型收尾原則）
        ending_finding = cls._check_ending_repetition(novel_id, chapter_index, prose_text)
        if ending_finding:
            findings.append(ending_finding)

        # 1c. 動態跨章物象/短語重複檢測（物象去重原則）
        motif_finding = cls._check_cross_chapter_motif_reuse(novel_id, chapter_index, prose_text)
        if motif_finding:
            findings.append(motif_finding)

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

                    # 累犯升級：若近期已多次出現同類零代價破局，從 WATCH 升級為 WARNING
                    try:
                        recent_audits = db.get_narrative_audits(
                            novel_id, unresolved_only=True, limit=30
                        )
                        recent_same_dim = [
                            a for a in (recent_audits or [])
                            if a.get("dimension") == "ability_constraints"
                            and a.get("chapter_index", 0) >= chapter_index - 3
                            and a.get("chapter_index", 0) < chapter_index
                        ]
                        if len(recent_same_dim) >= 2:
                            # 累犯 >= 2 次，升級為 WARNING 並強制修復
                            findings[-1]["severity"] = "warning"
                            findings[-1]["action_required"] = True
                            findings[-1]["evidence"] += (
                                f"（累犯升級：近 3 章內已有 {len(recent_same_dim)} 筆同類零代價觀察，"
                                "強制轉為修復要求）"
                            )
                            findings[-1]["recommendation"] += (
                                "此問題已連續多章未改善，本次必須在正文中補寫具體代價場景。"
                            )
                    except Exception:
                        pass

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
