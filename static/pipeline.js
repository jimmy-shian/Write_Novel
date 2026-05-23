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
                // onThinking – not used here
            },
            (delta) => {
                // 檢查是否仍為當前寫作的章節，防止用戶切換後的串流內容寫入錯誤位置
                if (targetTextarea && state.currentlyWritingChapterIndex === writingChapterIndex) {
                    targetTextarea.value += delta;
                    targetTextarea.scrollTop = targetTextarea.scrollHeight;
                }
            },
            (msg) => {
                failed = true;
                state.isPipelineRunning = false;
                state.currentlyWritingChapterIndex = null;
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
    const plotChapters = state.currentNovelData?.plot?.chapters || [];
    if (plotChapters.length === 0) {
        showToast('⚠️ 沒有大綱章節可寫，請先生成大綱');
        state.isPipelineRunning = false;
        return;
    }
    const totalChapters = plotChapters.length;
    showToast(`📖 共 ${totalChapters} 個大綱節點，開始逐章撰寫...`);
    const existingChapters = state.currentNovelData?.chapters || [];
    const writtenIndices = new Set(existingChapters.map(c => c.chapter_index));
    for (let i = 0; i < totalChapters; i++) {
        const chapterIndex = i + 1;
        if (writtenIndices.has(chapterIndex)) {
            updateDirectorMessage(`⏭️ 第 ${chapterIndex}/${totalChapters} 章已存在，跳過...`);
            continue;
        }
        if (!state.isPipelineRunning) {
            showToast('⏸️ 管道已暫停');
            break;
        }
        updateDirectorMessage(`✍️ 正在撰寫第 ${chapterIndex}/${totalChapters} 章...`);
        showToast(`✍️ 開始撰寫第 ${chapterIndex} 章（共 ${totalChapters} 章）`);
        state.activeTab = 'writer';
        state.activeChapterIndex = chapterIndex;
        state.currentlyWritingChapterIndex = chapterIndex; // 標記正在寫作此章節
        window.renderActiveTab();
        await new Promise((resolve) => {
            if (el.editorProse) el.editorProse.value = '';
            window.streamAPI(
                '/api/agent/write-chapter',
                { novel_id: state.currentNovelId, chapter_index: chapterIndex },
                () => {},
                (delta) => {
                    // 檢查是否仍為當前寫作的章節，防止切換後的串流內容寫入錯誤位置
                    if (el.editorProse && state.currentlyWritingChapterIndex === chapterIndex) {
                        el.editorProse.value += delta;
                        el.editorProse.scrollTop = el.editorProse.scrollHeight;
                    }
                },
                (msg) => {
                    showToast(`第 ${chapterIndex} 章寫作失敗: ${msg}`);
                    state.currentlyWritingChapterIndex = null;
                },
                async () => {
                    state.currentlyWritingChapterIndex = null;
                    await window.loadNovelDetails(state.currentNovelId);
                    resolve();
                }
            );
        });
        // 每 3 章或最後一章時，請求總監評估
        if ((chapterIndex % 3 === 0) || chapterIndex === totalChapters) {
            updateDirectorMessage(`🎬 總監正在評估第 ${chapterIndex} 章...`);
            const chapterDecision = await window.runDirectorDecision('writer');
            if (['GO_BACK_TO_WORLDVIEW', 'GO_BACK_TO_CHARACTERS', 'GO_BACK_TO_PLOT'].includes(chapterDecision.action)) {
                showToast(`⚡ 總監在第 ${chapterIndex} 章後指示回退修改...`);
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
    // 全部章節寫作完成
    updatePipelineStage('writer', 'done');
    updateDirectorMessage('🎉 全書撰寫完畢！');
    showToast('🎉 恭喜！全部章節正文已撰寫完成！');
    state.isPipelineRunning = false;
    setTimeout(() => showPipelineProgress(false), 3000);
    await window.loadNovelDetails(state.currentNovelId);
    window.selectWriterChapter(1);
}