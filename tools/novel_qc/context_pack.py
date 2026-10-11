# -*- coding: utf-8 -*-
"""上下文傳輸：把質檢 findings 合併整理，打包成修稿可直接消費的上下文。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List

from .audit_engine import DeathFinding

SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2, "watch": 3}

# 缺陷 → 五維評分權重（A故事/B連貫/C邏輯/D人物/E文筆），每條扣分
DIMENSIONS = ("A", "B", "C", "D", "E")
DIM_FULL = {"A": 25, "B": 20, "C": 20, "D": 15, "E": 20}
CHECK_DIM_PENALTY = {
    # check名 -> ({維度: 單條扣分}, severity乘數由finding決定是否計入)
    "death_resurrection": ({"B": 2, "C": 3}, None),
    "death_resurrection_multi": ({"B": 3, "C": 4}, None),  # 同一人死亡≥3次
    "date_backflow": ({"B": 3}, None),
    "adjacent_duplication": ({"B": 1, "E": 1}, None),
    "opener_template": ({"E": 2}, None),  # 整體一次性扣分
    "seed_unfulfilled": ({"A": 1}, None),
    "evaporation": ({"A": 2, "C": 1}, None),
    "synopsis_stitched": ({"E": 2}, None),  # 整體一次性扣分
}
SEVERITY_GATE = {"critical": 1.0, "major": 0.6, "minor": 0.25, "watch": 0.0}

# 同類檢查總扣分封頂（防誤報風暴擊穿總分）
CHECK_CAP = {
    "death_resurrection": 14.0,
    "death_resurrection_multi": 14.0,
    "date_backflow": 6.0,
    "adjacent_duplication": 6.0,
    "opener_template": 4.0,
    "seed_unfulfilled": 4.0,
    "evaporation": 6.0,
    "synopsis_stitched": 2.0,
}


def make_finding(
    fid: str,
    check: str,
    severity: str,
    title: str,
    chapters: List[int],
    evidence: List[Dict[str, str]],
    analysis: str,
    suggested_fix: str,
    confidence: str = "high",
) -> Dict[str, Any]:
    return {
        "id": fid,
        "check": check,
        "severity": severity,
        "title": title,
        "chapters": sorted(set(chapters)),
        "evidence": evidence,          # [{chapter, quote}]
        "analysis": analysis,
        "suggested_fix": suggested_fix,
        "confidence": confidence,      # high(逐字引證) / medium(模式推斷)
    }


def death_finding_to_dict(f: DeathFinding, fid: str) -> Dict[str, Any]:
    multi = len(f.death_chapters) >= 3
    check = "death_resurrection_multi" if multi else "death_resurrection"
    severity = "critical" if f.definitive else "major"
    ev: List[Dict[str, str]] = []
    for ch in f.death_chapters:
        for q in (f.death_quotes.get(ch) or [])[:2]:
            ev.append({"chapter": str(ch), "quote": q})
    ev.append({"chapter": str(f.alive_after[0]),
               "quote": f"該人物在第 {f.alive_after[0]} 章再度行動（其後共 {len(f.alive_after)} 章），"
                        f"其間無復活交代"})
    return make_finding(
        fid, check, severity,
        f"{f.name}：定論式死亡 {len(f.death_chapters)} 次、零復活交代" if multi
        else f"{f.name}：死亡後無交代再度出場",
        f.death_chapters + f.alive_after[:3], ev,
        f"{f.name}於 {f.death_chapters} 被定論式寫死，"
        f"卻於 {f.alive_after[:5]} 正常行動，無任何角色表示驚訝、無復活機制說明。",
        "多次死亡只保留一場並給出唯一真相（投影/分身/替死須明寫）；或併章刪除重複戰役。",
    )


def build_context_for_editor(
    finding: Dict[str, Any],
    chapter_texts: Dict[int, str],
    before_window: int = 2,
) -> Dict[str, Any]:
    """給修稿 Editor 的最小可用上下文：目標章＋前後文＋改寫指令。"""
    targets = finding["chapters"][:6]
    bundle: Dict[str, Any] = {
        "finding_id": finding["id"],
        "severity": finding["severity"],
        "instruction": finding["suggested_fix"],
        "targets": [],
    }
    for ch in targets:
        ctx = {"chapter": ch,
               "excerpt": (chapter_texts.get(ch) or "")[:1500]}
        prev_idx = [c for c in chapter_texts if ch - before_window <= c < ch]
        if prev_idx:
            c0 = max(prev_idx)
            ctx["prev_excerpt"] = {"chapter": c0,
                                   "tail": (chapter_texts[c0] or "")[-600:]}
        bundle["targets"].append(ctx)
    return bundle


def score_findings(findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    penalties = {d: 0.0 for d in DIMENSIONS}
    check_used = {c: 0.0 for c in CHECK_CAP}
    for f in findings:
        mapping = CHECK_DIM_PENALTY.get(f["check"])
        if not mapping:
            continue
        dims, _ = mapping
        gate = SEVERITY_GATE.get(f["severity"], 0.0)
        per_item = f.get("check") in (
            "death_resurrection", "death_resurrection_multi",
            "date_backflow", "adjacent_duplication",
            "seed_unfulfilled", "evaporation")
        raw = (min(6, f.get("missed_count", 1)) if f["check"] == "seed_unfulfilled"
               else (len(f["chapters"]) if per_item and f["check"] in (
                   "adjacent_duplication", "evaporation") else 1))
        adds = {d: pts * gate * raw for d, pts in dims.items()}
        total_add = sum(adds.values())
        if total_add <= 0:
            continue
        room = CHECK_CAP[f["check"]] - check_used[f["check"]]
        if room <= 0:
            continue
        scale = min(1.0, room / total_add)
        for d, v in adds.items():
            penalties[d] += v * scale
        check_used[f["check"]] += total_add * scale
    # 整體一次性項封頂，避免單項扣穿
    penalties["E"] = min(penalties["E"], 12.0)
    scores = {d: max(0, round(DIM_FULL[d] - penalties[d])) for d in DIMENSIONS}
    scores["TOTAL"] = sum(scores.values())
    grade = ("優秀" if scores["TOTAL"] >= 90 else "良好" if scores["TOTAL"] >= 80
             else "中等" if scores["TOTAL"] >= 70 else "待改善"
             if scores["TOTAL"] >= 60 else "品質不佳")
    return {"scores": scores, "grade": grade,
            "penalties": {d: round(v, 1) for d, v in penalties.items()},
            "per_check": {c: round(v, 1) for c, v in check_used.items()}}


def merge_pack(novel_id: str, title: str, total: int,
               findings: List[Dict[str, Any]],
               sample: Dict[str, Any],
               stats: Dict[str, Any]) -> Dict[str, Any]:
    """合併整理：把抽樣＋缺陷＋統計合併為一份傳輸包。"""
    findings_sorted = sorted(
        findings, key=lambda f: (SEVERITY_ORDER.get(f["severity"], 9), f["id"]))
    return {
        "novel_id": novel_id,
        "title": title,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "chapters_total": total,
        "sample": sample,          # 抽樣章（供人工/模型複核）
        "stats": stats,            # 聚合統計（開頭模板/提要/重複）
        "scoring": score_findings(findings),
        "findings": findings_sorted,
    }


def render_report(pack: Dict[str, Any]) -> str:
    """總結：由傳輸包渲染人類可讀報告。"""
    L: List[str] = []
    sc = pack["scoring"]
    L.append(f"# 《{pack['title']}》完本質檢報告")
    L.append(f"（{pack['generated_at']}，共 {pack['chapters_total']} 章）")
    L.append("")
    s = sc["scores"]
    L.append(f"## 總分 {s['TOTAL']}/100（{sc['grade']}）")
    L.append(f"A故事 {s['A']}/25｜B連貫 {s['B']}/20｜C邏輯 {s['C']}/20｜"
             f"D人物 {s['D']}/15｜E文筆 {s['E']}/20")
    L.append("")
    L.append("## 缺陷清單（依嚴重度）")
    for f in pack["findings"]:
        L.append(f"### [{f['severity']}] {f['title']}（{f['id']}）")
        L.append(f"- 章節：{f['chapters'][:12]}")
        for ev in f["evidence"][:4]:
            L.append(f"- ch{ev['chapter']}：{ev['quote'][:120]}")
        L.append(f"- 分析：{f['analysis'][:220]}")
        L.append(f"- 建議：{f['suggested_fix'][:220]}")
        L.append("")
    L.append("## 抽樣複核章")
    for name, chs in pack["sample"].get("strata", {}).items():
        L.append(f"- {name}：{chs}")
    L.append(f"- 相鄰組：{pack['sample'].get('pairs', [])}")
    L.append("")
    L.append("## 統計摘要")
    L.append("```json")
    L.append(json.dumps(pack["stats"], ensure_ascii=False, indent=1)[:3000])
    L.append("```")
    return "\n".join(L)
