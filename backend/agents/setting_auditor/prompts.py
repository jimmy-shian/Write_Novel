# -*- coding: utf-8 -*-
"""
Setting Auditor Prompts (Story Engine 2.0)
跨階段世界觀設定審查提示詞構建
"""

SETTING_AUDITOR_PROMPT = """你是一位專業的故事世界觀運作審查官（Setting Auditor）。
你的職責不是盲目增加設定名詞，而是審查既有設定是否真正成為「運作系統」。

## 審查五大維度
1. **Mechanism (機制)**：這個設定如何運作？底層因果規律是否清楚？
2. **Cost (代價)**：使用、維護或突破它需要付出什麼代價？
3. **Boundary (邊界)**：它絕對無法做到什麼？極限在哪裡？
4. **Usage (使用)**：情節是否真正調用了它的規則，還是僅為裝飾性背景？
5. **Theme Link (主題關聯)**：它是否呼應作品的主題矛盾或人性悖論？

輸出必須嚴格符合 JSON 物件格式。
"""

def build_setting_audit_messages(audit_type: str, context_text: str, novel_id: str = ""):
    """建構 Setting Auditor 審查訊息"""
    system_prompt = SETTING_AUDITOR_PROMPT
    user_prompt = f"""【審查類型】：{audit_type}
【相關內容脈絡】：
{context_text}

請針對上述內容進行世界觀設定審查，檢驗設定之機制、代價、邊界與運作狀態。
請只輸出純 JSON：
{{
  "audit_type": "{audit_type}",
  "passed": true,
  "setting_health_score": 85,
  "operating_mechanisms_count": 3,
  "issues_detected": [
    {{
      "setting_name": "設定名稱",
      "issue_type": "lacks_cost | lacks_boundary | cosmetic_only | contradiction | stale_unused",
      "description": "具體說明",
      "remediation_hint": "建議改善方向"
    }}
  ],
  "recommendations": ["具體改進建議 1", "具體改進建議 2"]
}}
"""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
