import { state } from '../core/state.js';
import { el } from '../core/dom.js';
import { showToast } from '../core/toast.js';
import { showAgentProcessingIndicator, hideAgentProcessingIndicator } from '../pipeline/agentProcessing.js';
import { renderSubAgentStatus } from '../pipeline/status_panel.js';
import { buildGenerationTaskPayload } from '../generation/generationTaskSchema.js';
import { buildFrontendStateReference } from '../generation/generationStateMapper.js';

function buildPipelineTaskPayload({
    stage,
    taskType = 'generate',
    scope = null,
    target = {},
    instruction = '',
    userPrompt = '',
    hint = '',
    options = {},
    extra = {}
} = {}) {
    return {
        ...buildGenerationTaskPayload({
            novelId: state.currentNovelId,
            taskType,
            stage,
            scope,
            target,
            options: { stream: true, ...options },
            frontendState: buildFrontendStateReference(state),
            instruction,
            userPrompt,
            hint
        }),
        ...extra
    };
}

// 顯示/隱藏管道進度條與子代理人面板
export function showPipelineProgress(show) {
    const progressBar = document.getElementById('pipeline-progress-bar');
    if (progressBar) {
        if (show) {
            progressBar.classList.remove('hidden');
        } else {
            progressBar.classList.add('hidden');
        }
    }
    const statusPanel = document.getElementById('sub-agent-status-panel');
    if (statusPanel) {
        if (show) {
            statusPanel.style.display = 'block';
        } else {
            statusPanel.style.display = 'none';
        }
    }
}

// 心跳機制
export function startPipelineHeartbeat(novelId) {
    state.pipelineStartTime = Date.now();
    state.receiveFinishCommand = false;
    state.pipelineHeartbeatMisses = 0;
    
    if (state.heartbeatTimer) clearInterval(state.heartbeatTimer);
    state.heartbeatTimer = null;
}

function getRunningPipelineStage() {
    const statuses = state.directorSubAgentStatus || {};
    const runningStage = Object.entries(statuses).find(([, status]) => status === 'running')?.[0];
    if (runningStage) return runningStage;
    if (state.activeTab === 'plot') return 'volume_skeleton';
    return state.activeTab || 'init';
}

async function recoverPipelineFromHeartbeat(type, message) {
    if (state.pipelineRecoveryInProgress || !state.isPipelineRunning || state.receiveFinishCommand) {
        return;
    }
    state.pipelineRecoveryInProgress = true;
    stopPipelineHeartbeat();
    showToast(`⚠️ ${message}...`);

    try {
        const stage = getRunningPipelineStage();
        const userPrompt = (state.pipelinePrompt || '').trim()
            || (state.currentNovelData?.novel?.pipeline_prompt || '').trim()
            || '請根據現有設定繼續創作';

        if (typeof window.runDirectorDecision !== 'function' || typeof window.executeDirectorAction !== 'function') {
            throw new Error('總監恢復函式尚未載入');
        }

        const nextDecision = await window.runDirectorDecision(stage, userPrompt, {
            system_event: {
                type,
                failed_stage: stage,
                active_chapter_index: state.activeChapterIndex || 1,
                active_volume_index: state.activeVolumeIndex || 1,
                original_user_prompt: userPrompt,
                instruction: '前端偵測到後端管線 lock 消失或逾時。請根據 validation_report 重新派發下一個正確階段；若內容已完成，直接前往下一階段，不要讓流程停擺。'
            }
        });

        if (nextDecision && nextDecision.action) {
            state.isPipelineRunning = true;
            showPipelineProgress(true);
            await window.executeDirectorAction(nextDecision, userPrompt);
        } else {
            state.isPipelineRunning = false;
            showPipelineProgress(false);
        }
    } catch (e) {
        console.error('[PipelineHeartbeat] Recovery failed:', e);
        state.isPipelineRunning = false;
        showPipelineProgress(false);
        showToast(`管線恢復失敗: ${e.message || e}`);
    } finally {
        state.pipelineRecoveryInProgress = false;
        state.pipelineHeartbeatMisses = 0;
    }
}

export function stopPipelineHeartbeat() {
    if (state.heartbeatTimer) {
        clearInterval(state.heartbeatTimer);
        state.heartbeatTimer = null;
    }
}

export function abortPipeline() {
    state.isPipelineRunning = false;
    state.receiveFinishCommand = true;
    stopPipelineHeartbeat();
    showPipelineProgress(false);
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
    const summary = (outline.chapter_summary || outline.summary || '').toString().trim();
    const scene = (outline.scene_setting || outline.scene || outline.chapter_scene || '').toString().trim();
    const time = (outline.time_setting || '').toString().trim();
    const cliffhanger = (outline.cliffhanger || '').toString().trim();
    const events = Array.isArray(outline.events) ? outline.events.filter(e => Boolean(e && String(e).trim())).length > 0 : false;

    const hasSummary = summary.length >= 18;
    const hasContext = scene.length > 0 || time.length > 0;
    const hasProgression = events || cliffhanger.length > 0;
    return !(hasSummary && hasContext && hasProgression);
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

function buildDirectorDrivenPrompt(basePrompt, decision = null) {
    const originalPrompt = (basePrompt || '').trim();
    const sections = [];

    if (originalPrompt) {
        sections.push(`【使用者原始創作需求】\n${originalPrompt}`);
    }

    if (decision) {
        const agentPrompt = (decision.agent_prompt || decision.hint || '').trim();
        const agentContext = (decision.agent_context || '').trim();
        const userIntentSummary = (decision.user_intent_summary || '').trim();
        const reason = (decision.reason || '').trim();
        const decisionEnvelope = {
            action: decision.action || null,
            target: decision.target || null,
            volume_index: decision.volume_index ?? null,
            chapter_index: decision.chapter_index ?? null,
            task_type: decision.task_type || null,
            chapter_range: decision.chapter_range || null,
            selection: decision.selection || null
        };

        if (agentPrompt && agentPrompt !== originalPrompt) {
            sections.push(`【總監指定任務】\n${agentPrompt}`);
        }
        if (agentContext && agentContext !== originalPrompt) {
            sections.push(`【總監指定素材】\n${agentContext}`);
        }
        if (userIntentSummary) {
            sections.push(`【總監理解的作者目標】\n${userIntentSummary}`);
        }
        if (reason) {
            sections.push(`【總監決策理由】\n${reason}`);
        }
        sections.push(`【總監決策封包】\n${JSON.stringify(decisionEnvelope, null, 2)}`);
    }

    return sections.join('\n\n').trim();
}

function getWorldviewJson() {
    const raw = state.currentNovelData?.worldbuilding?.content ?? state.currentNovelData?.worldbuilding ?? '';
    if (!raw) return {};
    if (typeof raw === 'object') return raw;
    const text = String(raw);
    try {
        return JSON.parse(text);
    } catch (e) {
        const match = String(text).match(/```json\s*([\s\S]*?)\s*```/i);
        if (match?.[1]) {
            try {
                return JSON.parse(match[1]);
            } catch (_) {
                return {};
            }
        }
    }
    return {};
}

function ensureForeshadowingBatchPrompt(prompt, decision = null) {
    const existingText = [
        prompt,
        decision?.hint,
        decision?.agent_prompt,
        decision?.agent_context
    ].filter(Boolean).join('\n');
    if (/\[BATCH:\s*(foreshadowing_seeds|key_turning_points)\]/i.test(existingText)) {
        return prompt;
    }

    const worldview = getWorldviewJson();
    const seedCount = Array.isArray(worldview.foreshadowing_seeds) ? worldview.foreshadowing_seeds.length : 0;
    const turnCount = Array.isArray(worldview.key_turning_points) ? worldview.key_turning_points.length : 0;
    const targetField = seedCount < 50 ? 'foreshadowing_seeds' : (turnCount < 50 ? 'key_turning_points' : 'foreshadowing_seeds');
    const label = targetField === 'foreshadowing_seeds' ? '伏筆種子' : '關鍵轉折點';
    return [
        `[BATCH: ${targetField}]`,
        `本次只生成 ${label}，至少 50 個，輸出必須符合該批次 JSON schema。`,
        prompt || ''
    ].join('\n\n').trim();
}

function extractForeshadowingBatchTarget(prompt = '') {
    const match = String(prompt || '').match(/\[BATCH:\s*(foreshadowing_seeds|key_turning_points)\]/i);
    return match ? match[1].toLowerCase() : null;
}

// 執行單一管道階段 → 完成後詢問總監 → 根據總監決策繼續
export async function executePipelineStage(stage, userPrompt, decision = null) {
    // Confirmation gate for volumes stage in generate (non-patch) mode
    if (stage === 'volumes') {
        const chapters = state.currentNovelData?.chapters || [];
        const chapterCount = chapters.length || 0;
        const mode = decision?.mode || 'generate';
        if (chapterCount > 0 && mode !== 'patch') {
            const confirmed = window.confirm(`重新產生篇卷將刪除 ${chapterCount} 章已寫內容，確定嗎？`);
            if (!confirmed) {
                showToast('已取消篇卷重新生成');
                updatePipelineStage('volumes', 'error');
                return;
            }
        }
    }
    return _executePipelineStageWithBody(stage, userPrompt, decision);
}

async function _executePipelineStageWithBody(stage, userPrompt, decision = null) {
    return new Promise((resolve) => {
        let endpoint, body, targetTextarea;
        let agentName = '';
        const directorDrivenPrompt = buildDirectorDrivenPrompt(userPrompt, decision);
        endpoint = '/api/generation-task';
        switch (stage) {
            case 'worldview':
                body = buildPipelineTaskPayload({
                    stage: 'worldview',
                    taskType: decision?.regenerate ? 'regenerate' : 'generate',
                    instruction: directorDrivenPrompt,
                    userPrompt: directorDrivenPrompt
                });
                targetTextarea = el.editorWorldview;
                state.activeTab = 'worldview';
                agentName = 'Story Architect (故事結構架構師)';
                break;
            case 'characters':
                body = buildPipelineTaskPayload({
                    stage: 'characters',
                    taskType: decision?.regenerate ? 'regenerate' : 'generate',
                    instruction: directorDrivenPrompt,
                    userPrompt: directorDrivenPrompt
                });
                targetTextarea = el.editorCharactersJson;
                state.activeTab = 'characters';
                agentName = 'Character Designer (角色設計大師)';
                break;
            case 'foreshadowing':
                {
                    const batchPrompt = ensureForeshadowingBatchPrompt(directorDrivenPrompt, decision);
                    const targetField = extractForeshadowingBatchTarget(batchPrompt);
                    body = buildPipelineTaskPayload({
                        stage: 'foreshadowing',
                        taskType: decision?.regenerate ? 'regenerate' : 'generate',
                        instruction: batchPrompt,
                        userPrompt: batchPrompt,
                        hint: batchPrompt,
                        extra: targetField ? { target_field: targetField } : {}
                    });
                }
                targetTextarea = el.editorWorldview;
                state.activeTab = 'worldview';
                agentName = 'Foreshadowing Orchestrator (伏筆與轉折編織師)';
                break;
            case 'volumes':
                body = buildPipelineTaskPayload({
                    stage: 'volumes',
                    taskType: decision?.regenerate ? 'regenerate' : 'generate',
                    instruction: directorDrivenPrompt,
                    userPrompt: directorDrivenPrompt,
                    options: { overwrite: true },
                    extra: { confirm_wipe: true }
                });
                targetTextarea = el.editorPlotJson;
                state.activeTab = 'plot';
                agentName = 'Volumes Planner (篇卷結構規劃師)';
                break;

            case 'volume_skeleton': {
                const volIdx = decision?.volume_index || state.activeVolumeIndex || 1;
                state.activeVolumeIndex = volIdx;
                const hint = decision?.hint || '';
                const target = { volume_index: volIdx };
                const prompt = buildDirectorDrivenPrompt(hint || userPrompt, decision);
                body = buildPipelineTaskPayload({
                    stage: 'volume_skeleton',
                    taskType: decision?.regenerate ? 'regenerate' : 'generate',
                    target,
                    instruction: prompt,
                    userPrompt: prompt,
                    hint: prompt
                });
                targetTextarea = el.editorPlotJson;
                state.activeTab = 'plot';
                agentName = `Volume Skeleton Planner (第 ${volIdx} 卷完整骨架規劃)`;
                break;
            }
            case 'writer':
                body = buildPipelineTaskPayload({
                    stage: 'writer',
                    taskType: decision?.regenerate ? 'regenerate' : 'generate',
                    scope: 'chapter',
                    target: { chapter_index: state.activeChapterIndex || 1 },
                    instruction: directorDrivenPrompt,
                    userPrompt: directorDrivenPrompt
                });
                targetTextarea = el.editorProse;
                state.activeTab = 'writer';
                agentName = 'Chapter Writer (小說正文寫作作家)';
                // 標記正在寫作此章節
                state.currentlyWritingChapterIndex = state.activeChapterIndex || 1;
                break;
            case 'editor':
                body = buildPipelineTaskPayload({
                    stage: 'editor',
                    taskType: 'refine',
                    scope: 'chapter',
                    target: { chapter_index: state.activeChapterIndex || 1 },
                    instruction: directorDrivenPrompt,
                    userPrompt: directorDrivenPrompt
                });
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

        // 即時狀態跟蹤與心跳開始
        state.directorSubAgentStatus[stage] = 'running';
        renderSubAgentStatus(state.directorSubAgentStatus);
        startPipelineHeartbeat(state.currentNovelId);

        // 🚀 使用具備自動重試與對話框同步紀錄的守護引擎
        window.streamAPIWithRetry(
            endpoint,
            body,
            (delta) => {
                if (delta === null) {
                    window.updateAgentStreamOutput(stage, null, 'thinking');
                    return;
                }
                window.updateAgentStreamOutput(stage, delta, 'thinking');
            },
            (delta) => {
                if (delta === null) {
                    // Reset signal: clear the textarea/buffer
                    if (targetTextarea) {
                        if (stage === 'writer') {
                            state.writingBuffer = "";
                        }
                        targetTextarea.value = '';
                    }
                    return;
                }
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
                    // 骨架階段：偵測後端 need_characters 事件
                    if (stage === 'volume_skeleton' && delta) {
                        const rawDelta = String(delta);
                        // 嘗試解析 SSE 事件資料中的 need_characters 類型
                        const ncMatch = rawDelta.match(/\{[^}]*"type"\s*:\s*"need_characters"[^}]*\}/);
                        if (ncMatch) {
                            try {
                                const ncData = JSON.parse(ncMatch[0]);
                                if (ncData.type === 'need_characters') {
                                    state.skeletonNeedsCharacters = {
                                        volume_index: ncData.volume_index,
                                        current_char_count: ncData.current_char_count,
                                        minimum_required: ncData.minimum_required
                                    };
                                    showToast(`⚠️ 角色不足偵測：第 ${ncData.volume_index} 卷骨架需要至少 ${ncData.minimum_required} 個角色`);
                                }
                            } catch (e) { /* ignore parse errors */ }
                        }
                    }
            },
            (msg) => {
                failed = true;
                state.directorSubAgentStatus[stage] = 'error';
                renderSubAgentStatus(state.directorSubAgentStatus);
                stopPipelineHeartbeat();
                const shouldAskDirector = state.isPipelineRunning && !state.receiveFinishCommand;
                state.currentlyWritingChapterIndex = null;
                window.updateAgentStreamOutput(stage, `\n[Error: ${msg}]`);
                showToast(`${stage} Agent 執行失敗: ${msg}`);
                updatePipelineStage(stage, 'error');
                hideAgentProcessingIndicator(stage);
                
                if (shouldAskDirector) {
                    // 啟用總監自癒容錯機制，將錯誤反饋給總監
                    showToast("⚠️ 偵測到管線執行錯誤，正在請求總監進行決策自癒修正...");
                    setTimeout(async () => {
                        try {
                            state.isPipelineRunning = true;
                            showPipelineProgress(true);
                            const nextDecision = await window.runDirectorDecision(stage, userPrompt, {
                                system_event: {
                                    type: 'agent_execution_error',
                                    failed_stage: stage,
                                    failed_endpoint: endpoint,
                                    active_chapter_index: state.activeChapterIndex || 1,
                                    active_volume_index: state.activeVolumeIndex || 1,
                                    error_message: msg,
                                    original_user_prompt: userPrompt || '',
                                    director_decision_before_failure: decision || null,
                                    instruction: '前端只回報錯誤事實；請總監根據 validation_report 與工具檢視結果決定下一步，避免重複同一錯誤指令。若後端已中斷，請重新派發正確階段，而不是讓流程停擺。'
                                }
                            });
                            if (nextDecision && nextDecision.action) {
                                await window.executeDirectorAction(nextDecision, userPrompt);
                            } else {
                                state.isPipelineRunning = false;
                                showPipelineProgress(false);
                            }
                        } catch (e) {
                            console.error('[PipelineRecovery] Director recovery failed:', e);
                            state.isPipelineRunning = false;
                            showPipelineProgress(false);
                            showToast(`總監自癒重試失敗: ${e.message || e}`);
                        }
                        resolve();
                    }, 3000);
                } else {
                    resolve();
                }
            },
            async () => {
                state.currentlyWritingChapterIndex = null;
                if (failed) {
                    state.directorSubAgentStatus[stage] = 'error';
                    renderSubAgentStatus(state.directorSubAgentStatus);
                    stopPipelineHeartbeat();
                    resolve();
                    return;
                }
                state.directorSubAgentStatus[stage] = 'done';
                renderSubAgentStatus(state.directorSubAgentStatus);
                stopPipelineHeartbeat();
                updatePipelineStage(stage, 'done');
                hideAgentProcessingIndicator(stage);
                await window.loadNovelDetails(state.currentNovelId);
                // 角色生成完成後，清除 need_characters 信號（已補充完畢）
                if (stage === 'characters') {
                    state.skeletonNeedsCharacters = null;
                }
                if (state.isPipelineRunning && !state.receiveFinishCommand) {
                    showToast(`${stage} 完成，正在請求 AI 總監評估...`);
                    const nextDecision = await window.runDirectorDecision(stage);
                    if (nextDecision && nextDecision.action === 'FINISH') {
                        state.receiveFinishCommand = true;
                        abortPipeline();
                    } else {
                        await window.executeDirectorAction(nextDecision, userPrompt);
                    }
                }
                resolve();
            },
            10,
            (error, retry, maxRetries) => {
                const retryLabel = maxRetries ? `${retry}/${maxRetries}` : `${retry}`;
                window.updateAgentStreamOutput(stage, `\n[Retry ${retryLabel}: ${error}]\n`);
            },
            async () => {
                failed = false;
                state.isPipelineRunning = true;
            }
        );
    });
}
