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
export async function executePipelineStage(stage, userPrompt, decision = null) {
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

            case 'volume_skeleton': {
                const volIdx = decision?.volume_index || state.activeVolumeIndex || 1;
                state.activeVolumeIndex = volIdx;
                const hint = decision?.hint || '';
                
                endpoint = '/api/agent/volume-skeleton';
                body = { 
                    novel_id: state.currentNovelId, 
                    volume_index: volIdx, 
                    user_prompt: hint || userPrompt 
                };
                targetTextarea = el.editorPlotJson;
                state.activeTab = 'plot';
                agentName = `Volume Skeleton Planner (第 ${volIdx} 卷骨架規劃)`;
                break;
            }
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




