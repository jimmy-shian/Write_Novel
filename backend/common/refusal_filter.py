# -*- coding: utf-8 -*-
"""
Central Refusal and Safety Disclaimer Filter Utility.
Detects and intercepts AI assistant refusal responses, safety disclaimers,
and guideline violations across Traditional Chinese, Simplified Chinese, and English,
while strictly preserving legitimate creative writing (e.g. sci-fi AI character dialogue).
"""

import re
from typing import Optional, List, Tuple


class RefusalContaminationError(ValueError):
    """Raised when text contaminated with AI refusal or safety disclaimers attempts to enter persistence."""
    pass


# 1. Chinese AI Persona combined with refusal/inability/policy constraints
# (Requires BOTH AI self-identification AND refusal/inability/constraint token to avoid false positives on sci-fi characters)
_ZH_AI_PERSONA_REFUSAL_PATTERNS = [
    # 我是AI / 我是語言模型 / 我只是個語言模型 / 我是文字型 AI ... 無法 / 不能 / 幫不上忙 / 超出能力
    r"(?:我是|我只?是(?:一個|一个|個|个)?|作為|作为|身為|身为)(?:一個|一个|個|个)?(?:AI|文字型\s*AI|人工智能|人工智慧|語言模型|语言模型|大型語言模型|大型语言模型|AI模型|AI助手|智能助手|虛擬助手|虚拟助手|助手|程式|程序)[\s，,。；;]*.*?(?:無法|无法|不能|没办法|沒辦法|不具備|不具备|難以|难以|不便|不可|不得|拒絕|拒绝|幫不上忙|帮不上忙|超出|必須遵守|必须遵守|需要遵守|受限於|受限于|安全規範|安全规范|安全政策|使用條款)",
    # 作為一個AI助手，我無法為您... / 我幫不上忙，因為我只是個語言模型
    r"(?:作為|作为|身為|身为)(?:一個|一个|個|个)?(?:AI|人工智能|人工智慧|語言模型|语言模型|AI助手|AI模型|智能助手)[\s，,。]*.*?(?:無法為您|无法为你|無法協助|无法协助|無法幫忙|无法帮忙|無法提供|无法提供|無法撰寫|无法撰写|無法創作|无法创作|無法生成|无法生成|不能為您|不能为你|不能協助|不能协助|不能撰寫|不能创作|無法滿足|无法满足|拒絕|拒绝|幫不上忙|帮不上忙)",
    # 我幫不上忙 / 無法幫忙，因為我只是...
    r"(?:我)?(?:幫不上忙|帮不上忙|無法幫忙|无法帮忙)[\s，,。]*.*?(?:因為|因为)?(?:我只?是|我是)?(?:一個|一个|個|个)?(?:AI|語言模型|语言模型|文字型)",
    # 我的程式設計裡沒有這樣的功能
    r"(?:我的)?(?:程式設計|程序设计|系統設計)[\s\S]{0,15}(?:沒有|没有|不包含)[\s\S]{0,15}(?:功能|能力)",
]

# 2. Chinese Inability and Refusal Expressions
_ZH_INABILITY_REFUSAL_PATTERNS = [
    # 抱歉 / 對不起 ... 我無法 / 不能為您...
    r"(?:很抱歉|非常抱歉|抱歉|對不起|对不起)[\s，,。！!]*.*?(?:我)?(?:無法|无法|不能|沒辦法|没办法)(?:為您|为你|協助|协助|幫忙|帮忙|提供|滿足|满足|撰寫|创作|創作|生成|回答|進行|进行)",
    # 我無法幫忙 / 我無法協助 / 無法為您創作
    r"(?:我)?(?:無法|无法|不能|沒辦法|没办法)(?:為您|为你|協助|协助|幫您|帮您|幫忙|帮忙)[\s，,。]*(?:撰寫|創作|创作|生成|提供|完成|描寫|描写|回答|續寫|续写|展開|展开)",
    # 無法/不能 + 此類/這類 + 內容/請求/章節
    r"(?:無法|无法|不能|沒辦法|没办法)(?:撰寫|創作|创作|生成|提供|完成|描寫|描写|回答|續寫|续写|展開|展开)(?:此類|此类|這類|这类|該類|该类|相關|相关)?(?:內容|内容|章節|章节|情節|情节|文字|請求|请求|話題|话题)",
    # 單獨明確的拒答開頭
    r"^(?:很抱歉|抱歉|非常抱歉|對不起|对不起)[，, ]*(?:我)?(?:無法|无法|不能|沒辦法|没办法|無法幫忙|无法帮忙)[。！!？?]?$",
    r"^(?:我是AI|作为AI模型|作為AI模型)[，, ]*(?:無法幫忙|无法帮忙|無法提供|无法提供)[。！!？?]?$",
    # 超出能力/職責/安全範圍 / 超出我的能力
    r"(?:已經|已经|已)?超出(?:了)?(?:我|AI)的?(?:能力|職責|职责|安全)?(?:範圍|范围)?",
    # 這個要求已經超出我的能力，我只能生成文字
    r"(?:這(?:個)?|此|该)(?:要求|請求|任務|内容)?(?:已經|已经)?超出(?:了我|我)?的?能力",
]

# 3. Chinese Safety, Ethical & Policy Disclaimers
_ZH_POLICY_DISCLAIMER_PATTERNS = [
    # 遵守/違反 安全規範、使用政策、倫理準則 + 無法/不能/超出
    r"(?:遵守|符合|基於|基于|觸及|触及|違反|违反|依據|依据|受限於|受限于)(?:相關|相关)?(?:安全規範|安全规范|安全準則|安全准则|使用政策|內容政策|内容政策|倫理準則|伦理准则|法律法規|法律法规|安全政策|社群守則|社群守则|道德標準|道德标准).*?(?:無法|无法|不能|拒絕|拒绝|超出|不能提供|不便提供|建議您更換|请提供其他|無法為您|无法为你|無法協助|无法协助|無法生成|无法生成)",
    # 涉及暴力/色情/敏感內容無法提供
    r"(?:涉及|包含|存在)(?:違法|违法|暴力|色情|血腥|敏感|不當|不合适|侵權|侵权)(?:內容|情节|情節|詞彙|词汇)?.*?(?:無法|无法|不能|拒絕|拒绝)",
    # 無法滿足包含敏感/暴力等請求
    r"無法滿足(?:您)?(?:包含|涉及)?(?:敏感|暴力|不當|違規|违规)的請求",
    # 建議更換主題 / 轉向引導
    r"(?:請提供其他|建议您更換|建議您更換|請嘗試提供其他)(?:合規|合適|正常)?的(?:寫作|創作|故事)?主題",
    r"如果你有其他不涉及.*?的(?:問題|需求|主題)",
    r"如果您有其他不涉及.*?的(?:問題|需求|主題)",
]

# 4. English Refusal & Disclaimer Patterns
_EN_REFUSAL_PATTERNS = [
    # As an AI language model...
    r"(?:as an?|i am an?|i'm an?)\s+(?:(?:large\s+)?language\s+model|ai\b|artificial\s+intelligence|virtual\s+assistant).*?(?:cannot|can't|unable|must\s+follow|adhere\s+to|programmed\s+to|not\s+allowed)",
    # I cannot fulfill/assist with this request...
    r"(?:i\s+cannot|i\s+can't|i\s+am\s+unable\s+to|i'm\s+unable\s+to)\s+(?:fulfill|assist\s+with|generate|write|create|proceed\s+with|help\s+with|comply\s+with)\s+(?:this|the|your)?\s*(?:request|prompt|story|content|chapter|task)",
    # I apologize, but I cannot...
    r"(?:i\s+apologize|i'm\s+sorry|sorry),\s*(?:but\s+)?i\s+(?:cannot|can't|am\s+unable\s+to|must\s+decline)",
    # Against / violates safety guidelines / content policies...
    r"(?:against|violates?|breaches?|in\s+violation\s+of)\s+(?:my|our|openai'?s|anthropic'?s|google'?s)?\s*(?:safety\s+guidelines|content\s+policies|content\s+policy|usage\s+policies|usage\s+policy|terms\s+of\s+service|community\s+guidelines|ethical\s+guidelines)",
    # Designed to be a helpful and harmless assistant
    r"designed\s+to\s+be\s+a\s+helpful\s+and\s+harmless\s+ai",
    r"as\s+a\s+responsible\s+ai",
    r"i\s+must\s+refuse\s+to\s+(?:generate|write|assist)",
]

# Precompile all regex patterns
_COMPILED_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("zh_ai_persona_refusal", re.compile(p, re.IGNORECASE | re.DOTALL))
    for p in _ZH_AI_PERSONA_REFUSAL_PATTERNS
] + [
    ("zh_inability_refusal", re.compile(p, re.IGNORECASE | re.DOTALL))
    for p in _ZH_INABILITY_REFUSAL_PATTERNS
] + [
    ("zh_policy_disclaimer", re.compile(p, re.IGNORECASE | re.DOTALL))
    for p in _ZH_POLICY_DISCLAIMER_PATTERNS
] + [
    ("en_refusal", re.compile(p, re.IGNORECASE | re.DOTALL))
    for p in _EN_REFUSAL_PATTERNS
]


def get_refusal_pattern_match(text: str) -> Optional[str]:
    """
    Inspects text for AI refusal or safety disclaimer patterns.
    Returns pattern name and snippet if matched, otherwise None.
    """
    if not text or not isinstance(text, str):
        return None
    cleaned = text.strip()
    if not cleaned:
        return None

    # We search the head (up to 2000 chars) as refusals typically occur at the start,
    # and also search the whole text if under 5000 chars.
    search_target = cleaned[:2000]

    for name, pattern in _COMPILED_PATTERNS:
        match = pattern.search(search_target)
        if match:
            matched_span = match.group(0)[:80]
            return f"[{name}] {matched_span}"

    # If the text is short (< 500 chars), also check if full text matches
    if len(cleaned) < 500:
        for name, pattern in _COMPILED_PATTERNS:
            match = pattern.search(cleaned)
            if match:
                matched_span = match.group(0)[:80]
                return f"[{name}] {matched_span}"

    return None


def is_refusal_or_disclaimer(text: str) -> bool:
    """
    Returns True if the text contains AI assistant refusal or safety disclaimer patterns,
    False otherwise.
    Safely ignores character dialogue in fiction unless paired with assistant refusal tokens.
    """
    return get_refusal_pattern_match(text) is not None


def assert_not_refusal(text: str, context_desc: str = "") -> None:
    """
    Asserts that the text does NOT contain any AI refusal or disclaimer patterns.
    Raises RefusalContaminationError if a pattern is matched.
    """
    match_info = get_refusal_pattern_match(text)
    if match_info:
        prefix = f"[{context_desc}] " if context_desc else ""
        sample = text.strip()[:100].replace("\n", " ")
        raise RefusalContaminationError(
            f"{prefix}Refusal or safety disclaimer detected ({match_info}): '{sample}...'"
        )


def sanitize_meta_narrative(text: str) -> str:
    """
    Removes only a redundant leading bridge clause without deleting narrative content.
    E.g. '承接上一章情節，李斯特拔出了長劍。' -> '李斯特拔出了長劍。'
    Remaining meta narration and outline tags are handled by find_meta_narrative_leaks
    as a hard validation failure so sanitization cannot silently erase story events.
    """
    if not text or not isinstance(text, str):
        return text or ""
    result = text
    # Strip leading meta bridge clauses
    result = re.sub(
        r"^(?:承接|延續|接續|正如|根據|如)?(?:上一章|前一章|上回|上一回|前文|上文)(?:的)?(?:結尾|情節|內容|所述|發生的事)?[，,：:\s]*",
        "",
        result.strip()
    )
    # Strip explicit outline bridges even when the model adds a short introductory clause.
    result = re.sub(
        r"^(?:接下來(?:我們)?(?:將|要)?|本章(?:將要|接下來)?)[，,：:\s]*",
        "",
        result,
    )
    return result.strip()


_META_NARRATIVE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:正如|如同|如|根據|承接|延續|接續)(?:在)?(?:上一章|前一章|上回|上一回|前文|上文)",
        r"(?:接上[文回]|承上|(?<![\u3400-\u9fff])續前(?![\u3400-\u9fff])|在(?:下一章|後一章|上一章|前一章)(?:中|裡|內)?)",
        r"(?:下一章|後一章)(?:將(?:要)?|接下來(?:會|將)?)(?:描寫|講述|發生|交代)",
        r"(?:上一章|前一章|上回|上一回)(?:的)?(?:結尾|情節|內容|所述|發生的事)",
        r"(?:如前所述|正如前面(?:所)?(?:說|提到|描述)|上回說到|先前提到|前文提到|上文提及)",
        r"(?:正如|如同|如)第\s*\d+\s*章(?:中|所)?(?:描述|提及|寫道|所述)",
        r"在第\s*\d+\s*章(?:中|裡|內)",
        r"讀者(?:可能)?(?:還)?記得",
        r"(?:本章|接下來)(?:將要|我們將|即將)\s*(?:描寫|講述|呈現)",
        r"(?:藉此|以此|用以)[^。！？\n]{0,40}(?:凸顯|呈現|展現|強化|營造|烘托)",
        r"【(?:場景目標|核心阻礙|轉折點|推進拍點|本章任務|視角人物|知情邊界|實質狀態位移)】",
    )
)


def find_meta_narrative_leaks(text: str) -> List[str]:
    """Return explicit chapter/reader/outline meta-narrative spans in prose."""
    if not text or not isinstance(text, str):
        return []
    hits = []
    in_world_reference = re.compile(
        r"(?:古籍|經卷|典籍|書籍|古冊|殘卷|書卷|卷軸|秘笈|魔導書|書中|冊中|筆記)的?(?:第\s*\d+\s*章|上一章|前一章|上一節|前文)"
    )
    for pattern in _META_NARRATIVE_PATTERNS:
        for match in pattern.finditer(text):
            surrounding = text[max(0, match.start() - 30):min(len(text), match.end() + 30)]
            if in_world_reference.search(surrounding):
                continue
            hits.append(match.group(0))
            break
    return hits
