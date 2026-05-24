import { state } from './state.js';
import { el } from './dom.js';
import { showToast } from './toast.js';
import { showAgentProcessingIndicator, hideAgentProcessingIndicator } from './agentProcessing.js';

// 顯示/隱藏管道進度條
export function showPipelineProgress(show) {
    const progressBar = document.getElementById('pipeline-progress-bar');
    if (progressBar) {
        if (show) {
            progressBar.classList.remove('hidden');
        } else {
            progressBar.classList.add('hidden');
        }
    }
}

// 更新管道階段指示器的狀態
export function updatePipelineStage(stage, status) {
    const stageIndicator = document.querySelector(`.stage-indicator[data-stage="${stage}"]`);
    if (!stageIndicator) return;
    
    stageIndicator.classList.remove('pending', 'running', 'done', 'error');
    if (status) {
        stageIndicator.classList.add(status);
    }
    
    const statusDiv = stageIndicator.querySelector('.stage-status');
    if (statusDiv) {
        if (status === 'running') {
            statusDiv.innerHTML = '<span class="loader-spinner"></span>';
        } else if (status === 'done') {
            statusDiv.textContent = '✓';
        } else if (status === 'error') {
            statusDiv.textContent = '✗';
        } else {
            statusDiv.textContent = '';
        }
    }
}

// 更新總監訊息
export function updateDirectorMessage(message) {
    const directorMsg = document.getElementById('director-message');
    if (directorMsg) {
        directorMsg.textContent = message;
    }
}

// 在 textarea 中顯示「生成中...」告示
export function showGeneratingIndicator(tabName) {
    let textarea = null;
    if (tabName === 'worldview') {
        textarea = el.editorWorldview;
    } else if (tabName === 'characters') {
        textarea = el.editorCharactersJson;
    } else if (tabName === 'plot') {
        textarea = el.editorPlotJson;
    } else if (tabName === 'writer') {
        textarea = el.editorProse;
    }
    if (textarea) {
        textarea.value = '🔄 AI 正在生成中，請稍候...\n\n';
        textarea.disabled = true;
    }
}

function getChapterIndex(outline, fallbackIndex) {
    const raw = outline?.chapter_index;
    const parsed = Number(raw);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : fallbackIndex;
}

function isPlaceholderOutline(outline) {
    if (!outline || typeof outline !== 'object') return true;
    const parts = [
        outline.title,
        outline.summary,
        outline.purpose,
        outline.cliffhanger,
        outline.scene,
        ...(Array.isArray(outline.events)
            ? outline.events.flatMap(event => typeof event === 'object'
                ? [event.scene, event.action, event.consequence]
                : [String(event)])
            : [])
    ].filter(Boolean).join('\n').toLowerCase();

    return [
        '保底',
        '占位',
        '佔位',
        'placeholder',
        '命運波折之章',
        '推進核心衝突',
        '推動大綱情節發展',
        '主角面臨新考驗'
    ].some(token => parts.includes(token.toLowerCase()));
}

// 執行單一管道階段 → 完成後詢問總監 → 根據總監決策繼續
export async function executePipelineStage(stage, userPrompt) {
    return new Promise((resolve) => {
        let endpoint, body, targetTextarea;
        let agentName = '';
        switch (stage) {
            case 'worldview':
                endpoint = '/api/agent/story-architect';
                body = { novel_id: state.currentNovelId, user_prompt: userPrompt };
                targetTextarea = el.editorWorldview;
                state.activeTab = 'worldview';
                agentName = 'Story Architect (故事結構架構師)';
                break;
            case 'characters':
                endpoint = '/api/agent/character-designer';
                body = { novel_id: state.currentNovelId, user_prompt: userPrompt };
                targetTextarea = el.editorCharactersJson;
                state.activeTab = 'characters';
                agentName = 'Character Designer (角色設計大師)';
                break;
            case 'plot':
                endpoint = '/api/agent/plot-planner';
                body = { novel_id: state.currentNovelId, user_prompt: userPrompt };
                targetTextarea = el.editorPlotJson;
                state.activeTab = 'plot';
                agentName = 'Plot Planner (章節劇情規劃師)';
                break;
            case 'writer':
                endpoint = '/api/agent/write-chapter';
                body = { novel_id: state.currentNovelId, chapter_index: state.activeChapterIndex || 1 };
                targetTextarea = el.editorProse;
                state.activeTab = 'writer';
                agentName = 'Chapter Writer (小說正文寫作作家)';
                // 標記正在寫作此章節
                state.currentlyWritingChapterIndex = state.activeChapterIndex || 1;
                break;
            default:
                resolve();
                return;
        }
        window.renderActiveTab();
        if (targetTextarea) targetTextarea.value = '';
        showToast(`🚀 正在啟動 ${stage} Agent...`);
        showAgentProcessingIndicator(stage, agentName);
        let failed = false;
        // 保存寫作章節索引用於閉包
        const writingChapterIndex = state.currentlyWritingChapterIndex;
        window.streamAPI(
            endpoint,
            body,
            (delta) => {
                window.updateAgentStreamOutput(stage, delta);
            },
            (delta) => {
                // 檢查是否仍為當前寫作的章節，防止用戶切換後的串流內容寫入錯誤位置
                if (targetTextarea && state.currentlyWritingChapterIndex === writingChapterIndex) {
                    targetTextarea.value += delta;
                    targetTextarea.scrollTop = targetTextarea.scrollHeight;
                }
                window.updateAgentStreamOutput(stage, delta);
            },
            (msg) => {
                failed = true;
                state.isPipelineRunning = false;
                state.currentlyWritingChapterIndex = null;
                window.updateAgentStreamOutput(stage, `\n[Error: ${msg}]`);
                showToast(`${stage} Agent 執行失敗: ${msg}`);
                updatePipelineStage(stage, 'error');
                hideAgentProcessingIndicator(stage);
                resolve();
            },
            async () => {
                state.currentlyWritingChapterIndex = null;
                if (failed) return;
                updatePipelineStage(stage, 'done');
                hideAgentProcessingIndicator(stage);
                await window.loadNovelDetails(state.currentNovelId);
                if (state.isPipelineRunning) {
                    showToast(`${stage} 完成，正在請求 AI 總監評估...`);
                    const nextDecision = await window.runDirectorDecision(stage);
                    await window.executeDirectorAction(nextDecision, userPrompt);
                }
                resolve();
            }
        );
    });
}

// 自動撰寫所有章節正文（按大綱順序，每章寫完後詢問總監）
export async function writeAllChaptersSequentially(userPrompt) {
    const plotChapters = [...(state.currentNovelData?.plot?.chapters || [])]
        .sort((a, b) => getChapterIndex(a, 0) - getChapterIndex(b, 0));
    if (plotChapters.length === 0) {
        showToast('⚠️ 沒有大綱章節可寫，請先生成大綱');
        state.isPipelineRunning = false;
        return;
    }

    const invalidOutlines = plotChapters.filter(isPlaceholderOutline);
    const dirtyVolumes = (state.currentNovelData?.volumes || [])
        .filter(v => Number(v.is_dirty || 0) === 1);
    if (invalidOutlines.length > 0 || dirtyVolumes.length > 0) {
        updateDirectorMessage('📋 偵測到髒卷或佔位大綱，先回到 Plot Planner 重新對齊...');
        showToast('📋 大綱需要回退修復，正在重新規劃後再寫正文');
        updatePipelineStage('writer', 'pending');
        updatePipelineStage('plot', 'running');
        await executePipelineStage('plot', userPrompt);
        return;
    }

    const totalChapters = plotChapters.length;
    showToast(`📖 共 ${totalChapters} 個大綱節點，開始逐章撰寫...`);
    const existingChapters = state.currentNovelData?.chapters || [];
    
    // 精準過濾出真正有效且一致的正文章節索引
    const writtenIndices = new Set(
        existingChapters
            .filter(c => {
                const content = c.content || '';
                const isPlaceholder = content.includes('保底') || 
                                      content.includes('占位') || 
                                      content.trim().length < 100;
                const isDirty = c.is_dirty === 1 || c.is_dirty === true;
                return !isPlaceholder && !isDirty;
            })
            .map(c => Number(c.chapter_index))
    );
    
    for (let i = 0; i < totalChapters; i++) {
        const outline = plotChapters[i];
        const position = i + 1;
        const chapterIndex = getChapterIndex(outline, i + 1);
        if (writtenIndices.has(chapterIndex)) {
            updateDirectorMessage(`⏭️ 第 ${chapterIndex} 章已存在且內容完整，跳過... (${position}/${totalChapters})`);
            continue;
        }
        if (!state.isPipelineRunning) {
            showToast('⏸️ 管道已暫停');
            break;
        }
        updateDirectorMessage(`✍️ 正在撰寫第 ${chapterIndex} 章... (${position}/${totalChapters})`);
        showToast(`✍️ 開始撰寫第 ${chapterIndex} 章（大綱節點 ${position}/${totalChapters}）`);
        state.activeTab = 'writer';
        state.activeChapterIndex = chapterIndex;
        state.currentlyWritingChapterIndex = chapterIndex; // 標記正在寫作此章節
        window.renderActiveTab();
        
        // Show processing indicator with terminal log for the writer stage
        showAgentProcessingIndicator('writer', `Chapter Writer (第 ${chapterIndex} 章寫作中)`);
        
        await new Promise((resolve) => {
            if (el.editorProse) el.editorProse.value = '';
            window.streamAPI(
                '/api/agent/write-chapter',
                { novel_id: state.currentNovelId, chapter_index: chapterIndex },
                (delta) => {
                    window.updateAgentStreamOutput('writer', delta);
                },
                (delta) => {
                    // 檢查是否仍為當前寫作的章節，防止切換後的串流內容寫入錯誤位置
                    if (el.editorProse && state.currentlyWritingChapterIndex === chapterIndex) {
                        el.editorProse.value += delta;
                        el.editorProse.scrollTop = el.editorProse.scrollHeight;
                    }
                    window.updateAgentStreamOutput('writer', delta);
                },
                (msg) => {
                    window.updateAgentStreamOutput('writer', `\n[Error: ${msg}]`);
                    showToast(`第 ${chapterIndex} 章寫作失敗: ${msg}`);
                    state.currentlyWritingChapterIndex = null;
                    hideAgentProcessingIndicator('writer');
                    resolve();
                },
                async () => {
                    state.currentlyWritingChapterIndex = null;
                    hideAgentProcessingIndicator('writer');
                    await window.loadNovelDetails(state.currentNovelId);
                    resolve();
                }
            );
        });
        // 每 3 章或最後一章時，請求總監評估
        if ((position % 3 === 0) || position === totalChapters) {
            updateDirectorMessage(`🎬 總監正在評估第 ${chapterIndex} 章...`);
            const chapterDecision = await window.runDirectorDecision('writer');
            if (['GO_BACK_TO_WORLDVIEW', 'GO_BACK_TO_CHARACTERS', 'GO_BACK_TO_PLOT'].includes(chapterDecision.action)) {
                showToast(`⚡ 總監在第 ${chapterIndex} 章後指示回退修改...`);
                await window.executeDirectorAction(chapterDecision, userPrompt);
                return;
            }
            if (chapterDecision.action === 'CONTINUE' && (chapterDecision.target === 'plot' || chapterDecision.target === '章節大綱')) {
                showToast('📋 總監評估後指示：當前批次已完成，繼續生成下一階段章節大綱...');
                await window.executeDirectorAction(chapterDecision, userPrompt);
                return;
            }
            if (chapterDecision.action === 'WAIT_USER') {
                showToast('⏸️ 總監要求暫停，請確認後繼續');
                state.isPipelineRunning = false;
                return;
            }
        }
    }
    
    // 檢查是否還有未規劃的篇卷 (滾動大綱規劃)
    const volumes = state.currentNovelData?.volumes || [];
    let hasUnplannedVolumes = false;
    try {
        hasUnplannedVolumes = volumes.some(v => {
            if (!v.chapters_outline) return true;
            const parsed = JSON.parse(v.chapters_outline);
            return !Array.isArray(parsed) || parsed.length === 0;
        });
    } catch (err) {
        console.error('Error checking unplanned volumes:', err);
        hasUnplannedVolumes = volumes.some(v => !v.chapters_outline);
    }

    if (hasUnplannedVolumes && state.isPipelineRunning) {
        updateDirectorMessage('📋 偵測到仍有未規劃大綱的篇卷，即將全自動啟動下一階段大綱規劃與伏筆對齊流程...');
        showToast('📋 偵測到未完篇卷，即將開始規劃下一波章節大綱...');
        updatePipelineStage('writer', 'done');
        updatePipelineStage('plot', 'running');
        await executePipelineStage('plot', userPrompt);
        return;
    }
    
    // 全部章節寫作完成
    updatePipelineStage('writer', 'done');
    updateDirectorMessage('🎉 全書撰寫完畢！正在召開 AI 圓桌論壇...');
    showToast('🎉 恭喜！全部章節已撰寫完成！正在召開圓桌復盤會議...');
    
    try {
        // 向總監對話區追加進度條
        window.appendChatMessage('system', '🎬 正在召開 AI 圓桌復盤論壇，集結 5 位設定專家與創意總監，提煉本次創作的終極金律與避坑指南，此報告將儲存在外部檔案中，請稍候...');
        
        const retroResult = await window.requestAPI(`/api/novels/${state.currentNovelId}/retrospective`, 'POST');
        if (retroResult && retroResult.status === 'success') {
            window.appendChatMessage('assistant', `🏆 **AI 復盤圓桌論壇暨創作避坑金律說明書產出完畢！**\n\n報告已成功強制以 UTF-8 儲存至外部安全路徑：\n📁 \`${retroResult.filepath}\`\n\n以下是圓桌會議摘錄：\n\n${retroResult.markdown.slice(0, 3000)}...\n\n*(完整報告請點擊外部 Markdown 檔案閱讀，該檔案在開發與 DB 清空期間依然會永久保留)*`);
            showToast('🏆 創作避坑金律產出完畢！已安全儲存於外部目錄');
        }
    } catch (retroErr) {
        console.error('Failed to run round-table retrospective:', retroErr);
        showToast('圓桌復盤會議召開失敗，但小說正文已生成完畢！');
    }
    
    state.isPipelineRunning = false;
    setTimeout(() => showPipelineProgress(false), 3000);
    await window.loadNovelDetails(state.currentNovelId);
    window.selectWriterChapter(getChapterIndex(plotChapters[0], 1));
}
