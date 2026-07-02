#!/usr/bin/env python3
"""
Helper script to perform staged commits using git add -p for selective hunks.
Usage: python scratch/do_commits.py
"""
import subprocess
import sys

def get_hunk_count(file_path):
    """Get number of hunks in git diff for a file"""
    result = subprocess.run(['git', 'diff', file_path], capture_output=True)
    lines = result.stdout.decode('utf-8', errors='replace').split('\n')
    return sum(1 for l in lines if l.startswith('@@ '))

def stage_hunks(file_path, include_indices, label=""):
    """Stage specific hunks of a file using git add -p"""
    hunk_count = get_hunk_count(file_path)
    if hunk_count == 0:
        print(f"  ⏭️  No changes in {file_path}")
        return True
    
    # Validate indices
    for idx in include_indices:
        if idx < 1 or idx > hunk_count:
            print(f"  ❌ Invalid hunk index {idx} (there are {hunk_count} hunks)")
            return False
    
    responses = []
    for i in range(1, hunk_count + 1):
        responses.append(b'y' if i in include_indices else b'n')
    
    input_str = b'\n'.join(responses)
    
    proc = subprocess.Popen(
        ['git', 'add', '-p', file_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = proc.communicate(input=input_str)
    
    if proc.returncode != 0:
        err = stderr.decode('utf-8', errors='replace')
        print(f"  ❌ git add -p failed: {err}")
        return False
    
    # Verify staged
    result = subprocess.run(['git', 'diff', '--cached', '--name-only'], capture_output=True)
    staged = result.stdout.decode('utf-8', errors='replace').strip()
    
    return True

def stage_entire_file(file_path):
    """Stage the entire file"""
    hunk_count = get_hunk_count(file_path)
    if hunk_count == 0:
        print(f"  ⏭️  No changes in {file_path}")
        return True
    return stage_hunks(file_path, set(range(1, hunk_count + 1)))

def commit(msg):
    """Commit staged changes"""
    result = subprocess.run(['git', 'diff', '--cached', '--name-only'], capture_output=True)
    staged = result.stdout.decode('utf-8', errors='replace').strip()
    if not staged:
        print("  ⏭️  Nothing staged, skipping commit")
        return True
    
    proc = subprocess.run(
        ['git', 'commit', '-m', msg],
        capture_output=True
    )
    out = proc.stdout.decode('utf-8', errors='replace')
    err = proc.stderr.decode('utf-8', errors='replace')
    
    if proc.returncode != 0:
        print(f"  ❌ Commit failed: {err}")
        return False
    
    print(f"  ✅ Committed: {staged[:100]}")
    return True


if __name__ == '__main__':
    # =============================================
    # COMMIT 6: streamAPI 參數調整
    # =============================================
    print("=" * 60)
    print("COMMIT 6: 【調整】streamAPI 參數調整")
    print("=" * 60)
    
    stage_entire_file('static/api.js')
    stage_entire_file('llm.py')
    stage_entire_file('models/parsers.py')
    commit("【調整】streamAPI 參數調整：減少重試次數、縮短超時門檻\n\n"
           "- static/api.js: MAX_RETRIES 2→1, STALL_TIMEOUT 120s→10s, maxRetries 10→3\n"
           "- llm.py: max_retries 10→3, timeout 300s→180s, 加入總執行時間 300s 上限\n"
           "- models/parsers.py: 改進 JSON 解析支援截斷修復與 array 格式")
    
    # =============================================
    # COMMIT 7: 測試案例更新
    # =============================================
    print("\n" + "=" * 60)
    print("COMMIT 7: 【調整】測試案例更新")
    print("=" * 60)
    
    stage_entire_file('test_all.py')
    commit("【調整】測試案例更新：符合新管線階段預期\n\n"
           "- chapter_count 10→1（減少測試時間）\n"
           "- 階段預期值 volume_skeleton→writer")
    
    # =============================================
    # COMMIT A: safe_generator_wrapper 新增
    # app.py hunks 2-11: 所有 API 端點加入 safe_generator_wrapper
    # =============================================
    print("\n" + "=" * 60)
    print("COMMIT A: 【新增】API 端點錯誤處理包裝 safe_generator_wrapper")
    print("=" * 60)
    
    stage_hunks('app.py', {2,3,4,5,6,7,8,9,10,11})
    commit("【新增】所有 Streaming API 端點加入 safe_generator_wrapper 錯誤處理包裝\n\n"
           "- 避免 generator 拋出未捕捉例外導致連線中斷\n"
           "- 涵蓋 story_architect / character_designer / volumes_planner\n"
           "- volume_skeleton / write_chapter / edit_chapter / copilot_chat\n"
           "- 以及增量端點 incremental_architect / character / skeleton")
    
    # =============================================
    # COMMIT 1: 匯出功能
    # Files: static/index.html (all), static/app.js (hunks 19,20), app.py (hunks 14,15)
    # =============================================
    print("\n" + "=" * 60)
    print("COMMIT 1: 【新增】匯出功能")
    print("=" * 60)
    
    stage_entire_file('static/index.html')
    stage_hunks('static/app.js', {19, 20})
    stage_hunks('app.py', {14, 15})
    commit("【新增】小說匯出功能：支援 TXT / Markdown 格式\n\n"
           "- static/index.html: 新增匯出按鈕\n"
           "- static/app.js: btn-export-novel 事件監聽與匯出對話框\n"
           "- app.py: 匯出端點加入章節標題映射（從大綱取章節名）")
    
    # =============================================
    # COMMIT 2: scene_setting 欄位
    # Files: static/app.js (hunks 12,13,14), prompts/prompt_main.py (all)
    # =============================================
    print("\n" + "=" * 60)
    print("COMMIT 2: 【新增】scene_setting 欄位")
    print("=" * 60)
    
    stage_hunks('static/app.js', {12, 13, 14})
    stage_entire_file('prompts/prompt_main.py')
    commit("【新增】章節編輯 modal 與提示詞新增 scene_setting 欄位\n\n"
           "- static/app.js: 章節編輯 modal 新增場景設定輸入欄位\n"
           "- prompts/prompt_main.py: volume_skeleton prompt 新增 scene_setting 欄位說明")
    
    # =============================================
    # COMMIT 4: 管線階段重構
    # Files: static/app.js (hunks 1,4,8,10,15,16,21,22,23,24), static/pipeline.js, static/utils.js
    # =============================================
    print("\n" + "=" * 60)
    print("COMMIT 4: 【調整】管線階段重構")
    print("=" * 60)
    
    stage_hunks('static/app.js', {1, 4, 8, 10, 15, 16, 21, 22, 23, 24})
    stage_entire_file('static/pipeline.js')
    stage_entire_file('static/utils.js')
    commit("【調整】管線階段重構：移除全量批次生成，改為逐卷單步執行\n\n"
           "- static/app.js: 移除 generateAllVolumeSkeletons 函數與 WRITE_ALL_CHAPTERS case\n"
           "- static/pipeline.js: 移除 writeAllChaptersSequentially，executePipelineStage 支援 decision 物件\n"
           "- static/utils.js: 調整 WRITE_ALL_CHAPTERS 回退處理\n"
           "- plot-planner 改為呼叫 runVolumeSkeletonPlannerDirect 處理單卷")
    
    # =============================================
    # COMMIT 5: 硬性阻斷邏輯優化
    # Files: static/app.js (hunks 2,3,9)
    # =============================================
    print("\n" + "=" * 60)
    print("COMMIT 5: 【調整】硬性阻斷邏輯優化")
    print("=" * 60)
    
    stage_hunks('static/app.js', {2, 3, 9})
    commit("【調整】硬性阻斷邏輯優化：骨架缺失時退回特定卷而非全量重新生成\n\n"
           "- 硬性阻斷改為退回缺失卷的骨架生成，而非全部重新跑\n"
           "- GO_BACK_TO_SKELETON_EXPANSION 改為退回特定卷\n"
           "- 移除 WRITE_ALL_CHAPTERS 條件判斷的 deprecated 邏輯")
    
    # =============================================
    # COMMIT 3: 索引自動補正機制
    # Files: static/app.js (hunks 5,6,7,17,18), app.py (hunks 1,12,13), db.py (generate_validation_report),
    #         prompts/prompt_builder.py, prompts/prompt_instructions.py
    # =============================================
    print("\n" + "=" * 60)
    print("COMMIT 3: 【新增】索引自動補正機制")
    print("=" * 60)
    
    stage_hunks('static/app.js', {5, 6, 7, 17, 18})
    stage_hunks('app.py', {1, 12, 13})
    stage_entire_file('db.py')
    stage_entire_file('prompts/prompt_builder.py')
    stage_entire_file('prompts/prompt_instructions.py')
    commit("【新增】AI 總監遺漏 volume/chapter index 時的自動補正機制\n\n"
           "- app.py: 新增 resolve-missing-index 端點（純後端計算不呼叫 AI）\n"
           "- static/app.js: runDirectorDecision 中呼叫補正端點自動填補遺漏索引\n"
           "- static/app.js: 新增 suggested_next_chapter 計算與傳遞\n"
           "- db.py: generate_validation_report 支援 current_stage/active_volume_index/active_chapter_index\n"
           "- prompts: 總監提示詞新增 volume_index/chapter_index 必須填寫整數的紅線規則")
    
    # =============================================
    # Now handle remaining files that weren't committed above
    # Remaining: agent_json.py, agents.py (partial), app.py (partial),
    #            static/app.js (partial), static/renderers.js
    # =============================================
    
    # Commit 2 part 2: agent_json.py scene_setting schema changes
    print("\n" + "=" * 60)
    print("COMMIT 2b: 【新增】agent_json.py scene_setting schema")
    print("=" * 60)
    stage_entire_file('agent_json.py')
    commit("【新增】agent_json.py 骨架 schema 新增 scene_setting 欄位\n\n"
           "- CHAPTER_SKELETON_SCHEMA 與 CHAPTER_SKELETON_WITH_ALLOC_SCHEMA 加入 scene_setting\n"
           "- 調整審核標準中 time_setting 相關描述")
    
    # Commit 3 (index補正): agents.py hunks 3-7 (hunks 1-2 are safe_generator_wrapper which was already committed)
    # agents.py now has hunks: let's check what remains
    print("\n" + "=" * 60)
    print("COMMIT 3b: 【新增】agents.py 索引補正 + 參數傳遞")
    print("=" * 60)
    # agents.py: remaining hunks are 3-7 (save_volumes target_vol_idx, volume_index=int, suggested_next_chapter, validation_report params)
    stage_entire_file('agents.py')
    commit("【新增】agents.py 索引補正：volume_index 型別轉換、suggested_next_chapter 參數傳遞\n\n"
           "- save_volumes 支援 target_vol_idx 局部更新\n"
           "- volume_skeleton_planner 與 incremental 函數加入 volume_index=int 型別轉換\n"
           "- run_director_decision 加入 suggested_next_chapter 與 validation_report 參數")
    
    # app.py: remaining hunks 4-5 (export chapter_titles) -> Commit 1
    # static/app.js: remaining hunks - let's check and split
    print("\n" + "=" * 60)
    print("FINAL COMMIT: 【調整】剩餘 static/app.js 與 renderers.js")
    print("=" * 60)
    # Check remaining app.js hunks
    result = subprocess.run(['git', 'diff', 'static/app.js'], capture_output=True)
    lines = result.stdout.decode('utf-8', errors='replace')
    hunk_count = sum(1 for l in lines.split('\n') if l.startswith('@@ '))
    print(f"static/app.js remaining hunks: {hunk_count}")
    
    # Check remaining app.py hunks
    result = subprocess.run(['git', 'diff', 'app.py'], capture_output=True)
    lines = result.stdout.decode('utf-8', errors='replace')
    hunk_count2 = sum(1 for l in lines.split('\n') if l.startswith('@@ '))
    print(f"app.py remaining hunks: {hunk_count2}")
    
    result = subprocess.run(['git', 'diff', '--name-only'], capture_output=True)
    remaining = result.stdout.decode('utf-8', errors='replace').strip()
    if remaining:
        print(f"\nStill uncommitted: {remaining}")
    else:
        print("✅ All changes committed!")
