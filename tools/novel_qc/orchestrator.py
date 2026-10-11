# -*- coding: utf-8 -*-
"""完本質檢編排：抽查 → 全書掃描 → 合併整理 → 總結输出。"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from .audit_engine import (
    adjacent_pairs,
    check_adjacent_duplication,
    check_date_monotonicity,
    check_death_resurrection,
    check_opener_templates,
    check_synopsis_health,
    stratify,
)
from .context_pack import (
    build_context_for_editor,
    death_finding_to_dict,
    make_finding,
    merge_pack,
    render_report,
)

PERSON_TYPES = {"person", "character", "人物", "角色", "protagonist", "antagonist"}


def person_names(entities: List[Dict[str, Any]],
                 extra_watch: List[str]) -> List[str]:
    base = [e["name"] for e in entities
            if (e.get("entity_type") or "").lower() in PERSON_TYPES
            and e.get("name") and 1 < len(e["name"]) <= 6]
    # 實體名之間做子串去重，但使用者點名的 --watch 永不丟棄
    watch = [w for w in extra_watch if w]
    base = [n for n in base
            if not any(n != m and n in m for m in base)]
    names = base + [w for w in watch if w not in base]
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out[:80]


def rare_entity_present(name: str, payoff: str,
                        texts: Dict[int, str], max_df: int = 12) -> bool:
    """罕見詞在場：名字/約定兌現中的 3 字窗若只在少數章出現，視為改寫存活。

    （專利局這種通用詞不算數；酒精燈/苔蘚/測量筆這種稀有實物算數。）
    """
    units = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{2,}", name or "")
    units += re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{2,}", payoff or "")
    for u in units:
        for i in range(0, len(u) - 2, 3):
            w = u[i:i + 3]
            df = sum(1 for t in texts.values() if w in t)
            if 1 <= df <= max_df:
                return True
    return False


def seed_hit_in_text(name: str, text: str) -> bool:
    """命中規則：全名命中，或編號命中，或≥2個中文語義塊同時命中。

    （避免「專利」等2字碎片造成的大量假命中。）
    """
    if name and name in text:
        return True
    serials = re.findall(r"[A-Za-z0-9]{2,}", name)
    if any(s in text for s in serials):
        return True
    runs = re.findall(r"[\u4e00-\u9fff]{2,}", name)
    if len(runs) >= 2 and sum(1 for r in runs if r in text) >= 2:
        return True
    return False


def run_audit(novel_id: str, title: str,
              chapters: List[Dict[str, Any]],
              entities: List[Dict[str, Any]],
              seeds: List[Dict[str, str]],
              audit_stats: Dict[str, Any],
              sample_per_stratum: int = 4,
              extra_watch: List[str] | None = None) -> Dict[str, Any]:
    extra_watch = extra_watch or []
    total = len(chapters)
    texts = {c["chapter_index"]: c.get("content") or "" for c in chapters}
    fulltext = "\n".join(texts.values())

    # ---- 一、抽查（分層＋相鄰組；供人/模型複核，自動檢查仍跑全書）
    sample = {"strata": stratify(total, sample_per_stratum),
              "pairs": adjacent_pairs(total),
              "note": "自動檢查覆蓋全書；抽樣章供人工複核與模型深讀"}

    findings: List[Dict[str, Any]] = []
    fid = [0]

    def nxt(prefix: str) -> str:
        fid[0] += 1
        return f"{prefix}-{fid[0]:02d}"

    # ---- 二、生死一致性（含重名合併：塞拉菲娜/塞拉菲娜·梵併入短名）
    names = person_names(entities, extra_watch)
    raw_deaths = check_death_resurrection(chapters, names)
    merged: Dict[str, Any] = {}
    for df in raw_deaths:
        host = next((k for k in merged if df.name in k or k in df.name), None)
        if host is None:
            merged[df.name] = df
            continue
        # 併入短名（塞拉菲娜·梵 → 塞拉菲娜）
        keep = host if len(host) <= len(df.name) else df.name
        if keep == host:
            src = df
        else:
            src = merged.pop(host)
            merged[df.name] = df
        base = merged[keep]
        base.death_chapters = sorted(set(base.death_chapters) | set(src.death_chapters))
        base.alive_after = sorted(set(base.alive_after) | set(src.alive_after))
        for ch, qs in src.death_quotes.items():
            base.death_quotes.setdefault(ch, [])
            for q in qs:
                if q not in base.death_quotes[ch]:
                    base.death_quotes[ch].append(q)
    for df in merged.values():
        d = death_finding_to_dict(df, nxt("DEATH"))
        d["editor_context"] = build_context_for_editor(d, texts)
        findings.append(d)

    # ---- 三、日期單調
    for dd in check_date_monotonicity(chapters):
        sev = "minor" if dd.flashback_hint else "major"
        f = make_finding(
            nxt("DATE"), "date_backflow", sev,
            f"第 {dd.chapter} 章時間倒流（前值第 {dd.prev_chapter} 章）",
            [dd.prev_chapter, dd.chapter],
            [{"chapter": str(dd.prev_chapter), "quote": f"錨點 {dd.prev_anchor}"},
             {"chapter": str(dd.chapter),
              "quote": f"錨點 {dd.anchor}（{'疑似倒敘但無標示' if not dd.flashback_hint else '有閃回詞，需人工確認'})"}],
            "後章日期早於前章，且無倒敘標示，屬時間線錯序。",
            "統一時間軸；如為倒敘須加明確標示（時間回到／倒敘）。")
        f["editor_context"] = build_context_for_editor(f, texts)
        findings.append(f)

    # ---- 四、相鄰重複
    for dup in check_adjacent_duplication(chapters):
        f = make_finding(
            nxt("DUP"), "adjacent_duplication", "major",
            f"第 {dup['prev']}→{dup['cur']} 章高度重複",
            [dup["prev"], dup["cur"]],
            [{"chapter": str(dup["cur"]),
              "quote": f"全文 Jaccard={dup['jaccard']}，開篇重合={dup['opener_overlap']}（閾值 0.5）"}],
            "相鄰章大面積複述，疑似重寫追加而非覆蓋，或同一事件寫兩遍。",
            "後章刪前情複述只留新資訊；或併章。")
        f["editor_context"] = build_context_for_editor(f, texts)
        findings.append(f)

    # ---- 五、人物蒸發（有名有姓＋中期前登場＋後期長期缺席＋無死亡）
    from .audit_engine import find_death_sentences, find_death_sentences_loose, is_definitive
    dead_names = {f["title"].split("：")[0] for f in findings if f["check"].startswith("death")}
    for e in entities:
        nm = e.get("name") or ""
        if nm not in names:
            continue
        if any(nm in d or d in nm for d in dead_names):
            continue  # 已有死亡結論（含重名變體）即不算蒸發
        apps = [ch for ch, t in texts.items() if nm in t]
        if len(apps) >= 5 and apps[0] < total * 0.5 and apps[-1] < total * 0.85:
            # 有死亡描寫（嚴＋寬口徑，查最後 3 個出場章）＝正常退場，不算蒸發
            tail_text = " ".join(texts[c] for c in apps[-3:])
            last_quotes = (find_death_sentences(nm, tail_text, others=names)
                           + find_death_sentences_loose(nm, tail_text))
            if last_quotes and is_definitive(last_quotes):
                continue
            f = make_finding(
                nxt("EVAP"), "evaporation", "major", f"{nm}：後期無聲消失",
                apps[:6] + apps[-2:],
                [{"chapter": str(apps[-1]), "quote": f"最後實質出場第 {apps[-1]} 章，共出場 {len(apps)} 章"}],
                f"{nm}自第 {apps[-1]} 章後再無出場、無死亡、無交代，疑似支線爛尾。",
                "補終局交代（死亡/退場/轉續作線），或在大綱刪除該線。")
            f["editor_context"] = build_context_for_editor(f, texts)
            findings.append(f)

    # ---- 六、種子兌現（同組多版本種子名歸組，每組一條；策展級單獨成條）
    from collections import defaultdict
    medium_pool: List[str] = []
    groups: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for s in seeds:
        key = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", s["name"])[:10] or s["name"]
        groups[key].append(s)
    for key, members in groups.items():
        rep = max((m["name"] for m in members), key=len)
        hits = sorted({ch for ch, t in texts.items() if seed_hit_in_text(rep, t)})
        if hits:
            continue
        src = members[0].get("source", "")
        if src != "worldbuilding":
            # 藍圖自動種子：措辭與正文多半不同，只進複核池
            medium_pool.append(f"[藍圖]{rep}")
            continue
        runs = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{2,}", rep)
        payoff = next((m.get("payoff", "") for m in members if m.get("payoff")), "")
        entity_present = rare_entity_present(rep, payoff, texts)
        # 策展級＝載入序前 10（正典種子）：逐條列項，置信度誠實標註；
        # 微粒種子只進複核池
        curated = any(m.get("curated") for m in members)
        if curated:
            if not entity_present:
                # 全文無痕：真落空（高置信）
                f = make_finding(
                    nxt("SEED"), "seed_unfulfilled", "major",
                    f"伏筆種子從未落實：{rep[:30]}", [],
                    [{"chapter": "-", "quote": "大綱約定的伏筆在正文零命中"}],
                    "大綱約定的伏筆在正文零命中，屬大綱-正文兌現斷裂。",
                    "補寫落實／改大綱刪除／以替換證物承接並明示。")
            else:
                # 實體在場但約定全名未命中：可能改寫存活，可能真落空
                f = make_finding(
                    nxt("SEED"), "seed_unfulfilled", "major",
                    f"伏筆種子疑似未按約定落實：{rep[:30]}", [],
                    [{"chapter": "-", "quote": "實體詞在場，但約定全名/關鍵細節未命中"}],
                    "種子相關實體在場，但大綱約定的關鍵細節（074 條款本文/紫斑/紀念碑星圖/黑板殘印場景等）未命中；可能改寫存活，可能真落空。",
                    "人工核對約定細節是否以替換形式出現，否則補寫或刪種。",
                    confidence="medium")
            f["missed_count"] = 1
            findings.append(f)
        else:
            medium_pool.append(rep)
    if medium_pool:
        f = make_finding(
            nxt("SEED"), "seed_unfulfilled", "major",
            f"{len(medium_pool)} 組種子疑似命名差異未命中（待人工複核）", [],
            [{"chapter": "-", "quote": m[:40]} for m in medium_pool[:12]],
            "種子實體詞在場、或屬微粒/藍圖自動種子，但約定全名未命中；多半是命名差異，少數是真落空。",
            "人工抽查每組 1 枚確認，再決定補寫或刪種。",
            confidence="medium")
        f["missed_count"] = len(medium_pool)
        findings.append(f)

    # ---- 七、統計（開頭模板／提要）
    opener = check_opener_templates(chapters)
    syn = check_synopsis_health(chapters)
    stats = {"opener_templates": opener, "synopsis": syn,
             "audit_stats": audit_stats,
             "watch_names": names[:20]}
    if syn["stitched_ratio"] > 0.5:
        findings.append(make_finding(
            nxt("SYN"), "synopsis_stitched", "minor",
            f"章節提要 {syn['stitched_count']} 章疑似首尾句拼接",
            [], [{"chapter": "-", "quote": f"拼接率 {syn['stitched_ratio']:.0%}，示例章 {syn['stitched'][:6]}"}],
            "synopsis 欄失去提要功能，影響連載回顧與上下文回填品質。",
            "以事件句重寫提要，或以 chapter_memory 回填。"))
    top_marker = max(opener["markers"].items(),
                     key=lambda kv: kv[1]["ratio"]) if opener["markers"] else None
    if top_marker and top_marker[1]["ratio"] > 0.25:
        findings.append(make_finding(
            nxt("OPEN"), "opener_template", "minor",
            f"開頭模板化：含「{top_marker[0]}」{top_marker[1]['count']} 章（{top_marker[1]['ratio']:.0%}）",
            [], [{"chapter": str(c), "quote": "同上標記開頭"} for c in top_marker[1]["sample"][:3]],
            "高頻同式開頭造成閱讀疲勞，屬 AI 長文典型特徵。",
            "建立開頭輪換清單逐章改寫首段。"))

    pack = merge_pack(novel_id, title, total, findings, sample, stats)
    pack["report_md"] = render_report(pack)
    return pack
