import { state } from './state.js';
import { el } from './dom.js';
import { showToast } from './toast.js';
import { requestAPI, streamAPI } from './api.js';
import { parseWorldviewJSON, showCustomConfirm, stripBulletPrefix, formatDate, renderMarkdown, parseDirectorDecisionText } from './utils.js';
import { renderActiveTab, renderWorldviewTab, renderWorldviewSections, renderWorldviewSection, renderCharactersTab, renderPlotTab, renderWriterTab, selectWriterChapter, renderActiveChapter, renderChatMessages, appendChatMessage, applySubSectionVisibility, getSubSectionCount } from './renderers.js';
import { loadNovels, loadNovelDetails, clearWorkspace, renderNovelsList } from './novelLifecycle.js';
import { loadSettings, loadAgentConfigFields, saveCurrentAgentSettings } from './settings.js';
import { showAgentProcessingIndicator, hideAgentProcessingIndicator, hideAllAgentProcessingIndicators } from './agentProcessing.js';
import { showPipelineProgress, updatePipelineStage, updateDirectorMessage, showGeneratingIndicator, executePipelineStage, writeAllChaptersSequentially } from './pipeline.js';


// ==========================================
// DIRECTOR PIPELINE - 總監管道流程控制
// ==========================================

/**
 * 設置執行模式切換開關
 */
function setupExecutionModeToggle() {
    const toggle = document.getElementById('toggle-auto-execute');
    const modeLabels = document.querySelectorAll('.mode-label');
    
    if (!toggle) return;
    
    // 同步 UI 狀態與全局 state
    toggle.checked = state.isAutoExecuteMode;
    
    const updateLabels = () => {
        modeLabels.forEach(label => {
            if (label.classList.contains('mode-auto')) {
                label.style.opacity = state.isAutoExecuteMode ? '1' : '0.5';
            } else {
                label.style.opacity = state.isAutoExecuteMode ? '0.5' : '1';
            }
        });
    };
    
    updateLabels();
    
    toggle.addEventListener('change', () => {
        state.isAutoExecuteMode = toggle.checked;
        localStorage.setItem('isAutoExecuteMode', state.isAutoExecuteMode);
        updateLabels();
        
        // 當切換執行模式時，立即重繪聊天訊息以顯示或隱藏動作按鈕
        renderChatMessages();
    });
}

function setupStreamLogToggle() {
    const toggle = document.getElementById('toggle-stream-log');
    if (!toggle) return;
    
    // 同步 UI 狀態與全局 state
    toggle.checked = state.showStreamLog;
    
    const applyToggleStatus = () => {
        const terminals = document.querySelectorAll('.agent-stream-output');
        terminals.forEach(term => {
            if (state.showStreamLog) {
                term.classList.remove('hidden');
            } else {
                term.classList.add('hidden');
            }
        });
    };
    
    applyToggleStatus();
    
    toggle.addEventListener('change', () => {
        state.showStreamLog = toggle.checked;
        localStorage.setItem('showStreamLog', state.showStreamLog);
        applyToggleStatus();
    });
}









/**
 * 隱藏生成中告示
 */
function hideGeneratingIndicator(tabName) {
    // 不恢復內容，讓真實內容替換
}

/**
 * 啟動管道流程 — 統一入口
 * 同時支援一鍵自動模式 (isAutoExecuteMode=true) 和一般模式 (顯示互動按鈕)
 */
async function runPipeline(pipelinePrompt = '') {
    if (!state.currentNovelId) {
        showToast('請先選擇或建立一個小說專案');
        return;
    }
    
    state.isPipelineRunning = true;
    showPipelineProgress(true);
    updateDirectorMessage('🎬 總監開始評估創作狀態...');
    
    // 重置所有階段狀態
    updatePipelineStage('worldview', 'pending');
    updatePipelineStage('characters', 'pending');
    updatePipelineStage('plot', 'pending');
    updatePipelineStage('writer', 'pending');
    
    try {
        // 先刷新數據（確保能讀到 DB 內的 pipeline_prompt）
        await loadNovelDetails(state.currentNovelId);

        // Single Source of Truth：pipeline prompt 以「使用者剛輸入」→ state.pipelinePrompt → DB pipeline_prompt 為優先序
        const userPrompt =
            (pipelinePrompt || '').trim() ||
            (state.pipelinePrompt || '').trim() ||
            (state.currentNovelData?.novel?.pipeline_prompt || '').trim() ||
            '請根據現有設定繼續創作';
        
        // 呼叫總監決策並根據結果執行
        updateDirectorMessage('🔍 總監正在掃描創作現狀...');
        const decision = await runDirectorDecision('init', userPrompt);
        
        // 根據總監決策執行對應動作
        await executeDirectorAction(decision, userPrompt);
        
    } catch (err) {
        console.error('Pipeline error:', err);
        showToast('管道執行失敗: ' + err.message);
        state.isPipelineRunning = false;
        showPipelineProgress(false);
    }
}


/**
 * 執行總監決策結果 — 核心路由引擎
 * 根據 runDirectorDecision 返回的解析結果，調度對應的 Agent 操作
 * @param {object} decision - runDirectorDecision 返回的決策物件
 * @param {string} userPrompt - 用戶原始創作需求
 */
async function executeDirectorAction(decision, userPrompt) {
    const action = decision.action;
    const hint = decision.hint || '';
    
    updateDirectorMessage(`🎯 總監決策：${action || '分析中'}...`);
    
    switch (action) {
        case 'CONTINUE': {
            const target = decision.target || '';
            if (target === 'worldview' || target === '世界觀設定' || (!checkStageHasContent('worldview') && !target)) {
                updatePipelineStage('worldview', 'running');
                updateDirectorMessage('🌍 開始生成世界觀設定...');
                await executePipelineStage('worldview', userPrompt);
            } else if (target === 'characters' || target === '角色設計') {
                updatePipelineStage('worldview', 'done');
                updatePipelineStage('characters', 'running');
                updateDirectorMessage('👥 開始生成角色設定...');
                await executePipelineStage('characters', userPrompt);
            } else if (target === 'plot' || target === '章節大綱') {
                updatePipelineStage('worldview', 'done');
                updatePipelineStage('characters', 'done');
                updatePipelineStage('plot', 'running');
                updateDirectorMessage('📋 開始生成章節大綱...');
                await executePipelineStage('plot', userPrompt);
            } else if (target === 'writer' || target === '正文寫作') {
                updatePipelineStage('worldview', 'done');
                updatePipelineStage('characters', 'done');
                updatePipelineStage('plot', 'done');
                updatePipelineStage('writer', 'running');
                updateDirectorMessage('✍️ 開始撰寫正文...');
                await executePipelineStage('writer', userPrompt);
            } else {
                // 無明確 target，根據當前狀態自動決定
                await executeNextMissingStage(userPrompt);
            }
            break;
        }
        
        case 'AUTO_REGENERATE': {
            const target = decision.target || decision.regenerateStage || '';
            showToast(`⚡ 總監指示重新生成：${hint || target}`);
            const enhancedPrompt = hint || userPrompt;
            if (target.includes('worldview') || target.includes('世界觀')) {
                updatePipelineStage('worldview', 'running');
                await executePipelineStage('worldview', enhancedPrompt);
            } else if (target.includes('character') || target.includes('角色')) {
                updatePipelineStage('characters', 'running');
                await executePipelineStage('characters', enhancedPrompt);
            } else if (target.includes('plot') || target.includes('大綱')) {
                updatePipelineStage('plot', 'running');
                await executePipelineStage('plot', enhancedPrompt);
            } else {
                // 預設重跑世界觀
                updatePipelineStage('worldview', 'running');
                await executePipelineStage('worldview', enhancedPrompt);
            }
            break;
        }
        
        case 'GO_BACK_TO_WORLDVIEW': {
            showToast('⚡ 總監指示回頭修改世界觀設定...');
            updatePipelineStage('worldview', 'running');
            const worldviewPrompt = hint 
                ? `請根據以下指示修改世界觀：\n\n${hint}\n\n現有世界觀：\n${state.currentNovelData?.worldbuilding || ''}`
                : userPrompt;
            await executePipelineStage('worldview', worldviewPrompt);
            break;
        }
        
        case 'GO_BACK_TO_CHARACTERS': {
            showToast('⚡ 總監指示回頭修改角色設計...');
            updatePipelineStage('characters', 'running');
            const charPrompt = hint 
                ? `請根據以下指示重新設計角色：\n\n${hint}\n\n現有角色設定：\n${state.currentNovelData?.characters_raw || ''}`
                : userPrompt;
            await executePipelineStage('characters', charPrompt);
            break;
        }
        
        case 'GO_BACK_TO_PLOT': {
            showToast('⚡ 總監指示回頭修改大綱...');
            updatePipelineStage('plot', 'running');
            const plotPrompt = hint 
                ? `請根據以下指示重新規劃大綱：\n\n${hint}\n\n現有大綱：\n${state.currentNovelData?.plot_raw || ''}`
                : userPrompt;
            await executePipelineStage('plot', plotPrompt);
            break;
        }
        
        case 'WRITE_ALL_CHAPTERS': {
            updatePipelineStage('worldview', 'done');
            updatePipelineStage('characters', 'done');
            updatePipelineStage('plot', 'done');
            updatePipelineStage('writer', 'running');
            updateDirectorMessage('✍️ 開始自動撰寫所有章節正文...');
            showToast('🚀 總監批准！開始自動撰寫全書章節...');
            await writeAllChaptersSequentially(userPrompt);
            break;
        }
        
        case 'WAIT_USER': {
            showToast('⏸️ 總監要求用戶確認，請查看右側聊天區的總監評估');
            updateDirectorMessage('⏸️ 等待用戶確認...');
            state.isPipelineRunning = false;
            break;
        }
        
        case 'FINISH': {
            showToast('🎉 總監宣布：全部創作任務已完成！');
            updateDirectorMessage('✅ 全部任務已完成');
            updatePipelineStage('worldview', 'done');
            updatePipelineStage('characters', 'done');
            updatePipelineStage('plot', 'done');
            updatePipelineStage('writer', 'done');
            state.isPipelineRunning = false;
            setTimeout(() => showPipelineProgress(false), 3000);
            await loadNovelDetails(state.currentNovelId);
            break;
        }
        
        default: {
            // 無法解析的 ACTION — 回退到智能狀態檢測
            console.warn('Unknown director action:', action, '— falling back to state detection');
            await executeNextMissingStage(userPrompt);
            break;
        }
    }
}

/**
 * 智能填補缺失階段（回退邏輯）
 * 當 Director 未返回明確 ACTION 時，根據當前狀態自動推進
 */
async function executeNextMissingStage(userPrompt) {
    const hasWorldview = state.currentNovelData?.worldbuilding && state.currentNovelData.worldbuilding.trim().length > 50;
    const hasCharacters = state.currentNovelData?.characters && state.currentNovelData.characters.characters?.length > 0;
    const hasPlot = state.currentNovelData?.plot && state.currentNovelData.plot.chapters?.length > 0;
    
    if (!hasWorldview) {
        updatePipelineStage('worldview', 'running');
        updateDirectorMessage('🌍 開始生成世界觀設定...');
        await executePipelineStage('worldview', userPrompt);
    } else if (!hasCharacters) {
        updatePipelineStage('worldview', 'done');
        updatePipelineStage('characters', 'running');
        updateDirectorMessage('👥 開始生成角色設定...');
        await executePipelineStage('characters', userPrompt);
    } else if (!hasPlot) {
        updatePipelineStage('worldview', 'done');
        updatePipelineStage('characters', 'done');
        updatePipelineStage('plot', 'running');
        updateDirectorMessage('📋 開始生成章節大綱...');
        await executePipelineStage('plot', userPrompt);
    } else {
        // 所有前期準備完成，開始寫作
        updatePipelineStage('worldview', 'done');
        updatePipelineStage('characters', 'done');
        updatePipelineStage('plot', 'done');
        updatePipelineStage('writer', 'running');
        updateDirectorMessage('✍️ 前期準備完成，開始撰寫正文...');
        await writeAllChaptersSequentially(userPrompt);
    }
}





/**
 * 執行 Story Architect Agent
 */
async function executeArchitectAgent() {
    showGeneratingIndicator('worldview');
    
    // 清理 textarea buffer 防止重複內容
    el.editorWorldview.value = '';
    
    const userPrompt = state.currentNovelData?.novel?.description || 
        `請為以下類型和風格的小說設計完整的世界觀：\n` +
        `類型：${state.currentNovelData?.novel?.genre || '待設定'}\n` +
        `風格：${state.currentNovelData?.novel?.style || '待設定'}\n`;
    
    streamAPI(
        `/api/agent/story-architect`,
        { novel_id: state.currentNovelId, user_prompt: userPrompt },
        null,
        (content) => {
            // 將內容追加到 textarea
            el.editorWorldview.value += content;
        },
        (error) => {
            showToast('世界觀生成失敗: ' + error);
            el.editorWorldview.disabled = false;
            updatePipelineStage('worldview', 'error');
            // 添加錯誤訊息到聊天
            appendChatMessage('assistant', `⚠️ 世界觀生成失敗: ${error}`);
        },
        async () => {
            el.editorWorldview.disabled = false;
            updatePipelineStage('worldview', 'done');
            
            // 刷新數據並繼續下一步
            await loadNovelDetails(state.currentNovelId);
            await handleDirectorDecision();
        }
    );
}

/**
 * 執行 Character Designer Agent
 */
async function executeCharacterAgent() {
    showGeneratingIndicator('characters');
    
    streamAPI(
        `/api/agent/character-designer`,
        { novel_id: state.currentNovelId },
        null,
        (content) => {
            el.editorCharactersJson.value += content;
        },
        (error) => {
            showToast('角色生成失敗: ' + error);
            el.editorCharactersJson.disabled = false;
            updatePipelineStage('characters', 'error');
        },
        async () => {
            el.editorCharactersJson.disabled = false;
            updatePipelineStage('characters', 'done');
            
            await loadNovelDetails(state.currentNovelId);
            await handleDirectorDecision();
        }
    );
}

/**
 * 執行 Plot Planner Agent
 */
async function executePlotAgent() {
    showGeneratingIndicator('plot');
    
    streamAPI(
        `/api/agent/plot-planner`,
        { novel_id: state.currentNovelId },
        null,
        (content) => {
            el.editorPlotJson.value += content;
        },
        (error) => {
            showToast('大綱生成失敗: ' + error);
            el.editorPlotJson.disabled = false;
            updatePipelineStage('plot', 'error');
        },
        async () => {
            el.editorPlotJson.disabled = false;
            updatePipelineStage('plot', 'done');
            
            await loadNovelDetails(state.currentNovelId);
            await handleDirectorDecision();
        }
    );
}

// ==========================================
// API WRAPPERS & STREAMING CORE
// ==========================================






// ==========================================
// NOVEL LIFE CYCLE
// ==========================================




// ==========================================
// SYSTEM SETTINGS CONTROLS
// ==========================================






// ==========================================
// RENDERERS (DOM TREE BUILDERS)
// ==========================================









async function saveWorldviewJSON(jsonObj) {
    if (!state.currentNovelId) {
        showToast('請先選擇或建立一個小說專案');
        return;
    }
    const text = JSON.stringify(jsonObj, null, 2);
    try {
        await requestAPI(`/api/novels/${state.currentNovelId}/worldbuilding`, 'POST', {
            content: text
        });
        state.currentNovelData.worldbuilding = text;
        el.editorWorldview.value = text;
        renderWorldviewSections();
        showToast('世界觀設定已儲存');
    } catch (e) {
        showToast('更新失敗');
        console.error(e);
    }
}

function openWorldviewTextSectionEditModal(field, title) {
    let modal = document.getElementById('modal-worldview-text-edit');
    if (!modal) {
        const html = `
        <div id="modal-worldview-text-edit" class="modal-overlay">
            <div class="modal-card" style="max-width: 600px;">
                <div class="modal-header">
                    <h2 id="wv-text-edit-title">編輯設定</h2>
                    <button class="btn-close-modal">✕</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label id="wv-text-edit-label">設定內容</label>
                        <textarea id="wv-text-edit-content" rows="10" placeholder="請輸入設定內容..." style="width: 100%; border: 1px solid var(--border-color); border-radius: var(--radius-sm); background: var(--bg-tertiary); color: var(--text-primary); padding: 8px; font-size: 0.85rem; font-family: inherit; resize: vertical;"></textarea>
                    </div>
                    <button id="btn-wv-text-edit-submit" class="btn btn-primary btn-full mt-4">儲存設定</button>
                </div>
            </div>
        </div>`;
        document.body.insertAdjacentHTML('beforeend', html);
        modal = document.getElementById('modal-worldview-text-edit');
        modal.querySelector('.btn-close-modal').addEventListener('click', () => modal.classList.remove('active'));
        modal.addEventListener('click', (e) => { if (e.target === modal) modal.classList.remove('active'); });
    }

    document.getElementById('wv-text-edit-title').innerText = `✏️ 編輯 ${title}`;
    document.getElementById('wv-text-edit-label').innerText = `${title} 詳細設定`;
    
    const worldviewText = state.currentNovelData?.worldbuilding || '';
    const js = parseWorldviewJSON(worldviewText);
    document.getElementById('wv-text-edit-content').value = js[field] || '';

    const submitBtn = document.getElementById('btn-wv-text-edit-submit');
    const newBtn = submitBtn.cloneNode(true);
    submitBtn.parentNode.replaceChild(newBtn, submitBtn);

    newBtn.addEventListener('click', async () => {
        const val = document.getElementById('wv-text-edit-content').value.trim();
        const worldviewText = state.currentNovelData?.worldbuilding || '';
        const js = parseWorldviewJSON(worldviewText);
        js[field] = val;
        await saveWorldviewJSON(js);
        modal.classList.remove('active');
    });

    modal.classList.add('active');
}

function openWorldviewComplexListEditModal(field, title, defaultItemTitle = '') {
    let modal = document.getElementById('modal-worldview-complex-list-edit');
    if (!modal) {
        const html = `
        <div id="modal-worldview-complex-list-edit" class="modal-overlay">
            <div class="modal-card" style="max-width: 650px; max-height: 85vh; display: flex; flex-direction: column;">
                <div class="modal-header">
                    <h2 id="wv-complex-list-edit-title">編輯清單</h2>
                    <button class="btn-close-modal">✕</button>
                </div>
                <div class="modal-body" style="overflow-y: auto; flex: 1; display: flex; flex-direction: column; gap: 12px; padding-bottom: 20px;">
                    <div id="wv-complex-list-items-container" style="display: flex; flex-direction: column; gap: 16px;"></div>
                    <button id="btn-wv-complex-list-add-item" class="btn btn-secondary btn-xs" style="align-self: flex-start; margin-top: 4px;">➕ 新增項目</button>
                    <button id="btn-wv-complex-list-submit" class="btn btn-primary btn-full mt-4">儲存變更</button>
                </div>
            </div>
        </div>`;
        document.body.insertAdjacentHTML('beforeend', html);
        modal = document.getElementById('modal-worldview-complex-list-edit');
        modal.querySelector('.btn-close-modal').addEventListener('click', () => modal.classList.remove('active'));
        modal.addEventListener('click', (e) => { if (e.target === modal) modal.classList.remove('active'); });
    }

    document.getElementById('wv-complex-list-edit-title').innerText = `📋 編輯 ${title}`;
    const container = document.getElementById('wv-complex-list-items-container');
    container.innerHTML = '';

    const worldviewText = state.currentNovelData?.worldbuilding || '';
    const js = parseWorldviewJSON(worldviewText);
    const list = Array.isArray(js[field]) ? JSON.parse(JSON.stringify(js[field])) : [];

    function renderItems() {
        container.innerHTML = '';
        if (list.length === 0) {
            container.innerHTML = '<div style="text-align: center; color: var(--text-muted); font-size: 0.8rem; padding: 12px; border: 1px dashed var(--border-color); border-radius: var(--radius-sm);">目前尚無項目</div>';
            return;
        }

        list.forEach((item, index) => {
            const card = document.createElement('div');
            card.className = 'complex-list-card';
            card.style = 'border: 1px solid var(--border-color); border-radius: var(--radius-md); background: rgba(255, 255, 255, 0.02); padding: 12px; display: flex; flex-direction: column; gap: 8px; position: relative;';
            card.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: 0.8rem; color: var(--text-muted); font-weight: 600;">項目 #${index + 1}</span>
                    <div style="display: flex; gap: 6px; align-items: center;">
                        <button class="btn btn-ghost btn-xs insert-item-btn" data-index="${index}" style="color: var(--primary); font-size: 0.75rem; border: none; background: none; cursor: pointer; padding: 2px 6px;">➕ 在此後插入</button>
                        <button class="btn btn-ghost btn-xs delete-item-btn" data-index="${index}" style="color: var(--text-muted); font-size: 1rem; border: none; background: none; cursor: pointer; padding: 0 4px;">✕</button>
                    </div>
                </div>
                <div class="form-group" style="margin-bottom: 0;">
                    <label style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 4px; display: block;">標題名稱</label>
                    <input type="text" class="wv-complex-item-title-input" data-index="${index}" value="${(item.title || '').replace(/"/g, '&quot;')}" style="width: 100%; border: 1px solid var(--border-color); border-radius: var(--radius-sm); background: var(--bg-tertiary); color: var(--text-primary); padding: 8px; font-size: 0.85rem;" placeholder="輸入標題 (例如：第一幕 (Setup) / 階段 1)...">
                </div>
                <div class="form-group" style="margin-bottom: 0;">
                    <label style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 4px; display: block;">詳細內容</label>
                    <textarea class="wv-complex-item-content-input" data-index="${index}" rows="3" style="width: 100%; border: 1px solid var(--border-color); border-radius: var(--radius-sm); background: var(--bg-tertiary); color: var(--text-primary); padding: 8px; font-size: 0.85rem; font-family: inherit; resize: vertical;" placeholder="輸入內容描述...">${item.content || ''}</textarea>
                </div>
            `;
            container.appendChild(card);

            card.querySelector('.wv-complex-item-title-input').addEventListener('input', (e) => {
                list[index].title = e.target.value;
            });

            card.querySelector('.wv-complex-item-content-input').addEventListener('input', (e) => {
                list[index].content = e.target.value;
            });

            card.querySelector('.insert-item-btn').addEventListener('click', () => {
                const defaultTitle = defaultItemTitle || `項目`;
                list.splice(index + 1, 0, { title: `新${defaultTitle}`, content: '' });
                renderItems();
            });

            card.querySelector('.delete-item-btn').addEventListener('click', () => {
                list.splice(index, 1);
                renderItems();
            });
        });
    }

    renderItems();

    // Rebind Add Button
    const addBtn = document.getElementById('btn-wv-complex-list-add-item');
    const newAddBtn = addBtn.cloneNode(true);
    addBtn.parentNode.replaceChild(newAddBtn, addBtn);
    newAddBtn.addEventListener('click', () => {
        const defaultTitle = defaultItemTitle || `新項目 #${list.length + 1}`;
        list.push({ title: defaultTitle, content: '' });
        renderItems();
        setTimeout(() => {
            const inputs = container.querySelectorAll('.wv-complex-item-title-input');
            if (inputs.length > 0) {
                inputs[inputs.length - 1].focus();
            }
        }, 50);
    });

    // Rebind Submit Button
    const submitBtn = document.getElementById('btn-wv-complex-list-submit');
    const newSubmitBtn = submitBtn.cloneNode(true);
    submitBtn.parentNode.replaceChild(newSubmitBtn, submitBtn);

    newSubmitBtn.addEventListener('click', async () => {
        const finalList = list.map(item => {
            return {
                title: (item.title || '').trim(),
                content: (item.content || '').trim()
            };
        }).filter(item => item.title !== '' || item.content !== '');
        
        const worldviewText = state.currentNovelData?.worldbuilding || '';
        const js = parseWorldviewJSON(worldviewText);
        js[field] = finalList;
        await saveWorldviewJSON(js);
        modal.classList.remove('active');
    });

    modal.classList.add('active');
}

function openWorldviewListEditModal(field, title) {
    let modal = document.getElementById('modal-worldview-list-edit');
    if (!modal) {
        const html = `
        <div id="modal-worldview-list-edit" class="modal-overlay">
            <div class="modal-card" style="max-width: 650px; max-height: 85vh; display: flex; flex-direction: column;">
                <div class="modal-header">
                    <h2 id="wv-list-edit-title">編輯清單</h2>
                    <button class="btn-close-modal">✕</button>
                </div>
                <div class="modal-body" style="overflow-y: auto; flex: 1; display: flex; flex-direction: column; gap: 12px; padding-bottom: 20px;">
                    <div id="wv-list-items-container" style="display: flex; flex-direction: column; gap: 8px;"></div>
                    <button id="btn-wv-list-add-item" class="btn btn-secondary btn-xs" style="align-self: flex-start; margin-top: 4px;">➕ 新增項目</button>
                    <button id="btn-wv-list-submit" class="btn btn-primary btn-full mt-4">儲存變更</button>
                </div>
            </div>
        </div>`;
        document.body.insertAdjacentHTML('beforeend', html);
        modal = document.getElementById('modal-worldview-list-edit');
        modal.querySelector('.btn-close-modal').addEventListener('click', () => modal.classList.remove('active'));
        modal.addEventListener('click', (e) => { if (e.target === modal) modal.classList.remove('active'); });
    }

    document.getElementById('wv-list-edit-title').innerText = `📋 編輯 ${title}`;
    const container = document.getElementById('wv-list-items-container');
    container.innerHTML = '';

    const worldviewText = state.currentNovelData?.worldbuilding || '';
    const js = parseWorldviewJSON(worldviewText);
    const list = Array.isArray(js[field]) ? [...js[field]] : [];

    function renderItems() {
        container.innerHTML = '';
        if (list.length === 0) {
            container.innerHTML = '<div style="text-align: center; color: var(--text-muted); font-size: 0.8rem; padding: 12px; border: 1px dashed var(--border-color); border-radius: var(--radius-sm);">目前尚無項目</div>';
            return;
        }

        list.forEach((item, index) => {
            const div = document.createElement('div');
            div.style = 'display: flex; gap: 8px; align-items: center;';
            div.innerHTML = `
                <span style="font-size: 0.8rem; color: var(--text-muted); min-width: 24px;">#${index + 1}</span>
                <input type="text" class="wv-list-item-input" data-index="${index}" value="${item.replace(/"/g, '&quot;')}" style="flex: 1; border: 1px solid var(--border-color); border-radius: var(--radius-sm); background: var(--bg-tertiary); color: var(--text-primary); padding: 8px; font-size: 0.85rem;" placeholder="請輸入項目內容...">
                <button class="btn btn-ghost btn-xs delete-item-btn" data-index="${index}" style="color: var(--text-muted); font-size: 1rem; border: none; background: none; cursor: pointer;">✕</button>
            `;
            container.appendChild(div);

            div.querySelector('.wv-list-item-input').addEventListener('input', (e) => {
                list[index] = e.target.value;
            });

            div.querySelector('.delete-item-btn').addEventListener('click', () => {
                list.splice(index, 1);
                renderItems();
            });
        });
    }

    renderItems();

    // Rebind Add Button
    const addBtn = document.getElementById('btn-wv-list-add-item');
    const newAddBtn = addBtn.cloneNode(true);
    addBtn.parentNode.replaceChild(newAddBtn, addBtn);
    newAddBtn.addEventListener('click', () => {
        list.push('');
        renderItems();
        setTimeout(() => {
            const inputs = container.querySelectorAll('.wv-list-item-input');
            if (inputs.length > 0) {
                inputs[inputs.length - 1].focus();
            }
        }, 50);
    });

    // Rebind Submit Button
    const submitBtn = document.getElementById('btn-wv-list-submit');
    const newSubmitBtn = submitBtn.cloneNode(true);
    submitBtn.parentNode.replaceChild(newSubmitBtn, submitBtn);

    newSubmitBtn.addEventListener('click', async () => {
        const finalList = list.map(item => item.trim()).filter(item => item !== '');
        const worldviewText = state.currentNovelData?.worldbuilding || '';
        const js = parseWorldviewJSON(worldviewText);
        js[field] = finalList;
        await saveWorldviewJSON(js);
        modal.classList.remove('active');
    });

    modal.classList.add('active');
}



async function deleteWorldviewSection(sectionId, title) {
    if (!(await showCustomConfirm(`確定要清空/刪除【${title}】的設定內容嗎？`))) {
        return;
    }
    
    const worldviewText = state.currentNovelData?.worldbuilding || '';
    const js = parseWorldviewJSON(worldviewText);
    
    if (sectionId === 'theme') js.theme = '';
    else if (sectionId === 'main_conflict') js.main_conflict = '';
    else if (sectionId === 'worldview') js.worldview = '';
    else if (sectionId === 'macro_outline') js.macro_outline = '';
    else if (sectionId === 'three-act') js.three_act_structure = [];
    else if (sectionId === 'character-waves') js.progressive_character_plan = [];
    else if (sectionId === 'turning-points') js.key_turning_points = [];
    else if (sectionId === 'seeds') js.foreshadowing_seeds = [];
    
    await saveWorldviewJSON(js);
    showToast(`${title} 的設定已清空`);
}

function addWorldviewSection(sectionType) {
    if (sectionType === 'core-theme') openWorldviewTextSectionEditModal('theme', '核心主題');
    else if (sectionType === 'core-conflict') openWorldviewTextSectionEditModal('main_conflict', '核心衝突');
    else if (sectionType === 'world-setting') openWorldviewTextSectionEditModal('worldview', '世界觀設定');
    else if (sectionType === 'overall-outline') openWorldviewTextSectionEditModal('macro_outline', '整體故事大綱');
    else if (sectionType === 'three-act') openWorldviewComplexListEditModal('three_act_structure', '三幕式結構', '第一幕');
    else if (sectionType === 'character-waves') openWorldviewComplexListEditModal('progressive_character_plan', '角色漸進規劃策略', '第一波');
    else if (sectionType === 'turning-points') openWorldviewListEditModal('key_turning_points', '關鍵轉折點');
    else if (sectionType === 'seeds') openWorldviewListEditModal('foreshadowing_seeds', '伏筆種子');
    else showToast('不支援新增此類型');
}

/**
 * 切換區塊展開/收合狀態
 */
function toggleSectionExpand(sectionId) {
    const content = document.getElementById(`content-${sectionId}`);
    if (content) {
        content.classList.toggle('expanded');
    }
}



/**
 * 解析世界觀文本中的伏筆種子
 * @param {string} text - 世界觀文本
 * @returns {string[]} 伏筆種子陣列
 */
function parseWorldviewSeeds(text) {
    if (!text) return [];
    
    // 查找【伏筆種子】或【伏筆與設定種子】區塊
    const seedsSectionMatch = text.match(/【伏筆[與]?設定?種子】\s*([\s\S]*?)(?=\n【|$)/i);
    if (seedsSectionMatch) {
        const seedsText = seedsSectionMatch[1];
        // 按行分割，過濾空行，並去除前綴
        return seedsText.split('\n')
            .map(line => stripBulletPrefix(line.trim()))
            .filter(line => line.length > 0 && !line.startsWith('#'));
    }
    
    // 如果沒有找到專用區塊，嘗試查找其他可能的格式
    // 例如：- 伏筆1, - 伏筆2 或數字列表
    const bulletMatch = text.match(/(?:^|\n)(?:[-*•]|\d+[.、])\s*([^#\n]+)/gm);
    if (bulletMatch) {
        return bulletMatch
            .map(line => stripBulletPrefix(line))
            .filter(line => line.length > 0);
    }
    
    return [];
}

/**
 * 解析世界觀文本中的【核心主題】
 * @param {string} text - 世界觀文本
 * @returns {string|null} 核心主題內容
 */
function parseCoreTheme(text) {
    if (!text) return null;
    const match = text.match(/【核心主題】\s*([\s\S]*?)(?=\n【|$)/i);
    return match ? match[1].trim() : null;
}

/**
 * 解析世界觀文本中的【核心衝突】
 * @param {string} text - 世界觀文本
 * @returns {string|null} 核心衝突內容
 */
function parseCoreConflict(text) {
    if (!text) return null;
    const match = text.match(/【核心衝突】\s*([\s\S]*?)(?=\n【|$)/i);
    return match ? match[1].trim() : null;
}

/**
 * 解析世界觀文本中的【世界觀設定】
 * @param {string} text - 世界觀文本
 * @returns {string|null} 世界觀設定內容
 */
function parseWorldSetting(text) {
    if (!text) return null;
    const match = text.match(/【世界觀設定】\s*([\s\S]*?)(?=\n【|$)/i);
    return match ? match[1].trim() : null;
}

/**
 * 解析世界觀文本中的【三幕式結構】
 * @param {string} text - 世界觀文本
 * @returns {string|null} 三幕式結構內容
 */
function parseThreeActStructure(text) {
    if (!text) return null;
    const match = text.match(/【三幕式結構】\s*([\s\S]*?)(?=\n【|$)/i);
    return match ? match[1].trim() : null;
}

/**
 * 解析世界觀文本中的【整體故事大綱】
 * @param {string} text - 世界觀文本
 * @returns {string|null} 整體故事大綱內容
 */
function parseOverallOutline(text) {
    if (!text) return null;
    const match = text.match(/【整體故事大綱】\s*([\s\S]*?)(?=\n【|$)/i);
    return match ? match[1].trim() : null;
}

/**
 * 解析世界觀文本中的【角色漸進規劃策略】
 * @param {string} text - 世界觀文本
 * @returns {Array} 角色漸進規劃陣列
 */
function parseCharacterWavePlan(text) {
    if (!text) return [];
    const match = text.match(/【角色漸進規劃策略】\s*([\s\S]*?)(?=\n【|$)/i);
    if (!match) return [];
    
    const section = match[1];
    // 按 wave 分組 - 支援 "- wave_X_name:" 或 "wave_X_name:" 格式
    const waves = [];
    // 匹配 "- wave_1_opening: 內容" 或 "wave_1_opening: 內容" 格式
    const waveMatches = section.matchAll(/(?:^|\n)\s*[-*]?\s*wave_(\d+)[_:](\w+):\s*([\s\S]*?)(?=\n\s*[-*]?\s*wave_|\n【|$$)/gi);
    for (const wm of waveMatches) {
        waves.push({
            name: `wave_${wm[1]}_${wm[2]}`,
            content: wm[3].trim()
        });
    }
    return waves;
}

/**
 * 解析世界觀文本中的【關鍵轉折點】
 * @param {string} text - 世界觀文本
 * @returns {Array} 關鍵轉折點陣列
 */
function parseKeyTurningPoints(text) {
    if (!text) return [];
    const match = text.match(/【關鍵轉折點】\s*([\s\S]*?)(?=\n【|$)/i);
    if (!match) return [];
    
    const section = match[1];
    const points = [];
    // 匹配 "轉折點 X（第Y章）：內容" 格式，支援前導的空白、項目符號(-, *, •)和數字編號
    const pointMatches = section.matchAll(/(?:^|\n)\s*[-*•]?\s*轉折點\s*(\d+)[（(]第(\d+)章[)）][：:]\s*([^\n]+)/g);
    for (const pm of pointMatches) {
        points.push({
            index: parseInt(pm[1]),
            chapter: parseInt(pm[2]),
            content: pm[3].trim()
        });
    }
    return points;
}

/**
 * 渲染伏筆種子視覺化列表
 * 當有伏筆時顯示伏筆列表，當沒有伏筆但有世界觀內容時顯示世界觀摘要
 */
function renderWorldviewSeedsList() {
    const container = document.getElementById('seeds-list-container');
    if (!container) return;
    
    const worldviewText = state.currentNovelData?.worldbuilding || '';
    const seeds = parseWorldviewSeeds(worldviewText);
    
    if (seeds.length === 0) {
        // 沒有伏筆時，顯示世界觀內容預覽（前500字）
        if (worldviewText && worldviewText.trim().length > 0) {
            const preview = worldviewText.trim().substring(0, 500);
            const hasMore = worldviewText.trim().length > 500;
            container.innerHTML = `
                <div class="seed-card">
                    <div class="seed-header">
                        <span class="seed-badge">📖 世界觀內容預覽</span>
                    </div>
                    <div class="seed-content">${preview}${hasMore ? '...' : ''}</div>
                    <div style="margin-top:8px; font-size:0.75rem; color:var(--text-muted);">
                        完整內容請在左側編輯器中查看和編輯
                    </div>
                </div>
                <div style="margin-top:12px;">
                    <button class="btn btn-secondary btn-xs" onclick="document.getElementById('btn-seed-add').click()" style="width:100%;">
                        ➕ 新增伏筆
                    </button>
                </div>
            `;
        } else {
            container.innerHTML = '<div class="empty-placeholder">尚無世界觀內容。請在左側編輯器中輸入，或點擊「AI 自動規劃世界觀」生成。</div>';
        }
        return;
    }
    
    container.innerHTML = seeds.map((seed, index) => `
        <div class="seed-card" data-seed-index="${index}">
            <div class="seed-header">
                <span class="seed-badge">伏筆 #${index + 1}</span>
                <div class="seed-actions">
                    <button class="seed-delete-btn" data-index="${index}" title="刪除此伏筆">✕</button>
                </div>
            </div>
            <div class="seed-content">${seed}</div>
        </div>
    `).join('');
    
    // 綁定刪除按鈕事件
    container.querySelectorAll('.seed-delete-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const seedIndex = parseInt(e.target.dataset.index);
            deleteWorldviewSeed(seedIndex);
        });
    });
}

/**
 * 刪除指定的伏筆種子
 * @param {number} seedIndex - 要刪除的伏筆索引
 */
async function deleteWorldviewSeed(seedIndex) {
    const worldviewText = state.currentNovelData?.worldbuilding || '';
    const seeds = parseWorldviewSeeds(worldviewText);
    
    if (seedIndex < 0 || seedIndex >= seeds.length) {
        showToast('無效的伏筆索引');
        return;
    }
    
    const seedToDelete = seeds[seedIndex];
    
    if (!(await showCustomConfirm(`確定要刪除伏筆「${seedToDelete.substring(0, 30)}...」嗎？`))) {
        return;
    }
    
    // 從文本中移除該伏筆
    const lines = worldviewText.split('\n');
    const newLines = [];
    let currentSeedIndex = -1;
    let inSeedsSection = false;
    
    for (const line of lines) {
        // 檢測是否進入伏筆區塊
        if (line.match(/【伏筆[與]?設定?種子】/i)) {
            inSeedsSection = true;
            newLines.push(line);
            continue;
        }
        
        // 檢測是否離開伏筆區塊（遇到新的【標題】）
        if (inSeedsSection && line.match(/^【/) && !line.match(/【伏筆/)) {
            inSeedsSection = false;
            newLines.push(line);
            continue;
        }
        
        if (inSeedsSection) {
            const trimmedLine = line.trim();
            // 跳過空行和標題行
            if (!trimmedLine || trimmedLine.startsWith('#')) {
                newLines.push(line);
                continue;
            }
            
            // 檢查這一行是否是我們要刪除的伏筆
            const isTargetSeed = trimmedLine === seedToDelete || 
                                  trimmedLine.replace(/^[-*•]\s*/, '') === seedToDelete ||
                                  trimmedLine.replace(/^\d+[.、]\s*/, '') === seedToDelete;
            
            if (!isTargetSeed) {
                newLines.push(line);
            }
            // 如果是目標伏筆，就跳過（刪除）
        } else {
            newLines.push(line);
        }
    }
    
    const newWorldviewText = newLines.join('\n');
    
    try {
        await requestAPI(`/api/novels/${state.currentNovelId}/worldbuilding`, 'POST', {
            content: newWorldviewText
        });
        state.currentNovelData.worldbuilding = newWorldviewText;
        el.editorWorldview.value = newWorldviewText;
        renderWorldviewSeedsList();
        showToast('伏筆已刪除');
    } catch (e) {
        showToast('刪除失敗');
    }
}

/**
 * 伏筆 Modal 狀態
 */
let seedModalState = {
    mode: 'add', // 'add' or 'edit'
    editIndex: -1,
    originalText: ''
};

/**
 * 打開新增伏筆 Modal
 */
function openAddSeedModal() {
    if (!state.currentNovelId) {
        showToast('請先選擇或建立一個小說專案');
        return;
    }
    
    seedModalState = {
        mode: 'add',
        editIndex: -1,
        originalText: ''
    };
    
    document.getElementById('seed-modal-title').textContent = '新增伏筆';
    document.getElementById('input-seed-content').value = '';
    document.getElementById('modal-seed').classList.remove('hidden');
    document.getElementById('input-seed-content').focus();
}

/**
 * 打開編輯伏筆 Modal
 * @param {number} index - 伏筆索引
 * @param {string} text - 伏筆內容
 */
function openEditSeedModal(index, text) {
    if (!state.currentNovelId) {
        showToast('請先選擇或建立一個小說專案');
        return;
    }
    
    seedModalState = {
        mode: 'edit',
        editIndex: index,
        originalText: text
    };
    
    document.getElementById('seed-modal-title').textContent = '編輯伏筆';
    document.getElementById('input-seed-content').value = text;
    document.getElementById('modal-seed').classList.remove('hidden');
    document.getElementById('input-seed-content').focus();
}

/**
 * 關閉伏筆 Modal
 */
function closeSeedModal() {
    document.getElementById('modal-seed').classList.add('hidden');
    seedModalState = {
        mode: 'add',
        editIndex: -1,
        originalText: ''
    };
}

// ==========================================
// STRATEGY CARD VIEW TOGGLE (策略卡片視圖切換)
// 三幕式結構、角色漸進規劃、關鍵轉折點、伏筆種子
// ==========================================

/**
 * 切換策略卡片顯示模式
 * @param {string} viewMode - 'all' | '<' | '>'
 *   all: 全部展開顯示（預設）
 *   <:  向左切換（向前一張卡片）
 *   >:  向右切換（向後一張卡片）
 */
function jumpToStrategyCard(index) {
    state.currentCardIndex = index;
    state.currentSubSectionIndex = 'all'; // 進入單張卡片時，預設顯示全部子章節
    const container = document.getElementById('worldview-sections-container');
    if (!container) return;
    const strategyCardsArray = [
        container.querySelector('.worldview-section-card[data-section="three-act"]'),
        container.querySelector('.worldview-section-card[data-section="character-waves"]'),
        container.querySelector('.worldview-section-card[data-section="turning-points"]'),
        container.querySelector('.worldview-section-card[data-section="seeds"]')
    ].filter(Boolean);
    
    applySingleCardView(strategyCardsArray, index);
    applySubSectionVisibility();
}

function setStrategyCardView(viewMode) {
    const container = document.getElementById('worldview-sections-container');
    if (!container) return;

    const strategyNames = ['three-act', 'character-waves', 'turning-points', 'seeds'];
    const strategyCardsArray = strategyNames.map(id => 
        container.querySelector(`.worldview-section-card[data-section="${id}"]`)
    ).filter(Boolean);

    const total = strategyCardsArray.length;
    if (total === 0) return;

    if (viewMode === 'all') {
        state.strategyCardView = 'all';
        state.currentSubSectionIndex = 'all'; // 重設子章節
        
        const strategyWrapper = container.querySelector('.worldview-strategy-container');
        if (strategyWrapper) {
            strategyWrapper.classList.remove('single-mode');
            strategyWrapper.classList.add('all-mode');
        }

        strategyCardsArray.forEach(card => {
            card.style.display = 'flex';
            card.classList.remove('collapsed');
            card.classList.add('expanded');
            
            // 恢復所有子章節/項目顯示
            const activeSectionName = card.dataset.section;
            let subItems = [];
            if (activeSectionName === 'three-act' || activeSectionName === 'character-waves') {
                subItems = Array.from(card.querySelectorAll('.worldview-sub-item'));
            } else {
                subItems = Array.from(card.querySelectorAll('.worldview-list > li'));
            }
            subItems.forEach(item => item.style.display = '');

            // 恢復原始標題 (去除 statusText)
            const titleContainer = card.querySelector('.worldview-section-title');
            if (titleContainer && titleContainer.dataset.originalText) {
                const badgeSpan = titleContainer.querySelector('.worldview-section-badge');
                titleContainer.innerHTML = '';
                if (badgeSpan) titleContainer.appendChild(badgeSpan);
                titleContainer.appendChild(document.createTextNode(' ' + titleContainer.dataset.originalText));
            }
        });

        const toggleBtns = document.querySelectorAll('.view-toggle-btn');
        toggleBtns.forEach(btn => {
            btn.classList.remove('active');
            if (btn.dataset.view === 'all') {
                btn.classList.add('active');
            }
        });
    } else if (viewMode === '<') {
        // 如果當前不在單卡檢視模式，直接進入第一張卡片
        if (state.strategyCardView !== 'single') {
            state.strategyCardView = 'single';
            state.currentCardIndex = 0;
            state.currentSubSectionIndex = 'all';
        }

        const count = getSubSectionCount(state.currentCardIndex);
        if (count > 0) {
            if (state.currentSubSectionIndex === 'all') {
                state.currentSubSectionIndex = count - 1; // 到最後一個子項目
            } else if (state.currentSubSectionIndex === 0) {
                state.currentSubSectionIndex = 'all'; // 循環到 "全部"
            } else {
                state.currentSubSectionIndex--;
            }
        }
        applySingleCardView(strategyCardsArray, state.currentCardIndex);
        applySubSectionVisibility();
    } else if (viewMode === '>') {
        // 如果當前不在單卡檢視模式，直接進入第一張卡片
        if (state.strategyCardView !== 'single') {
            state.strategyCardView = 'single';
            state.currentCardIndex = 0;
            state.currentSubSectionIndex = 'all';
        }

        const count = getSubSectionCount(state.currentCardIndex);
        if (count > 0) {
            if (state.currentSubSectionIndex === 'all') {
                state.currentSubSectionIndex = 0; // 從第一個子項目開始
            } else if (state.currentSubSectionIndex === count - 1) {
                state.currentSubSectionIndex = 'all'; // 循環到 "全部"
            } else {
                state.currentSubSectionIndex++;
            }
        }
        applySingleCardView(strategyCardsArray, state.currentCardIndex);
        applySubSectionVisibility();
    }
}

function applySingleCardView(cards, activeIndex) {
    state.strategyCardView = 'single';
    
    const container = document.getElementById('worldview-sections-container');
    if (container) {
        const strategyWrapper = container.querySelector('.worldview-strategy-container');
        if (strategyWrapper) {
            strategyWrapper.classList.remove('all-mode');
            strategyWrapper.classList.add('single-mode');
        }
    }

    cards.forEach((card, index) => {
        if (index === activeIndex) {
            card.style.display = 'flex';
            card.classList.remove('collapsed');
            card.classList.add('expanded');
        } else {
            card.style.display = 'none';
            card.classList.remove('expanded');
            card.classList.add('collapsed');
        }
    });

    const strategyNames = ['three-act', 'character-waves', 'turning-points', 'seeds'];
    const activeViewName = strategyNames[activeIndex];
    
    const toggleBtns = document.querySelectorAll('.view-toggle-btn');
    toggleBtns.forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.view === activeViewName) {
            btn.classList.add('active');
        }
    });
}

// ==========================================
// MARKDOWN 渲染支援
// ==========================================

// renderMarkdown is now imported from ./utils.js

/**
 * 為指定的元素內容器渲染 Markdown 內容
 * @param {string} elementId - 目標元素的 ID
 * @param {string} markdownText - Markdown 原始文字
 */
function setMarkdownContent(elementId, markdownText) {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = renderMarkdown(markdownText);
    }
}

// ==========================================
// 其他單個項目的高度與滾動設定
// ==========================================

/**
 * 設定單一卡片為可滾動的固定高度
 * @param {string} cardSelector - CSS 選擇器
 * @param {number} maxHeight - 最大高度 (px)，預設 400
 */
function setupScrollableCard(cardSelector, maxHeight = 400) {
    const cards = document.querySelectorAll(cardSelector);
    cards.forEach(card => {
        card.style.maxHeight = `${maxHeight}px`;
        card.style.overflowY = 'auto';
        card.style.overflowX = 'hidden';
        // 自定義滾動條樣式
        card.style.scrollbarWidth = 'thin';
        card.style.scrollbarColor = 'var(--border-color) transparent';
    });
}

/**
 * 初始化伏筆 Modal 事件
 */
function initSeedModalEvents() {
    const modal = document.getElementById('modal-seed');
    const confirmBtn = document.getElementById('btn-seed-modal-confirm');
    const cancelBtn = document.getElementById('btn-seed-modal-cancel');
    const inputContent = document.getElementById('input-seed-content');
    
    // 確認按鈕
    confirmBtn.onclick = async () => {
        const content = inputContent.value.trim();
        if (!content) {
            showToast('請輸入伏筆內容');
            return;
        }
        
        if (seedModalState.mode === 'add') {
            await addWorldviewSeed(content);
        } else {
            await editWorldviewSeed(seedModalState.editIndex, content);
        }
        closeSeedModal();
    };
    
    // 取消按鈕
    cancelBtn.onclick = closeSeedModal;
    
    // 點擊 Modal 背景關閉
    modal.onclick = (e) => {
        if (e.target === modal) {
            closeSeedModal();
        }
    };
    
    // ESC 鍵關閉
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !modal.classList.contains('hidden')) {
            closeSeedModal();
        }
    });
}

/**
 * 手動新增伏筆種子
 */
async function addWorldviewSeed(seedText) {
    if (!seedText || !seedText.trim()) {
        showToast('請輸入伏筆內容');
        return;
    }
    
    if (!state.currentNovelId) {
        showToast('請先選擇或建立一個小說專案');
        return;
    }
    
    const worldviewText = state.currentNovelData?.worldbuilding || '';
    let newWorldviewText = worldviewText;
    
    // 檢查是否已有伏筆區塊
    if (worldviewText.match(/【伏筆[與]?設定?種子】/i)) {
        // 在現有伏筆區塊中添加
        newWorldviewText = worldviewText.replace(
            /【伏筆[與]?設定?種子】\s*/i,
            `【伏筆與設定種子】\n- ${seedText.trim()}`
        );
    } else {
        // 在文本末尾添加新的伏筆區塊
        newWorldviewText = worldviewText + '\n\n【伏筆與設定種子】\n- ' + seedText.trim();
    }
    
    try {
        await requestAPI(`/api/novels/${state.currentNovelId}/worldbuilding`, 'POST', {
            content: newWorldviewText
        });
        state.currentNovelData.worldbuilding = newWorldviewText;
        el.editorWorldview.value = newWorldviewText;
        renderWorldviewSections();
        showToast('伏筆已新增');
    } catch (e) {
        showToast('新增失敗');
    }
}

/**
 * 編輯指定的伏筆種子
 * @param {number} seedIndex - 要編輯的伏筆索引
 * @param {string} newText - 新的伏筆內容
 */
async function editWorldviewSeed(seedIndex, newText) {
    if (!newText || !newText.trim()) {
        showToast('請輸入伏筆內容');
        return;
    }
    
    if (!state.currentNovelId) {
        showToast('請先選擇或建立一個小說專案');
        return;
    }
    
    const worldviewText = state.currentNovelData?.worldbuilding || '';
    const seeds = parseWorldviewSeeds(worldviewText);
    
    if (seedIndex < 0 || seedIndex >= seeds.length) {
        showToast('無效的伏筆索引');
        return;
    }
    
    const oldText = seeds[seedIndex];
    
    // 從文本中替換該伏筆
    const lines = worldviewText.split('\n');
    const newLines = [];
    let currentSeedIndex = -1;
    let inSeedsSection = false;
    
    for (const line of lines) {
        // 檢測是否進入伏筆區塊
        if (line.match(/【伏筆[與]?設定?種子】/i)) {
            inSeedsSection = true;
            newLines.push(line);
            continue;
        }
        
        // 檢測是否離開伏筆區塊（遇到新的【標題】）
        if (inSeedsSection && line.match(/^【/) && !line.match(/【伏筆/)) {
            inSeedsSection = false;
            newLines.push(line);
            continue;
        }
        
        if (inSeedsSection) {
            const trimmedLine = line.trim();
            // 跳過空行和標題行
            if (!trimmedLine || trimmedLine.startsWith('#')) {
                newLines.push(line);
                continue;
            }
            
            // 檢查這一行是否是我們要編輯的伏筆
            const isTargetSeed = trimmedLine === oldText || 
                                  trimmedLine.replace(/^[-*•]\s*/, '') === oldText ||
                                  trimmedLine.replace(/^\d+[.、]\s*/, '') === oldText;
            
            if (isTargetSeed) {
                // 保留原有的前綴格式
                const prefixMatch = line.match(/^(\s*[-*•]\s*)/);
                const prefix = prefixMatch ? prefixMatch[1] : '';
                newLines.push(prefix + newText);
            } else {
                newLines.push(line);
            }
        } else {
            newLines.push(line);
        }
    }
    
    const newWorldviewText = newLines.join('\n');
    
    try {
        await requestAPI(`/api/novels/${state.currentNovelId}/worldbuilding`, 'POST', {
            content: newWorldviewText
        });
        state.currentNovelData.worldbuilding = newWorldviewText;
        el.editorWorldview.value = newWorldviewText;
        renderWorldviewSections();
        showToast('伏筆已更新');
    } catch (e) {
        showToast('更新失敗');
    }
}

/**
 * 使用 AI 生成伏筆種子
 */
async function generateWorldviewSeedsWithAI() {
    const hint = await showCustomPrompt('請輸入伏筆生成提示（可留空使用預設）：', '生成3個與主角成長相關的伏筆線索');
    if (hint === null) return; // 用戶取消
    
    showAgentProcessingIndicator('worldview', 'Story Architect');
    
    streamAPI(
        '/api/agent/incremental-architect',
        {
            novel_id: state.currentNovelId,
            target_section: 'foreshadowing_seeds',
            user_hint: hint || '生成3個與主角成長相關的伏筆線索'
        },
        null,
        (delta) => {
            // 將生成的內容追加到世界觀編輯器
            el.editorWorldview.value += delta;
        },
        (err) => {
            showToast('AI 生成失敗: ' + err);
            hideAgentProcessingIndicator('worldview');
        },
        async () => {
            hideAgentProcessingIndicator('worldview');
            showToast('伏筆生成完成');
            await loadNovelDetails(state.currentNovelId);
        }
    );
}



/**
 * 開啟角色 AI 局部增強 Modal
 */
function openCharacterAIEnhanceModal(charIndex, charName) {
    let modal = document.getElementById('modal-character-ai-enhance');
    if (!modal) {
        const html = `
        <div id="modal-character-ai-enhance" class="modal-overlay">
            <div class="modal-card" style="max-width: 500px;">
                <div class="modal-header">
                    <h2>✨ AI 局部增強角色</h2>
                    <button class="btn-close-modal">✕</button>
                </div>
                <div class="modal-body">
                    <p style="margin-bottom:12px; color: var(--text-secondary); font-size:0.85rem;">
                        選擇要增強的欄位，AI 將根據世界觀和已有設定為角色生成更豐富的內容。
                    </p>
                    <div class="form-group">
                        <label>增強欄位</label>
                        <select id="ai-enhance-field">
                            <option value="personality">性格特質 (Personality)</option>
                            <option value="flaws">致命缺陷 (Flaws)</option>
                            <option value="motivation">動機 (Motivation)</option>
                            <option value="arc">成長弧線 (Arc)</option>
                            <option value="backstory">背景故事 (Backstory)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>提示方向（選填）</label>
                        <input type="text" id="ai-enhance-hint" placeholder="例如：讓性格更矛盾、添加童年陰影...">
                    </div>
                    <button id="btn-ai-enhance-submit" class="btn btn-primary btn-full mt-4">🚀 開始 AI 增強</button>
                </div>
            </div>
        </div>`;
        document.body.insertAdjacentHTML('beforeend', html);
        modal = document.getElementById('modal-character-ai-enhance');
        modal.querySelector('.btn-close-modal').addEventListener('click', () => modal.classList.remove('active'));
        modal.addEventListener('click', (e) => { if (e.target === modal) modal.classList.remove('active'); });
    }
    
    document.getElementById('ai-enhance-hint').value = '';
    
    // Rebind submit
    const submitBtn = document.getElementById('btn-ai-enhance-submit');
    const newBtn = submitBtn.cloneNode(true);
    submitBtn.parentNode.replaceChild(newBtn, submitBtn);
    
    newBtn.addEventListener('click', () => {
        const fieldName = document.getElementById('ai-enhance-field').value;
        const userHint = document.getElementById('ai-enhance-hint').value || `增強角色「${charName}」的${fieldName}設定`;
        modal.classList.remove('active');
        
        showAgentProcessingIndicator('characters', 'Character Designer (局部增強)');
        showToast(`正在為「${charName}」進行 AI 局部增強...`);
        
        streamAPI(
            '/api/agent/incremental-character',
            {
                novel_id: state.currentNovelId,
                target_char_index: charIndex,
                field_name: fieldName,
                user_hint: userHint
            },
            null,
            (delta) => {
                // Incremental character returns updated data
                el.editorCharactersJson.value += delta;
            },
            (err) => {
                showToast('AI 增強失敗: ' + err);
                hideAgentProcessingIndicator('characters');
            },
            async () => {
                hideAgentProcessingIndicator('characters');
                showToast(`角色「${charName}」增強完成`);
                await loadNovelDetails(state.currentNovelId);
            }
        );
    });
    
    modal.classList.add('active');
}

// NEW: Open character edit modal
function openCharacterEditModal(index, character) {
    // Create modal if doesn't exist
    let editModal = document.getElementById('modal-character-edit');
    if (!editModal) {
        const modalHtml = `
        <div id="modal-character-edit" class="modal-overlay">
            <div class="modal-card" style="max-width: 600px;">
                <div class="modal-header">
                    <h2>編輯角色</h2>
                    <button class="btn-close-modal">✕</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label>角色名稱</label>
                        <input type="text" id="edit-char-name" placeholder="角色名稱">
                    </div>
                    <div class="form-group">
                        <label>角色定位</label>
                        <select id="edit-char-role">
                            <option value="主角">主角</option>
                            <option value="反派">反派</option>
                            <option value="導師">導師</option>
                            <option value="配角">配角</option>
                            <option value="對手">對手</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>動機</label>
                        <input type="text" id="edit-char-motivation" placeholder="角色的核心動機">
                    </div>
                    <div class="form-group">
                        <label>成長弧線</label>
                        <textarea id="edit-char-arc" rows="2" placeholder="角色的成長軌跡"></textarea>
                    </div>
                    <div class="form-group">
                        <label>性格特質（逗號分隔）</label>
                        <input type="text" id="edit-char-personality" placeholder="勇敢, 冷酷, 機智">
                    </div>
                    <div class="form-group">
                        <label>致命缺陷（逗號分隔）</label>
                        <input type="text" id="edit-char-flaws" placeholder="傲慢, 暴躁">
                    </div>
                    <button id="btn-save-character-edit" class="btn btn-primary btn-full mt-4">保存修改</button>
                </div>
            </div>
        </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        editModal = document.getElementById('modal-character-edit');
        
        // Close handler
        editModal.querySelector('.btn-close-modal').addEventListener('click', () => {
            editModal.classList.remove('active');
        });
        editModal.addEventListener('click', (e) => {
            if (e.target === editModal) editModal.classList.remove('active');
        });
    }
    
    // Populate fields
    document.getElementById('edit-char-name').value = character.name || '';
    document.getElementById('edit-char-role').value = character.role || '配角';
    document.getElementById('edit-char-motivation').value = character.motivation || character.want || '';
    document.getElementById('edit-char-arc').value = character.arc || character.need || '';
    document.getElementById('edit-char-personality').value = (character.personality || []).join(', ');
    
    // Support flaws as array or string or fatal_flaw
    let flawsText = '';
    if (Array.isArray(character.flaws)) {
        flawsText = character.flaws.join(', ');
    } else if (typeof character.flaws === 'string') {
        flawsText = character.flaws;
    } else if (character.fatal_flaw) {
        flawsText = character.fatal_flaw;
    }
    document.getElementById('edit-char-flaws').value = flawsText;
    
    // Save handler - 直接保存，不要觸發其他事件
    const saveBtn = document.getElementById('btn-save-character-edit');
    
    // 移除舊的事件監聽器（用 cloneNode 方式）
    const newSaveBtn = saveBtn.cloneNode(true);
    saveBtn.parentNode.replaceChild(newSaveBtn, saveBtn);
    
    newSaveBtn.addEventListener('click', () => {
        // 直接發送 API 請求，不要從 textarea 讀取
        const charData = state.currentNovelData.characters;
        if (charData && charData.characters && charData.characters[index]) {
            const originalChar = charData.characters[index];
            const updatedChar = {
                ...originalChar,
                name: document.getElementById('edit-char-name').value,
                role: document.getElementById('edit-char-role').value,
                motivation: document.getElementById('edit-char-motivation').value,
                want: document.getElementById('edit-char-motivation').value, // compatibility
                arc: document.getElementById('edit-char-arc').value,
                need: document.getElementById('edit-char-arc').value, // compatibility
                personality: document.getElementById('edit-char-personality').value.split(',').map(s => s.trim()).filter(s => s),
                flaws: document.getElementById('edit-char-flaws').value.split(',').map(s => s.trim()).filter(s => s),
                fatal_flaw: document.getElementById('edit-char-flaws').value // compatibility
            };
            
            charData.characters[index] = updatedChar;
            state.currentNovelData.characters = charData;
            const newRaw = JSON.stringify(charData, null, 2);
            state.currentNovelData.characters_raw = newRaw;
            if (el.editorCharactersJson) el.editorCharactersJson.value = newRaw;
            
            // 直接發送 API 請求保存
            requestAPI(`/api/novels/${state.currentNovelId}/characters`, 'POST', { json_data: charData })
                .then(() => {
                    showToast('角色已更新');
                    // 重新渲染卡片
                    renderCharactersTab();
                })
                .catch(() => {
                    showToast('保存失敗');
                });
            
            editModal.classList.remove('active');
        }
    });
    
    editModal.classList.add('active');
}



/**
 * 手動插入章節大綱 Modal
 */
function openManualChapterInsertModal(afterChapterIndex) {
    let modal = document.getElementById('modal-chapter-insert');
    if (!modal) {
        const html = `
        <div id="modal-chapter-insert" class="modal-overlay">
            <div class="modal-card" style="max-width: 600px;">
                <div class="modal-header">
                    <h2>➕ 手動插入新章大綱</h2>
                    <button class="btn-close-modal">✕</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label>章節標題</label>
                        <input type="text" id="insert-chapter-title" placeholder="新章節標題">
                    </div>
                    <div class="form-group">
                        <label>章節目的/功能本質</label>
                        <input type="text" id="insert-chapter-purpose" placeholder="本章存在的敘事目的">
                    </div>
                    <div class="form-group">
                        <label>核心事件（每行一項）</label>
                        <textarea id="insert-chapter-events" rows="3" placeholder="每行一個事件描述"></textarea>
                    </div>
                    <div class="form-group">
                        <label>伏筆提示（每行一項）</label>
                        <textarea id="insert-chapter-foreshadowing" rows="2" placeholder="需要在本章埋下的伏筆"></textarea>
                    </div>
                    <div class="form-group">
                        <label>情緒基調</label>
                        <select id="insert-chapter-tone">
                            <option value="緊張">緊張</option>
                            <option value="舒緩">舒緩</option>
                            <option value="悲傷">悲傷</option>
                            <option value="振奮">振奮</option>
                            <option value="懸疑">懸疑</option>
                            <option value="均衡" selected>均衡</option>
                        </select>
                    </div>
                    <button id="btn-insert-chapter-submit" class="btn btn-primary btn-full mt-4">插入章節</button>
                </div>
            </div>
        </div>`;
        document.body.insertAdjacentHTML('beforeend', html);
        modal = document.getElementById('modal-chapter-insert');
        modal.querySelector('.btn-close-modal').addEventListener('click', () => modal.classList.remove('active'));
        modal.addEventListener('click', (e) => { if (e.target === modal) modal.classList.remove('active'); });
    }
    
    // Clear fields
    document.getElementById('insert-chapter-title').value = '';
    document.getElementById('insert-chapter-purpose').value = '';
    document.getElementById('insert-chapter-events').value = '';
    document.getElementById('insert-chapter-foreshadowing').value = '';
    document.getElementById('insert-chapter-tone').value = '均衡';
    
    // Rebind submit
    const submitBtn = document.getElementById('btn-insert-chapter-submit');
    const newBtn = submitBtn.cloneNode(true);
    submitBtn.parentNode.replaceChild(newBtn, submitBtn);
    
    newBtn.addEventListener('click', async () => {
        const chapterData = {
            title: document.getElementById('insert-chapter-title').value || '新章節',
            purpose: document.getElementById('insert-chapter-purpose').value || '推動劇情',
            events: document.getElementById('insert-chapter-events').value.split('\n').map(s => s.trim()).filter(s => s),
            foreshadowing: document.getElementById('insert-chapter-foreshadowing').value.split('\n').map(s => s.trim()).filter(s => s),
            emotional_tone: document.getElementById('insert-chapter-tone').value
        };
        
        try {
            await requestAPI(`/api/novels/${state.currentNovelId}/plot/chapters/insert`, 'POST', {
                insert_after_index: afterChapterIndex,
                chapter_data: chapterData
            });
            modal.classList.remove('active');
            showToast('新章節已插入');
            await loadNovelDetails(state.currentNovelId);
        } catch (e) {
            showToast('插入失敗: ' + (e.message || '未知錯誤'));
        }
    });
    
    modal.classList.add('active');
}

// 新增：章節大綱編輯 Modal
function openChapterOutlineEditModal(index, chapter) {
    let editModal = document.getElementById('modal-chapter-outline-edit');
    if (!editModal) {
        const modalHtml = `
        <div id="modal-chapter-outline-edit" class="modal-overlay">
            <div class="modal-card" style="max-width: 700px; max-height: 90vh; overflow-y: auto;">
                <div class="modal-header">
                    <h2>編輯章節大綱</h2>
                    <button class="btn-close-modal">✕</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label>章節標題</label>
                        <input type="text" id="edit-chapter-title" placeholder="章節標題">
                    </div>
                    <div class="form-group">
                        <label>故事內時間設定</label>
                        <input type="text" id="edit-chapter-time-setting" placeholder="例如：大元三年春・深夜">
                    </div>
                    <div class="form-group">
                        <label>距前章時間跨度</label>
                        <input type="text" id="edit-chapter-time-span" placeholder="例如：三日後、半年後">
                    </div>
                    <div class="form-group">
                        <label>本章目的/功能本質</label>
                        <input type="text" id="edit-chapter-purpose" placeholder="本章存在的敘事目的">
                    </div>
                    <div class="form-group">
                        <label>主導情緒基調</label>
                        <select id="edit-chapter-emotional-tone">
                            <option value="緊張">緊張</option>
                            <option value="舒緩">舒緩</option>
                            <option value="悲傷">悲傷</option>
                            <option value="振奮">振奮</option>
                            <option value="懸疑">懸疑</option>
                            <option value="均衡">均衡</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>事件大綱（每行一項）</label>
                        <textarea id="edit-chapter-events" rows="4" placeholder="每行描述一個核心事件"></textarea>
                    </div>
                    <div class="form-group">
                        <label>伏筆埋設（每行一項）</label>
                        <textarea id="edit-chapter-foreshadowing" rows="2" placeholder="需要在本章埋下的伏筆線索"></textarea>
                    </div>
                    <div class="form-group">
                        <label>章末懸念/鉤子</label>
                        <textarea id="edit-chapter-cliffhanger" rows="2" placeholder="驅動讀者翻下一章的懸念"></textarea>
                    </div>
                    <button id="btn-save-chapter-outline-edit" class="btn btn-primary btn-full mt-4">保存修改</button>
                </div>
            </div>
        </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        editModal = document.getElementById('modal-chapter-outline-edit');
        
        // Close handler
        editModal.querySelector('.btn-close-modal').addEventListener('click', () => {
            editModal.classList.remove('active');
        });
        editModal.addEventListener('click', (e) => {
            if (e.target === editModal) editModal.classList.remove('active');
        });
    }
    
    // 填充當前值
    document.getElementById('edit-chapter-title').value = chapter.title || '';
    document.getElementById('edit-chapter-time-setting').value = chapter.time_setting || '';
    document.getElementById('edit-chapter-time-span').value = chapter.time_span || '';
    document.getElementById('edit-chapter-purpose').value = chapter.purpose || '';
    document.getElementById('edit-chapter-emotional-tone').value = chapter.emotional_tone || '均衡';
    
    // 處理 events 轉為文字行
    let eventsText = '';
    if (Array.isArray(chapter.events)) {
        eventsText = chapter.events.map(e => {
            if (typeof e === 'string') return e;
            if (typeof e === 'object' && e !== null) {
                return `${e.scene || ''}: ${e.action || ''}`;
            }
            return String(e);
        }).join('\n');
    }
    document.getElementById('edit-chapter-events').value = eventsText;
    
    // 處理 foreshadowing
    let foreshadowText = '';
    if (chapter.foreshadowing && Array.isArray(chapter.foreshadowing)) {
        foreshadowText = chapter.foreshadowing.map(f => typeof f === 'string' ? f : JSON.stringify(f)).join('\n');
    }
    document.getElementById('edit-chapter-foreshadowing').value = foreshadowText;
    
    document.getElementById('edit-chapter-cliffhanger').value = chapter.cliffhanger || '';
    
    // 保存 handler
    const saveBtn = document.getElementById('btn-save-chapter-outline-edit');
    const newSaveBtn = saveBtn.cloneNode(true);
    saveBtn.parentNode.replaceChild(newSaveBtn, saveBtn);
    
    newSaveBtn.addEventListener('click', () => {
        const plotData = state.currentNovelData.plot;
        if (plotData && plotData.chapters && plotData.chapters[index]) {
            const eventsInput = document.getElementById('edit-chapter-events').value;
            const eventsArray = eventsInput.split('\n').map(s => s.trim()).filter(s => s);
            
            const foreshadowInput = document.getElementById('edit-chapter-foreshadowing').value;
            const foreshadowArray = foreshadowInput.split('\n').map(s => s.trim()).filter(s => s);
            
            // 更新章節數據，保留所有欄位
            const updatedChapter = {
                ...plotData.chapters[index],
                title: document.getElementById('edit-chapter-title').value,
                time_setting: document.getElementById('edit-chapter-time-setting').value,
                time_span: document.getElementById('edit-chapter-time-span').value,
                purpose: document.getElementById('edit-chapter-purpose').value,
                emotional_tone: document.getElementById('edit-chapter-emotional-tone').value,
                events: eventsArray,
                foreshadowing: foreshadowArray,
                cliffhanger: document.getElementById('edit-chapter-cliffhanger').value
            };
            
            plotData.chapters[index] = updatedChapter;
            state.currentNovelData.plot = plotData;
            state.currentNovelData.plot_raw = JSON.stringify(plotData, null, 2);
            el.editorPlotJson.value = state.currentNovelData.plot_raw;
            savePlotOutlineDirect();
            
            editModal.classList.remove('active');
            showToast('章節大綱已更新');
        }
    });
    
    editModal.classList.add('active');
}



function disableWriterPanel() {
    el.btnWriteChapter.disabled = true;
    el.btnEditChapter.disabled = true;
    el.btnProseSave.disabled = true;
    el.editorProse.disabled = true;
    el.editorProse.value = '';
    el.activeChapterTitle.textContent = "第 0 章：請選擇一個章節";
    el.chapterOutlineSummaryText.textContent = "選擇左側章節查看 AI 大綱事件...";
}



/**
 * 格式化時間戳為 HH:MM 格式
 * @param {string|Date} timestamp - 時間戳或 Date 物件
 * @returns {string} 格式化後的時間字串
 */
function formatTimestamp(timestamp) {
    if (!timestamp) {
        // 如果沒有時間戳，使用當前時間
        const now = new Date();
        return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    }
    
    try {
        const date = timestamp instanceof Date ? timestamp : new Date(timestamp);
        if (isNaN(date.getTime())) {
            // 無效日期，使用當前時間
            const now = new Date();
            return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
        }
        return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
    } catch (e) {
        const now = new Date();
        return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    }
}



// ==========================================
// DIRECT DATABASE SAVE CALLBACKS
// ==========================================
async function saveWorldviewDirect() {
    if (!state.currentNovelId) return;
    const content = el.editorWorldview.value;
    try {
        await requestAPI(`/api/novels/${state.currentNovelId}/worldbuilding`, 'POST', { content });
        state.currentNovelData.worldbuilding = content;
        showToast("世界觀保存成功");
    } catch (e) {
        showToast("世界觀保存失敗");
    }
}

async function saveCharactersDirect() {
    if (!state.currentNovelId) return;
    const rawVal = el.editorCharactersJson.value;
    let parsedData = null;
    try {
        parsedData = JSON.parse(rawVal);
    } catch (e) {
        showToast("JSON 語法錯誤！無法保存視覺卡片。");
        return;
    }
    
    try {
        await requestAPI(`/api/novels/${state.currentNovelId}/characters`, 'POST', { json_data: parsedData });
        state.currentNovelData.characters = parsedData;
        state.currentNovelData.characters_raw = rawVal;
        renderCharactersTab();
        showToast("角色 Bible 保存成功");
    } catch (e) {
        showToast("角色 Bible 保存失敗");
    }
}

async function savePlotOutlineDirect() {
    if (!state.currentNovelId) return;
    const rawVal = el.editorPlotJson.value;
    let parsedData = null;
    try {
        parsedData = JSON.parse(rawVal);
    } catch (e) {
        showToast("JSON 語法錯誤！無法保存時間軸。");
        return;
    }
    
    try {
        await requestAPI(`/api/novels/${state.currentNovelId}/plot`, 'POST', { outline_json: parsedData });
        state.currentNovelData.plot = parsedData;
        state.currentNovelData.plot_raw = rawVal;
        renderPlotTab();
        showToast("章節大綱保存成功");
    } catch (e) {
        showToast("章節大綱保存失敗");
    }
}

async function saveProseDirect() {
    if (!state.currentNovelId || !state.activeChapterIndex) return;
    
    // 💡 防禦安全鎖：如果當前活動章節正在 AI 背景寫作，優先保存快取，絕不讀取文本框 (防止切換章節時的 `blur` 覆蓋污染)
    let content = el.editorProse.value;
    const isWriting = state.currentlyWritingChapterIndex === state.activeChapterIndex;
    if (isWriting && state.writingBuffer !== undefined && state.writingBuffer !== null) {
        content = state.writingBuffer;
    }
    
    try {
        await requestAPI(`/api/novels/${state.currentNovelId}/chapters/${state.activeChapterIndex}`, 'POST', { content });
        
        // update memory state
        const chs = state.currentNovelData.chapters || [];
        const existingIdx = chs.findIndex(c => c.chapter_index === state.activeChapterIndex);
        if (existingIdx !== -1) {
            chs[existingIdx].content = content;
        } else {
            chs.push({ chapter_index: state.activeChapterIndex, content });
        }
        state.currentNovelData.chapters = chs;
        
        renderWriterTab();
        showToast(`第 ${state.activeChapterIndex} 章正文已保存`);
    } catch (e) {
        showToast("正文保存失敗");
    }
}

// ==========================================
// DIRECTOR COMMAND PARSER (總監指令解析器)
// ==========================================

/**
 * 解析總監回覆中的執行指令區塊
 * 支援舊格式（ACTION/TARGET/HINT）和新格式（JSON格式）
 */
function parseDirectorCommand(responseText) {
    const result = {
        action: null,
        tool: null,
        target: null,
        params: {},
        reason: "",
        raw_command: null
    };
    
    // 嘗試解析 JSON 格式的執行指令區塊
    const jsonBlockMatch = responseText.match(/```json\s*(\{[\s\S]*?\})\s*```/);
    if (jsonBlockMatch) {
        try {
            const jsonCommand = JSON.parse(jsonBlockMatch[1]);
            result.action = jsonCommand.action;
            result.tool = jsonCommand.tool;
            result.target = jsonCommand.target;
            result.params = jsonCommand.params || {};
            result.reason = jsonCommand.reason || "";
            result.raw_command = jsonCommand;
            return result;
        } catch (e) {
            console.warn("Failed to parse JSON command block:", e);
        }
    }
    
    // 嘗試解析舊格式的【執行指令】區塊
    const actionMatch = responseText.match(/\【執行指令\][\s\S]*?ACTION:\s*(\w+)/);
    const targetMatch = responseText.match(/TARGET:\s*(\w+)/);
    const hintMatch = responseText.match(/HINT:\s*([\s\S]*?)(?=```|$)/);
    const reasonMatch = responseText.match(/REASON:\s*([\s\S]*?)(?=```|$)/);
    const toolMatch = responseText.match(/TOOL:\s*(\w+)/);
    
    if (actionMatch) {
        result.action = actionMatch[1].trim().toUpperCase();
        result.target = targetMatch ? targetMatch[1].trim() : null;
        result.reason = reasonMatch ? reasonMatch[1].trim() : "";
        
        // 從舊格式提取 hint 到 params
        if (hintMatch) {
            result.params.hint = hintMatch[1].trim();
        }
        
        // 嘗試從 responseText 中提取其他參數
        const userPromptMatch = responseText.match(/user_prompt["\s:]+([^}"]+)/);
        if (userPromptMatch) {
            result.params.user_prompt = userPromptMatch[1].trim();
        }
    }
    
    return result;
}

/**
 * 執行總監的增量更新指令
 */
async function executeIncrementalCommand(command) {
    const { action, target, params } = command;
    
    switch (action) {
        case 'INCREMENTAL_UPDATE':
            return await executeIncrementalUpdate(target, params);
        case 'TOOL_CALL':
            return await executeToolCall(target, params);
        case 'AUTO_REGENERATE':
            return await executeAutoRegenerate(target, params);
        default:
            console.warn("Unknown action:", action);
            return false;
    }
}

/**
 * 執行增量更新操作
 */
async function executeIncrementalUpdate(target, params) {
    const { user_hint, insert_after_index, target_char_index, field_name } = params;
    
    switch (target) {
        case 'foreshadowing_seeds':
            // 新增伏筆種子
            showToast("🌱 增量新增伏筆種子...");
            return new Promise((resolve) => {
                streamAPI(
                    '/api/agent/incremental-architect',
                    { 
                        novel_id: state.currentNovelId, 
                        target_section: 'foreshadowing_seeds',
                        user_hint: user_hint || params.hint || '新增一個伏筆'
                    },
                    null,
                    (delta) => {
                        if (el.editorWorldview) {
                            el.editorWorldview.value += delta;
                        }
                    },
                    (err) => showToast("Error: " + err),
                    async () => {
                        showToast("伏筆種子新增完成");
                        await loadNovelDetails(state.currentNovelId);
                        resolve(true);
                    }
                );
            });
            
        case 'three_act_structure':
            // 更新三幕式結構
            showToast("📐 增量更新三幕式結構...");
            return new Promise((resolve) => {
                streamAPI(
                    '/api/agent/incremental-architect',
                    { 
                        novel_id: state.currentNovelId, 
                        target_section: 'three_act_structure',
                        user_hint: user_hint || params.hint || '更新三幕式結構'
                    },
                    null,
                    (delta) => {
                        if (el.editorWorldview) {
                            el.editorWorldview.value += delta;
                        }
                    },
                    (err) => showToast("Error: " + err),
                    async () => {
                        showToast("三幕式結構更新完成");
                        await loadNovelDetails(state.currentNovelId);
                        resolve(true);
                    }
                );
            });
            
        case 'character':
            // 修改角色的特定欄位
            showToast("👤 增量更新角色欄位...");
            return new Promise((resolve) => {
                streamAPI(
                    '/api/agent/incremental-character',
                    { 
                        novel_id: state.currentNovelId, 
                        target_char_index: target_char_index,
                        field_name: field_name,
                        user_hint: user_hint || params.hint || '修改角色'
                    },
                    null,
                    (delta) => {
                        if (el.editorCharactersJson) {
                            el.editorCharactersJson.value += delta;
                        }
                    },
                    (err) => showToast("Error: " + err),
                    async () => {
                        showToast("角色更新完成");
                        await loadNovelDetails(state.currentNovelId);
                        resolve(true);
                    }
                );
            });
            
        case 'new_character':
            // 新增一個新角色
            showToast("➕ 新增角色...");
            return new Promise((resolve) => {
                streamAPI(
                    '/api/agent/incremental-character',
                    { 
                        novel_id: state.currentNovelId, 
                        target_char_index: null, // 表示新增
                        field_name: null,
                        user_hint: user_hint || params.hint || '新增一個新角色'
                    },
                    null,
                    (delta) => {
                        if (el.editorCharactersJson) {
                            el.editorCharactersJson.value += delta;
                        }
                    },
                    (err) => showToast("Error: " + err),
                    async () => {
                        showToast("新角色新增完成");
                        await loadNovelDetails(state.currentNovelId);
                        resolve(true);
                    }
                );
            });
            
        case 'plot_chapter':
            // 在指定位置插入新章節大綱
            showToast("📝 增量插入新章節大綱...");
            return new Promise((resolve) => {
                streamAPI(
                    '/api/agent/incremental-plot',
                    { 
                        novel_id: state.currentNovelId, 
                        insert_after_index: insert_after_index ?? 0,
                        user_hint: user_hint || params.hint || '插入新章節'
                    },
                    null,
                    (delta) => {
                        if (el.editorPlotJson) {
                            el.editorPlotJson.value += delta;
                        }
                    },
                    (err) => showToast("Error: " + err),
                    async () => {
                        showToast("新章節插入完成");
                        await loadNovelDetails(state.currentNovelId);
                        resolve(true);
                    }
                );
            });
            
        default:
            showToast(`⚠️ 不支援的增量操作目標: ${target}`);
            return false;
    }
}

/**
 * 執行工具調用（全量生成）
 */
async function executeToolCall(tool, params) {
    const { user_prompt, chapter_index } = params;
    
    switch (tool) {
        case 'story-architect':
            showToast("🏗️ 執行故事架構師（全量生成）...");
            return new Promise((resolve) => {
                el.editorWorldview.value = '';
                streamAPI(
                    '/api/agent/story-architect',
                    { novel_id: state.currentNovelId, user_prompt: user_prompt || params.hint },
                    null,
                    (delta) => { el.editorWorldview.value += delta; },
                    (err) => showToast("Error: " + err),
                    async () => {
                        await loadNovelDetails(state.currentNovelId);
                        resolve(true);
                    }
                );
            });
            
        case 'character-designer':
            showToast("👥 執行角色設計師（全量生成）...");
            return new Promise((resolve) => {
                el.editorCharactersJson.value = '';
                streamAPI(
                    '/api/agent/character-designer',
                    { novel_id: state.currentNovelId, user_prompt: user_prompt || params.hint },
                    null,
                    (delta) => { el.editorCharactersJson.value += delta; },
                    (err) => showToast("Error: " + err),
                    async () => {
                        await loadNovelDetails(state.currentNovelId);
                        resolve(true);
                    }
                );
            });
            
        case 'plot-planner':
            showToast("📋 執行劇情規劃師（全量生成）...");
            return new Promise((resolve) => {
                el.editorPlotJson.value = '';
                streamAPI(
                    '/api/agent/plot-planner',
                    { novel_id: state.currentNovelId, user_prompt: user_prompt || params.hint },
                    null,
                    (delta) => { el.editorPlotJson.value += delta; },
                    (err) => showToast("Error: " + err),
                    async () => {
                        await loadNovelDetails(state.currentNovelId);
                        resolve(true);
                    }
                );
            });
            
        case 'write-chapter':
            showToast(`✍️ 執行章節寫手（第 ${chapter_index} 章）...`);
            return new Promise((resolve) => {
                state.currentlyWritingChapterIndex = chapter_index || 1;
                state.writingBuffer = "";
                
                const virtualTarget = {
                    get value() { return state.writingBuffer; },
                    set value(val) {
                        state.writingBuffer = val;
                        if (state.activeChapterIndex === state.currentlyWritingChapterIndex) {
                            el.editorProse.value = val;
                            el.editorProse.scrollTop = el.editorProse.scrollHeight;
                        }
                    },
                    get scrollTop() { return el.editorProse.scrollTop; },
                    set scrollTop(val) {
                        if (state.activeChapterIndex === state.currentlyWritingChapterIndex) {
                            el.editorProse.scrollTop = val;
                        }
                    },
                    get scrollHeight() { return el.editorProse.scrollHeight; }
                };

                streamAPI(
                    '/api/agent/write-chapter',
                    { novel_id: state.currentNovelId, chapter_index: chapter_index || 1 },
                    null,
                    (delta) => { virtualTarget.value += delta; },
                    (err) => showToast("Error: " + err),
                    async () => {
                        if (state.writingBuffer.trim().length > 0) {
                            await saveProseDirect();
                        }
                        state.currentlyWritingChapterIndex = null;
                        state.writingBuffer = "";
                        await loadNovelDetails(state.currentNovelId);
                        resolve(true);
                    }
                );
            });
            
        default:
            showToast(`⚠️ 不支援的工具調用: ${tool}`);
            return false;
    }
}

/**
 * 執行自動重新生成
 */
async function executeAutoRegenerate(target, params) {
    const { hint } = params;
    
    switch (target) {
        case 'worldview':
        case '世界觀':
            showToast("🔄 重新生成世界觀...");
            return new Promise((resolve) => {
                el.editorWorldview.value = '';
                const prompt = hint || "請重新設計世界觀";
                streamAPI(
                    '/api/agent/story-architect',
                    { novel_id: state.currentNovelId, user_prompt: prompt },
                    null,
                    (delta) => { el.editorWorldview.value += delta; },
                    (err) => showToast("Error: " + err),
                    async () => {
                        await loadNovelDetails(state.currentNovelId);
                        resolve(true);
                    }
                );
            });
            
        case 'characters':
        case '角色':
            showToast("🔄 重新生成角色設計...");
            return new Promise((resolve) => {
                el.editorCharactersJson.value = '';
                const prompt = hint || "請重新設計角色";
                streamAPI(
                    '/api/agent/character-designer',
                    { novel_id: state.currentNovelId, user_prompt: prompt },
                    null,
                    (delta) => { el.editorCharactersJson.value += delta; },
                    (err) => showToast("Error: " + err),
                    async () => {
                        await loadNovelDetails(state.currentNovelId);
                        resolve(true);
                    }
                );
            });
            
        case 'plot':
        case '章節大綱':
            showToast("🔄 重新生成章節大綱...");
            return new Promise((resolve) => {
                el.editorPlotJson.value = '';
                const prompt = hint || "請重新規劃章節大綱";
                streamAPI(
                    '/api/agent/plot-planner',
                    { novel_id: state.currentNovelId, user_prompt: prompt },
                    null,
                    (delta) => { el.editorPlotJson.value += delta; },
                    (err) => showToast("Error: " + err),
                    async () => {
                        await loadNovelDetails(state.currentNovelId);
                        resolve(true);
                    }
                );
            });
            
        default:
            showToast(`⚠️ 不支援的重新生成目標: ${target}`);
            return false;
    }
}

// ==========================================
// DYNAMIC AGENT AGENT TEAM EXECUTION (STREAMING)
// ==========================================
function startAgentStream(endpoint, body, onContentTarget, onDoneCallback, options = {}) {
    const tabName = options.tabName || 'worldview';
    const agentName = options.agentName || 'AI Agent';
    
    // Reset thinking text, show streaming box
    el.aiThinkingStream.classList.remove('hidden');
    el.aiThinkingText.textContent = '';
    
    // Clear and focus target
    onContentTarget.value = '';
    
    // Show Agent processing indicator
    showAgentProcessingIndicator(tabName, agentName);
    
    let hasError = false; // Track error to prevent done callback
    
    streamAPI(
        endpoint,
        body,
        // onThinking
        (delta) => {
            el.aiThinkingText.textContent += delta;
            window.updateAgentStreamOutput(tabName, delta);
        },
        // onContent
        (delta) => {
            onContentTarget.value += delta;
            // auto scroll textarea to bottom while streaming
            onContentTarget.scrollTop = onContentTarget.scrollHeight;
            window.updateAgentStreamOutput(tabName, delta);
        },
        // onError
        (msg) => {
            showToast(msg);
            el.aiThinkingText.textContent += `\n[Error: ${msg}]`;
            window.updateAgentStreamOutput(tabName, `\n[Error: ${msg}]`);
            hasError = true;
        },
        // onDone
        () => {
            el.aiThinkingStream.classList.add('hidden');
            // Hide Agent processing indicator
            hideAgentProcessingIndicator(tabName);
            if (!hasError && onDoneCallback) onDoneCallback();
        }
    );
}



/**
 * 從歷史聊天按鈕或暫停後重新啟動 Pipeline
 */
async function resumePipelineWithDecision(activeTab, parsed, choice) {
    const userPrompt = (state.pipelinePrompt || '').trim()
        || (state.currentNovelData?.novel?.pipeline_prompt || '').trim()
        || '';
        
    let decisionResult = { ...parsed };
    
    state.isPipelineRunning = true;
    showPipelineProgress(true);
    
    if (choice === 'accept') {
        showToast('✅ 用戶接受總監決策');
        await executeDirectorAction(decisionResult, userPrompt);
    } else if (choice === 'continue') {
        showToast('▶️ 用戶強制繼續下一階段');
        let nextTarget = decisionResult.target;
        if (!nextTarget) {
            if (activeTab === 'worldview') nextTarget = 'characters';
            else if (activeTab === 'characters') nextTarget = 'plot';
            else if (activeTab === 'plot') nextTarget = 'writer';
        }
        await executeDirectorAction({ 
            ...decisionResult, 
            action: 'CONTINUE', 
            continue: true, 
            shouldPause: false,
            target: nextTarget 
        }, userPrompt);
    } else if (choice === 'regen') {
        showToast('🔄 用戶指示重新生成');
        await executeDirectorAction({ 
            ...decisionResult, 
            action: 'AUTO_REGENERATE', 
            continue: true, 
            regenerate: true, 
            regenerateStage: activeTab, 
            target: activeTab 
        }, userPrompt);
    } else {
        showToast('⏸️ 管線已暫停');
        state.isPipelineRunning = false;
        showPipelineProgress(false);
        await loadNovelDetails(state.currentNovelId);
    }
}

async function runDirectorDecision(currentStage, providedUserPrompt = null) {
    return new Promise((resolve) => {
        const directorResponseContainer = document.createElement('div');
        directorResponseContainer.className = 'message assistant-msg';
        const directorTimestamp = formatTimestamp();
        directorResponseContainer.innerHTML = `<div class="msg-sender-row"><div class="msg-sender">🎬 AI 總監決策中...</div><div class="msg-timestamp">${directorTimestamp}</div></div><div class="msg-content stream-typing"></div>`;
        el.chatMessagesContainer.appendChild(directorResponseContainer);
        el.chatMessagesContainer.scrollTop = el.chatMessagesContainer.scrollHeight;
        
        const streamTarget = directorResponseContainer.querySelector('.stream-typing');
        
        const userPrompt = (providedUserPrompt || '').trim()
            || (state.pipelinePrompt || '').trim()
            || (state.currentNovelData?.novel?.pipeline_prompt || '').trim()
            || '';
        
        streamAPI(
            '/api/novels/' + state.currentNovelId + '/director-decision',
            { current_stage: currentStage, user_prompt: userPrompt },
            () => {},
            (delta) => {
                streamTarget.textContent += delta;
                el.chatMessagesContainer.scrollTop = el.chatMessagesContainer.scrollHeight;
            },
            (err) => {
                streamTarget.textContent += `\n[總監連線錯誤: ${err}]`;
                streamTarget.classList.remove('stream-typing');
                streamTarget.classList.add('streaming-done');
            },
            async () => {
                // 回覆完成，停止閃爍效果
                streamTarget.classList.remove('stream-typing');
                streamTarget.classList.add('streaming-done');
                
                const responseText = streamTarget.textContent;
                
                // 添加 director-response 樣式
                directorResponseContainer.classList.add('director-response');
                
                const decisionResult = parseDirectorDecisionText(responseText, currentStage);
                const action = decisionResult.action;
                
                // 顯示解析結果的 Toast
                const actionLabels = {
                    'CONTINUE': '✅ 繼續下一階段',
                    'AUTO_REGENERATE': '⚡ 重新生成',
                    'GO_BACK_TO_WORLDVIEW': '↩️ 回退到世界觀',
                    'GO_BACK_TO_CHARACTERS': '↩️ 回退到角色',
                    'GO_BACK_TO_PLOT': '↩️ 回退到大綱',
                    'WRITE_ALL_CHAPTERS': '📖 開始寫全書',
                    'WAIT_USER': '⏸️ 等待確認',
                    'FINISH': '🎉 任務完成'
                };
                if (action && actionLabels[action]) {
                    showToast(`總監決策：${actionLabels[action]}`);
                }
                
                // DUAL-MODE: Auto vs Normal
                if (state.isAutoExecuteMode) {
                    // 一鍵模式：自動執行總監的指令
                    resolve(decisionResult);
                } else {
                    // 一般模式：顯示互動選項按鈕讓用戶選擇
                    const actionsDiv = document.createElement('div');
                    actionsDiv.className = 'chat-action-buttons';
                    actionsDiv.innerHTML = `
                        <button class="btn-chat-action" data-action="accept" title="執行總監建議的動作">✅ 接受總監決策${action ? ` (${actionLabels[action] || action})` : ''}</button>
                        <button class="btn-chat-action" data-action="continue">▶️ 強制繼續下一階段</button>
                        <button class="btn-chat-action" data-action="regen">🔄 重新生成此階段</button>
                        <button class="btn-chat-action" data-action="pause">⏸️ 暫停並手動修改</button>
                    `;
                    directorResponseContainer.querySelector('.msg-content').appendChild(actionsDiv);
                    
                    actionsDiv.querySelectorAll('.btn-chat-action').forEach(btn => {
                        btn.addEventListener('click', function() {
                            const userChoice = this.dataset.action;
                            // Disable buttons after choice
                            actionsDiv.querySelectorAll('.btn-chat-action').forEach(b => {
                                b.disabled = true;
                                b.style.opacity = '0.5';
                            });
                            this.style.opacity = '1';
                            this.style.borderColor = 'var(--primary)';
                            this.style.fontWeight = '700';
                            
                            if (userChoice === 'accept') {
                                // 執行總監原始決策
                                showToast('✅ 用戶接受總監決策');
                                resolve(decisionResult);
                            } else if (userChoice === 'continue') {
                                showToast('▶️ 用戶強制繼續下一階段');
                                resolve({ ...decisionResult, action: 'CONTINUE', continue: true, shouldPause: false });
                            } else if (userChoice === 'regen') {
                                showToast('🔄 用戶指示重新生成');
                                resolve({ ...decisionResult, action: 'AUTO_REGENERATE', continue: true, regenerate: true, regenerateStage: currentStage, target: currentStage });
                            } else {
                                showToast('⏸️ 管線暫停，可手動修改後再繼續');
                                resolve({ ...decisionResult, action: 'WAIT_USER', continue: false, shouldPause: true });
                            }
                        });
                    });
                }
            }
        );
    });
}


// 詢問用戶對於已有內容的處理方式（三選項：加強、重新生成、跳過）
function askContentAction(stageName, callback) {
    const result = prompt(`【${stageName}】已有內容存在。\n\n請輸入數字選擇操作：\n1. 加強現有內容\n2. 重新生成\n3. 跳過此階段\n\n（直接關閉 = 跳過）`);
    
    if (result === '1') {
        callback('enhance');
    } else if (result === '2') {
        callback('regenerate');
    } else {
        callback('skip');
    }
}

// 檢查某個階段是否有內容
function checkStageHasContent(stage) {
    const data = state.currentNovelData;
    if (!data) return false;
    
    switch (stage) {
        case 'worldview':
            return data.worldbuilding && data.worldbuilding.trim().length > 0;
        case 'characters':
            return data.characters_raw && data.characters_raw.trim().length > 0 && 
                   data.characters_raw !== '{\n  "characters": []\n}';
        case 'plot':
            return data.plot_raw && data.plot_raw.trim().length > 0 && 
                   data.plot_raw !== '{\n  "chapters": []\n}';
        case 'writer':
            return data.chapters && data.chapters.length > 0;
        default:
            return false;
    }
}

// 增強現有內容（不重新生成，只是補充）
function enhanceExistingContent(stage) {
    return new Promise((resolve) => {
        const data = state.currentNovelData;
        let enhancePrompt = '';
        
        switch (stage) {
            case 'worldview':
                enhancePrompt = `請基於以下現有的世界觀設定，進行補充與強化，使其更加完善：\n\n${data.worldbuilding}\n\n請以 JSON 格式輸出更新後的世界觀。`;
                streamAPI(
                    '/api/agent/story-architect',
                    { novel_id: state.currentNovelId, user_prompt: enhancePrompt },
                    () => {},
                    (delta) => {
                        if (el.editorWorldview) {
                            el.editorWorldview.value += delta;
                            el.editorWorldview.scrollTop = el.editorWorldview.scrollHeight;
                        }
                    },
                    (msg) => showToast(`Error: ${msg}`),
                    async () => {
                        showToast("世界觀加強完成");
                        await loadNovelDetails(state.currentNovelId);
                        resolve();
                    }
                );
                break;
                
            case 'characters':
                enhancePrompt = `請基於以下現有的角色設定，進行補充與強化：\n\n${data.characters_raw}\n\n請以 JSON 格式輸出更新後的角色設定。`;
                streamAPI(
                    '/api/agent/character-designer',
                    { novel_id: state.currentNovelId, user_prompt: enhancePrompt },
                    () => {},
                    (delta) => {
                        if (el.editorCharactersJson) {
                            el.editorCharactersJson.value += delta;
                            el.editorCharactersJson.scrollTop = el.editorCharactersJson.scrollHeight;
                        }
                    },
                    (msg) => showToast(`Error: ${msg}`),
                    async () => {
                        showToast("角色加強完成");
                        await loadNovelDetails(state.currentNovelId);
                        resolve();
                    }
                );
                break;
                
            case 'plot':
                enhancePrompt = `請基於以下現有的大綱，進行補充與優化：\n\n${data.plot_raw}\n\n請以 JSON 格式輸出更新後的大綱。`;
                streamAPI(
                    '/api/agent/plot-planner',
                    { novel_id: state.currentNovelId, user_prompt: enhancePrompt },
                    () => {},
                    (delta) => {
                        if (el.editorPlotJson) {
                            el.editorPlotJson.value += delta;
                            el.editorPlotJson.scrollTop = el.editorPlotJson.scrollHeight;
                        }
                    },
                    (msg) => showToast(`Error: ${msg}`),
                    async () => {
                        showToast("大綱加強完成");
                        await loadNovelDetails(state.currentNovelId);
                        resolve();
                    }
                );
                break;
                
            default:
                resolve();
        }
    });
}

function runFullPipeline(userPrompt) {
    if (!state.currentNovelId) return;
    
    // 保存用戶輸入的 prompt 到後端（非阻塞）
    savePipelinePrompt(userPrompt).catch(() => {});
    
    // 設定分階段模式
    state.isPipelineRunning = true;
    state.currentPipelineStageIndex = 0;
    
    // 添加工作中的發光效果到各分頁標題
    const worldviewTab = document.querySelector('[data-tab="worldview"]');
    const charactersTab = document.querySelector('[data-tab="characters"]');
    const plotTab = document.querySelector('[data-tab="plot"]');
    const writerTab = document.querySelector('[data-tab="writer"]');
    
    function addGlowEffect(tab, isWorking) {
        if (tab) {
            if (isWorking) {
                tab.style.boxShadow = '0 0 20px var(--primary-glow), 0 0 40px var(--primary-glow)';
                tab.style.borderColor = 'var(--primary)';
                tab.style.background = 'rgba(0, 113, 227, 0.08)';
            } else {
                tab.style.boxShadow = '';
                tab.style.borderColor = '';
                tab.style.background = '';
            }
        }
    }
    
    function addSuccessGlow(tab) {
        if (tab) {
            tab.style.boxShadow = '0 0 20px rgba(52, 199, 89, 0.3), 0 0 40px rgba(52, 199, 89, 0.2)';
            tab.style.borderColor = 'var(--status-written)';
            tab.style.background = 'rgba(52, 199, 89, 0.08)';
        }
    }
    
    function clearAllGlows() {
        [worldviewTab, charactersTab, plotTab, writerTab].forEach(tab => {
            if (tab) {
                tab.style.boxShadow = '';
                tab.style.borderColor = '';
                tab.style.background = '';
            }
        });
    }
    
    // 初始化 Director 評估模式：讓 Director 判斷每個階段該加強、重新生成還是跳過
    
    // 首先詢問 Director 對整體進度的評估
    showToast("🎬 AI 總監正在評估當前進度...");
    
    runDirectorDecision('init').then(async (directorInit) => {
        // Director 初始化評估完成，開始執行流程
        // 根據 Director 的判斷來決定世界觀階段
        
        if (directorInit.action === 'AUTO_REGENERATE' || directorInit.regenerate) {
            // Director 指示需要重新生成或擴充
            showToast(`⚡ 總監指示：${directorInit.hint || '需要重新擴充世界觀'}`);
            state.activeTab = 'worldview';
            renderActiveTab();
            if (el.editorWorldview) el.editorWorldview.value = state.currentNovelData.worldbuilding || '';
            
            // 構建擴充 prompt
            const enhancePrompt = directorInit.hint || `請擴充並深化以下世界觀設定，確保包含：
1. 力量體系詳解（命燈、燃壽修行、等級）
2. 世界運行規則（永夜封印、妖魔、社會結構）
3. 核心衝突錨點（打破封印的收益與風險）
4. 燈火城邦與荒原的文化差異
5. 守夜人組織的內部權力結構
6. 永夜起源與古神的具體設定

現有世界觀：\n${state.currentNovelData.worldbuilding || ''}`;
            
            streamAPI(
                '/api/agent/story-architect',
                { novel_id: state.currentNovelId, user_prompt: enhancePrompt },
                () => {},
                (delta) => {
                    if (el.editorWorldview) {
                        el.editorWorldview.value = delta;
                        el.editorWorldview.scrollTop = el.editorWorldview.scrollHeight;
                    }
                },
                (msg) => showToast(`Error: ${msg}`),
                async () => {
                    addSuccessGlow(worldviewTab);
                    await loadNovelDetails(state.currentNovelId);
                    // 繼續角色階段
                    startStage2_Characters();
                }
            );
        } else if (directorInit.action === 'CONTINUE' || directorInit.continue) {
            // Director 指示可以繼續
            if (checkStageHasContent('worldview')) {
                // 有內容，Director 指示繼續，跳到角色階段
                showToast("✅ 總監評估：世界觀無需修改，直接進入角色設計");
                startStage2_Characters();
            } else {
                // 無內容，開始世界觀生成
                state.activeTab = 'worldview';
                renderActiveTab();
                if (el.editorWorldview) el.editorWorldview.value = '';
                startStage1_Worldview();
            }
        } else {
            // Director 要求等待用戶確認
            showToast("⏸️ 總監要求確認，請查看右側聊天區的總監評估");
            state.isPipelineRunning = false;
            return;
        }
    });
    
    // 處理角色階段（由 Director 決策驅動）
    function handleCharactersStage() {
        // 詢問 Director 對角色階段的判斷
        showToast("🎬 AI 總監正在評估角色設計...");
        
        runDirectorDecision('characters').then(async (directorChars) => {
            if (directorChars.action === 'AUTO_REGENERATE' || directorChars.regenerate) {
                // 需要重新生成角色
                showToast(`⚡ 總監指示：${directorChars.hint || '需要重新設計角色'}`);
                startStage2_Characters();
            } else if (directorChars.action === 'CONTINUE' || directorChars.continue) {
                // 可以繼續
                if (checkStageHasContent('characters')) {
                    showToast("✅ 總監評估：角色設定無需修改，直接進入大綱規劃");
                    startStage3_Plot();
                } else {
                    startStage2_Characters();
                }
            } else {
                showToast("⏸️ 總監要求確認，請查看右側聊天區的總監評估");
                state.isPipelineRunning = false;
            }
        });
    }
    
    // STAGE 1: 世界觀生成
    function startStage1_Worldview() {
        showToast("正在啟動世界觀架構師 Agent...");
        
        streamAPI(
            '/api/agent/story-architect',
            { novel_id: state.currentNovelId, user_prompt: userPrompt },
            () => {},
            (delta) => {
                if (el.editorWorldview) {
                    el.editorWorldview.value += delta;
                    el.editorWorldview.scrollTop = el.editorWorldview.scrollHeight;
                }
            },
            (msg) => {
                showToast(`Story Architect Error: ${msg}`);
            },
            async () => {
                addSuccessGlow(worldviewTab);
                
                // 詢問總監是否繼續
                showToast("世界觀完成，正在請求 AI 總監評估...");
                const director1 = await runDirectorDecision('worldview');
                
                // 處理導演的執行指令
                if (director1.action === 'WAIT_USER' || director1.shouldPause) {
                    addSuccessGlow(worldviewTab);
                    showToast("⏸️ 總監要求用戶確認，請查看反饋後再繼續");
                    state.isPipelineRunning = false;
                    return;
                }
                
                if (director1.action === 'AUTO_REGENERATE' || director1.regenerate) {
                    // 導演指示重跑/擴充當前階段
                    showToast("⚡ 導演指示重跑世界觀，正在執行擴充...");
                    addGlowEffect(worldviewTab, true);
                    // 根據導演的提示（HINT）構建擴充 prompt
                    const regeneratePrompt = director1.hint || `請擴充並深化以下世界觀設定，確保包含：
1. 力量體系詳解（命燈、燃壽修行、等級）
2. 世界運行規則（永夜封印、妖魔、社會結構）
3. 核心衝突錨點（打破封印的收益與風險）

現有世界觀：\n${state.currentNovelData.worldbuilding}`;
                    
                    streamAPI(
                        '/api/agent/story-architect',
                        { novel_id: state.currentNovelId, user_prompt: regeneratePrompt },
                        () => {},
                        (delta) => {
                            if (el.editorWorldview) {
                                el.editorWorldview.value = delta;
                                el.editorWorldview.scrollTop = el.editorWorldview.scrollHeight;
                            }
                        },
                        (msg) => showToast(`Error: ${msg}`),
                        async () => {
                            showToast("世界觀擴充完成，正在重新評估...");
                            // 重新保存並繼續
                            await loadNovelDetails(state.currentNovelId);
                            // 繼續角色階段
                            startStage2_Characters();
                        }
                    );
                    return;
                }
                
                if (!director1.continue) {
                    addSuccessGlow(worldviewTab);
                    showToast("⏸️ 總監建議暫停，請查看反饋後再繼續");
                    state.isPipelineRunning = false;
                    return;
                }
                
                // 繼續角色階段
                startStage2_Characters();
            }
        );
    }
    
    // STAGE 2: 角色設計
    function startStage2_Characters(regenerateStage = null, hint = null) {
        addGlowEffect(charactersTab, true);
        state.activeTab = 'characters';
        renderActiveTab();
        
        // 如果是回頭重新設計，先加載現有內容
        if (regenerateStage === 'characters' && state.currentNovelData.characters_raw) {
            if (el.editorCharactersJson) el.editorCharactersJson.value = state.currentNovelData.characters_raw;
        } else if (el.editorCharactersJson) {
            el.editorCharactersJson.value = '';
        }
        
        showToast("總監批准！正在啟動角色設計大師 Agent...");
        
        // 構建 prompt，如果是回頭修改，需要包含現有角色和修改指示
        let characterPrompt = userPrompt;
        if (regenerateStage === 'characters' && hint) {
            characterPrompt = `請根據以下指示重新設計角色：\n\n${hint}\n\n---\n\n現有角色設定：\n${state.currentNovelData.characters_raw || '尚無角色'}\n\n請嚴格以 JSON 格式輸出更新後的角色設定。`;
        }
        
        streamAPI(
            '/api/agent/character-designer',
            { novel_id: state.currentNovelId, user_prompt: characterPrompt },
            () => {},
            (delta) => {
                if (el.editorCharactersJson) {
                    el.editorCharactersJson.value += delta;
                    el.editorCharactersJson.scrollTop = el.editorCharactersJson.scrollHeight;
                }
            },
            (msg) => {
                showToast(`Character Designer Error: ${msg}`);
            },
            async () => {
                addSuccessGlow(charactersTab);
                
                // 重新載入以確保資料同步
                await loadNovelDetails(state.currentNovelId);
                
                // 如果是從後續階段回頭修改，需要重新評估角色
                if (regenerateStage === 'characters') {
                    showToast("角色已重新設計，正在重新評估...");
                    // 繼續流程，詢問總監對大綱的影響
                    await reevaluateAfterRegression('characters');
                } else {
                    // 正常流程：詢問總監是否繼續
                    showToast("角色完成，正在請求 AI 總監評估...");
                    const director2 = await runDirectorDecision('characters');
                    
                    if (director2.action === 'GO_BACK_TO_WORLDVIEW') {
                        // 總監指示回到世界觀重新設計
                        showToast("⚡ 總監指示：需要回頭修改世界觀設定");
                        await handleGoBack('worldview');
                        return;
                    }
                    
                    if (director2.action === 'GO_BACK_TO_CHARACTERS') {
                        // 總監指示重新設計角色
                        showToast("⚡ 總監指示：需要重新設計角色");
                        startStage2_Characters('characters', director2.hint);
                        return;
                    }
                    
                    if (!director2.continue) {
                        addSuccessGlow(charactersTab);
                        showToast("⏸️ 總監建議暫停，請查看反饋後再繼續");
                        state.isPipelineRunning = false;
                        return;
                    }
                    
                    // 繼續大綱階段
                    startStage3_Plot();
                }
            }
        );
    }
    
    // STAGE 3: 章節大綱
    function startStage3_Plot() {
        addGlowEffect(plotTab, true);
        state.activeTab = 'plot';
        renderActiveTab();
        if (el.editorPlotJson) el.editorPlotJson.value = '';
        showToast("總監批准！正在啟動大綱規劃師 Agent...");
        
        streamAPI(
            '/api/agent/plot-planner',
            { novel_id: state.currentNovelId, user_prompt: userPrompt },
            () => {},
            (delta) => {
                if (el.editorPlotJson) {
                    el.editorPlotJson.value += delta;
                    el.editorPlotJson.scrollTop = el.editorPlotJson.scrollHeight;
                }
            },
            (msg) => {
                showToast(`Plot Planner Error: ${msg}`);
            },
            async () => {
                addSuccessGlow(plotTab);
                
                // 詢問總監是否繼續
                showToast("大綱完成，正在請求 AI 總監評估...");
                const director3 = await runDirectorDecision('plot');
                
                if (!director3.continue) {
                    addSuccessGlow(plotTab);
                    showToast("⏸️ 總監建議暫停，請查看反饋後再繼續");
                    state.isPipelineRunning = false;
                    return;
                }
                
                // 繼續寫作階段
                startStage4_Writer();
            }
        );
    }
    
    // STAGE 4: 正文寫作
    function startStage4_Writer() {
        addGlowEffect(writerTab, true);
        state.activeTab = 'writer';
        renderActiveTab();
        showToast("總監批准！正在啟動小說作家 Agent 撰寫第一章...");
        
        state.activeChapterIndex = 1;
        if (el.editorProse) el.editorProse.value = '';
        
        streamAPI(
            '/api/agent/write-chapter',
            { novel_id: state.currentNovelId, chapter_index: 1 },
            () => {},
            (delta) => {
                if (el.editorProse) {
                    el.editorProse.value += delta;
                    el.editorProse.scrollTop = el.editorProse.scrollHeight;
                }
            },
            (msg) => {
                showToast(`Chapter Writer Error: ${msg}`);
            },
            async () => {
                addSuccessGlow(writerTab);
                
                // 詢問總監是否繼續
                showToast("第一章完成，正在請求 AI 總監評估...");
                const director4 = await runDirectorDecision('writer');
                
                // 最終完成
                showToast("🎉 聯動工作流執行完畢！");
                state.isPipelineRunning = false;
                
                // 移除所有發光效果
                setTimeout(clearAllGlows, 3000);
                
                // Reload novel details and select first chapter
                await loadNovelDetails(state.currentNovelId);
                selectWriterChapter(1);
            }
        );
    }
}

async function savePipelinePrompt(prompt) {
    if (!state.currentNovelId) return;
    try {
        await requestAPI(`/api/novels/${state.currentNovelId}/pipeline-prompt`, 'POST', { pipeline_prompt: prompt });
    } catch (e) {
        console.warn("Failed to save pipeline prompt");
    }
}

async function handleDrawerPromptSubmit() {
    let userPrompt = el.promptDrawerTextarea.value.trim();
    if (!userPrompt) {
        const placeholderVal = el.promptDrawerTextarea.placeholder || '';
        if (placeholderVal) {
            userPrompt = placeholderVal.replace(/^例如[：:\s]*/, '');
        }
    }
    el.drawerPrompt.classList.remove('active');
    
    if (state.activeDrawerAction === 'pipeline_orchestration') {
        // 保存用戶的創作需求到 pipeline prompt
        state.pipelinePrompt = userPrompt;
        await savePipelinePrompt(userPrompt);
        // 保持目前執行模式，不要在啟動管道時強制切換
        const toggle = document.getElementById('toggle-auto-execute');
        if (toggle) {
            state.isAutoExecuteMode = toggle.checked;
        }
        runPipeline(userPrompt);
    }
    
    if (state.activeDrawerAction === 'architect') {
        startAgentStream(
            '/api/agent/story-architect',
            { novel_id: state.currentNovelId, user_prompt: userPrompt },
            el.editorWorldview,
            async () => {
                showToast("世界觀結構起草完畢");
                await loadNovelDetails(state.currentNovelId);
            }
        );
    }
    
    if (state.activeDrawerAction === 'character') {
        // Stream back to JSON textarea
        startAgentStream(
            '/api/agent/character-designer',
            { novel_id: state.currentNovelId, user_prompt: userPrompt },
            el.editorCharactersJson,
            async () => {
                showToast("角色 Bible 生成完畢");
                await loadNovelDetails(state.currentNovelId);
            }
        );
    }
    
    if (state.activeDrawerAction === 'plot') {
        startAgentStream(
            '/api/agent/plot-planner',
            { novel_id: state.currentNovelId, user_prompt: userPrompt },
            el.editorPlotJson,
            async () => {
                showToast("章節大綱拆分完畢");
                await loadNovelDetails(state.currentNovelId);
            }
        );
    }
    
    if (state.activeDrawerAction === 'editor') {
        startAgentStream(
            '/api/agent/edit-chapter',
            { novel_id: state.currentNovelId, chapter_index: state.activeChapterIndex, edit_instructions: userPrompt },
            el.editorProse,
            async () => {
                showToast("本章正文精細編輯完畢");
                await loadNovelDetails(state.currentNovelId);
                
                // 呼叫總監評估
                showToast(`第 ${state.activeChapterIndex} 章優化完成，正在請求 AI 總監評估...`);
                await runDirectorDecision('writer');
            },
            { tabName: 'writer', agentName: 'Editor Agent' }
        );
    }
}

// ==========================================
// EVENT LISTENERS & SETUP
// ==========================================
function setupEventListeners() {
    // 1. Tab switches
    el.navTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            state.activeTab = tab.dataset.tab;
            renderActiveTab();
        });
    });
    
    // 2. Open Create Novel Modal
    el.btnNewNovel.addEventListener('click', () => {
        el.inputNovelTitle.value = '';
        el.inputNovelGenre.value = '仙俠';
        el.inputNovelStyle.value = '史詩宏大、文筆流暢';
        el.modalCreateNovel.classList.add('active');
    });
    
    // Create Novel Submit
    el.btnSubmitCreateNovel.addEventListener('click', async () => {
        const title = el.inputNovelTitle.value.trim();
        const genre = el.inputNovelGenre.value.trim();
        const styleText = el.inputNovelStyle.value.trim();
        
        if (!title) {
            await showCustomAlert("請輸入書名！");
            return;
        }
        
        el.modalCreateNovel.classList.remove('active');
        const res = await requestAPI('/api/novels', 'POST', { title, genre, style: styleText });
        showToast("小說專案建立成功");
        
        await loadNovels();
        await loadNovelDetails(res.novel_id);
    });
    
    // 3. Open Settings Modal
    el.btnSettings.addEventListener('click', () => {
        loadSettings();
        el.modalSettings.classList.add('active');
    });
    
    // Close modals - Highly robust button click closing
    document.querySelectorAll('.btn-close-modal').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const overlay = btn.closest('.modal-overlay');
            if (overlay) overlay.classList.remove('active');
        });
    });

    // Close modals on clicking backdrop background overlay itself
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                overlay.classList.remove('active');
            }
        });
    });
    
    // Settings Tab Switcher
    el.settingsTabBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            el.settingsTabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            state.activeSettingAgent = btn.dataset.agent;
            loadAgentConfigFields(state.activeSettingAgent);
        });
    });
    
    // Save Settings
    el.btnSaveAgentSettings.addEventListener('click', saveCurrentAgentSettings);
    
    // Quick apply Nvidia Presets
    if (el.settingPresetModel) {
        el.settingPresetModel.addEventListener('change', () => {
            const presetVal = el.settingPresetModel.value;
            if (!presetVal) return;
            
            const presets = {
                "nvidia/nemotron-3-super-120b-a12b": {
                    model: "nvidia/nemotron-3-super-120b-a12b",
                    temperature: 1.0,
                    top_p: 0.95,
                    max_tokens: 16384,
                    enable_thinking: true
                },
                "openai/gpt-oss-120b": {
                    model: "openai/gpt-oss-120b",
                    temperature: 1.0,
                    top_p: 1.0,
                    max_tokens: 4096,
                    enable_thinking: false
                },
                "minimaxai/minimax-m2.7": {
                    model: "minimaxai/minimax-m2.7",
                    temperature: 1.0,
                    top_p: 0.95,
                    max_tokens: 8192,
                    enable_thinking: false
                },
                "mistralai/mistral-small-4-119b-2603": {
                    model: "mistralai/mistral-small-4-119b-2603",
                    temperature: 0.10,
                    top_p: 1.00,
                    max_tokens: 16384,
                    enable_thinking: false
                },
                "stepfun-ai/step-3.5-flash": {
                    model: "stepfun-ai/step-3.5-flash",
                    temperature: 1.0,
                    top_p: 0.9,
                    max_tokens: 16384,
                    enable_thinking: false
                }
            };
            
            const preset = presets[presetVal];
            if (preset) {
                el.settingModel.value = preset.model;
                el.settingMaxTokens.value = preset.max_tokens;
                el.settingTemperature.value = preset.temperature;
                el.settingTopP.value = preset.top_p;
                el.settingEnableThinking.checked = preset.enable_thinking;
                
                // If Base URL is empty or matches qwen placeholder/blank, set default Nvidia integration base
                if (!el.settingBaseUrl.value || el.settingBaseUrl.value.trim() === '' || el.settingBaseUrl.value.includes('qwen')) {
                    el.settingBaseUrl.value = 'https://integrate.api.nvidia.com/v1';
                }
                
                showToast(`已套用 ${preset.model} 預設值，點擊儲存以套用！`);
            }
        });
    }
    
    // 4. Save Text Editors Handlers
    el.btnWorldviewSave.addEventListener('click', saveWorldviewDirect);
    el.editorWorldview.addEventListener('blur', saveWorldviewDirect);
    
    el.btnCharactersSave.addEventListener('click', saveCharactersDirect);
    el.editorCharactersJson.addEventListener('blur', saveCharactersDirect);
    
    el.btnPlotSave.addEventListener('click', savePlotOutlineDirect);
    el.editorPlotJson.addEventListener('blur', savePlotOutlineDirect);
    
    el.btnProseSave.addEventListener('click', saveProseDirect);
    el.editorProse.addEventListener('blur', saveProseDirect);
    
    // 5. Add Manual placeholders - WORK DIRECTLY WITH STATE, NOT TEXTAREA
    el.btnCharacterAdd.addEventListener('click', () => {
        let charData = state.currentNovelData?.characters || { characters: [] };
        if (!charData.characters) charData.characters = [];
        
        const newChar = {
            name: "新登場角色",
            role: "配角",
            personality: ["勇敢", "冷酷"],
            flaws: ["傲慢"],
            motivation: "尋找真相",
            arc: "逐漸理解愛與奉獻"
        };
        
        charData.characters.push(newChar);
        state.currentNovelData.characters = charData;
        state.currentNovelData.characters_raw = JSON.stringify(charData, null, 2);
        
        // Save directly to API
        requestAPI(`/api/novels/${state.currentNovelId}/characters`, 'POST', { json_data: charData })
            .then(() => {
                showToast('新角色已新增');
                renderCharactersTab();
                // Open edit modal for the new character
                openCharacterEditModal(charData.characters.length - 1, newChar);
            })
            .catch(() => showToast('新增角色失敗'));
    });
    
    el.btnPlotAddChapter.addEventListener('click', () => {
        let plotData = state.currentNovelData?.plot || { chapters: [] };
        if (!plotData.chapters) plotData.chapters = [];
        
        const nextIdx = plotData.chapters.length + 1;
        const newChapter = {
            chapter_index: nextIdx,
            title: `第 ${nextIdx} 章故事`,
            events: ["發生了事件一", "發生了重要轉折"],
            purpose: "推動故事主線",
            foreshadowing: ["埋下一個線索"],
            emotional_tone: "緊張"
        };
        
        plotData.chapters.push(newChapter);
        state.currentNovelData.plot = plotData;
        state.currentNovelData.plot_raw = JSON.stringify(plotData, null, 2);
        
        // Save directly to API
        requestAPI(`/api/novels/${state.currentNovelId}/plot`, 'POST', { outline_json: plotData })
            .then(() => {
                showToast('新章節已新增');
                renderPlotTab();
            })
            .catch(() => showToast('新增章節失敗'));
    });
    
    // 6. AGENTS PIPELINE TRIGGERS
    const btnPipelineExecute = document.getElementById('btn-pipeline-execute');
    if (btnPipelineExecute) {
        btnPipelineExecute.addEventListener('click', () => {
            if (!state.currentNovelId) return showToast("請先選擇或建立一部小說");
            state.activeDrawerAction = 'pipeline_orchestration';
            el.promptDrawerTitle.textContent = "🧠 一鍵啟動 Multi-Agent 聯動工作流";
            el.promptDrawerDesc.textContent = "AI 聯動大腦將會啟動【世界觀規劃師 ➡️ 角色設計大師 ➡️ 劇情規劃大師 ➡️ 小說作家】四階流水線，全自動生成整本小說的完整企劃案！請輸入您的小說主線大綱靈感：";
            
            // 讀取上次輸入的 prompt（如果有）
            const savedPrompt = state.currentNovelData?.novel?.pipeline_prompt || '';
            el.promptDrawerTextarea.value = savedPrompt;
            el.promptDrawerTextarea.placeholder = "例如：仙俠題材。主角是一個身懷魔門功法的正道弟子，講述他如何游走黑白兩道，修得太上斬仙之路。基調宏大，充滿宿命感。";
            
            el.drawerPrompt.classList.add('active');
        });
    }

    el.btnArchitectGenerate.addEventListener('click', () => {
        if (!state.currentNovelId) return showToast("請先選擇或建立一部小說");
        state.activeDrawerAction = 'architect';
        el.promptDrawerTitle.textContent = "🤖 1️⃣ Story Architect 世界觀規劃";
        el.promptDrawerDesc.textContent = "為這部小說構建一個引人入勝的世界觀。請輸入您的小說主線大綱構想或基本靈感條件：";
        el.promptDrawerTextarea.value = "";
        el.promptDrawerTextarea.placeholder = "例如：仙俠題材。主角是一個身懷魔門功法的正道弟子，講述他如何游走黑白兩道，修得太上斬仙之路。基調宏大，充滿宿命感。";
        el.drawerPrompt.classList.add('active');
    });
    
    el.btnCharacterGenerate.addEventListener('click', () => {
        if (!state.currentNovelId) return showToast("請先選擇或建立一部小說");
        state.activeDrawerAction = 'character';
        el.promptDrawerTitle.textContent = "🤖 2️⃣ Character Designer 角色設計";
        el.promptDrawerDesc.textContent = "根據目前已建立的世界觀，讓 AI 精細化設計所有核心要角。請輸入對角色的特定要求（可留空）：";
        el.promptDrawerTextarea.value = "";
        el.promptDrawerTextarea.placeholder = "例如：需要一個性格極度腹黑的反派，看似是主角的師尊，但實際上有驚天密謀；還要設計一位背負家族血債的劍仙女主角。";
        el.drawerPrompt.classList.add('active');
    });
    
    el.btnPlotGenerate.addEventListener('click', () => {
        if (!state.currentNovelId) return showToast("請先選擇或建立一部小說");
        state.activeDrawerAction = 'plot';
        el.promptDrawerTitle.textContent = "🤖 3️⃣ Plot Planner 章節拆分大綱";
        el.promptDrawerDesc.textContent = "AI 將自動依據世界觀與人物 Bible 拆分出整部小說的細節章節大綱。請輸入章節數量或核心情節走向指示：";
        el.promptDrawerTextarea.value = "";
        el.promptDrawerTextarea.placeholder = "例如：規劃 10 個章節的大綱。故事前期要有正魔衝突爆發，中期是師尊反水，後期主角完成突破並封印神魔。每一章節情節密度要高。";
        el.drawerPrompt.classList.add('active');
    });
    
    el.btnWriteChapter.addEventListener('click', () => {
        if (!state.currentNovelId || !state.activeChapterIndex) return;
        
        state.currentlyWritingChapterIndex = state.activeChapterIndex;
        state.writingBuffer = "";
        
        const virtualTarget = {
            get value() { return state.writingBuffer; },
            set value(val) {
                state.writingBuffer = val;
                if (state.activeChapterIndex === state.currentlyWritingChapterIndex) {
                    el.editorProse.value = val;
                    el.editorProse.scrollTop = el.editorProse.scrollHeight;
                }
            },
            get scrollTop() { return el.editorProse.scrollTop; },
            set scrollTop(val) {
                if (state.activeChapterIndex === state.currentlyWritingChapterIndex) {
                    el.editorProse.scrollTop = val;
                }
            },
            get scrollHeight() { return el.editorProse.scrollHeight; }
        };

        startAgentStream(
            '/api/agent/write-chapter',
            { novel_id: state.currentNovelId, chapter_index: state.activeChapterIndex },
            virtualTarget,
            async () => {
                showToast(`第 ${state.currentlyWritingChapterIndex} 章正文撰寫完畢`);
                if (state.writingBuffer.trim().length > 0) {
                    await saveProseDirect();
                }
                
                state.currentlyWritingChapterIndex = null;
                state.writingBuffer = "";
                
                await loadNovelDetails(state.currentNovelId);
                
                // 呼叫總監評估
                showToast(`第 ${state.activeChapterIndex} 章已完成，正在請求 AI 總監評估...`);
                await runDirectorDecision('writer');
            },
            { tabName: 'writer', agentName: 'Chapter Writer' }
        );
    });
    
    el.btnEditChapter.addEventListener('click', () => {
        if (!state.currentNovelId || !state.activeChapterIndex) return;
        state.activeDrawerAction = 'editor';
        el.promptDrawerTitle.textContent = "🤖 5️⃣ Editor Agent 精修優化";
        el.promptDrawerDesc.textContent = "請輸入您對此章節文字的精細修改方針（例如：增加懸疑細節、潤色對話、加快打鬥節奏，留空則由編輯自主優化）：";
        el.promptDrawerTextarea.value = "";
        el.promptDrawerTextarea.placeholder = "例如：讓主角與師尊的對話更加綿裡藏針、話中有話，加強環境描寫的寂靜肃殺氛圍。";
        el.drawerPrompt.classList.add('active');
    });
    
    el.btnPromptDrawerSubmit.addEventListener('click', handleDrawerPromptSubmit);
    
    // 7. CO-PILOT CHAT DIRECT INPUT
    const sendChatMessage = () => {
        const text = el.chatInput.value.trim();
        if (!text || !state.currentNovelId) return;
        
        el.chatInput.value = '';
        
        // Render user message bubble locally
        const userMsg = document.createElement('div');
        userMsg.className = 'message user-msg';
        const userTimestamp = formatTimestamp();
        userMsg.innerHTML = `<div class="msg-sender-row"><div class="msg-sender">You</div><div class="msg-timestamp">${userTimestamp}</div></div><div class="msg-content">${text}</div>`;
        el.chatMessagesContainer.appendChild(userMsg);
        el.chatMessagesContainer.scrollTop = el.chatMessagesContainer.scrollHeight;
        
        // Create assistant message stream bubble placeholder
        const assistantMsg = document.createElement('div');
        assistantMsg.className = 'message assistant-msg';
        const assistantTimestamp = formatTimestamp();
        assistantMsg.innerHTML = `<div class="msg-sender-row"><div class="msg-sender">Novel Director</div><div class="msg-timestamp">${assistantTimestamp}</div></div><div class="msg-content stream-typing"></div>`;
        el.chatMessagesContainer.appendChild(assistantMsg);
        el.chatMessagesContainer.scrollTop = el.chatMessagesContainer.scrollHeight;
        
        const streamTarget = assistantMsg.querySelector('.stream-typing');
        
        // Start streaming copilot response
        streamAPI(
            '/api/agent/copilot-chat',
            { novel_id: state.currentNovelId, user_message: text },
            // onThinking
            () => {}, // don't show reasoning details in chat bubble to keep it clean
            // onContent
            (delta) => {
                streamTarget.textContent += delta;
                el.chatMessagesContainer.scrollTop = el.chatMessagesContainer.scrollHeight;
            },
            // onError
            (err) => {
                streamTarget.textContent += `\n[Director connection lost: ${err}]`;
            },
            // onDone
            async () => {
                // Refresh memory to keep SQLite state in sync
                await loadNovelDetails(state.currentNovelId);
            }
        );
    };
    
    el.btnChatSend.addEventListener('click', sendChatMessage);
    el.chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChatMessage();
        }
    });
    
    el.btnClearChat.addEventListener('click', async () => {
        if (!state.currentNovelId) return;
        if (await showCustomConfirm("清空與小說總監的對話記憶？(SQLite memory)")) {
            await requestAPI(`/api/novels/${state.currentNovelId}/clear-chat`, 'POST');
            await loadNovelDetails(state.currentNovelId);
        }
    });
    
    // 8. EXPORT DROPDOWN HANDLERS
    if (el.btnExportDropdown && el.exportDropdownMenu) {
        el.btnExportDropdown.addEventListener('click', (e) => {
            e.stopPropagation();
            el.exportDropdownMenu.classList.toggle('show');
        });
        
        // Hide dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (el.btnExportDropdown && el.exportDropdownMenu) {
                if (!el.btnExportDropdown.contains(e.target) && !el.exportDropdownMenu.contains(e.target)) {
                    el.exportDropdownMenu.classList.remove('show');
                }
            }
        });
        
        // Handle dropdown item click
        el.exportDropdownMenu.querySelectorAll('.dropdown-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.stopPropagation();
                el.exportDropdownMenu.classList.remove('show');
                
                if (!state.currentNovelId) return;
                
                const format = item.dataset.format;
                
                // Trigger direct file download
                const a = document.createElement('a');
                a.href = `/api/novels/${state.currentNovelId}/export?format=${format}`;
                a.download = '';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                
                showToast(`正在匯出為 ${format.toUpperCase()} 格式...`);
            });
        });
    }
    
    // 9. FORESHADOWING SEEDS HANDLERS
    const btnSeedAdd = document.getElementById('btn-seed-add');
    if (btnSeedAdd) {
        btnSeedAdd.addEventListener('click', async () => {
            const seedText = await showCustomPrompt('請輸入伏筆內容：');
            if (seedText) {
                addWorldviewSeed(seedText);
            }
        });
    }
    
    const btnSeedAiGenerate = document.getElementById('btn-seed-ai-generate');
    if (btnSeedAiGenerate) {
        btnSeedAiGenerate.addEventListener('click', () => {
            generateWorldviewSeedsWithAI();
        });
    }
}

/**
 * 初始化並確保聊天歷史正確顯示
 * 確保系統消息不被覆蓋，並顯示所有歷史記錄
 */
function initializeChatHistory() {
    const chatContainer = el.chatMessagesContainer;
    if (!chatContainer) return;
    
    // 檢查是否已有系統消息
    const existingSystemMsg = chatContainer.querySelector('.system-msg, .message.system');
    
    // 如果沒有系統消息，添加默認的系統歡迎消息
    if (!existingSystemMsg) {
        const systemWelcome = document.createElement('div');
        systemWelcome.className = 'message system-msg';
        systemWelcome.innerHTML = `
            <div class="msg-sender">AI Novel Director</div>
            <div class="msg-content">你好！我是你的小說創作協同總監。我擁有對當前小說的完整長期記憶 (SQLite)。<br><br>你可以對我發出指令，例如：<br>「幫我修改主角設定，讓他背景多一條伏筆」<br>「給我想 3 個世界觀的魔法限制」<br>「重寫第一章，讓氛圍更懸疑」<br><br>我會直接指導各個 Agent 配合，或是為你提供靈感！</div>
        `;
        chatContainer.appendChild(systemWelcome);
    }
}

// ==========================================
// INITIALIZATION
// ==========================================
window.addEventListener('DOMContentLoaded', async () => {
    // 0. 初始化聊天歷史顯示
    initializeChatHistory();
    
    // 1. Load initial novels
    await loadNovels();
    
    // Auto select first novel if available
    if (state.novels.length > 0) {
        await loadNovelDetails(state.novels[0].id);
    }
    
    // 2. Setup buttons and tabs handlers
    setupEventListeners();
    
    // 3. Setup execution mode toggle
    setupExecutionModeToggle();
    setupStreamLogToggle();
    
    // 4. 初始化伏筆 Modal 事件
    initSeedModalEvents();
});
/**
 * 當從後續階段回頭修改某個階段後，進行連鎖重新評估
 * @param {string} modifiedStage - 被修改的階段：worldview, characters, plot
 */
async function reevaluateAfterRegression(modifiedStage) {
    showToast(`🔄 正在重新評估修改後的「${modifiedStage}」對後續內容的影響...`);
    
    // 根據修改的階段，判斷需要重新檢查哪些後續階段
    if (modifiedStage === 'worldview') {
        // 世界觀修改後，需要重新檢查角色設定和大綱
        const directorReview = await runDirectorDecision('worldview_review');
        
        if (directorReview.action === 'GO_BACK_TO_CHARACTERS') {
            // 世界觀修改影響了角色，需要重新設計角色
            showToast("⚡ 世界觀變更影響角色設定，需要重新設計...");
            startStage2_Characters('characters', directorReview.hint);
        } else if (directorReview.continue) {
            // 角色設定不受影響，繼續大綱
            startStage3_Plot();
        } else {
            // 需要用戶確認
            showToast("⏸️ 請查看總監評估，確認是否需要其他調整");
        }
    } else if (modifiedStage === 'characters') {
        // 角色修改後，需要重新檢查大綱
        const directorReview = await runDirectorDecision('characters_review');
        
        if (directorReview.action === 'GO_BACK_TO_CHARACTERS') {
            showToast("⚡ 角色變更需要進一步調整...");
            startStage2_Characters('characters', directorReview.hint);
        } else if (directorReview.action === 'GO_BACK_TO_PLOT') {
            showToast("⚡ 角色變更影響大綱，需要重新規劃...");
            startStage3_Plot(true, directorReview.hint);
        } else if (directorReview.continue) {
            // 大綱不受影響，繼續寫作
            startStage4_Writer();
        } else {
            showToast("⏸️ 請查看總監評估");
        }
    } else if (modifiedStage === 'plot') {
        // 大綱修改後，需要重新檢查正文
        const directorReview = await runDirectorDecision('plot_review');
        
        if (directorReview.action === 'GO_BACK_TO_PLOT') {
            showToast("⚡ 大綱需要進一步調整...");
            startStage3_Plot(true, directorReview.hint);
        } else if (directorReview.action === 'GO_BACK_TO_WRITER') {
            showToast("⚡ 大綱變更需要重新撰寫部分章節...");
            startStage4_Writer(true);
        } else {
            showToast("✅ 評估完成，大綱變更無需重新撰寫");
            state.isPipelineRunning = false;
        }
    }
}

/**
 * 處理回頭修改的指令
 * @param {string} targetStage - 要回頭修改的階段
 */
async function handleGoBack(targetStage) {
    const stageLabels = {
        'worldview': '世界觀設定',
        'characters': '角色設計',
        'plot': '章節大綱',
        'writer': '正文寫作'
    };
    
    showToast(`⚡ 總監指示回頭修改「${stageLabels[targetStage]}」...`);
    
    // 切換到目標階段
    state.activeTab = targetStage;
    renderActiveTab();
    
    // 根據目標階段觸發相應的修改流程
    switch (targetStage) {
        case 'worldview':
            // 詢問總監需要修改什麼
            const worldviewDecision = await runDirectorDecision('worldview_go_back');
            if (worldviewDecision.hint) {
                // 根據總監提示修改世界觀
                streamAPI(
                    '/api/agent/story-architect',
                    { novel_id: state.currentNovelId, user_prompt: `請根據以下指示修改世界觀：\n\n${worldviewDecision.hint}\n\n現有世界觀：\n${state.currentNovelData.worldbuilding}` },
                    () => {},
                    (delta) => {
                        if (el.editorWorldview) {
                            el.editorWorldview.value = delta;
                            el.editorWorldview.scrollTop = el.editorWorldview.scrollHeight;
                        }
                    },
                    (msg) => showToast(`Error: ${msg}`),
                    async () => {
                        showToast("世界觀已修改，正在重新評估...");
                        await loadNovelDetails(state.currentNovelId);
                        // 修改完成後，重新評估角色和大綱
                        await reevaluateAfterRegression('worldview');
                    }
                );
            }
            break;
            
        case 'characters':
            const charactersDecision = await runDirectorDecision('characters_go_back');
            if (charactersDecision.hint) {
                startStage2_Characters('characters', charactersDecision.hint);
            }
            break;
            
        case 'plot':
            const plotDecision = await runDirectorDecision('plot_go_back');
            if (plotDecision.hint) {
                startStage3_Plot(true, plotDecision.hint);
            }
            break;
            
        case 'writer':
            showToast("請手動編輯章節正文，完成後系統將重新評估");
            state.isPipelineRunning = false;
            break;
    }
}

// 擴展 startStage3_Plot 以支持重新生成
function startStage3_Plot(regenerate = false, hint = null) {
    addGlowEffect(plotTab, true);
    state.activeTab = 'plot';
    renderActiveTab();
    
    if (regenerate && state.currentNovelData.plot_raw) {
        if (el.editorPlotJson) el.editorPlotJson.value = state.currentNovelData.plot_raw;
    } else if (el.editorPlotJson) {
        el.editorPlotJson.value = '';
    }
    
    showToast("總監批准！正在啟動大綱規劃師 Agent...");
    
    // 構建 prompt
    let plotPrompt = userPrompt;
    if (regenerate && hint) {
        plotPrompt = `請根據以下指示重新規劃大綱：\n\n${hint}\n\n---\n\n現有大綱：\n${state.currentNovelData.plot_raw || '尚無大綱'}\n\n請嚴格以 JSON 格式輸出更新後的大綱。`;
    }
    
    streamAPI(
        '/api/agent/plot-planner',
        { novel_id: state.currentNovelId, user_prompt: plotPrompt },
        () => {},
        (delta) => {
            if (el.editorPlotJson) {
                el.editorPlotJson.value += delta;
                el.editorPlotJson.scrollTop = el.editorPlotJson.scrollHeight;
            }
        },
        (msg) => {
            showToast(`Plot Planner Error: ${msg}`);
        },
        async () => {
            addSuccessGlow(plotTab);
            await loadNovelDetails(state.currentNovelId);
            
            // 如果是重新生成，需要重新評估
            if (regenerate) {
                showToast("大綱已重新規劃，正在重新評估...");
                await reevaluateAfterRegression('plot');
            } else {
                // 正常流程：詢問總監是否繼續
                showToast("大綱完成，正在請求 AI 總監評估...");
                const director3 = await runDirectorDecision('plot');
                
                if (director3.action === 'GO_BACK_TO_CHARACTERS') {
                    showToast("⚡ 大綱變更需要調整角色...");
                    await handleGoBack('characters');
                    return;
                }
                
                if (director3.action === 'GO_BACK_TO_PLOT') {
                    showToast("⚡ 大綱需要進一步調整...");
                    startStage3_Plot(true, director3.hint);
                    return;
                }
                
                if (!director3.continue) {
                    addSuccessGlow(plotTab);
                    showToast("⏸️ 總監建議暫停，請查看反饋後再繼續");
                    state.isPipelineRunning = false;
                    return;
                }
                
                // 繼續寫作階段
                startStage4_Writer();
            }
        }
    );
}

// 擴展 startStage4_Writer 以支持重新生成
function startStage4_Writer(regenerate = false) {
    addGlowEffect(writerTab, true);
    state.activeTab = 'writer';
    renderActiveTab();
    
    if (!regenerate) {
        state.activeChapterIndex = 1;
    }
    
    if (el.editorProse) el.editorProse.value = '';
    showToast("總監批准！正在啟動小說作家 Agent...");
    
    streamAPI(
        '/api/agent/write-chapter',
        { novel_id: state.currentNovelId, chapter_index: state.activeChapterIndex || 1 },
        () => {},
        (delta) => {
            if (el.editorProse) {
                el.editorProse.value += delta;
                el.editorProse.scrollTop = el.editorProse.scrollHeight;
            }
        },
        (msg) => {
            showToast(`Chapter Writer Error: ${msg}`);
        },
        async () => {
            addSuccessGlow(writerTab);
            
            if (regenerate) {
                showToast("章節已重新撰寫");
            } else {
                showToast("第一章完成，正在請求 AI 總監評估...");
                const director4 = await runDirectorDecision('writer');
                
                if (director4.action === 'GO_BACK_TO_PLOT') {
                    showToast("⚡ 正文需要調整大綱...");
                    await handleGoBack('plot');
                    return;
                }
                
                if (director4.action === 'GO_BACK_TO_CHARACTERS') {
                    showToast("⚡ 正文需要調整角色...");
                    await handleGoBack('characters');
                    return;
                }
            }
            
            // 最終完成
            showToast("🎉 聯動工作流執行完畢！");
            state.isPipelineRunning = false;
            
            // 移除所有發光效果
            setTimeout(clearAllGlows, 3000);
            
            // Reload novel details and select first chapter
            await loadNovelDetails(state.currentNovelId);
            selectWriterChapter(state.activeChapterIndex || 1);
        }
    );
}


// ============================================================
// Phase 5 Custom Dialog Modals & AI Enhancements (Antigravity)
// ============================================================

let currentDialogPromise = null;

function closeCustomDialog() {
    const modal = document.getElementById('modal-custom-dialog');
    if (modal) {
        modal.classList.remove('active');
        modal.style.display = 'none';
    }
}

window.showCustomDialog = function({ title, message, type = 'alert', defaultValue = '', options = null }) {
    return new Promise((resolve) => {
        const modal = document.getElementById('modal-custom-dialog');
        const titleEl = document.getElementById('custom-dialog-title');
        const msgEl = document.getElementById('custom-dialog-message');
        const inputContainer = document.getElementById('custom-dialog-input-container');
        const textarea = document.getElementById('custom-dialog-textarea');
        const optionsContainer = document.getElementById('custom-dialog-options-container');
        const standardActions = document.getElementById('custom-dialog-standard-actions');
        const cancelBtn = document.getElementById('btn-custom-dialog-cancel');
        const confirmBtn = document.getElementById('btn-custom-dialog-confirm');

        if (!modal) {
            if (type === 'confirm') resolve(confirm(message));
            else if (type === 'prompt') resolve(prompt(message, defaultValue));
            else { alert(message); resolve(); }
            return;
        }

        // Reset display states
        titleEl.textContent = title || '提示';
        msgEl.textContent = message || '';
        inputContainer.style.display = 'none';
        optionsContainer.style.display = 'none';
        standardActions.style.display = 'flex';
        cancelBtn.style.display = 'block';
        confirmBtn.style.display = 'block';

        if (type === 'prompt') {
            inputContainer.style.display = 'block';
            textarea.value = defaultValue || '';
        } else if (type === 'options' && options) {
            optionsContainer.style.display = 'flex';
            standardActions.style.display = 'none';
            optionsContainer.innerHTML = '';
            options.forEach(opt => {
                const btn = document.createElement('button');
                btn.className = opt.className || 'btn btn-primary';
                btn.style.width = '100%';
                btn.style.textAlign = 'left';
                btn.style.padding = '12px 16px';
                btn.style.borderRadius = '8px';
                btn.style.border = '1px solid rgba(255,255,255,0.08)';
                btn.style.background = 'rgba(255,255,255,0.03)';
                btn.style.color = '#fff';
                btn.style.cursor = 'pointer';
                btn.style.transition = 'all 0.2s';
                btn.innerHTML = opt.text;
                
                btn.onmouseover = () => {
                    btn.style.background = 'rgba(255,255,255,0.08)';
                    btn.style.transform = 'translateY(-1px)';
                };
                btn.onmouseout = () => {
                    btn.style.background = 'rgba(255,255,255,0.03)';
                    btn.style.transform = 'none';
                };

                btn.onclick = () => {
                    closeCustomDialog();
                    resolve(opt.value);
                };
                optionsContainer.appendChild(btn);
            });
        } else if (type === 'alert') {
            cancelBtn.style.display = 'none';
        }

        // Bind Standard Buttons
        confirmBtn.onclick = () => {
            closeCustomDialog();
            if (type === 'prompt') {
                resolve(textarea.value);
            } else {
                resolve(true);
            }
        };

        cancelBtn.onclick = () => {
            closeCustomDialog();
            if (type === 'prompt') {
                resolve(null);
            } else {
                resolve(false);
            }
        };

        // Show modal
        modal.classList.add('active');
        modal.style.display = 'flex';
    });
};

window.showCustomAlert = function(msg, title = '系統提示') {
    return window.showCustomDialog({ title, message: msg, type: 'alert' });
};

window.showCustomConfirm = function(msg, title = '確認操作') {
    return window.showCustomDialog({ title, message: msg, type: 'confirm' });
};

window.showCustomPrompt = function(msg, defaultValue = '', title = '輸入內容') {
    return window.showCustomDialog({ title, message: msg, type: 'prompt', defaultValue });
};

window.updateAgentStreamOutput = function(tabName, delta) {
    const terminal = document.getElementById(`stream-output-${tabName}`);
    if (terminal) {
        terminal.textContent += delta;
        terminal.scrollTop = terminal.scrollHeight;
    }
};

window.enhanceWorldviewSectionWithAI = async function(field, title) {
    const hint = await window.showCustomPrompt(`請輸入 AI 規劃「${title}」的提示或方向（留空將以當前設定進行擴充）：`, '');
    if (hint === null) return; 
    
    showAgentProcessingIndicator('worldview', `Story Architect (AI 規劃: ${title})`);
    
    streamAPI(
        '/api/agent/incremental-architect',
        {
            novel_id: state.currentNovelId,
            target_section: field,
            user_hint: hint || `請為「${title}」生成或擴展深度設定，確保與目前小說的風格和背景完美相容。`
        },
        (delta) => {
            window.updateAgentStreamOutput('worldview', delta);
        },
        (delta) => {
            window.updateAgentStreamOutput('worldview', delta);
        },
        (err) => {
            showToast('AI 規劃失敗: ' + err);
            hideAgentProcessingIndicator('worldview');
        },
        async () => {
            hideAgentProcessingIndicator('worldview');
            showToast(`✨ ${title} AI 規劃與更新完成！`);
            await loadNovelDetails(state.currentNovelId);
        }
    );
};

// Overwrite dead askContentAction with visual glassmorphism version
window.askContentAction = async function(stageName, callback) {
    const options = [
        { text: "✨ AI 自動增強優化 (加強現有內容)", value: "enhance", className: "btn btn-primary" },
        { text: "🔄 重新生成此步驟", value: "regenerate", className: "btn btn-secondary" },
        { text: "⏩ 跳過並沿用當前設定", value: "skip", className: "btn btn-ghost" }
    ];
    
    const choice = await window.showCustomDialog({
        title: `【${stageName}】已有內容存在`,
        message: `請選擇操作：`,
        type: 'options',
        options: options
    });
    
    callback(choice || 'skip');
};

// Global exports of worldview and modal handlers to prevent ReferenceError in inline onclick handlers
window.openWorldviewTextSectionEditModal = openWorldviewTextSectionEditModal;
window.openWorldviewComplexListEditModal = openWorldviewComplexListEditModal;
window.openWorldviewListEditModal = openWorldviewListEditModal;
window.deleteWorldviewSection = deleteWorldviewSection;
window.addWorldviewSection = addWorldviewSection;
window.toggleSectionExpand = toggleSectionExpand;
window.closeSeedModal = closeSeedModal;
window.closeCustomDialog = closeCustomDialog;
window.editWorldviewSection = openWorldviewTextSectionEditModal; // legacy fallback

// Direct aliases for worldview complex rendering
window.editWorldviewComplexList = openWorldviewComplexListEditModal;
window.editWorldviewList = openWorldviewListEditModal;

// Character edit modal and delete handlers
window.openCharacterEditModal = openCharacterEditModal;
window.deleteCharacter = function(index) {
    window.showCustomDialog({
        title: '🗑️ 刪除角色設定',
        message: '您確定要刪除這個角色設定嗎？此操作不可逆！',
        type: 'confirm'
    }).then(confirmed => {
        if (confirmed) {
            const charData = state.currentNovelData?.characters;
            if (charData && charData.characters && charData.characters[index] !== undefined) {
                charData.characters.splice(index, 1);
                state.currentNovelData.characters = charData;
                const newRaw = JSON.stringify(charData, null, 2);
                state.currentNovelData.characters_raw = newRaw;
                if (el.editorCharactersJson) el.editorCharactersJson.value = newRaw;
                
                requestAPI(`/api/novels/${state.currentNovelId}/characters`, 'POST', { json_data: charData })
                    .then(() => {
                        showToast('角色已刪除');
                        renderCharactersTab();
                    })
                    .catch(() => {
                        showToast('刪除失敗');
                    });
            }
        }
    });
};

// Plot Chapter handlers
window.openChapterOutlineEditModal = openChapterOutlineEditModal;
window.openManualChapterInsertModal = openManualChapterInsertModal;
window.deletePlotChapter = function(index) {
    window.showCustomDialog({
        title: '🗑️ 刪除章節大綱',
        message: '您確定要刪除此章節大綱嗎？（已寫完的正文不會受影響，但大綱本身會永久刪除）',
        type: 'confirm'
    }).then(confirmed => {
        if (confirmed) {
            const plotData = state.currentNovelData?.plot;
            if (plotData && plotData.chapters && plotData.chapters[index] !== undefined) {
                plotData.chapters.splice(index, 1);
                
                // Re-index remaining chapters
                plotData.chapters.forEach((ch, i) => {
                    ch.chapter_index = i + 1;
                });
                
                state.currentNovelData.plot = plotData;
                const newRaw = JSON.stringify(plotData, null, 2);
                state.currentNovelData.plot_raw = newRaw;
                if (el.editorPlotJson) el.editorPlotJson.value = newRaw;
                
                savePlotOutlineDirect();
                showToast('章節大綱已刪除');
            }
        }
    });
};

// Export strategy card view toggle functions for inline onclick handlers
window.setStrategyCardView = setStrategyCardView;
window.jumpToStrategyCard = jumpToStrategyCard;
window.applySingleCardView = applySingleCardView;

// Expose pipeline & streaming helpers to window for pipeline.js
window.streamAPI = streamAPI;
window.renderActiveTab = renderActiveTab;
window.loadNovelDetails = loadNovelDetails;
window.runDirectorDecision = runDirectorDecision;
window.executeDirectorAction = executeDirectorAction;
window.selectWriterChapter = selectWriterChapter;
window.parseDirectorDecisionText = parseDirectorDecisionText;
window.resumePipelineWithDecision = resumePipelineWithDecision;
