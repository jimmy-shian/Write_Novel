const state = {
    novels: [],
    currentNovelId: null,
    currentNovelData: null,
    activeTab: 'worldview', // worldview, characters, plot, writer
    activeChapterIndex: null,
    settingsData: {},
    activeSettingAgent: 'global',
    
    // UI Drawer state
    activeDrawerAction: null, // pipeline_orchestration, architect, character, plot, writer, editor
    
    // Pipeline workflow state
    isPipelineRunning: false,
    
    // Director pipeline stage control
    pipelineStages: ['worldview', 'characters', 'plot', 'writer'],
    currentPipelineStageIndex: 0,
    
    // Director execution mode: 一鍵執行模式 vs 一般模式
    // 一鍵執行模式：總監的建議即為執行令（自動執行）
    // 一般模式：總監提供建議，由用戶決定
    isAutoExecuteMode: false
};

// ==========================================
// DOM ELEMENT CACHE
// ==========================================
const el = {
    // Left Sidebar
    novelsList: document.getElementById('novels-list'),
    btnNewNovel: document.getElementById('btn-new-novel'),
    btnSettings: document.getElementById('btn-settings'),
    
    // Workspace Header
    currentNovelTitle: document.getElementById('current-novel-title'),
    currentNovelGenre: document.getElementById('current-novel-genre'),
    novelHeaderActions: document.getElementById('novel-header-actions'),
    btnExportDropdown: document.getElementById('btn-export-dropdown'),
    exportDropdownMenu: document.getElementById('export-dropdown-menu'),
    navTabs: document.querySelectorAll('.nav-tab'),
    workpanels: document.querySelectorAll('.workpanel'),
    
    // Worldview Tab
    editorWorldview: document.getElementById('editor-worldview'),
    btnArchitectGenerate: document.getElementById('btn-architect-generate'),
    btnWorldviewSave: document.getElementById('btn-worldview-save'),
    agentProcessingWorldview: document.getElementById('agent-processing-worldview'),
    
    // Characters Tab
    editorCharactersJson: document.getElementById('editor-characters-json'),
    btnCharacterGenerate: document.getElementById('btn-character-generate'),
    btnCharacterAdd: document.getElementById('btn-character-add'),
    btnCharactersSave: document.getElementById('btn-characters-save'),
    charactersCardsGrid: document.getElementById('characters-cards-grid'),
    
    // Plot Outline Tab
    editorPlotJson: document.getElementById('editor-plot-json'),
    btnPlotGenerate: document.getElementById('btn-plot-generate'),
    btnPlotAddChapter: document.getElementById('btn-plot-add-chapter'),
    btnPlotSave: document.getElementById('btn-plot-save'),
    plotTimeline: document.getElementById('plot-timeline'),
    
    // Prose Writer Tab
    writerChaptersList: document.getElementById('writer-chapters-list'),
    activeChapterTitle: document.getElementById('active-chapter-title'),
    activeChapterStatus: document.getElementById('active-chapter-status'),
    chapterOutlineSummaryText: document.getElementById('chapter-outline-summary-text'),
    btnWriteChapter: document.getElementById('btn-write-chapter'),
    btnEditChapter: document.getElementById('btn-edit-chapter'),
    btnProseSave: document.getElementById('btn-prose-save'),
    editorProse: document.getElementById('editor-prose'),
    aiThinkingStream: document.getElementById('ai-thinking-stream'),
    aiThinkingText: document.getElementById('ai-thinking-text'),
    
    // Chat Sidebar (Right)
    chatMessagesContainer: document.getElementById('chat-messages-container'),
    chatInput: document.getElementById('chat-input'),
    btnChatSend: document.getElementById('btn-chat-send'),
    btnClearChat: document.getElementById('btn-clear-chat'),
    
    // Modals
    modalSettings: document.getElementById('modal-settings'),
    modalCreateNovel: document.getElementById('modal-create-novel'),
    drawerPrompt: document.getElementById('drawer-prompt'),
    
    // Modal controls
    btnSubmitCreateNovel: document.getElementById('btn-submit-create-novel'),
    inputNovelTitle: document.getElementById('input-novel-title'),
    inputNovelGenre: document.getElementById('input-novel-genre'),
    inputNovelStyle: document.getElementById('input-novel-style'),
    
    // Settings Tab Fields
    settingsTabBtns: document.querySelectorAll('.settings-tab-btn'),
    settingsAgentTitle: document.getElementById('settings-agent-title'),
    settingAgentName: document.getElementById('setting-agent-name'),
    settingApiKey: document.getElementById('setting-api-key'),
    settingBaseUrl: document.getElementById('setting-base-url'),
    settingPresetModel: document.getElementById('setting-preset-model'),
    settingModel: document.getElementById('setting-model'),
    settingMaxTokens: document.getElementById('setting-max-tokens'),
    settingTemperature: document.getElementById('setting-temperature'),
    settingTopP: document.getElementById('setting-top-p'),
    settingEnableThinking: document.getElementById('setting-enable-thinking'),
    btnSaveAgentSettings: document.getElementById('btn-save-agent-settings'),
    
    // Prompt Drawer fields
    promptDrawerTitle: document.getElementById('prompt-drawer-title'),
    promptDrawerDesc: document.getElementById('prompt-drawer-desc'),
    promptDrawerTextarea: document.getElementById('prompt-drawer-textarea'),
    btnPromptDrawerSubmit: document.getElementById('btn-prompt-drawer-submit'),
    
    // General
    toast: document.getElementById('toast')
};

// ==========================================
// TOAST NOTIFICATIONS
// ==========================================
function showToast(message) {
    el.toast.textContent = message;
    el.toast.classList.remove('hidden');
    setTimeout(() => {
        el.toast.classList.add('hidden');
    }, 2500);
}

// ==========================================
// AGENT PROCESSING INDICATOR
// ==========================================

/**
 * 顯示指定 Tab 的 Agent 處理中指示器
 * @param {string} tabName - Tab 名稱：worldview, characters, plot, writer
 * @param {string} agentName - Agent 名稱（如 "Story Architect"）
 */
function showAgentProcessingIndicator(tabName, agentName) {
    // 根據 tab 名稱找到對應的指示器
    let indicator = null;
    let navTab = null;
    
    if (tabName === 'worldview') {
        indicator = el.agentProcessingWorldview;
        navTab = document.querySelector('[data-tab="worldview"]');
    } else if (tabName === 'characters') {
        indicator = document.getElementById('agent-processing-characters');
        navTab = document.querySelector('[data-tab="characters"]');
    } else if (tabName === 'plot') {
        indicator = document.getElementById('agent-processing-plot');
        navTab = document.querySelector('[data-tab="plot"]');
    } else if (tabName === 'writer') {
        indicator = document.getElementById('agent-processing-writer');
        navTab = document.querySelector('[data-tab="writer"]');
    }
    
    if (indicator) {
        indicator.classList.remove('hidden');
        const textEl = indicator.querySelector('.processing-text');
        if (textEl && agentName) {
            textEl.innerHTML = `<strong>${agentName}</strong> 正在處理中，請稍候...`;
        }
    }
    
    // 為對應的 Nav Tab 添加處理中效果
    if (navTab) {
        navTab.classList.add('processing');
    }
}

/**
 * 隱藏指定 Tab 的 Agent 處理中指示器
 * @param {string} tabName - Tab 名稱
 */
function hideAgentProcessingIndicator(tabName) {
    let indicator = null;
    let navTab = null;
    
    if (tabName === 'worldview') {
        indicator = el.agentProcessingWorldview;
        navTab = document.querySelector('[data-tab="worldview"]');
    } else if (tabName === 'characters') {
        indicator = document.getElementById('agent-processing-characters');
        navTab = document.querySelector('[data-tab="characters"]');
    } else if (tabName === 'plot') {
        indicator = document.getElementById('agent-processing-plot');
        navTab = document.querySelector('[data-tab="plot"]');
    } else if (tabName === 'writer') {
        indicator = document.getElementById('agent-processing-writer');
        navTab = document.querySelector('[data-tab="writer"]');
    }
    
    if (indicator) {
        indicator.classList.add('hidden');
    }
    
    if (navTab) {
        navTab.classList.remove('processing');
    }
}

/**
 * 隱藏所有 Agent 處理中指示器
 */
function hideAllAgentProcessingIndicators() {
    document.querySelectorAll('.agent-processing-indicator').forEach(ind => {
        ind.classList.add('hidden');
    });
    document.querySelectorAll('.nav-tab.processing').forEach(tab => {
        tab.classList.remove('processing');
    });
}

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
    
    toggle.addEventListener('change', () => {
        state.isAutoExecuteMode = toggle.checked;
        modeLabels.forEach(label => {
            if (label.classList.contains('mode-auto')) {
                label.style.opacity = state.isAutoExecuteMode ? '1' : '0.5';
            } else {
                label.style.opacity = state.isAutoExecuteMode ? '0.5' : '1';
            }
        });
    });
}

/**
 * 顯示/隱藏管道進度條
 */
function showPipelineProgress(show) {
    const progressBar = document.getElementById('pipeline-progress-bar');
    if (progressBar) {
        if (show) {
            progressBar.classList.remove('hidden');
        } else {
            progressBar.classList.add('hidden');
        }
    }
}

/**
 * 更新管道階段指示器的狀態
 * @param {string} stage - 階段名稱：worldview, characters, plot, writer
 * @param {string} status - 狀態：pending, running, done, error
 */
function updatePipelineStage(stage, status) {
    const stageIndicator = document.querySelector(`.stage-indicator[data-stage="${stage}"]`);
    if (!stageIndicator) return;
    
    // 移除所有狀態類
    stageIndicator.classList.remove('pending', 'running', 'done', 'error');
    // 添加新狀態
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

/**
 * 更新總監訊息
 */
function updateDirectorMessage(message) {
    const directorMsg = document.getElementById('director-message');
    if (directorMsg) {
        directorMsg.textContent = message;
    }
}

/**
 * 在 textarea 中顯示「生成中...」告示
 * @param {string} tabName - 目標標籤：worldview, characters, plot
 */
function showGeneratingIndicator(tabName) {
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

/**
 * 隱藏生成中告示
 */
function hideGeneratingIndicator(tabName) {
    // 不恢復內容，讓真實內容替換
}

/**
 * 啟動管道流程
 */
async function runPipeline() {
    if (!state.currentNovelId) {
        showToast('請先選擇或建立一個小說專案');
        return;
    }
    
    if (!state.isAutoExecuteMode) {
        showToast('請先切換到「一鍵執行模式」再開始');
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
    
    // 首先呼叫 director-decision 來評估當前狀態
    updateDirectorMessage('🔍 總監正在掃描創作現狀...');
    
    try {
        // 獲取用戶的原始創作需求（如果有的話）
        const userPrompt = state.currentNovelData?.novel?.description || '請根據現有設定繼續創作';
        
        // 呼叫總監決策 API
        streamAPI(
            `/api/novels/${state.currentNovelId}/director-decision`,
            {
                current_stage: 'init',
                user_prompt: userPrompt,
                auto_execute: state.isAutoExecuteMode
            },
            // onThinking
            (thinking) => {
                const thinkingBox = el.aiThinkingStream;
                if (thinkingBox) {
                    thinkingBox.classList.remove('hidden');
                    el.aiThinkingText.textContent += thinking;
                }
            },
            // onContent
            (content) => {
                // 內容會顯示在聊天區
                updateDirectorMessage('📝 總監決策分析中...');
            },
            // onError
            (error) => {
                console.error('Director decision error:', error);
                showToast('決策評估失敗: ' + error);
            },
            // onDone
            async () => {
                // 決策完成後，根據結果執行
                await handleDirectorDecision();
            }
        );
    } catch (err) {
        console.error('Pipeline error:', err);
        showToast('管道執行失敗: ' + err.message);
        state.isPipelineRunning = false;
        showPipelineProgress(false);
    }
}

/**
 * 處理總監決策結果
 */
async function handleDirectorDecision() {
    // 這裡需要從聊天區或特殊區域讀取總監的決策
    // 為了簡化，我們直接根據當前狀態來判斷下一步
    
    updateDirectorMessage('🎯 總監正在制定創作策略...');
    
    // 檢查當前創作狀態
    const hasWorldview = state.currentNovelData?.worldbuilding && state.currentNovelData.worldbuilding.trim().length > 50;
    const hasCharacters = state.currentNovelData?.characters && state.currentNovelData.characters.characters?.length > 0;
    const hasPlot = state.currentNovelData?.plot && state.currentNovelData.plot.chapters?.length > 0;
    
    // 決定下一步
    if (!hasWorldview) {
        // 需要生成世界觀
        updatePipelineStage('worldview', 'running');
        updateDirectorMessage('🌍 開始生成世界觀設定...');
        await executeArchitectAgent();
    } else if (!hasCharacters) {
        // 需要生成角色
        updatePipelineStage('worldview', 'done');
        updatePipelineStage('characters', 'running');
        updateDirectorMessage('👥 開始生成角色設定...');
        await executeCharacterAgent();
    } else if (!hasPlot) {
        // 需要生成大綱
        updatePipelineStage('worldview', 'done');
        updatePipelineStage('characters', 'done');
        updatePipelineStage('plot', 'running');
        updateDirectorMessage('📋 開始生成章節大綱...');
        await executePlotAgent();
    } else {
        // 所有前期準備完成
        updatePipelineStage('worldview', 'done');
        updatePipelineStage('characters', 'done');
        updatePipelineStage('plot', 'done');
        updateDirectorMessage('✅ 前期準備完成！可以開始寫作章節正文。');
        state.isPipelineRunning = false;
        
        // 自動切換到寫作模式
        state.activeTab = 'writer';
        renderActiveTab();
        
        // 延遲關閉進度條，確保用戶能看到完成狀態
        setTimeout(() => {
            showPipelineProgress(false);
        }, 3000);
    }
}

/**
 * 執行 Story Architect Agent
 */
async function executeArchitectAgent() {
    showGeneratingIndicator('worldview');
    
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
        },
        async () => {
            el.editorWorldview.disabled = false;
            updatePipelineStage('worldview', 'done');
            
            // 保存世界觀
            await requestAPI(`/api/novels/${state.currentNovelId}/worldbuilding`, 'POST', {
                content: el.editorWorldview.value
            });
            
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
            
            // 保存角色
            let charData;
            try {
                charData = JSON.parse(el.editorCharactersJson.value);
            } catch (e) {
                charData = { characters: [] };
            }
            await requestAPI(`/api/novels/${state.currentNovelId}/characters`, 'POST', {
                json_data: charData
            });
            
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
            
            // 保存大綱
            let plotData;
            try {
                plotData = JSON.parse(el.editorPlotJson.value);
            } catch (e) {
                plotData = { chapters: [] };
            }
            await requestAPI(`/api/novels/${state.currentNovelId}/plot`, 'POST', {
                outline_json: plotData
            });
            
            await loadNovelDetails(state.currentNovelId);
            await handleDirectorDecision();
        }
    );
}

// ==========================================
// API WRAPPERS & STREAMING CORE
// ==========================================
async function requestAPI(url, method = 'GET', body = null) {
    try {
        const options = {
            method,
            headers: { 'Content-Type': 'application/json' }
        };
        if (body) {
            options.body = JSON.stringify(body);
        }
        const response = await fetch(url, options);
        if (!response.ok) {
            const errData = await response.json().catch(() => ({ detail: response.statusText }));
            throw new Error(errData.detail || response.statusText);
        }
        return await response.json();
    } catch (e) {
        console.error(`API Error: ${e.message}`);
        showToast(`錯誤: ${e.message}`);
        throw e;
    }
}

async function streamAPI(endpoint, body, onThinking, onContent, onError, onDone) {
    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        
        if (!response.ok) {
            const errText = await response.text();
            onError(`HTTP 錯誤 ${response.status}: ${errText}`);
            onDone();
            return;
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';
        
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop(); 
            
            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed || !trimmed.startsWith('data:')) continue;
                
                try {
                    const dataStr = trimmed.slice(5).trim();
                    if (dataStr === '[DONE]') continue;
                    const parsed = JSON.parse(dataStr);
                    
                    if (parsed.type === 'thinking') {
                        onThinking(parsed.delta);
                    } else if (parsed.type === 'content') {
                        onContent(parsed.delta);
                    } else if (parsed.type === 'error') {
                        onError(parsed.message);
                    }
                } catch (e) {
                    // Ignore JSON parsing errors for partial chunks
                }
            }
        }
        onDone();
    } catch (err) {
        onError(`網路連接錯誤: ${err.message}`);
        onDone();
    }
}

// ==========================================
// NOVEL LIFE CYCLE
// ==========================================
async function loadNovels() {
    try {
        state.novels = await requestAPI('/api/novels');
        renderNovelsList();
    } catch (e) {
        console.error("Failed to load novels list");
    }
}

async function loadNovelDetails(novelId) {
    if (!novelId) return;
    try {
        el.currentNovelTitle.textContent = "載入中...";
        const data = await requestAPI(`/api/novels/${novelId}`);
        state.currentNovelId = novelId;
        state.currentNovelData = data;
        
        // Update header UI
        el.currentNovelTitle.textContent = data.novel.title;
        el.currentNovelGenre.textContent = `${data.novel.genre} • Style: ${data.novel.style}`;
        if (el.novelHeaderActions) el.novelHeaderActions.style.display = 'flex';
        
        // Render appropriate workspace components
        renderActiveTab();
        renderChatMessages();
        
        // Select active item in sidebar list
        document.querySelectorAll('#novels-list li').forEach(li => {
            if (li.dataset.id === novelId) {
                li.classList.add('active');
            } else {
                li.classList.remove('active');
            }
        });
    } catch (e) {
        el.currentNovelTitle.textContent = "載入錯誤";
    }
}

// ==========================================
// SYSTEM SETTINGS CONTROLS
// ==========================================
async function loadSettings() {
    try {
        state.settingsData = await requestAPI('/api/settings');
        loadAgentConfigFields(state.activeSettingAgent);
    } catch (e) {
        console.error("Failed to load settings");
    }
}

function loadAgentConfigFields(agentName) {
    const config = state.settingsData[agentName] || {};
    
    el.settingAgentName.value = agentName;
    el.settingApiKey.value = config.api_key || '';
    el.settingBaseUrl.value = config.base_url || 'https://integrate.api.nvidia.com/v1';
    el.settingModel.value = config.model || '';
    el.settingMaxTokens.value = config.max_tokens || '';
    el.settingTemperature.value = config.temperature ?? '';
    el.settingTopP.value = config.top_p ?? '';
    el.settingEnableThinking.checked = config.enable_thinking === 1;
    
    // Auto-select match preset if it exists
    if (el.settingPresetModel) {
        const presetModels = ["nvidia/nemotron-3-super-120b-a12b", "openai/gpt-oss-120b", "minimaxai/minimax-m2.7", "mistralai/mistral-small-4-119b-2603", "stepfun-ai/step-3.5-flash", "google/gemma-3n-e4b-it", "qwen/qwen3.5-122b-a10b"];
        if (config.model && presetModels.includes(config.model)) {
            el.settingPresetModel.value = config.model;
        } else {
            el.settingPresetModel.value = "";
        }
    }
    
    // Use display_name from backend if available
    el.settingsAgentTitle.textContent = config.display_name || agentName;
}

async function saveCurrentAgentSettings() {
    const agentName = el.settingAgentName.value;
    const payload = {
        agent_name: agentName,
        api_key: el.settingApiKey.value,
        base_url: el.settingBaseUrl.value,
        model: el.settingModel.value,
        temperature: parseFloat(el.settingTemperature.value) || 0.7,
        top_p: parseFloat(el.settingTopP.value) || 0.95,
        max_tokens: parseInt(el.settingMaxTokens.value) || 4096,
        enable_thinking: el.settingEnableThinking.checked
    };
    
    try {
        await requestAPI('/api/settings', 'POST', payload);
        showToast(`${agentName} 設定保存成功`);
        loadSettings(); // refresh state
    } catch (e) {
        showToast("設定保存失敗");
    }
}

// ==========================================
// RENDERERS (DOM TREE BUILDERS)
// ==========================================
function clearWorkspace() {
    state.currentNovelId = null;
    state.currentNovelData = null;
    
    // Header
    el.currentNovelTitle.textContent = "請選擇或建立一部小說";
    el.currentNovelGenre.textContent = "小說類型";
    if (el.novelHeaderActions) el.novelHeaderActions.style.display = 'none';
    
    // Worldview Tab
    if (el.editorWorldview) el.editorWorldview.value = '';
    
    // Characters Tab
    if (el.editorCharactersJson) el.editorCharactersJson.value = '{\n  "characters": []\n}';
    if (el.charactersCardsGrid) el.charactersCardsGrid.innerHTML = '<div class="empty-placeholder">請建立或選擇小說以查看角色。</div>';
    
    // Plot Tab
    if (el.editorPlotJson) el.editorPlotJson.value = '{\n  "chapters": []\n}';
    if (el.plotTimeline) el.plotTimeline.innerHTML = '<div class="empty-placeholder">請建立或選擇小說以查看大綱。</div>';
    
    // Writer Tab
    if (el.writerChaptersList) el.writerChaptersList.innerHTML = '<li class="loading-placeholder">請建立或選擇小說。</li>';
    if (el.activeChapterTitle) el.activeChapterTitle.textContent = "請選擇章節";
    if (el.activeChapterStatus) el.activeChapterStatus.textContent = "";
    if (el.chapterOutlineSummaryText) el.chapterOutlineSummaryText.textContent = "等待選擇章節大綱...";
    if (el.editorProse) el.editorProse.value = "";
    if (el.aiThinkingStream) el.aiThinkingStream.classList.add('hidden');
    if (el.aiThinkingText) el.aiThinkingText.textContent = "";
    
    // Chat messages
    if (el.chatMessagesContainer) el.chatMessagesContainer.innerHTML = '<div class="chat-message system"><div class="msg-content">💡 選擇一部小說開始討論。</div></div>';
}

function renderNovelsList() {
    el.novelsList.innerHTML = '';
    if (state.novels.length === 0) {
        el.novelsList.innerHTML = '<li class="loading-placeholder">目前尚無創作專案</li>';
        return;
    }
    state.novels.forEach(n => {
        const li = document.createElement('li');
        li.dataset.id = n.id;
        if (state.currentNovelId === n.id) {
            li.className = 'active';
        }
        
        const dateObj = new Date(n.created_at);
        const formattedDate = `${dateObj.getMonth() + 1}/${dateObj.getDate()}`;
        
        li.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="novel-title-text" style="font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:160px;">${n.title}</span>
                <span class="delete-novel-btn" style="color:var(--text-muted); cursor:pointer; font-size:0.8rem; padding: 2px 6px;" title="刪除小說">✕</span>
            </div>
            <div class="novel-meta">
                <span>${n.genre}</span>
                <span>${formattedDate}</span>
            </div>
        `;
        
        // Delete novel handler
        li.querySelector('.delete-novel-btn').addEventListener('click', async (e) => {
            e.stopPropagation();
            if (confirm(`確定要刪除「${n.title}」專案嗎？此操作無法還原！`)) {
                try {
                    await requestAPI(`/api/novels/${n.id}`, 'DELETE');
                    if (state.currentNovelId === n.id) {
                        clearWorkspace();
                    }
                    await loadNovels();
                    showToast("專案已成功刪除");
                } catch (err) {
                    showToast("刪除失敗: " + err.message);
                }
            }
        });
        
        // Select novel handler
        li.addEventListener('click', (e) => {
            if (e.target.closest('.delete-novel-btn')) {
                return;
            }
            loadNovelDetails(n.id);
        });
        
        el.novelsList.appendChild(li);
    });
}

function renderActiveTab() {
    // Hide all workpanels, activate correct nav tab
    el.navTabs.forEach(t => {
        if (t.dataset.tab === state.activeTab) {
            t.classList.add('active');
        } else {
            t.classList.remove('active');
        }
    });
    
    el.workpanels.forEach(p => {
        if (p.id === `panel-${state.activeTab}`) {
            p.classList.add('active');
        } else {
            p.classList.remove('active');
        }
    });
    
    if (!state.currentNovelData) return;
    
    // Call specific tab renderer
    if (state.activeTab === 'worldview') renderWorldviewTab();
    if (state.activeTab === 'characters') renderCharactersTab();
    if (state.activeTab === 'plot') renderPlotTab();
    if (state.activeTab === 'writer') renderWriterTab();
}

function renderWorldviewTab() {
    el.editorWorldview.value = state.currentNovelData.worldbuilding || '';
}

function renderCharactersTab() {
    // Sync JSON text
    el.editorCharactersJson.value = state.currentNovelData.characters_raw || '{\n  "characters": []\n}';
    
    // Generate Cards
    el.charactersCardsGrid.innerHTML = '';
    const charData = state.currentNovelData.characters;
    
    if (!charData || !charData.characters || charData.characters.length === 0) {
        el.charactersCardsGrid.innerHTML = '<div class="empty-placeholder">尚無角色。點擊「AI 自動設計角色」或「新增角色」開始。</div>';
        return;
    }
    
    charData.characters.forEach((c, index) => {
        const card = document.createElement('div');
        card.className = 'character-card';
        card.dataset.index = index;
        
        const traitsHtml = (c.personality || []).map(t => `<span class="char-trait-pill">${t}</span>`).join('');
        const flawsHtml = (c.flaws || []).map(f => `<span class="char-trait-pill" style="border-color:rgba(239, 68, 68, 0.2); color:#fca5a5;">${f}</span>`).join('');
        
        card.innerHTML = `
            <div class="char-header">
                <span class="char-name">${c.name}</span>
                <span class="char-role">${c.role}</span>
            </div>
            <div class="char-bio">
                <strong>動機：</strong><span class="char-motivation">${c.motivation}</span><br>
                <strong>成長弧線：</strong><span class="char-arc">${c.arc}</span>
            </div>
            <div class="char-traits">
                ${traitsHtml}
                ${flawsHtml}
            </div>
            <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:8px;">
                <button class="btn btn-secondary btn-xs edit-char-btn" data-index="${index}">編輯</button>
                <button class="btn btn-ai btn-xs ai-enhance-char-btn" data-index="${index}">✨ AI 局部增強</button>
                <button class="btn btn-ghost btn-xs delete-char-btn" data-index="${index}">刪除</button>
            </div>
        `;
        
        // Delete character handler - FIXED: properly capture index in closure
        const deleteBtn = card.querySelector('.delete-char-btn');
        deleteBtn.addEventListener('click', (function(idx, charName) {
            return function() {
                if (confirm(`刪除角色「${charName}」？`)) {
                    // Re-fetch fresh data from state to avoid stale reference
                    const freshCharData = state.currentNovelData.characters;
                    if (freshCharData && freshCharData.characters && freshCharData.characters[idx]) {
                        freshCharData.characters.splice(idx, 1);
                        state.currentNovelData.characters = freshCharData;
                        const newRaw = JSON.stringify(freshCharData, null, 2);
                        state.currentNovelData.characters_raw = newRaw;
                        // 同步更新 textarea
                        el.editorCharactersJson.value = newRaw;
                        // 直接發送 API 請求保存
                        requestAPI(`/api/novels/${state.currentNovelId}/characters`, 'POST', { json_data: freshCharData })
                            .then(() => {
                                showToast('角色已刪除');
                                renderCharactersTab();
                            })
                            .catch(() => {
                                showToast('刪除失敗');
                            });
                    }
                }
            };
        })(index, c.name));
        
        // Edit character handler - NEW: opens edit modal
        const editBtn = card.querySelector('.edit-char-btn');
        editBtn.addEventListener('click', (function(idx, char) {
            return function() {
                openCharacterEditModal(idx, char);
            };
        })(index, {...c})); // spread to avoid reference issues
        
        el.charactersCardsGrid.appendChild(card);
    });
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
    document.getElementById('edit-char-motivation').value = character.motivation || '';
    document.getElementById('edit-char-arc').value = character.arc || '';
    document.getElementById('edit-char-personality').value = (character.personality || []).join(', ');
    document.getElementById('edit-char-flaws').value = (character.flaws || []).join(', ');
    
    // Save handler - 直接保存，不要觸發其他事件
    const saveBtn = document.getElementById('btn-save-character-edit');
    
    // 移除舊的事件監聽器（用 cloneNode 方式）
    const newSaveBtn = saveBtn.cloneNode(true);
    saveBtn.parentNode.replaceChild(newSaveBtn, saveBtn);
    
    newSaveBtn.addEventListener('click', () => {
        // 直接發送 API 請求，不要從 textarea 讀取
        const updatedChar = {
            name: document.getElementById('edit-char-name').value,
            role: document.getElementById('edit-char-role').value,
            motivation: document.getElementById('edit-char-motivation').value,
            arc: document.getElementById('edit-char-arc').value,
            personality: document.getElementById('edit-char-personality').value.split(',').map(s => s.trim()).filter(s => s),
            flaws: document.getElementById('edit-char-flaws').value.split(',').map(s => s.trim()).filter(s => s)
        };
        
        // 更新本地 state
        const charData = state.currentNovelData.characters;
        if (charData && charData.characters && charData.characters[index]) {
            charData.characters[index] = updatedChar;
            state.currentNovelData.characters = charData;
            const newRaw = JSON.stringify(charData, null, 2);
            state.currentNovelData.characters_raw = newRaw;
            
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

function renderPlotTab() {
    el.editorPlotJson.value = state.currentNovelData.plot_raw || '{\n  "chapters": []\n}';
    
    el.plotTimeline.innerHTML = '';
    const plotData = state.currentNovelData.plot;
    
    if (!plotData || !plotData.chapters || plotData.chapters.length === 0) {
        el.plotTimeline.innerHTML = '<div class="empty-placeholder">尚無章節規劃。點擊「AI 自動拆分章節」來建立整本大綱。</div>';
        return;
    }
    
    plotData.chapters.forEach((ch, index) => {
        const item = document.createElement('div');
        item.className = 'timeline-item';
        item.dataset.index = index;
        
        // 處理 events 可能為字串陣列或物件陣列
        let eventsContent = '';
        if (Array.isArray(ch.events)) {
            eventsContent = ch.events.map(e => {
                if (typeof e === 'string') {
                    return `<li>${e}</li>`;
                } else if (typeof e === 'object' && e !== null) {
                    // 處理物件格式的事件 {scene, action, consequence}
                    return `<li><strong>${e.scene || ''}</strong>：${e.action || ''}</li>`;
                }
                return `<li>${String(e)}</li>`;
            }).join('');
        }
        
        // 處理 foreshadowing
        let foreshadowHtml = '無設定伏筆';
        if (ch.foreshadowing && Array.isArray(ch.foreshadowing) && ch.foreshadowing.length > 0) {
            foreshadowHtml = `<strong>伏筆提示：</strong>` + ch.foreshadowing.map(f => {
                if (typeof f === 'string') return f;
                return JSON.stringify(f);
            }).join('、');
        } else if (ch.foreshadowing_plant && Array.isArray(ch.foreshadowing_plant)) {
            foreshadowHtml = `<strong>伏筆提示：</strong>` + ch.foreshadowing_plant.join('、');
        }
            
        item.innerHTML = `
            <div class="timeline-header">
                <span class="timeline-chapter-idx">第 ${ch.chapter_index} 章</span>
                <span class="timeline-tone">${ch.emotional_tone || '均衡'}</span>
            </div>
            <div class="timeline-title">${ch.title || '未命名章節'}</div>
            <div class="timeline-purpose"><strong>功能本質：</strong>${ch.purpose || '未定義'}</div>
            <ul class="timeline-events-list">
                ${eventsContent || '<li>無事件記錄</li>'}
            </ul>
            <div class="timeline-foreshadow">
                ${foreshadowHtml}
            </div>
            <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:12px; border-top:1px solid var(--border-color); padding-top:8px;">
                <button class="btn btn-secondary btn-xs edit-chapter-outline-btn" data-index="${index}">編輯</button>
                <button class="btn btn-ghost btn-xs delete-chapter-outline-btn" data-index="${index}">刪除</button>
            </div>
        `;
        
        // 編輯按鈕 - 開啟編輯 Modal
        const editBtn = item.querySelector('.edit-chapter-outline-btn');
        editBtn.addEventListener('click', () => {
            openChapterOutlineEditModal(index, ch);
        });
        
        // 刪除按鈕 - 使用正確的 index 引用
        const deleteBtn = item.querySelector('.delete-chapter-outline-btn');
        deleteBtn.addEventListener('click', (function(idx, chapter) {
            return function() {
                if (confirm(`刪除第 ${chapter.chapter_index} 章大綱？`)) {
                    // 確保使用最新的 plotData
                    const freshPlotData = state.currentNovelData.plot;
                    if (freshPlotData && freshPlotData.chapters && freshPlotData.chapters[idx]) {
                        freshPlotData.chapters.splice(idx, 1);
                        // reindex
                        freshPlotData.chapters.forEach((item, i) => {
                            item.chapter_index = i + 1;
                        });
                        // 同步更新 state
                        state.currentNovelData.plot = freshPlotData;
                        state.currentNovelData.plot_raw = JSON.stringify(freshPlotData, null, 2);
                        el.editorPlotJson.value = state.currentNovelData.plot_raw;
                        savePlotOutlineDirect();
                    }
                }
            };
        })(index, ch));
        
        el.plotTimeline.appendChild(item);
    });
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

function renderWriterTab() {
    el.writerChaptersList.innerHTML = '';
    const plotData = state.currentNovelData.plot;
    const writtenChapters = state.currentNovelData.chapters || [];
    
    if (!plotData || !plotData.chapters || plotData.chapters.length === 0) {
        el.writerChaptersList.innerHTML = '<li class="loading-placeholder">請先前往「劇情大綱」建立大綱章節。</li>';
        disableWriterPanel();
        return;
    }
    
    // Enable buttons
    el.btnWriteChapter.disabled = false;
    el.btnEditChapter.disabled = false;
    el.btnProseSave.disabled = false;
    el.editorProse.disabled = false;
    
    plotData.chapters.forEach(ch => {
        const li = document.createElement('li');
        li.dataset.index = ch.chapter_index;
        
        // check if this chapter is written
        const isWritten = writtenChapters.some(c => c.chapter_index === ch.chapter_index);
        const statusText = isWritten ? '已寫作' : '草稿';
        const statusClass = isWritten ? 'status-written' : 'status-draft';
        
        if (state.activeChapterIndex === ch.chapter_index) {
            li.className = 'active';
        }
        
        li.innerHTML = `
            <span class="ch-num">Chapter ${ch.chapter_index}</span>
            <span style="font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${ch.title}</span>
            <span class="status-pill ${statusClass}" style="align-self:flex-start; margin-top:2px; font-size:0.65rem;">${statusText}</span>
        `;
        
        li.addEventListener('click', () => {
            selectWriterChapter(ch.chapter_index);
        });
        
        el.writerChaptersList.appendChild(li);
    });
    
    // Auto select first chapter if none selected
    if (state.activeChapterIndex === null && plotData.chapters.length > 0) {
        selectWriterChapter(plotData.chapters[0].chapter_index);
    }
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

function selectWriterChapter(chapterIndex) {
    state.activeChapterIndex = parseInt(chapterIndex);
    
    // Update active highlight in list
    document.querySelectorAll('#writer-chapters-list li').forEach(li => {
        if (parseInt(li.dataset.index) === state.activeChapterIndex) {
            li.classList.add('active');
        } else {
            li.classList.remove('active');
        }
    });
    
    const plotData = state.currentNovelData.plot;
    const chapterOutline = (plotData.chapters || []).find(ch => ch.chapter_index === state.activeChapterIndex);
    
    if (chapterOutline) {
        el.activeChapterTitle.textContent = `第 ${chapterOutline.chapter_index} 章：${chapterOutline.title}`;
        el.chapterOutlineSummaryText.innerHTML = `
            <strong>本章目的：</strong>${chapterOutline.purpose}<br>
            <strong>情節事件：</strong><br>${(chapterOutline.events || []).map(e => `• ${e}`).join('<br>')}
        `;
    }
    
    // Load chapter content from state
    const writtenChapters = state.currentNovelData.chapters || [];
    const chapterProse = writtenChapters.find(c => c.chapter_index === state.activeChapterIndex);
    
    if (chapterProse) {
        el.editorProse.value = chapterProse.content;
        el.activeChapterStatus.className = 'status-pill status-written';
        el.activeChapterStatus.textContent = '已寫作';
    } else {
        el.editorProse.value = '';
        el.activeChapterStatus.className = 'status-pill status-draft';
        el.activeChapterStatus.textContent = '草稿';
    }
}

function renderChatMessages() {
    // Keep first system prompt
    const systemMsg = el.chatMessagesContainer.firstElementChild.outerHTML;
    el.chatMessagesContainer.innerHTML = systemMsg;
    
    if (!state.currentNovelData || !state.currentNovelData.chat_memory) return;
    
    state.currentNovelData.chat_memory.forEach(m => {
        const msg = document.createElement('div');
        const isUser = m.role === 'user';
        msg.className = `message ${isUser ? 'user-msg' : 'assistant-msg'}`;
        
        msg.innerHTML = `
            <div class="msg-sender">${isUser ? 'You' : 'Novel Director'}</div>
            <div class="msg-content">${m.content}</div>
        `;
        el.chatMessagesContainer.appendChild(msg);
    });
    
    // scroll bottom
    el.chatMessagesContainer.scrollTop = el.chatMessagesContainer.scrollHeight;
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
    const content = el.editorProse.value;
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
        showToast(`第 ${state.activeChapterIndex} 章正文已手動保存`);
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
                el.editorProse.value = '';
                streamAPI(
                    '/api/agent/write-chapter',
                    { novel_id: state.currentNovelId, chapter_index: chapter_index || 1 },
                    null,
                    (delta) => { el.editorProse.value += delta; },
                    (err) => showToast("Error: " + err),
                    async () => {
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
    
    streamAPI(
        endpoint,
        body,
        // onThinking
        (delta) => {
            el.aiThinkingText.textContent += delta;
        },
        // onContent
        (delta) => {
            onContentTarget.value += delta;
            // auto scroll textarea to bottom while streaming
            onContentTarget.scrollTop = onContentTarget.scrollHeight;
        },
        // onError
        (msg) => {
            showToast(msg);
            el.aiThinkingText.textContent += `\n[Error: ${msg}]`;
        },
        // onDone
        () => {
            el.aiThinkingStream.classList.add('hidden');
            // Hide Agent processing indicator
            hideAgentProcessingIndicator(tabName);
            if (onDoneCallback) onDoneCallback();
        }
    );
}

async function runDirectorDecision(currentStage) {
    return new Promise((resolve) => {
        const directorResponseContainer = document.createElement('div');
        directorResponseContainer.className = 'message assistant-msg';
        directorResponseContainer.innerHTML = `<div class="msg-sender">🎬 AI 總監決策中...</div><div class="msg-content stream-typing"></div>`;
        el.chatMessagesContainer.appendChild(directorResponseContainer);
        el.chatMessagesContainer.scrollTop = el.chatMessagesContainer.scrollHeight;
        
        const streamTarget = directorResponseContainer.querySelector('.stream-typing');
        
        const userPrompt = el.promptDrawerTextarea.value;
        
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
                // 發生錯誤時也要停止閃爍
                streamTarget.classList.remove('stream-typing');
                streamTarget.classList.add('streaming-done');
            },
            async () => {
                // 回覆完成，停止閃爍效果
                streamTarget.classList.remove('stream-typing');
                streamTarget.classList.add('streaming-done');
                
                // Parse director's response to determine if we should continue
                const responseText = streamTarget.textContent;
                
                // Parse execution command from Director's response
                // 解析【執行指令】區塊
                const executionBlock = responseText.match(/\【執行指令\】\s*ACTION:\s*(\w+)/);
                let action = executionBlock ? executionBlock[1].trim().toUpperCase() : null;
                
                // 解析目標階段
                const targetBlock = responseText.match(/TARGET:\s*(\w+)/);
                let target = targetBlock ? targetBlock[1].trim() : null;
                
                // 解析提示信息
                const hintBlock = responseText.match(/HINT:\s*([\s\S]*?)(?=```|$)/);
                let hint = hintBlock ? hintBlock[1].trim() : '';
                
                // 根據ACTION決定後續行動
                let shouldContinue = false;
                let shouldPause = false;
                let regenerate = false;
                let regenerateStage = null;
                
                if (action === 'CONTINUE') {
                    shouldContinue = true;
                    showToast("✅ 總監批准，繼續執行下一階段");
                } else if (action === 'AUTO_REGENERATE') {
                    shouldContinue = true;
                    regenerate = true;
                    regenerateStage = target || currentStage;
                    showToast("⚡ 總監指示重跑/擴充，正在執行...");
                } else if (action === 'WAIT_USER') {
                    shouldPause = true;
                    showToast("⏸️ 總監要求用戶確認");
                } else {
                    // 舊版解析邏輯（向後兼容）
                    shouldContinue = responseText.includes('繼續') || responseText.includes('是');
                    shouldPause = responseText.includes('暫停') || responseText.includes('等待') || responseText.includes('修改');
                }
                
                // Add director's full response to chat
                directorResponseContainer.classList.add('director-response');
                
                resolve({ 
                    continue: shouldContinue && !shouldPause, 
                    response: responseText,
                    shouldPause: shouldPause,
                    action: action,
                    target: target,
                    hint: hint,
                    regenerate: regenerate,
                    regenerateStage: regenerateStage
                });
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

function handleDrawerPromptSubmit() {
    const userPrompt = el.promptDrawerTextarea.value;
    el.drawerPrompt.classList.remove('active');
    
    if (state.activeDrawerAction === 'pipeline_orchestration') {
        if (!state.isAutoExecuteMode) {
            showToast('請先開啟「一鍵執行模式」再開始'); 
            return;
        }
        runFullPipeline(userPrompt);
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
            }
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
            alert("請輸入書名！");
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
    
    // 5. Add Manual placeholders
    el.btnCharacterAdd.addEventListener('click', () => {
        const rawText = el.editorCharactersJson.value;
        let charData = { characters: [] };
        try {
            charData = JSON.parse(rawText);
        } catch (e) {}
        
        charData.characters.push({
            name: "新登場角色",
            role: "主角 / 配角",
            personality: ["勇敢", "冷酷"],
            flaws: ["傲慢"],
            motivation: "尋找真相",
            arc: "逐漸理解愛與奉獻"
        });
        
        el.editorCharactersJson.value = JSON.stringify(charData, null, 2);
        saveCharactersDirect();
    });
    
    el.btnPlotAddChapter.addEventListener('click', () => {
        const rawText = el.editorPlotJson.value;
        let plotData = { chapters: [] };
        try {
            plotData = JSON.parse(rawText);
        } catch (e) {}
        
        const nextIdx = plotData.chapters.length + 1;
        plotData.chapters.push({
            chapter_index: nextIdx,
            title: `第 ${nextIdx} 章故事`,
            events: ["發生了事件一", "發生了重要轉折"],
            purpose: "推動故事主線",
            foreshadowing: ["埋下一個線索"],
            emotional_tone: "緊張"
        });
        
        el.editorPlotJson.value = JSON.stringify(plotData, null, 2);
        savePlotOutlineDirect();
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
            el.promptDrawerTextarea.value = savedPrompt || "例如：仙俠題材。主角是一個身懷魔門功法的正道弟子，講述他如何游走黑白兩道，修得太上斬仙之路。基調宏大，充滿宿命感。";
            
            el.drawerPrompt.classList.add('active');
        });
    }

    el.btnArchitectGenerate.addEventListener('click', () => {
        if (!state.currentNovelId) return showToast("請先選擇或建立一部小說");
        state.activeDrawerAction = 'architect';
        el.promptDrawerTitle.textContent = "🤖 1️⃣ Story Architect 世界觀規劃";
        el.promptDrawerDesc.textContent = "為這部小說構建一個引人入勝的世界觀。請輸入您的小說主線大綱構想或基本靈感條件：";
        el.promptDrawerTextarea.value = "例如：仙俠題材。主角是一個身懷魔門功法的正道弟子，講述他如何游走黑白兩道，修得太上斬仙之路。基調宏大，充滿宿命感。";
        el.drawerPrompt.classList.add('active');
    });
    
    el.btnCharacterGenerate.addEventListener('click', () => {
        if (!state.currentNovelId) return showToast("請先選擇或建立一部小說");
        state.activeDrawerAction = 'character';
        el.promptDrawerTitle.textContent = "🤖 2️⃣ Character Designer 角色設計";
        el.promptDrawerDesc.textContent = "根據目前已建立的世界觀，讓 AI 精細化設計所有核心要角。請輸入對角色的特定要求（可留空）：";
        el.promptDrawerTextarea.value = "例如：需要一個性格極度腹黑的反派，看似是主角的師尊，但實際上有驚天密謀；還要設計一位背負家族血債的劍仙女主角。";
        el.drawerPrompt.classList.add('active');
    });
    
    el.btnPlotGenerate.addEventListener('click', () => {
        if (!state.currentNovelId) return showToast("請先選擇或建立一部小說");
        state.activeDrawerAction = 'plot';
        el.promptDrawerTitle.textContent = "🤖 3️⃣ Plot Planner 章節拆分大綱";
        el.promptDrawerDesc.textContent = "AI 將自動依據世界觀與人物 Bible 拆分出整部小說的細節章節大綱。請輸入章節數量或核心情節走向指示：";
        el.promptDrawerTextarea.value = "例如：規劃 10 個章節的大綱。故事前期要有正魔衝突爆發，中期是師尊反水，後期主角完成突破並封印神魔。每一章節情節密度要高。";
        el.drawerPrompt.classList.add('active');
    });
    
    el.btnWriteChapter.addEventListener('click', () => {
        if (!state.currentNovelId || !state.activeChapterIndex) return;
        // Chapter writer streams directly into editorProse
        startAgentStream(
            '/api/agent/write-chapter',
            { novel_id: state.currentNovelId, chapter_index: state.activeChapterIndex },
            el.editorProse,
            async () => {
                showToast(`第 ${state.activeChapterIndex} 章正文撰寫完畢`);
                await loadNovelDetails(state.currentNovelId);
            }
        );
    });
    
    el.btnEditChapter.addEventListener('click', () => {
        if (!state.currentNovelId || !state.activeChapterIndex) return;
        state.activeDrawerAction = 'editor';
        el.promptDrawerTitle.textContent = "🤖 5️⃣ Editor Agent 精修優化";
        el.promptDrawerDesc.textContent = "請輸入您對此章節文字的精細修改方針（例如：增加懸疑細節、潤色對話、加快打鬥節奏，留空則由編輯自主優化）：";
        el.promptDrawerTextarea.value = "例如：讓主角與師尊的對話更加綿裡藏針、話中有話，加強環境描寫的寂靜肃殺氛圍。";
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
        userMsg.innerHTML = `<div class="msg-sender">You</div><div class="msg-content">${text}</div>`;
        el.chatMessagesContainer.appendChild(userMsg);
        el.chatMessagesContainer.scrollTop = el.chatMessagesContainer.scrollHeight;
        
        // Create assistant message stream bubble placeholder
        const assistantMsg = document.createElement('div');
        assistantMsg.className = 'message assistant-msg';
        assistantMsg.innerHTML = `<div class="msg-sender">Novel Director</div><div class="msg-content stream-typing"></div>`;
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
        if (confirm("清空與小說總監的對話記憶？(SQLite memory)")) {
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
