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


def _is_one_character_edit(left: str, right: str) -> bool:
    """True only for one insertion, deletion, or substitution; avoids broad prefix collisions."""
    if left == right or abs(len(left) - len(right)) > 1:
        return False
    i = j = edits = 0
    while i < len(left) and j < len(right):
        if left[i] == right[j]:
            i += 1
            j += 1
            continue
        edits += 1
        if edits > 1:
            return False
        if len(left) > len(right):
            i += 1
        elif len(right) > len(left):
            j += 1
        else:
            i += 1
            j += 1
    edits += int(i < len(left) or j < len(right))
    return edits == 1


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

    # 通用公式化開篇模式（套路環境/微動作/模板開場）
    FORMULAIC_OPENING_PATTERNS = [
        (r"網咖.*?(?:泡麵|屏幕|鍵盤|機箱|煙味|汗水)", "cyber_cafe", "網咖/廉價泡麵/電腦屏幕定型開頭"),
        (r"(?:老舊的|逼仄.*?|斑駁.*?)?霓虹招牌.*?(?:滋滋|光暈|雨水|微弱|閃爍)", "neon_buzzing", "霓虹招牌滋滋作響套路開局"),
        (r"(?:刺耳的)?(?:鬧鐘|鐘聲|鬧鈴).*?(?:驚醒|醒來|冷汗|心臟)", "alarm_waking", "鬧鐘驚醒/冷汗心悸套路開局"),
        (r"(?:窗外|夜雨|暴雨|大雨).*?(?:暴雨|灰濛濛|拍打|水窪|壓抑)", "rain_weather", "窗外陰雨/拍打玻璃天氣開場"),
        (r"(?:酒館|酒吧).*?(?:玻璃杯|酒保|冰塊|碰撞)", "bar_whiskey", "酒館/擦拭玻璃杯定型開局"),
    ]

    # 通用抽象公式化結尾模式（預言/宣告/宏大抒情，而非現場實質情節動作）
    FORMULAIC_ENDING_PATTERNS = [
        (r"(?:風暴|暴風雨|波瀾|暗湧|序幕|帷幕|輪迴|變革|血雨腥風|動盪|深淵|黑暗).*?(?:拉開|落下|將至|降臨|展開|醞釀|到來|重啟|吞噬)", "宏大預言/風暴序幕套路結尾"),
        (r"(?:這|這一切|這場.*?)(?:，|,)?(?:只是|僅僅是|才剛剛?)(?:一個)?(?:開始|序曲|序幕)", "「這才剛剛開始」公式化懸念"),
        (r"等待著?(?:他|她|他們|這座.*?|整個.*?)(?:的)?(?:，|,)?(?:將是|又是).*?", "「等待著他的將是」宣告式收束"),
        (r"(?:命運|歷史).*?(?:齒輪|車輪|筆觸|天平).*?(?:轉動|落下|開啟|傾斜)", "命運齒輪抽象宏大宣告"),
    ]

    @classmethod
    def _check_opening_repetition(
        cls,
        novel_id: str,
        chapter_index: int,
        prose_text: str,
    ) -> Optional[Dict[str, Any]]:
        """動態檢測章節開篇是否陷入公式化模板開局，或與近期章節連續出現同類開篇模式。"""
        if not prose_text or len(prose_text.strip()) < 20:
            return None

        opening_snippet = prose_text.strip()[:400]
        cur_cliche_key = None
        cur_cliche_label = None

        for pat, key, label in cls.FORMULAIC_OPENING_PATTERNS:
            if re.search(pat, opening_snippet):
                cur_cliche_key = key
                cur_cliche_label = label
                break

        if not cur_cliche_key:
            # Check 2-gram similarity with immediate previous chapter's opening
            if chapter_index > 1:
                try:
                    prev_ch = db.get_latest_chapter(novel_id, chapter_index - 1)
                    if prev_ch and (prev_ch.get("content") or "").strip():
                        prev_open = prev_ch["content"].strip()[:100]
                        cur_open = opening_snippet[:100]
                        prev_first = re.split(r"[。！？\n]", prev_open)[0].strip()
                        cur_first = re.split(r"[。！？\n]", cur_open)[0].strip()
                        if len(prev_first) >= 15 and len(cur_first) >= 15:
                            prev_2grams = set(prev_first[i:i+2] for i in range(len(prev_first) - 1))
                            cur_2grams = set(cur_first[i:i+2] for i in range(len(cur_first) - 1))
                            if prev_2grams and cur_2grams:
                                overlap = len(prev_2grams & cur_2grams) / min(len(prev_2grams), len(cur_2grams))
                                if overlap >= 0.50:
                                    return {
                                        "dimension": "voice_integrity",
                                        "severity": "warning",
                                        "evidence": f"連續跨章（第 {chapter_index - 1} 章與本章）開篇存在極高句式與詞彙重合（重疊度 {int(overlap * 100)}%）。",
                                        "recommendation": "開篇應避免連續跨章套用相同切入點模式，請更換全新感官、對白或突發行動入局。",
                                        "action_required": True,
                                    }
                except Exception as exc:
                    print(f"[WARN] Opening repetition cross-chapter check failed (novel {novel_id}, chapter {chapter_index}): {exc}")
            return None

        # 檢查近期章節（前 1~3 章）開頭是否也有相同套路
        consecutive_count = 1
        prev_examples = []
        try:
            for prev_idx in range(max(1, chapter_index - 3), chapter_index):
                prev_ch = db.get_latest_chapter(novel_id, prev_idx)
                if prev_ch and (prev_ch.get("content") or "").strip():
                    prev_open = prev_ch["content"].strip()[:400]
                    for pat, key, label in cls.FORMULAIC_OPENING_PATTERNS:
                        if key == cur_cliche_key and re.search(pat, prev_open):
                            consecutive_count += 1
                            prev_examples.append(f"第 {prev_idx} 章（{label}）")
                            break
        except Exception as exc:
            print(f"[WARN] Opening pattern history scan failed (novel {novel_id}): {exc}")

        if consecutive_count >= 2:
            return {
                "dimension": "voice_integrity",
                "severity": "warning",
                "evidence": f"本章開篇命中「{cur_cliche_label}」；且近 3 章中已有 {', '.join(prev_examples)} 採用同類定型開局。",
                "recommendation": "開篇嚴禁連續跨章復用相同場景切入點或環境套路，請更換全新視角、對白或突發行動入局。",
                "action_required": True,
            }
        else:
            return {
                "dimension": "voice_integrity",
                "severity": "watch",
                "evidence": f"本章開篇出現模板化場景起筆（{cur_cliche_label}）。",
                "recommendation": "建議開篇嘗試更豐富多元的切入方式（如行動中入局、對白切入），避免單一套路起筆。",
                "action_required": False,
            }

    @classmethod
    def _check_meta_narrative_leak(cls, prose_text: str) -> Optional[Dict[str, Any]]:
        """檢測正文是否洩漏大綱標籤、上一章銜接語等元文本 (Meta-Narrative Leakage)。"""
        if not prose_text:
            return None
        from backend.common.refusal_filter import find_meta_narrative_leaks
        leaks = find_meta_narrative_leaks(prose_text)
        if leaks:
            return {
                "dimension": "meta_narrative_leak",
                "severity": "critical",
                "evidence": f"正文檢測到破壁元敘事、寫作指令洩漏或大綱標籤：「{leaks[0]}」。",
                "recommendation": "正文嚴禁出現『上一章』、第四面牆打破、AI負向寫作指令（如『沒有制式化的...』）或大綱標籤等元文本；小說必須100%處於沉浸式故事世界內部，禁止旁白對讀者或寫作大綱進行元評論。",
                "action_required": True,
            }
        return None

    @classmethod
    def _check_terms_compliance(cls, novel_id: str, prose_text: str) -> Optional[Dict[str, Any]]:
        """檢查術語庫名詞是否被近義詞隨意替換或未嚴格遵守唯一性。"""
        if not novel_id or not prose_text:
            return None
        try:
            terms = db.get_terms(novel_id)
            if not terms:
                return None
            # Terms explicitly registered as separate canon entries are not typos of
            # one another, even when the old prefix/suffix heuristic considers them close.
            # This is essential for places, factions, devices, and variants with shared names.
            registered_terms = {
                str(item.get("term") or "").strip()
                for item in terms
                if str(item.get("term") or "").strip()
            }
            SYNONYM_REPLACEMENTS = {
                "靈能": ["法力", "真氣", "內力", "魔法值"],
                "星能": ["能量", "核能", "靈力"],
                "超元": ["超能", "異能"],
                "真元": ["真氣", "內力", "魔力", "法力", "靈力"],
            }
            for t in terms:
                term_name = t.get("term", "")
                if not term_name:
                    continue
                synonyms = SYNONYM_REPLACEMENTS.get(term_name, [])
                for syn in synonyms:
                    if syn in prose_text and term_name not in prose_text:
                        return {
                            "dimension": "terms_compliance",
                            "severity": "warning",
                            "evidence": f"檢測到使用近義詞「{syn}」代替登錄術語「{term_name}」",
                            "recommendation": f"請將全篇「{syn}」修改為術語庫標準名稱「{term_name}」，嚴禁隨意使用近義詞換皮。",
                            "action_required": True,
                        }
                # Corrupted proper noun fuzzy check (length >= 4)
                if len(term_name) >= 4 and term_name not in prose_text:
                    prefix = term_name[:2]
                    suffix = term_name[-2:]
                    pat = rf"{prefix}[\u4e00-\u9fa5]{{1,2}}{suffix}"
                    fuzzy_match = re.search(pat, prose_text)
                    if fuzzy_match and fuzzy_match.group(0) != term_name:
                        corrupted = fuzzy_match.group(0)
                        if corrupted in registered_terms or not _is_one_character_edit(term_name, corrupted):
                            continue
                        return {
                            "dimension": "terms_compliance",
                            "severity": "warning",
                            "evidence": f"檢測到疑似錯訛或擅改之專有名詞「{corrupted}」（登錄術語為「{term_name}」）",
                            "recommendation": f"請將「{corrupted}」修正為標準專有名詞「{term_name}」，嚴禁隨意變造字詞。",
                            "action_required": True,
                        }
        except Exception as exc:
            print(f"[WARN] Terms compliance check failed (novel {novel_id}): {exc}")
        return None

    @classmethod
    def _check_temporal_fact_compliance(
        cls, novel_id: str, chapter_index: int, prose_text: str
    ) -> Optional[Dict[str, Any]]:
        """檢查正文是否違反時序記憶圖譜事實（如陣亡角色復活、已破壞物品復現）。"""
        if not novel_id or not prose_text:
            return None
        try:
            facts = db.get_all_facts(novel_id)
            if not facts:
                return None
            for f in facts:
                inv_ch = f.get("invalid_from_chapter")
                stmt = f.get("fact_statement", "")
                if inv_ch is not None and chapter_index >= inv_ch and stmt:
                    m = re.search(r"([\u4e00-\u9fa5]{2,6}).*?(?:戰死|身亡|犧牲|隕落|死亡|消散|陣亡|死去|被殺|身死道消|自爆.*?身亡|斬首)", stmt)
                    if m:
                        raw_name = m.group(1)
                        # Strip trailing verbs/prepositions if captured
                        raw_name = re.sub(r"[在為於被自].*$", "", raw_name).strip()
                        cleaned_name = re.sub(r"^(?:長老|將軍|隊長|護法|掌門|殿主|教主|舵主|宗主|堂主|老祖|師尊|師父)", "", raw_name).strip()
                        faction_cleaned = re.sub(r"^.*?(?:教|宗|門|殿|閣|會|幫|府)", "", raw_name).strip()
                        candidate_names = []
                        if raw_name:
                            candidate_names.append(raw_name)
                        if cleaned_name and len(cleaned_name) >= 2 and cleaned_name not in candidate_names:
                            candidate_names.append(cleaned_name)
                        if faction_cleaned and len(faction_cleaned) >= 2 and faction_cleaned not in candidate_names:
                            candidate_names.append(faction_cleaned)
                        for cname in candidate_names:
                            if re.search(rf"{cname}.*?(?:說|道|笑|拍|走|看|拔|站|回|微|現身|出手|狂笑|獰笑|冷笑|殺出|喝道|大喊)", prose_text):
                                return {
                                    "dimension": "temporal_graph_compliance",
                                    "severity": "critical",
                                    "evidence": f"時序世界線穿幫：已於第 {inv_ch} 章戰死之角色「{cname}」在正文中再次行動或發言。",
                                    "recommendation": f"「{cname}」已於第 {inv_ch} 章陣亡，嚴禁在後續章節復活或直接參與對話。",
                                    "action_required": True,
                                }
        except Exception as exc:
            print(f"[WARN] Temporal fact compliance check failed (novel {novel_id}): {exc}")
        return None

    @classmethod
    def _check_ability_costs_and_boundaries(
        cls,
        novel_id: str,
        chapter_index: int,
        prose_text: str,
        outline: Optional[Dict[str, Any]] = None,
        candidate_conflict_sig: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """檢查高階破局與重大交鋒中是否出現零代價、輕鬆隨意秒殺等套路。"""
        sig = candidate_conflict_sig or {}
        cost = str(sig.get("cost") or "").strip().lower()
        strategy = sig.get("protagonist_strategy", "")
        pressure = sig.get("pressure_type", "")
        effortless_markers = ["輕鬆隨意", "隨手一擊", "毫髮無傷", "毫無波瀾", "隨手拍飛", "不費吹灰之力"]
        is_effortless = any(m in prose_text for m in effortless_markers)

        if (cost in ("無", "none", "零代價", "") or is_effortless) and (pressure in ("life_or_death", "high", "生死危機") or strategy in ("direct_clash", "asymmetric_wit")):
            return {
                "dimension": "ability_constraints",
                "severity": "warning",
                "evidence": "高難度生死交鋒中，主角以零代價或過度輕易的定型化方式破局（缺乏體力/資源消耗或反噬代價）。",
                "recommendation": "必須在正文中具體描寫能力代價、精神負擔或情境阻力，禁止無痛通脹破局。",
                "action_required": True,
            }
        return None

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
        except Exception as exc:
            print(f"[WARN] Ending repetition history scan failed (novel {novel_id}): {exc}")

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
        if not prose_text or chapter_index <= 1 or len(prose_text.strip()) < 300:
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
                "與此相關", "顯而易見", "無時無刻", "不由自主", "自言自語",
                "後續情節", "情節發展", "情節推進", "角色對白", "進度平穩",
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
        except Exception as exc:
            print(f"[WARN] Cross-chapter motif reuse check failed (novel {novel_id}, chapter {chapter_index}): {exc}")
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

        # 0. 拒答與免責聲明檢測 (AI Refusal & Safety Disclaimer)
        from backend.common.refusal_filter import is_refusal_or_disclaimer
        if is_refusal_or_disclaimer(prose_text):
            findings.append({
                "dimension": "voice_integrity",
                "severity": "critical",
                "evidence": "正文輸出包含 AI 助手拒答、免責聲明或安全性限制聲明語句。",
                "recommendation": "此輸出為無效拒答，禁止存入正文庫；必須清空並重新觸發章節寫作流水線。",
                "action_required": True,
            })

        # 0b. 破壁元敘事與大綱洩漏檢測 (Meta-Narrative Leakage)
        meta_finding = cls._check_meta_narrative_leak(prose_text)
        if meta_finding:
            findings.append(meta_finding)

        # 0c. 開篇套路與跨章重複檢測 (Opening Deduplication)
        opening_finding = cls._check_opening_repetition(novel_id, chapter_index, prose_text)
        if opening_finding:
            findings.append(opening_finding)

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
            except Exception as exc:
                print(f"[WARN] Failed to fetch recent voice_integrity audits (novel {novel_id}): {exc}")

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
                    except Exception as exc:
                        print(f"[WARN] Failed to fetch recent ability_constraints audits (novel {novel_id}): {exc}")

        # 維度 3b: ability_costs_and_boundaries (生死交鋒無代價與秒殺套路)
        ability_finding = cls._check_ability_costs_and_boundaries(
            novel_id, chapter_index, prose_text, outline=outline, candidate_conflict_sig=candidate_conflict_sig
        )
        if ability_finding:
            findings.append(ability_finding)

        # 維度 5: terms_compliance (術語庫規範遵守檢測)
        terms_finding = cls._check_terms_compliance(novel_id, prose_text)
        if terms_finding:
            findings.append(terms_finding)

        # 維度 6: temporal_graph_compliance (時序事實世界線穿幫檢測)
        temporal_finding = cls._check_temporal_fact_compliance(novel_id, chapter_index, prose_text)
        if temporal_finding:
            findings.append(temporal_finding)

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
        elif is_breathing_scene:
            overall_action = "NO_ACTION_REQUIRED"
        elif watch_issues:
            overall_action = "WATCH"
        else:
            overall_action = "PASS"

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

    @classmethod
    def extract_banned_hits(cls, prose_text: str) -> List[Dict[str, Any]]:
        return extract_banned_hits(prose_text)


def extract_banned_hits(prose_text: str) -> List[Dict[str, Any]]:
    """以 NarrativeAuditor 的 GESTURE_REUSE_PATTERNS、FORMULAIC_OPENING_PATTERNS（僅掃開頭 400 字）、
    FORMULAIC_ENDING_PATTERNS（僅掃結尾 400 字）掃描正文，
    回傳 [{pattern_label, matched_sentence, paragraph_index, context_20chars, matched_text}]
    """
    if not prose_text or not prose_text.strip():
        return []

    hits: List[Dict[str, Any]] = []
    paragraphs = [p.strip() for p in prose_text.splitlines() if p.strip()]

    # 1. 開篇套路（僅掃前 400 字）
    opening_text = prose_text.strip()[:400]
    for pat, key, label in NarrativeAuditor.FORMULAIC_OPENING_PATTERNS:
        for m in re.finditer(pat, opening_text):
            matched_str = m.group(0)
            p_idx = 1
            matched_sentence = matched_str
            for idx, p in enumerate(paragraphs, 1):
                if matched_str in p:
                    p_idx = idx
                    sentences = re.split(r"(?<=[。！？!?\n])", p)
                    for s in sentences:
                        if matched_str in s:
                            matched_sentence = s.strip()
                            break
                    break
            start_pos = m.start()
            context_20 = opening_text[max(0, start_pos - 20):min(len(opening_text), m.end() + 20)]
            hits.append({
                "pattern_label": f"開篇套路：{label}",
                "matched_sentence": matched_sentence,
                "paragraph_index": p_idx,
                "context_20chars": context_20,
                "matched_text": matched_str,
            })
            break

    # 2. 結尾套路（僅掃末尾 400 字）
    ending_text = prose_text.strip()[-400:]
    for pat, label in NarrativeAuditor.FORMULAIC_ENDING_PATTERNS:
        for m in re.finditer(pat, ending_text):
            matched_str = m.group(0)
            p_idx = len(paragraphs)
            matched_sentence = matched_str
            for idx in range(len(paragraphs), 0, -1):
                p = paragraphs[idx - 1]
                if matched_str in p:
                    p_idx = idx
                    sentences = re.split(r"(?<=[。！？!?\n])", p)
                    for s in sentences:
                        if matched_str in s:
                            matched_sentence = s.strip()
                            break
                    break
            start_pos = m.start()
            context_20 = ending_text[max(0, start_pos - 20):min(len(ending_text), m.end() + 20)]
            hits.append({
                "pattern_label": f"結尾套路：{label}",
                "matched_sentence": matched_sentence,
                "paragraph_index": p_idx,
                "context_20chars": context_20,
                "matched_text": matched_str,
            })
            break

    # 3. 模板動作/口癖檢測（全篇各段落掃描）
    for p_idx, p in enumerate(paragraphs, 1):
        sentences = re.split(r"(?<=[。！？!?\n])", p)
        for s in sentences:
            s_clean = s.strip()
            if not s_clean:
                continue
            for pat, label in NarrativeAuditor.GESTURE_REUSE_PATTERNS:
                for m in re.finditer(pat, s_clean):
                    matched_str = m.group(0)
                    start_pos = m.start()
                    context_20 = s_clean[max(0, start_pos - 20):min(len(s_clean), m.end() + 20)]
                    hits.append({
                        "pattern_label": label,
                        "matched_sentence": s_clean,
                        "paragraph_index": p_idx,
                        "context_20chars": context_20,
                        "matched_text": matched_str,
                    })

    return hits


def find_explicit_term_alias_hits(novel_id: str, prose_text: str) -> List[Dict[str, str]]:
    """Find only aliases explicitly marked as forbidden in the story-term registry.

    Ordinary words and unmarked synonyms are not rejected: this keeps the hard gate
    precise and lets the author distinguish a true canonical alias from a related concept.
    Notes syntax: ``禁用別稱：咒禁、禁法``. A ``forbidden_aliases`` list is also supported.
    """
    if not novel_id or not prose_text:
        return []
    try:
        terms = db.get_terms(novel_id) or []
    except Exception as exc:
        print(f"[WARN] Failed to load terms for forbidden alias check (novel {novel_id}): {exc}")
        return []
    hits = []
    marker = re.compile(r"(?:禁用別稱|禁止稱作|錯誤稱呼|禁止使用)\s*[：:]\s*([^\n。；;]+)")
    for item in terms:
        canonical = str(item.get("term") or "").strip()
        if not canonical:
            continue
        aliases = item.get("forbidden_aliases") or []
        if isinstance(aliases, str):
            aliases = re.split(r"[,，、/／|｜]", aliases)
        elif not isinstance(aliases, list):
            aliases = [aliases]
        notes = str(item.get("notes") or "")
        for declaration in marker.findall(notes):
            aliases.extend(re.split(r"[,，、/／|｜]", declaration))
        for alias in dict.fromkeys(str(value).strip() for value in aliases if value):
            if len(alias) < 2 or alias == canonical or alias not in prose_text:
                continue
            hits.append({"canonical_term": canonical, "forbidden_alias": alias})
    return hits
