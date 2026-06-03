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

function isShallowOutline(outline) {
    if (!outline || typeof outline !== 'object') return true;
    const summary = (outline.summary || outline.chapter_summary || outline.brief_summary || '').toString().trim();
    const scene = (outline.scene || outline.chapter_scene || '').toString().trim();
    const purpose = (outline.purpose || '').toString().trim();
    const cliffhanger = (outline.cliffhanger || '').toString().trim();
    const events = Array.isArray(outline.events) ? outline.events.filter(e => Boolean(e && String(e).trim())).length > 0 : false;

    const hasSummary = summary.length >= 20;
    const hasExtraDetail = scene.length >= 20 || purpose.length >= 20 || cliffhanger.length >= 20 || events;
    return !(hasSummary && hasExtraDetail);
}

function getPlotReviewBatchSize() {
    const raw = state.settingsData?.plot?.plot_review_batch_size
        ?? state.settingsData?.global?.plot_review_batch_size
        ?? state.plotReviewBatchSize
        ?? 3;
    const parsed = Number.parseInt(raw, 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 3;
}

function isDetailedOutline(outline) {
    const events = outline?.events || outline?.scenes;
    return Array.isArray(events) && events.length > 0;
}

function getDetailedPlotChapterCount() {
    const chapters = state.currentNovelData?.plot?.chapters || [];
    return chapters.filter(isDetailedOutline).length;
}

function getExpectedPlotChapterCount(fallbackChapterIndex) {
    const vols = state.currentNovelData?.volumes || [];
    const planned = vols.reduce((sum, v) => {
        const count = Number.parseInt(v.chapter_count, 10);
        return sum + (Number.isFinite(count) && count > 0 ? count : 0);
    }, 0);
    if (planned > 0) return planned;

    const skeletonMax = vols.reduce((maxIdx, v) => {
        try {
            const parsed = typeof v.chapters_outline === 'string' ? JSON.parse(v.chapters_outline) : v.chapters_outline;
            if (!Array.isArray(parsed)) return maxIdx;
            return Math.max(maxIdx, ...parsed.map(ch => Number.parseInt(ch.chapter_index ?? ch.chapter ?? ch.chapter_number ?? ch.index ?? ch.id, 10) || 0));
        } catch (e) {
            return maxIdx;
        }
    }, 0);
    return skeletonMax || (fallbackChapterIndex + getPlotReviewBatchSize());
}

function shouldReviewPlotBatch(currentChapterIndex) {
    return true;
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
            case 'volumes':
                endpoint = '/api/agent/volumes-planner';
                body = { novel_id: state.currentNovelId, user_prompt: userPrompt };
                targetTextarea = el.editorPlotJson;
                state.activeTab = 'plot';
                agentName = 'Volumes Planner (篇卷結構規劃師)';
                break;

            case 'volume_skeleton':
                endpoint = '/api/agent/volume-skeleton';
                targetTextarea = el.editorPlotJson;
                state.activeTab = 'plot';
                agentName = 'Volume Skeleton Planner';
                // void window.generateAllVolumeSkeletons(userPrompt);
                // resolve();
                window.generateAllVolumeSkeletons(userPrompt).then(() => resolve());
                return;
            case 'writer':
                endpoint = '/api/agent/write-chapter';
                body = { novel_id: state.currentNovelId, chapter_index: state.activeChapterIndex || 1 };
                targetTextarea = el.editorProse;
                state.activeTab = 'writer';
                agentName = 'Chapter Writer (小說正文寫作作家)';
                // 標記正在寫作此章節
                state.currentlyWritingChapterIndex = state.activeChapterIndex || 1;
                break;
            case 'editor':
                endpoint = '/api/agent/edit-chapter';
                body = { novel_id: state.currentNovelId, chapter_index: state.activeChapterIndex || 1 };
                targetTextarea = el.editorProse;
                state.activeTab = 'editor';
                agentName = 'Chapter Editor (小說正文編輯作家)';
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
        // Initialize buffer
        if (stage === 'writer') {
            state.writingBuffer = "";
        }
        // 🚀 使用具備 10 次自動重試與對話框同步紀錄的守護引擎
        window.streamAPIWithRetry(
            endpoint,
            body,
            (delta) => {
                window.updateAgentStreamOutput(stage, delta, 'thinking');
            },
            (delta) => {
                if (targetTextarea) {
                    if (stage === 'writer') {
                        state.writingBuffer = (state.writingBuffer || "") + delta;
                        
                        let proseVal = state.writingBuffer;
                        let thinkingVal = "";
                        const specialWords = ["[START_OF_PROSE]", "[正文開始]"];
                        let splitIndex = -1;
                        for (const sw of specialWords) {
                            const idx = state.writingBuffer.indexOf(sw);
                            if (idx !== -1) {
                                splitIndex = idx;
                                thinkingVal = state.writingBuffer.substring(0, idx).trim();
                                proseVal = state.writingBuffer.substring(idx + sw.length).trim();
                                break;
                            }
                        }
                        if (splitIndex === -1) {
                            thinkingVal = state.writingBuffer;
                            proseVal = "";
                        }
                        
                        if (state.activeChapterIndex === writingChapterIndex) {
                            targetTextarea.value = proseVal;
                            if (typeof window.smartScrollToBottom === 'function') {
                                window.smartScrollToBottom(targetTextarea, false);
                            } else {
                                targetTextarea.scrollTop = targetTextarea.scrollHeight;
                            }
                            
                            // Update thinking preview real-time
                            const thinkingPreviewText = document.getElementById('chapter-thinking-preview-text');
                            const thinkingPreview = document.getElementById('chapter-thinking-preview');
                            if (thinkingPreview && thinkingPreviewText && thinkingVal.trim()) {
                                thinkingPreview.classList.remove('hidden');
                                thinkingPreviewText.textContent = thinkingVal;
                            }
                        }
                    } else {
                        targetTextarea.value += delta;
                        if (typeof window.smartScrollToBottom === 'function') {
                            window.smartScrollToBottom(targetTextarea, false);
                        } else {
                            targetTextarea.scrollTop = targetTextarea.scrollHeight;
                        }
                    }
                }
                window.updateAgentStreamOutput(stage, delta, 'content');
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
            state.writingBuffer = "";
            // 🚀 使用具備 10 次自動重試的守護引擎撰寫章節
            window.streamAPIWithRetry(
                '/api/agent/write-chapter',
                { novel_id: state.currentNovelId, chapter_index: chapterIndex },
                (delta) => {
                    window.updateAgentStreamOutput('writer', delta, 'thinking');
                },
                (delta) => {
                    state.writingBuffer = (state.writingBuffer || "") + delta;
                    
                    let proseVal = state.writingBuffer;
                    let thinkingVal = "";
                    const specialWords = ["[START_OF_PROSE]", "[正文開始]"];
                    let splitIndex = -1;
                    for (const sw of specialWords) {
                        const idx = state.writingBuffer.indexOf(sw);
                        if (idx !== -1) {
                            splitIndex = idx;
                            thinkingVal = state.writingBuffer.substring(0, idx).trim();
                            proseVal = state.writingBuffer.substring(idx + sw.length).trim();
                            break;
                        }
                    }
                    if (splitIndex === -1) {
                        thinkingVal = state.writingBuffer;
                        proseVal = "";
                    }
                    
                    if (el.editorProse && state.activeChapterIndex === chapterIndex) {
                        el.editorProse.value = proseVal;
                        if (typeof window.smartScrollToBottom === 'function') {
                            window.smartScrollToBottom(el.editorProse, false);
                        } else {
                            el.editorProse.scrollTop = el.editorProse.scrollHeight;
                        }
                        
                        // Update thinking preview real-time
                        const thinkingPreviewText = document.getElementById('chapter-thinking-preview-text');
                        const thinkingPreview = document.getElementById('chapter-thinking-preview');
                        if (thinkingPreview && thinkingPreviewText && thinkingVal.trim()) {
                            thinkingPreview.classList.remove('hidden');
                            thinkingPreviewText.textContent = thinkingVal;
                        }
                    }
                    window.updateAgentStreamOutput('writer', delta, 'content');
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
        // 🎬 逐章校驗：每寫完一章，即刻啟動 AI 總監連貫性校驗與決策
        updateDirectorMessage(`🎬 總監正在對第 ${chapterIndex} 章正文進行寫作連貫性校驗與決策...`);
        const chapterDecision = await window.runDirectorDecision('writer');
        
        // 判斷是否為修補、回退或暫停等非常規動作，如果是則立刻退出寫作迴圈，由 executeDirectorAction 進行修補
        const normalActions = ['CONTINUE', 'WRITE_ALL_CHAPTERS'];
        const nextTarget = (chapterDecision.target || '').toString().trim().toLowerCase();
        
        if (!normalActions.includes(chapterDecision.action) || nextTarget) {
            showToast(`⚠️ 總監在第 ${chapterIndex} 章後下達非連續指令 [${chapterDecision.action}]，啟動修補/回退管線...`);
            await window.executeDirectorAction(chapterDecision, userPrompt);
            return; // 立即 return 退出 batch 寫作迴圈，防止連帶錯誤！
        } else {
            showToast(`✅ 第 ${chapterIndex} 章連貫性校驗放行，繼續下一章寫作。`);
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
        updateDirectorMessage('📋 偵測到仍有未規劃大綱的篇卷，即將全自動啟動下一階段大綱規劃與流程...');
        showToast('📋 偵測到未完篇卷，即將開始規劃下一波章節大綱...');
        await window.generateAllVolumeSkeletons(userPrompt);
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


