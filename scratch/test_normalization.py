# -*- coding: utf-8 -*-
import sys
import os

# Force stdout/stderr to use UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# Add parent dir to path so we can import llm
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm import normalize_messages

def run_tests():
    print("=== 🚀 開始測試訊息角色交替與歸一化 (normalize_messages) ===")
    
    # 測試案例 1：正常 alternating 角色
    test_1 = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"}
    ]
    res_1 = normalize_messages(test_1)
    assert len(res_1) == 3, "測試 1 失敗：長度應該為 3"
    assert res_1[0]["role"] == "system"
    assert res_1[1]["role"] == "user"
    assert res_1[2]["role"] == "assistant"
    print("✅ 測試案例 1 通過：正常 alternating 角色無變動")

    # 測試案例 2：連續 user 角色合併
    test_2 = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Message 1"},
        {"role": "user", "content": "Message 2"},
        {"role": "assistant", "content": "Assistant reply"}
    ]
    res_2 = normalize_messages(test_2)
    assert len(res_2) == 3, f"測試 2 失敗：合併後長度應為 3，實際為 {len(res_2)}"
    assert res_2[1]["role"] == "user"
    assert "Message 1\n\nMessage 2" in res_2[1]["content"], "測試 2 失敗：連續 user 訊息未合併"
    print("✅ 測試案例 2 通過：連續 user 角色合併成功")

    # 測試案例 3：連續 assistant 角色合併且開頭為 assistant (一鍵執行後總監連續 decision 狀態)
    test_3 = [
        {"role": "system", "content": "System prompt"},
        {"role": "assistant", "content": "Decision 1"},
        {"role": "assistant", "content": "Decision 2"},
        {"role": "user", "content": "User input"}
    ]
    res_3 = normalize_messages(test_3)
    # 期望結果：
    # 1. system
    # 2. user (自動插入 "請開始小說寫作、分析與指導：")
    # 3. assistant (合併後的 Decision 1 & 2)
    # 4. user (User input)
    assert len(res_3) == 4, f"測試 3 失敗：預期長度為 4，實際為 {len(res_3)}"
    assert res_3[0]["role"] == "system"
    assert res_3[1]["role"] == "user"
    assert res_3[1]["content"] == "請開始小說寫作、分析與指導："
    assert res_3[2]["role"] == "assistant"
    assert "Decision 1\n\nDecision 2" in res_3[2]["content"]
    assert res_3[3]["role"] == "user"
    assert res_3[3]["content"] == "User input"
    print("✅ 測試案例 3 通過：連續 assistant 合併且成功在開頭補齊 user")

    # 測試案例 4：無 system，純 assistant 開頭
    test_4 = [
        {"role": "assistant", "content": "Assistant start"}
    ]
    res_4 = normalize_messages(test_4)
    assert len(res_4) == 2, f"測試 4 失敗：實際長度 {len(res_4)}"
    assert res_4[0]["role"] == "user"
    assert res_4[1]["role"] == "assistant"
    print("✅ 測試案例 4 通過：無 system 且純 assistant 開頭時自動補足 user")

    print("\n🎉 所有測試順利通過！`normalize_messages` 運作完美無缺！")

if __name__ == "__main__":
    run_tests()


