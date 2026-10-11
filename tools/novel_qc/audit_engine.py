# -*- coding: utf-8 -*-
"""完本質檢：抽查引擎（純函數＋檢查器，不碰 DB 連線細節）。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------- 分層抽樣

STRATA = (
    (0.00, 0.20, "前期"),
    (0.20, 0.40, "中前期"),
    (0.40, 0.60, "中期"),
    (0.60, 0.80, "中後期"),
    (0.80, 1.00, "後期"),
)


def stratify(total: int, per_stratum: int = 4) -> Dict[str, List[int]]:
    """把 1..total 按五等分均勻抽樣，回傳 {區段名: [章號]}。"""
    out: Dict[str, List[int]] = {}
    for lo, hi, name in STRATA:
        start = max(1, int(total * lo) + 1)
        end = max(start, int(total * hi))
        span = end - start + 1
        picks = sorted({min(end, start + int(span * (i + 1) / (per_stratum + 1)))
                        for i in range(per_stratum)})
        out[name] = picks
    return out


def adjacent_pairs(total: int, n_pairs: int = 3) -> List[Tuple[int, int]]:
    """均勻挑 n 組相鄰章（交接檢查用）。"""
    step = max(2, total // (n_pairs + 1))
    pairs = []
    ch = step
    while len(pairs) < n_pairs and ch + 1 <= total:
        pairs.append((ch, ch + 1))
        ch += step
    return pairs


# ---------------------------------------------------------------- 相似度

def char_ngrams(text: str, n: int = 4) -> set:
    t = re.sub(r"\s+", "", text or "")
    if len(t) < n:
        return {t} if t else set()
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def jaccard(a: str, b: str, n: int = 4) -> float:
    sa, sb = char_ngrams(a, n), char_ngrams(b, n)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def opener_overlap(a: str, b: str, width: int = 60) -> float:
    return jaccard((a or "")[:width], (b or "")[:width])


# ---------------------------------------------------------------- 死亡 / 復活

DEATH_VERBS_STRONG = (
    "隕滅", "隕落", "身亡", "斃命", "斷氣", "伏誅",
    "灰飛煙滅", "魂飛魄散",
)
DEATH_VERBS_WEAK = (
    "死亡", "消散", "崩解", "化作", "化為", "湮滅", "消融", "融化",
    "屍體", "屍首", "遺體",  # 別人的屍體常與主角同句，須另有實錘
)
# 「將X徹底V」：將字句的病人若非本名/代指，動詞與本名無關
JIANG_PAT = re.compile(r"將(.{1,14}?)(徹底|瞬間|直接|無情地)?"
                       r"(隕滅|隕落|身亡|斃命|斷氣|伏誅|灰飛煙滅|魂飛魄散|"
                       r"死亡|消散|崩解|化作|化為|湮滅|消融|融化)")
# 化＋殘留物（化齏粉 / 化作星屑 / 化為灰燼 …）：弱動詞轉強的條件
ASH_RESIDUE = re.compile(r"化(作|為)?(星屑|晶粉|灰燼|齏粉|虛無|血霧|塵埃|飛灰|煙塵|齏|粉末)")
# 否定／假設／威脅語境：本句命中即整句作廢（寧漏勿炸）
DEATH_NEG_GUARDS = (
    "若", "如果", "假如", "倘若", "否則", "必死", "找死", "去死", "尋死",
    "死地", "死裡逃生", "瀕死", "垂死", "差點", "險些", "幾乎",
    "以為", "夢", "假裝", "幻覺",
    "死亡威脅", "死亡通牒", "死亡網格", "死亡氣息", "死亡凝視", "死亡陰影",
    "死死", "殺了他", "殺死", "置於死地", "置之死地", "要他死", "讓他死",
    "逼他死", "害死",
)
# 跨句假設（常寫在下句：「若繼續停留必然會被湮滅」）：scope 命中即作廢
DEATH_NEG_SCOPE = (
    "會被", "將被", "必然會", "若繼續", "如果繼續",
    "死裡逃生", "差點", "險些", "找死", "去死", "必死",
)
# 器物被毀≠人死：其間有這些詞、且人身未同步被毀，即跳過
POSSESSION_GUARDS = (
    "影刃", "武器", "護甲", "鎧甲", "戰甲", "陣法", "結界", "光幕",
    "護盾", "防禦", "術式", "手套", "諧振", "晶芯", "法器", "權杖",
    "斗篷", "披風", "外套", "面具", "鎧", "刃",
    "衣袖", "衣袍", "風衣", "衣角", "衣服",
    "玉佩", "吊墜", "戒指", "手環", "項鍊", "玉牌", "令牌", "配飾",
    "吊燈", "燈具",
)
# 人身同步被毀：人身詞 20 字內緊跟毀滅動詞（否則只是衣服/玉佩碎了）
PERSON_DESTRUCTION_RE = re.compile(
    r"(整個人|身軀|肉身|氣息|靈魂|頭顱).{0,20}"
    r"(化作|化為|湮滅|崩解|消融|碎裂|撕裂|吞沒|冰封|凍結|洞穿|貫穿|"
    r"絞碎|碾碎|汽化|蒸發|隕滅|死亡)")
PERSON_DESTRUCTION = ("整個人", "身軀", "肉身", "氣息", "靈魂", "頭顱")
# 定論級死亡修飾（出現即高置信）
DEFINITIVE_MARKERS = (
    "身軀與靈魂", "肉身與魔力根基", "肉身及其所有", "肉身及",
    "氣息徹底消散", "連一絲殘渣", "徹底湮滅", "化作無數",
)
ACTION_VERBS = (
    "說", "道", "笑", "喝", "吼", "問", "拍", "走", "看", "拔", "站",
    "現身", "出手", "催動", "舉起", "掃視", "下令", "轉身", "點頭", "冷哼",
)
# 大死亡實錘（殘留物／定論修飾；虛無/血霧除外：常見於場景與賣力描寫）
BIG_DEATH_CUES = (
    "星屑", "晶粉", "灰燼", "齏粉", "飛灰",
    "身軀與靈魂", "肉身", "氣息徹底消散", "連一絲",
    "徹底湮滅", "灰飛煙滅", "魂飛魄散",
)
# 投影/化身類死亡不算本體死亡（須緊貼人名：A的分身/投影…）
PROJECTION_RE = re.compile(r".{0,6}的?(投影|分身|光影|化身|影像|虛影)")
# 主語代指：死亡動詞與人名之間須有其一（否則多半是別人的死）
SUBJECT_PRONOUNS = ("其", "他", "她", "自己", "整個人", "整個", "本體", "肉身",
                    "這位", "此人", "該人", "那人")
# 目擊者：看著別人死不算自己死
WITNESS_GUARDS = ("看著", "看著", "望著", "目睹", "見證", "盯著", "注視", "瞧著")
# 強復活標記（gap 全程有效）vs 弱標記（只在復出場當章±1 有效）
RESURRECT_STRONG = ("復活", "重生", "奪舍", "還活", "死而復生", "捲土重來",
                    "歸來", "復出")
RESURRECT_WEAK = ("分身", "化身", "殘魂", "元神", "替身", "假死",
                  "原來是", "不過是")

_SENT_SPLIT = re.compile(r"[。！？\n]+")

# 常見非人物名詞黑名單（避免把地名/招式/雜兵/泛稱職位當人物追生死）
_NON_NAME_TAILS = ("學院", "氏族", "大陸", "帝國", "禁域", "圓環", "樞紐", "神殿",
                   "生物", "界獸", "幼獸", "死士", "私兵", "守衛", "傀儡", "艦隊",
                   "首領", "主人", "大人", "將軍", "隊長", "局長", "導師", "教授",
                   "老祖", "族長", "總裁", "女皇", "陛下", "祭司", "元帥", "城主",
                   "盟主", "掌門", "長老", "執事")


def split_sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text or "") if s.strip()]


def _verb_hits(text: str):
    """Yield (start, end, is_strong) for death expressions in text."""
    for v in DEATH_VERBS_STRONG:
        for m in re.finditer(re.escape(v), text):
            yield (m.start(), m.end(), True)
    for m in ASH_RESIDUE.finditer(text):
        yield (m.start(), m.end(), True)
    for v in DEATH_VERBS_WEAK:
        for m in re.finditer(re.escape(v), text):
            yield (m.start(), m.end(), False)


def _death_hit_in_scope(name: str, sent: str, window: int = 80) -> Optional[str]:
    return None  # 保留舊名義；實作改走 _death_hit_in_sentences（跨句＋主語判定）


def _death_hit_in_sentences(name: str, sents: List[str], idx: int,
                            others: List[str], max_dist: int = 40) -> Optional[str]:
    """第 idx 句含 name；scope 擴及下一句（處理『A重傷。她化作灰燼』式跨句）。

    命中條件（寧嚴勿寬）：
    - 死亡動詞距 name ≤max_dist，其間無其他人名；
    - 主語成立：相鄰（≤8字，如「A的隕滅」）或其間有代指（其/他/整個人…）；
    - 其＋弱動詞（消散/崩解/單獨化作）不算，須另有大實錘；
    - 「A的分身/投影/光影」類死亡直接排除。
    """
    if any(g in sents[idx] for g in DEATH_NEG_GUARDS):
        return None
    tail = "".join(" " + s for s in sents[idx + 1:idx + 3])
    scope = sents[idx] + tail
    base_len = len(sents[idx])
    if any(g in scope for g in DEATH_NEG_SCOPE):
        # 跨句假設語境：「若繼續停留必然會被湮滅」不算真死
        return None
    if re.search(re.escape(name) + r".{0,6}?(投影|分身|光影|化身|影像|虛影)", sents[idx]):
        # 「A的分身/投影…」之死不算本體死亡
        return None
    for npos in [m.start() for m in re.finditer(re.escape(name), sents[idx])]:
        for vs, ve, strong in _verb_hits(scope):
            if ve <= npos:
                dist, between = npos - ve, scope[ve:npos]
            elif vs >= npos + len(name):
                dist, between = vs - (npos + len(name)), scope[npos + len(name):vs]
            else:
                dist, between = 0, ""
            if dist > 140:
                continue
            if any(o in between for o in others if o != name):
                continue
            verb_idx = idx
            if not (ve <= base_len):
                # 動詞落在下兩句中的哪一句：實錘只認該句
                acc = base_len
                for k in (idx + 1, idx + 2):
                    if k >= len(sents):
                        break
                    acc += 1 + len(sents[k])
                    if ve < acc:
                        verb_idx = k
                        break
            verb_sent = sents[verb_idx]
            # 實錘必須與動詞同句（人名句裡「別人的齏粉」不算；動詞在人名句則認該句）
            cue_scope = sents[idx] if verb_idx == idx else verb_sent
            quote = (sents[idx] if verb_sent == sents[idx]
                     else sents[idx] + "｜" + verb_sent)
            person_scope = sents[idx] + " " + verb_sent
            # 「將X徹底V」病人排除：病人非本名/代指即與本名無關
            jm = JIANG_PAT.search(verb_sent)
            if jm and name not in jm.group(0) and not any(
                    p in jm.group(0) for p in SUBJECT_PRONOUNS):
                continue
            if (any(p in between for p in POSSESSION_GUARDS)
                    and not PERSON_DESTRUCTION_RE.search(person_scope)):
                continue
            adjacent = dist <= 8
            has_subj = adjacent or any(p in between for p in SUBJECT_PRONOUNS)
            if not has_subj:
                continue
            if any(w in between for w in WITNESS_GUARDS):
                continue  # 看著別人死不算自己死
            # 實錘必須和動詞同句（人名句裡的別人家齏粉不算）
            cue = any(c in cue_scope for c in BIG_DEATH_CUES)
            if dist > max_dist and not (
                    dist <= 140 and any(p in between for p in SUBJECT_PRONOUNS) and cue):
                # 長鏈（名→她→晶粉式跨句）須同時有代指＋大實錘
                continue
            if strong and (adjacent or cue):
                return ("strong", quote[:200])
            if not strong and cue and any(p in between for p in SUBJECT_PRONOUNS):
                return ("strong", quote[:200])
    return None


def find_death_sentences(name: str, text: str, window: int = 80,
                         others: Optional[List[str]] = None) -> List[str]:
    """找出 name 的死亡句（主語判定＋跨句＋投影排除，寧嚴勿寬）。"""
    sents = split_sentences(text)
    others = others or []
    hits: List[str] = []
    for i, sent in enumerate(sents):
        if name not in sent:
            continue
        r = _death_hit_in_sentences(name, sents, i, others)
        if r and r[1] not in hits:
            hits.append(r[1])
    return hits


def find_death_sentences_loose(name: str, text: str) -> List[str]:
    """寬鬆版（僅供蒸發排除用）：人名＋死亡詞同句即算。"""
    hits = []
    pats = DEATH_VERBS_STRONG + DEATH_VERBS_WEAK
    for sent in split_sentences(text):
        if name in sent and any(v in sent for v in pats):
            hits.append(sent[:140])
    return hits


def is_definitive(death_quotes: List[str]) -> bool:
    blob = "\n".join(death_quotes)
    return bool(ASH_RESIDUE.search(blob)) or any(m in blob for m in DEFINITIVE_MARKERS)


def chapter_shows_alive(name: str, text: str) -> bool:
    """人物存活證據（三檔，任一即算）：同句動作動詞／相鄰對話／全章≥3次提及。"""
    sents = split_sentences(text)
    mentions = 0
    for i, sent in enumerate(sents):
        if name not in sent:
            continue
        mentions += sent.count(name)
        if any(v in sent for v in ACTION_VERBS):
            return True
        near = "".join(sents[max(0, i - 1):i + 2])
        if "「" in near or "“" in near or "：" in sent:
            return True
    return mentions >= 3


def find_action_sentences(name: str, text: str, limit: int = 3) -> List[str]:
    out = []
    for sent in split_sentences(text):
        idx = sent.find(name)
        if idx < 0:
            continue
        after = sent[idx + len(name):idx + len(name) + 12]
        if any(v in after for v in ACTION_VERBS):
            out.append(sent[:140])
            if len(out) >= limit:
                break
    return out


def has_resurrection_note(texts: List[str], name: str = "",
                          alive_chapter: Optional[int] = None,
                          chapters_of_texts: Optional[List[int]] = None) -> Optional[str]:
    """復活交代須指名道姓（標記句含本名，或代指句前後 60 字有本名）。

    強標記（復活/重生/歸來…）在 gap 全程有效；弱標記（分身/原來是…）
    只在復出場當章 ±1 章有效，避免路人一句『分身』銷掉真案。
    """
    for k, t in enumerate(texts):
        ch = chapters_of_texts[k] if chapters_of_texts else None
        for i, sent in enumerate(split_sentences(t)):
            strong = any(m in sent for m in RESURRECT_STRONG)
            weak = any(m in sent for m in RESURRECT_WEAK)
            if not (strong or weak):
                continue
            named = bool(name) and name in sent
            if not named and name:
                near = "".join(split_sentences(t)[max(0, i - 1):i + 2])
                if not (name in near and (any(p in sent for p in ("他", "她", "其", "自己"))
                                          or len(sent) <= 12)):
                    continue
            elif not name:
                pass
            if strong:
                return sent[:140]
            # 弱標記：只認復出場當章附近
            if alive_chapter is not None and ch is not None and abs(ch - alive_chapter) <= 1:
                return sent[:140]
            if alive_chapter is None:
                return sent[:140]
    return None


@dataclass
class DeathFinding:
    name: str
    death_chapters: List[int]
    death_quotes: Dict[int, List[str]]
    alive_after: List[int]
    resurrection_note: Optional[str] = None

    @property
    def definitive(self) -> bool:
        return any(is_definitive(q) for q in self.death_quotes.values())


def check_death_resurrection(
    chapters: List[Dict[str, Any]],
    names: List[str],
    resurrection_lookback: int = 3,
) -> List[DeathFinding]:
    """生死一致性：死亡後無交代再度行動即嫌疑。

    chapters: [{chapter_index, content}]（最新版本）。
    names: 候選人名（建議來自 temporal_entities）。
    """
    texts = {c["chapter_index"]: c.get("content") or "" for c in chapters}
    order = sorted(texts)
    findings: List[DeathFinding] = []
    for name in names:
        if any(name.endswith(t) for t in _NON_NAME_TAILS):
            continue
        deaths: Dict[int, List[str]] = {}
        for ch in order:
            qs = find_death_sentences(name, texts[ch], others=names)
            if qs:
                deaths[ch] = qs
        if not deaths:
            continue
        first_death = min(deaths)
        alive_after: List[int] = []
        for ch in order:
            if ch <= first_death:
                continue
            if chapter_shows_alive(name, texts[ch]):
                alive_after.append(ch)
        if not alive_after:
            continue
        # 在死亡章與復出場之間找復活交代
        gap_idx = [c for c in order if first_death < c <= alive_after[0]][-resurrection_lookback:]
        gap_texts = [texts[c] for c in gap_idx]
        note = has_resurrection_note(gap_texts + [texts[alive_after[0]]], name,
                                     alive_after[0], gap_idx + [alive_after[0]])
        if note:
            continue  # 有交代，不算缺陷
        findings.append(DeathFinding(
            name=name,
            death_chapters=sorted(deaths),
            death_quotes=deaths,
            alive_after=alive_after,
            resurrection_note=None,
        ))
    return findings


# ---------------------------------------------------------------- 日期單調

_FLASHBACK_MARKERS = ("回憶", "憶起", "當年", "三年前", "多年前", "夢境", "前世",
                      "傳聞", "據說", "史載", "倒敘", "時間回到",
                      "昨日", "前夜", "當晚", "那晚", "上個月", "回想")

_DATE_RES = (
    re.compile(r"魔法歷(\d+)年(\d+)月(\d+)日"),
    re.compile(r"新紀元(\d+)年(\d+)月"),
    re.compile(r"(?<!\d)(\d{1,2})月(\d{1,2})日"),
)


def extract_date_anchor(text: str) -> Optional[Tuple[int, ...]]:
    """抽章節首 400 字的第一個日期錨點；無則 None。"""
    head = (text or "")[:400]
    m = _DATE_RES[0].search(head)
    if m:
        return (0, int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _DATE_RES[1].search(head)
    if m:
        return (1, int(m.group(1)), int(m.group(2)), 0)
    m = _DATE_RES[2].search(head)
    if m:
        return (2, int(m.group(1)), int(m.group(2)))
    return None


def has_flashback_marker(text: str) -> bool:
    head = (text or "")[:600]
    return any(m in head for m in _FLASHBACK_MARKERS)


@dataclass
class DateFinding:
    chapter: int
    prev_chapter: int
    prev_anchor: Tuple[int, ...]
    anchor: Tuple[int, ...]
    flashback_hint: bool = False


def check_date_monotonicity(chapters: List[Dict[str, Any]]) -> List[DateFinding]:
    out: List[DateFinding] = []
    last: Optional[Tuple[int, Tuple[int, ...]]] = None  # (chapter, anchor)
    for c in sorted(chapters, key=lambda x: x["chapter_index"]):
        anchor = extract_date_anchor(c.get("content") or "")
        if anchor is None:
            continue
        if last is not None and anchor[0] == last[1][0] and anchor < last[1]:
            # 只比同紀年體系；裸月日 vs 年號錨點不可比，直接跳過
            out.append(DateFinding(
                chapter=c["chapter_index"],
                prev_chapter=last[0],
                prev_anchor=last[1],
                anchor=anchor,
                flashback_hint=has_flashback_marker(c.get("content") or ""),
            ))
        if last is None or anchor[0] != last[1][0] or anchor >= last[1]:
            last = (c["chapter_index"], anchor)
        # 倒流後仍以前值為準，避免連鎖誤報
    return out


# ---------------------------------------------------------------- 開頭模板

def check_opener_templates(
    chapters: List[Dict[str, Any]],
    markers: Optional[List[str]] = None,
    width: int = 60,
) -> Dict[str, Any]:
    markers = markers or ["魔力感應塔", "感應塔", "空氣中瀰漫", "空氣中彌漫", "夜色"]
    total = len(chapters)
    hits: Dict[str, List[int]] = {m: [] for m in markers}
    for c in chapters:
        head = (c.get("content") or "")[:width]
        for m in markers:
            if m in head:
                hits[m].append(c["chapter_index"])
    # 最常見的開頭 12 字前綴（通用模板探測）
    from collections import Counter
    prefixes = Counter((c.get("content") or "")[:12] for c in chapters)
    return {
        "total": total,
        "markers": {m: {"count": len(v), "ratio": (len(v) / total if total else 0),
                        "sample": v[:8]} for m, v in hits.items()},
        "top_prefixes": [{"prefix": p, "count": n} for p, n in prefixes.most_common(8)],
    }


# ---------------------------------------------------------------- 相鄰重複

def check_adjacent_duplication(
    chapters: List[Dict[str, Any]],
    sim_threshold: float = 0.50,
    opener_threshold: float = 0.50,
) -> List[Dict[str, Any]]:
    out = []
    by_ch = {c["chapter_index"]: c.get("content") or "" for c in chapters}
    order = sorted(by_ch)
    for prev, cur in zip(order, order[1:]):
        if cur != prev + 1:
            continue  # 只查真正相鄰
        sim = jaccard(by_ch[prev], by_ch[cur])
        op = opener_overlap(by_ch[prev], by_ch[cur])
        if sim >= sim_threshold or op >= opener_threshold:
            out.append({"prev": prev, "cur": cur,
                        "jaccard": round(sim, 3),
                        "opener_overlap": round(op, 3)})
    return out


# ---------------------------------------------------------------- 提要健康

def first_sentence(text: str) -> str:
    parts = split_sentences(text or "")
    return parts[0] if parts else ""


def last_sentence(text: str) -> str:
    parts = split_sentences(text or "")
    return parts[-1] if parts else ""


def check_synopsis_health(chapters: List[Dict[str, Any]]) -> Dict[str, Any]:
    """提要若只是首句+尾句拼接，視為無資訊價值。"""
    bad, empty = [], []
    for c in chapters:
        syn = (c.get("synopsis") or "").strip()
        if not syn:
            empty.append(c["chapter_index"])
            continue
        content = c.get("content") or ""
        if first_sentence(content) in syn and last_sentence(content) in syn \
                and len(syn) < 400:
            bad.append(c["chapter_index"])
    total = len(chapters)
    return {"total": total, "stitched": bad[:20], "stitched_count": len(bad),
            "stitched_ratio": (len(bad) / total if total else 0),
            "empty": empty[:20], "empty_count": len(empty)}
