# -*- coding: utf-8 -*-
"""
Story Engine 2.0 Setting Registry
設定系統運作態登錄與邊界追蹤引擎

核心原則：
- 世界觀不是名詞清單，而是「運作系統」。
- 追蹤每個設定的五大維度：Mechanism (機制), Cost (代價), Boundary (邊界), Failure Condition (崩潰條件), Theme Link (主題關聯)。
- 檢驗設定是否真正在小說情節中產生後果，防止無效膨脹與空洞換皮。
"""

import json
from typing import Any, Dict, List, Optional, Set

from backend import persistence as db
from backend.common.config import SETTING_AUDIT_STALENESS_CHAPTERS


class SettingRegistry:
    """管理世界觀設定系統的運作態、邊界約束與使用歷史。"""

    @classmethod
    def sync_from_worldview(cls, novel_id: str, worldview_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        從 Story Architect 生成之世界觀字典中，提煉並登錄運作態設定系統。
        """
        registered = []
        # 1. 力量體系
        power_sys = worldview_dict.get("power_system")
        if power_sys and isinstance(power_sys, str) and len(power_sys.strip()) > 10:
            registered.append(db.upsert_setting_system(
                novel_id=novel_id,
                name="核心力量體系與能階律",
                setting_type="power_mechanism",
                mechanism=power_sys[:500],
                cost="超常爆發伴隨反噬、精神耗損或生理不可逆負擔",
                boundary="無法直接憑空顛覆根本因果律；受環境魔能/靈能濃度限制",
                failure_condition="超出容納極限時導致能脈崩潰或同化異變",
                theme_link=str(worldview_dict.get("theme") or "")[:200],
            ))
        elif isinstance(worldview_dict.get("power_systems"), list):
            for ps in worldview_dict["power_systems"]:
                if isinstance(ps, dict) and ps.get("name"):
                    registered.append(db.upsert_setting_system(
                        novel_id=novel_id,
                        name=ps["name"],
                        setting_type="power_system",
                        mechanism=ps.get("rules") or ps.get("mechanism") or "力量運作機制",
                        cost=ps.get("costs") or ps.get("cost"),
                        boundary=ps.get("boundaries") or ps.get("boundary"),
                        failure_condition=ps.get("failure_condition"),
                        theme_link=str(worldview_dict.get("theme") or "")[:200],
                    ))

        # 2. 世界規則列表
        rules = worldview_dict.get("rules", [])
        if isinstance(rules, list):
            for r in rules:
                if isinstance(r, dict):
                    r_name = r.get("rule_name") or r.get("name") or "世界法則"
                    r_desc = r.get("details") or r.get("description") or str(r)
                    registered.append(db.upsert_setting_system(
                        novel_id=novel_id,
                        name=r_name,
                        setting_type="ecological_law",
                        mechanism=r_desc[:400],
                        cost=r.get("cost") or "遵從或抵觸該法則之社會與個體代價",
                        boundary=r.get("boundary") or "只在特定領域或維度生效",
                        failure_condition=r.get("failure_condition") or "法則干涉共振崩解",
                        theme_link="秩序與代價之權衡",
                    ))
                elif isinstance(r, str) and len(r.strip()) > 5:
                    registered.append(db.upsert_setting_system(
                        novel_id=novel_id,
                        name=r[:25].strip(),
                        setting_type="ecological_law",
                        mechanism=r.strip(),
                        boundary="受物理或世界環境邊界約束",
                    ))

        # 3. 核心陣營制度 (Factions as Institutional Settings)
        factions = worldview_dict.get("factions", [])
        if isinstance(factions, list):
            for f in factions:
                if isinstance(f, dict) and f.get("name"):
                    f_name = f["name"]
                    f_pos = f.get("position") or ""
                    f_res = f.get("resources") or ""
                    mechanism_desc = f"立場：{f_pos}。掌控資源與制度特權：{f_res}"
                    registered.append(db.upsert_setting_system(
                        novel_id=novel_id,
                        name=f"{f_name}體制運作律",
                        setting_type="political_institution",
                        mechanism=mechanism_desc[:400],
                        cost="維持制度統治需要的下層犧牲與監控成本",
                        boundary="體制無法消滅底層暗流生存意志與資訊洩漏",
                        failure_condition="基層反叛、壟斷鏈條斷裂或最高層利益分裂",
                        stakeholder=f"既得利益者：{f_name}高層；對抗者：受壓制民眾與變革派",
                    ))

        # 4. Fallback：真實世界觀 shape（theme/main_conflict/worldview/
        #    macro_outline）不含 power_systems/rules/factions 時，舊邏輯會回傳
        #    空 list 導致運作庫永遠是空的。此處至少提煉 1~2 個可治理實體。
        if not registered:
            theme = str(worldview_dict.get("theme") or "").strip()
            main_conflict = str(worldview_dict.get("main_conflict") or "").strip()
            world_text = str(worldview_dict.get("worldview") or "").strip()
            macro = str(worldview_dict.get("macro_outline") or "").strip()
            if len(world_text) >= 10:
                registered.append(db.upsert_setting_system(
                    novel_id=novel_id,
                    name="核心世界法則與環境脈絡",
                    setting_type="ecological_law",
                    mechanism=world_text[:500],
                    cost="違逆世界法則者須承擔環境反噬與社會排斥代價",
                    boundary="法則僅在既定世界環境與能量條件下生效，無法憑空顛覆因果",
                    failure_condition="能量失衡或法則干涉共振時引發崩解",
                    theme_link=theme[:200],
                ))
            if len(main_conflict) >= 10:
                registered.append(db.upsert_setting_system(
                    novel_id=novel_id,
                    name="核心矛盾與對立結構",
                    setting_type="political_institution",
                    mechanism=f"全書核心對立：{main_conflict[:400]}",
                    cost="維持對立需要持續的資源投入與下層犧牲",
                    boundary="任何一方皆無法以單一手段徹底消滅另一方",
                    failure_condition="內部分裂或關鍵資源鏈斷裂",
                    stakeholder="對立雙方高層與被捲入的底層",
                    theme_link=theme[:200],
                ))
            if not registered and len(macro) >= 10:
                registered.append(db.upsert_setting_system(
                    novel_id=novel_id,
                    name="故事推進節奏律",
                    setting_type="narrative_law",
                    mechanism=f"全書推進脈絡：{macro[:400]}",
                    cost="偏離主線將消耗讀者信任與敘事動能",
                    boundary="不以單章爆發取代長程因果鋪墊",
                    theme_link=theme[:200],
                ))

        return registered

    @classmethod
    def sync_systems_from_worldview(cls, novel_id: str, worldview_dict: Optional[Dict[str, Any]] = None) -> int:
        """主動同步或從資料庫載入最新世界觀並登錄設定體系"""
        if worldview_dict is None:
            wb = db.get_latest_worldbuilding(novel_id)
            if wb and wb.get("content"):
                try:
                    worldview_dict = json.loads(wb["content"])
                    if not isinstance(worldview_dict, dict):
                        raise ValueError("worldview content is not a dict")
                except Exception:
                    # 文字型世界觀（【世界觀設定】等章節格式）走正規解析器，
                    # 否則 sync 永遠拿到 {}、已完結作品也永遠是空的。
                    try:
                        worldview_dict = db.parse_worldview_to_json(wb["content"])
                    except Exception:
                        worldview_dict = {}
            else:
                worldview_dict = {}
        registered = cls.sync_from_worldview(novel_id, worldview_dict or {})
        return len(registered)

    @classmethod
    def audit_setting_health(cls, novel_id: str, current_chapter: Optional[int] = None) -> Dict[str, Any]:
        """
        審查設定系統健康度（是否具備機制、代價與邊界，杜絕純裝飾性名詞）。
        """
        systems = db.get_setting_systems(novel_id)
        if not systems:
            return {
                "passed": True,
                "score": 100,
                "total_systems": 0,
                "systems_count": 0,
                "boundary_missing_systems": [],
                "issues": [],
                "summary": "尚未登錄特定設定系統實體",
            }

        issues = []
        boundary_missing = []
        score = 100
        for sys in systems:
            name = sys.get("name", "未命名設定")
            # 檢查是否有機制
            if not sys.get("mechanism") or len(str(sys["mechanism"]).strip()) < 10:
                issues.append({
                    "setting_name": name,
                    "issue_type": "cosmetic_only",
                    "description": f"設定「{name}」缺乏運作機制說明，僅為裝飾性名詞。",
                    "remediation": "補充該設定的因果運作規律，寫出它如何影響現實。",
                })
                score -= 15

            # 檢查是否有邊界
            if not sys.get("boundary") or len(str(sys["boundary"]).strip()) < 5:
                boundary_missing.append(name)
                issues.append({
                    "setting_name": name,
                    "issue_type": "lacks_boundary",
                    "description": f"設定「{name}」缺乏能力或適用邊界，容易導致主角或反派無限通脹。",
                    "remediation": "明定該設定在何種情況下無效、對什麼事物不起作用。",
                })
                score -= 10

            # 檢查是否有代價
            if not sys.get("cost") or len(str(sys["cost"]).strip()) < 5:
                issues.append({
                    "setting_name": name,
                    "issue_type": "lacks_cost",
                    "description": f"設定「{name}」缺乏維持或使用之代價，缺乏戲劇張力。",
                    "remediation": "補充動用該力量或維繫該體制時必須付出的資源、生理或社會代價。",
                })
                score -= 10

        score = max(0, score)
        return {
            "passed": score >= 65,
            "score": score,
            "total_systems": len(systems),
            "systems_count": len(systems),
            "boundary_missing_systems": boundary_missing,
            "issues": issues,
            "summary": f"共檢查 {len(systems)} 個設定系統，健康評分 {score} 分；發現 {len(issues)} 處邊界與代價疑慮。"
        }

    @classmethod
    def record_system_usage(
        cls,
        novel_id: str,
        system_name: str,
        chapter_index: int,
        cost_paid: Optional[str] = None,
        boundary_tested: Optional[str] = None,
        new_state: Optional[str] = None,
    ) -> bool:
        """記錄特定設定系統在章節中的調用與邊界檢驗"""
        return db.update_setting_system_usage(
            novel_id=novel_id,
            name=system_name,
            chapter_index=chapter_index,
            new_state=new_state,
        )

    @classmethod
    def get_scoped_context_for_writer(
        cls,
        novel_id: str,
        active_setting_names: Optional[List[str]] = None,
        max_systems: int = 3,
    ) -> str:
        """
        為 Chapter Writer 提取最相關的設定系統機制與邊界（嚴格控制 Token 預算）。
        """
        all_systems = db.get_setting_systems(novel_id, active_only=True)
        if not all_systems:
            return ""

        target_set = set(active_setting_names or [])
        selected = []

        # 優先匹配本章指明的設定
        if target_set:
            for s in all_systems:
                if any(ts in s["name"] or s["name"] in ts for ts in target_set):
                    selected.append(s)

        # 補充最常用之核心設定
        for s in all_systems:
            if s not in selected and len(selected) < max_systems:
                selected.append(s)

        if not selected:
            return ""

        lines = ["### ⚙️【本章相關設定運作機制與絕對邊界 (Setting Boundaries)】"]
        for s in selected:
            lines.append(f"**【{s['name']}】**（類別：{s['type']} | 狀態：{s.get('current_state', 'active')}）")
            lines.append(f"  - 運作機制：{s.get('mechanism', '未載明')}")
            if s.get("cost"):
                lines.append(f"  - 使用代價：{s['cost']}")
            if s.get("boundary"):
                lines.append(f"  - 嚴格邊界 (絕對做不到的事)：{s['boundary']}")
            if s.get("failure_condition"):
                lines.append(f"  - 失效/反噬條件：{s['failure_condition']}")

        lines.append("*(請作家在落實情節時，嚴格遵守上述邊界；力量與制度必須承擔代價，嚴禁無視設定邊界無痛通脹)*")
        return "\n".join(lines)

    @classmethod
    def get_setting_context_for_writer(
        cls,
        novel_id: str,
        active_systems: Optional[List[str]] = None,
        max_systems: int = 3,
    ) -> str:
        return cls.get_scoped_context_for_writer(
            novel_id=novel_id,
            active_setting_names=active_systems,
            max_systems=max_systems,
        )

