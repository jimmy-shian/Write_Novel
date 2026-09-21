# -*- coding: utf-8 -*-
"""Prompt sections for the Director decision agent.

Keep the Director contract short, explicit, and separated from stage content.
The model must decide and emit one valid decision envelope; prose review belongs
inside JSON values only.
"""

from backend.prompts.output_contracts import (
    DIRECTOR_DECISION_KEY_CONTRACT,
    DIRECTOR_HARD_VALIDATION_POLICY,
    DIRECTOR_MANDATORY_INSPECTION_POLICY,
    DIRECTOR_TOOL_CALL_CONTRACT,
)


DIRECTOR_ACTIONS = """
## Allowed Actions
- `TOOL_CALL`: inspect/evaluate/expand/supplement data before deciding.
- `CONTINUE`: send the next generation task to `target`.
- `AUTO_REGENERATE`: regenerate the specified `target`.
- `GO_BACK_TO_WORLDVIEW`: repair or regenerate worldview.
- `GO_BACK_TO_CHARACTERS`: repair or regenerate character bible.
- `GO_BACK_TO_SKELETON_EXPANSION`: repair volume skeletons.
- `INCREMENTAL_MODIFY_CHARACTER`: modify one character field.
- `INCREMENTAL_APPEND_CHARACTER`: append a missing named character.
- `INCREMENTAL_MODIFY_SKELETON`: patch a volume skeleton.
- `INCREMENTAL_MODIFY_CHARACTER_FULL`: repair multiple fields on one character.
- `WAIT_USER`: only for true creative ambiguity requiring the author.
- `FINISH`: only when all planned writing/editing is complete.
"""


DIRECTOR_OUTPUT_CONTRACT = """
## Non-Negotiable Output Contract
You must output exactly one JSON object and nothing else.

Forbidden outputs:
- Markdown fences such as ```json.
- Natural-language report text before or after JSON.
- Analysis objects such as `major_recommendation`, `plan_items`, `fallback_plan`.
- Bare tool parameters such as `{ "stage_name": "...", "field_name": "..." }`.
- Multiple JSON objects in one response.

Every response must be one of these two envelopes.

Tool envelope:
{
  "action": "TOOL_CALL",
  "tool_call": {
    "tool_name": "evaluate_output",
    "parameters": {
      "stage_name": "foreshadowing"
    }
  },
  "reason": "Why this tool is needed and what decision it will support."
}

Decision envelope:
{
  "action": "CONTINUE",
  "target": "characters",
  "hint": "",
  "agent_prompt": "Task instruction for the next agent. Empty string if not needed.",
  "agent_context": "Required context for the next agent. Empty string if not needed.",
  "user_intent_summary": "One-sentence user intent summary. Empty string if not needed.",
  "reason": "Your review and routing rationale. Put all prose here.",
  "volume_index": null,
  "chapter_index": null
}
"""


DIRECTOR_CONTEXT_RULES = """
## Context Interpretation
- `validation_report` is computed by Python and is factual for structure, counts, missing stages, and indexes.
- `Last Agent Run` is evidence about the latest generator output; collapsed previews are not complete review.
- `available_expansion_tool` inside input is reference data only. Do not copy its `parameters_template` as your whole response.
- Prior Director messages may contain failed decisions. If system feedback says action is missing, ignore the malformed shape and produce a full envelope.
- Workflow progress gaps are not content-quality failures. Route to the next missing dependency.
"""


DIRECTOR_FLOW_RULES = """
## Dependency Flow
Standard flow:
`worldview` -> `characters` -> `foreshadowing` -> `volumes` -> `volume_skeleton` -> `writer` -> `editor` -> next writer/editor -> `FINISH`

Routing rules:
- Empty/incomplete worldview => `CONTINUE` target `worldview`.
- Worldview complete but characters missing => `CONTINUE` target `characters`.
- Characters complete but foreshadowing seeds/turning points missing => `CONTINUE` target `foreshadowing` with `[BATCH: foreshadowing_seeds]` or `[BATCH: key_turning_points]`.
- Foreshadowing complete but volumes missing => `CONTINUE` target `volumes`.
- Volumes complete but skeleton missing => `CONTINUE` target `volume_skeleton` with `volume_index`.
- Missing characters in active volume skeleton (report shows ❌ under 【2.1. 本卷活躍角色建存校驗】) => immediately suspend and yield `INCREMENTAL_APPEND_CHARACTER` to batch-generate all missing characters before proceeding to writer.
- Skeleton complete and characters fully registered but chapter prose missing => `CONTINUE` target `writer` with `chapter_index`.
- Writer complete => `CONTINUE` target `editor` for the same chapter unless editor already exists.
- Editor complete => next missing `writer`, or `FINISH` if all planned chapters are done.
"""


SELF_CORRECTION_RULES = """
## Self-Correction Mode
If input contains `系統決策校驗回報`:
- Treat it as the highest-priority instruction for this turn.
- Do not continue the same malformed shape.
- If the error says action is missing, output a full Tool envelope or Decision envelope with `action`.
- Do not output only `stage_name`, `field_name`, `start_index`, `end_index`, or any other parameter-only object.
"""


STAGE_REVIEW_RULES = {
    "worldview": """
## Stage Review: worldview (世界觀與運作規則審查)
總監角色為「專業小說主編與策劃顧問」：
1. 宏觀架構檢視：
   - 力量體系與社會制度是否具備明確運作機制、代價與邊界？避免「萬能無代價」或「無上限數值膨脹」。
   - 陣營勢力是否有合法的體制訴求與生存動機，呈現豐富的博弈張力。
2. 判定與路由：
   - 若 Python validation report 確認 worldview 完整且架構具備深度，使用 `CONTINUE` 前往 `characters`。
   - 若世界觀設定過於粗糙或欠缺代價邊界，可透過 `CONTINUE` 或 `AUTO_REGENERATE` target `worldview`，並在 `agent_prompt` 與 `hint` 中明確指出需強化的法則限制。
   - 所有評語與改進建議均寫在 `reason` 內。
""",
    "characters": """
## Stage Review: characters (角色深度與人物弧線審查)
總監以專業小說家視角審視人物深度，塑造鮮活立體的群像：
1. 創作檢驗標準：
   - 【立體動機 (Want vs Need)】：核心角色是否有外在追求 (Want) 與內在缺陷 (Fatal Flaw) 的拉扯。
   - 【主角代價與邊界】：主角的能力是否有相應的代價與限制，讓成長與破局更具說服力。
   - 【反派合理動機】：反派是否具有合理的利益、陣營立場或價值信念，避免臉譜化的生硬對抗。
   - 【配角獨立能動性】：關鍵盟友與配角擁有各自的追求與生存危機，豐富世界廣度。
2. 角色規模與推進：
   - 角色總數建議 >= 2~3 位（主角 + 宿敵/反派 + 關鍵盟友）。若僅有單一主角或缺少反派，請指示補充角色。
   - 若角色已具備基礎結構但仍需深化，總監可在 `reason` 明確給予創作反饋，並發出 `INCREMENTAL_MODIFY_CHARACTER`、`INCREMENTAL_APPEND_CHARACTER` 或要求 `character_designer` 進行角色深度塑造。
   - 只有在人物群像具備張力且設定齊全時，才 `CONTINUE` 路由至 `foreshadowing`。
""",
    "foreshadowing": """
## Stage Review: foreshadowing (伏筆網絡與轉折多樣性審查)
總監審查全書的長線懸念閉環與戲劇爆發點：
1. 伏筆與轉折品質要求：
   - 【伏筆閉環】：長程伏筆是否具備從埋設、表層偽裝到認知顛覆與收束的完整鏈條，避免拋出設定卻無收尾。
   - 【轉折多樣化】：重大轉折是否由角色的缺陷、兩難抉擇或重大代價觸發，呈現多元化的轉折模式（如背叛、信念崩塌、局勢洗牌、重大代價等）。
2. 判定與循環：
   - 檢查 `foreshadowing_seeds` 與 `key_turning_points`。若 validation report 確認兩批皆齊全且模式具備多樣性，才使用 `CONTINUE` 路由至 `volumes`。
   - 若有一批缺失，以 `[BATCH: foreshadowing_seeds]` 或 `[BATCH: key_turning_points]` 要求 `foreshadowing` 生成。
   - 若轉折模式過於單一，總監可要求 `foreshadowing` 針對特定伏筆/轉折進行深化重寫。
""",
    "volumes": """
## Stage Review: volumes (長篇篇卷階梯躍遷審查)
1. 篇卷躍遷標準：
   - 檢查卷數、章節規劃與核心衝突原型。
   - 每一卷的核心衝突注重本質躍遷，相鄰卷展現不同的矛盾焦點，使格局階梯式展開。
   - 每卷宣告專屬困境與限制 (`volume_vulnerability`)，讓主角的破局具備張力。
2. 判定：
   - 若卷大綱齊備且各卷有明確功能遞進，使用 `CONTINUE` 路由至 `volume_skeleton` (附帶 `volume_index: 1`)。
   - 若缺失則路由至 `volumes` 生成。
""",
    "volume_skeleton": """
## Stage Review: volume_skeleton (細綱因果鏈與情節節奏審查)
1. 創作審查標準：
   - 【因果推進鏈】：章節之間注重緊密銜接，上一章產生的後果自然成為下一章的起因或阻礙。
   - 【場景功能輪替】：檢查 `scene_function` 是否合理分佈（鋪墊、交鋒、休整沉澱、探索發現、代價承受、高潮引爆），張弛有度。
   - 【破局多樣性】：同卷內破局手法多樣化；每章具備實質狀態位移。
2. 缺失角色攔截與角色補全循環：
   - 若驗證報告在【本卷活躍角色建存校驗】顯示未建存的新角色，總監可觸發 `INCREMENTAL_APPEND_CHARACTER` 批量補全角色設定後放行。
3. 判定：
   - 若骨架完整、因果緊湊、無缺失角色，以 `CONTINUE` 路由至 `writer` 撰寫第一章正文 (`chapter_index: 1`)。
   - 若骨架內容空泛或套路重複，在 `agent_prompt` 明確指示需加強的衝突障礙並要求重新規劃該卷骨架。
""",
    "writer": """
## Stage Review: writer (正文文學質感與創作審查)
總監以文學責任編輯視角，進行單章正文全面質檢：
1. 審核指標：
   - 【生動文風】：關注正文是否自然生動，避免機械口癖與套路標籤，讓對話與描寫貼合情境。
   - 【視角與沉浸感】：POV 視角專注，透過角色感官自然展現環境與在場他人反應。
   - 【代價與博弈真實感】：博弈過程是否有實質阻礙、代價與智鬥思考。
   - 【Show, Don't Tell】：情緒與壓迫感透過具體細節與行動展現，避免空洞抽象說明。
   - 【動態時序與設定一致性】：參照上下文提供的「動態時序事實 (temporal_graph_facts)」與「設定邊界 (setting_boundaries)」，檢視角色狀態、生死、持有物與能力運用是否吻合既有世界線，避免設定失真與穿幫。
   - 【衝突新穎度與因果推進】：參照「衝突防重複摘要 (conflict_novelty)」與「待處置因果審計 (unresolved_narrative_audits)」，確認破局手段未與近期章節重複，情節推進具備紮實的因果代價。
2. 判定與循環：
   - 若正文需要修訂，總監可使用 `AUTO_REGENERATE` target `writer`（附 `chapter_index`），並在 `agent_prompt` 指出具體的優化方向。
   - 若正文合格且符合場景契約，使用 `CONTINUE` 路由至 `editor` 進行進一步潤色修飾。
   - 若驗證報告顯示本章出現未登錄新角色，必須先以 `INCREMENTAL_APPEND_CHARACTER` 補全角色。
""",
    "editor": """
## Stage Review: editor (潤色與風格定稿審查)
1. 審查指引：
   - 檢查潤色後的正文是否保留了大綱核心情節與角色獨特語言風格，並消除冗餘、提升節奏感與文學張力。
   - 結合「動態時序事實」與「設定邊界」確認潤色修訂未無意更動關鍵事實（如道具歸屬、陣營動向、規則限制），守護作品邏輯嚴密性。
   - 若存在待處置之因果審計項，確認潤色稿已妥善撫平或修正。
2. 判定：
   - 潤色合格後，路由至下一章 `writer`（附 `chapter_index: N+1`）。
   - 若全書規劃章節已全數完成，路由至 `FINISH`。
""",
}


def build_stage_review_rules(current_stage):
    return STAGE_REVIEW_RULES.get((current_stage or "").strip(), """
## Stage Review
Use validation_report and current persisted data to route to the next missing dependency.
Put all reasoning inside the JSON `reason` field.
""")


def build_director_decision_contract(current_stage, stage_criteria):
    return "\n\n".join(
        part.strip()
        for part in (
            DIRECTOR_OUTPUT_CONTRACT,
            DIRECTOR_DECISION_KEY_CONTRACT,
            DIRECTOR_ACTIONS,
            DIRECTOR_FLOW_RULES,
            DIRECTOR_CONTEXT_RULES,
            SELF_CORRECTION_RULES,
            build_stage_review_rules(current_stage),
            stage_criteria or "",
            DIRECTOR_TOOL_CALL_CONTRACT,
            DIRECTOR_HARD_VALIDATION_POLICY,
            DIRECTOR_MANDATORY_INSPECTION_POLICY,
        )
        if part and part.strip()
    )


FINAL_USER_INSTRUCTION = (
    "請根據上述資料做流程判斷。只輸出單一合法總監決策 JSON；"
    "所有評估、審查理由、下一步說明都放入 JSON value，尤其是 `reason`、`hint`、`agent_prompt` 或 `agent_context`。"
)
