// ==========================================
// STATE MANAGEMENT
// ==========================================
const state = {
    novels: [],
    currentNovelId: null,
    currentNovelData: null,
    activeTab: 'pipeline', // pipeline, worldview, characters, plot, writer
    activeChapterIndex: null,
    settingsData: {},
    activeSettingAgent: 'global',
    
    // UI Drawer state
    activeDrawerAction: null // pipeline_orchestration, architect, character, plot, writer, editor
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
        const presetModels = ["nvidia/nemotron-3-super-120b-a12b", "openai/gpt-oss-120b", "minimaxai/minimax-m2.7", "mistralai/mistral-small-4-119b-2603", "stepfun-ai/step-3.5-flash", "google/gemma-3n-e4b-it"];
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
        
        const traitsHtml = (c.personality || []).map(t => `<span class="char-trait-pill">${t}</span>`).join('');
        const flawsHtml = (c.flaws || []).map(f => `<span class="char-trait-pill" style="border-color:rgba(239, 68, 68, 0.2); color:#fca5a5;">${f}</span>`).join('');
        
        card.innerHTML = `
            <div class="char-header">
                <span class="char-name">${c.name}</span>
                <span class="char-role">${c.role}</span>
            </div>
            <div class="char-bio">
                <strong>動機：</strong>${c.motivation}<br>
                <strong>成長弧線：</strong>${c.arc}
            </div>
            <div class="char-traits">
                ${traitsHtml}
                ${flawsHtml}
            </div>
            <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:8px;">
                <button class="btn btn-ghost btn-xs delete-char-btn" data-index="${index}">刪除</button>
            </div>
        `;
        
        card.querySelector('.delete-char-btn').addEventListener('click', () => {
            if (confirm(`刪除角色「${c.name}」？`)) {
                charData.characters.splice(index, 1);
                // Save updated characters back
                state.currentNovelData.characters = charData;
                state.currentNovelData.characters_raw = JSON.stringify(charData, null, 2);
                saveCharactersDirect();
            }
        });
        
        el.charactersCardsGrid.appendChild(card);
    });
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
        
        const eventsHtml = (ch.events || []).map(e => `<li>${e}</li>`).join('');
        const foreshadowHtml = (ch.foreshadowing || []).length > 0
            ? `<strong>伏筆提示：</strong>` + ch.foreshadowing.join('、')
            : '無設定伏筆';
            
        item.innerHTML = `
            <div class="timeline-header">
                <span class="timeline-chapter-idx">第 ${ch.chapter_index} 章</span>
                <span class="timeline-tone">${ch.emotional_tone || '均衡'}</span>
            </div>
            <div class="timeline-title">${ch.title}</div>
            <div class="timeline-purpose"><strong>功能本質：</strong>${ch.purpose}</div>
            <ul class="timeline-events-list">
                ${eventsHtml}
            </ul>
            <div class="timeline-foreshadow">
                ${foreshadowHtml}
            </div>
            <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:12px; border-top:1px solid var(--border-color); padding-top:8px;">
                <button class="btn btn-ghost btn-xs delete-chapter-outline-btn" data-index="${index}">刪除</button>
            </div>
        `;
        
        item.querySelector('.delete-chapter-outline-btn').addEventListener('click', () => {
            if (confirm(`刪除第 ${ch.chapter_index} 章大綱？`)) {
                plotData.chapters.splice(index, 1);
                // reindex
                plotData.chapters.forEach((item, idx) => {
                    item.chapter_index = idx + 1;
                });
                state.currentNovelData.plot = plotData;
                state.currentNovelData.plot_raw = JSON.stringify(plotData, null, 2);
                savePlotOutlineDirect();
            }
        });
        
        el.plotTimeline.appendChild(item);
    });
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
// DYNAMIC AGENT AGENT TEAM EXECUTION (STREAMING)
// ==========================================
function startAgentStream(endpoint, body, onContentTarget, onDoneCallback) {
    // Reset thinking text, show streaming box
    el.aiThinkingStream.classList.remove('hidden');
    el.aiThinkingText.textContent = '';
    
    // Clear and focus target
    onContentTarget.value = '';
    
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
            if (onDoneCallback) onDoneCallback();
        }
    );
}

function runFullPipeline(userPrompt) {
    if (!state.currentNovelId) return;
    
    // Get the visual flow elements
    const nodeArchitect = document.getElementById('node-architect');
    const nodeCharacter = document.getElementById('node-character');
    const nodePlot = document.getElementById('node-plot');
    
    const statusArchitect = document.getElementById('status-architect');
    const statusCharacter = document.getElementById('status-character');
    const statusPlot = document.getElementById('status-plot');
    
    const consoleArchitect = document.getElementById('pipeline-console-architect');
    const consoleCharacter = document.getElementById('pipeline-console-character');
    const consolePlot = document.getElementById('pipeline-console-plot');
    
    // 1. START STORY ARCHITECT
    nodeArchitect.className = 'pipeline-node node-working';
    statusArchitect.className = 'node-status-pill status-working';
    statusArchitect.textContent = 'Working 規劃中...';
    
    nodeCharacter.className = 'pipeline-node';
    statusCharacter.className = 'node-status-pill status-idle';
    statusCharacter.textContent = 'Waiting 等待中';
    
    nodePlot.className = 'pipeline-node';
    statusPlot.className = 'node-status-pill status-idle';
    statusPlot.textContent = 'Waiting 等待中';
    
    consoleArchitect.value = '【Story Architect Worldview Planning Start】...\n';
    consoleCharacter.value = '等待世界觀規劃完成...\n';
    consolePlot.value = '等待角色設計完成...\n';
    
    showToast("正在啟動世界觀架構師 Agent...");
    
    streamAPI(
        '/api/agent/story-architect',
        { novel_id: state.currentNovelId, user_prompt: userPrompt },
        // onThinking
        (delta) => {
            consoleArchitect.value += delta;
            consoleArchitect.scrollTop = consoleArchitect.scrollHeight;
        },
        // onContent
        (delta) => {
            consoleArchitect.value += delta;
            consoleArchitect.scrollTop = consoleArchitect.scrollHeight;
        },
        // onError
        (msg) => {
            consoleArchitect.value += `\n[Error: ${msg}]`;
            showToast(`Story Architect Error: ${msg}`);
        },
        // onDone
        async () => {
            nodeArchitect.className = 'pipeline-node node-success';
            statusArchitect.className = 'node-status-pill status-success';
            statusArchitect.textContent = 'Success 已完成';
            
            showToast("世界觀架構完成！正在啟動角色設計大師 Agent...");
            
            // 2. START CHARACTER DESIGNER
            nodeCharacter.className = 'pipeline-node node-working';
            statusCharacter.className = 'node-status-pill status-working';
            statusCharacter.textContent = 'Working 設計中...';
            consoleCharacter.value = '【Character Designer Role Generation Start】...\n';
            
            streamAPI(
                '/api/agent/character-designer',
                { novel_id: state.currentNovelId, user_prompt: userPrompt },
                // onThinking
                (delta) => {
                    consoleCharacter.value += delta;
                    consoleCharacter.scrollTop = consoleCharacter.scrollHeight;
                },
                // onContent
                (delta) => {
                    consoleCharacter.value += delta;
                    consoleCharacter.scrollTop = consoleCharacter.scrollHeight;
                },
                // onError
                (msg) => {
                    consoleCharacter.value += `\n[Error: ${msg}]`;
                    showToast(`Character Designer Error: ${msg}`);
                },
                // onDone
                async () => {
                    nodeCharacter.className = 'pipeline-node node-success';
                    statusCharacter.className = 'node-status-pill status-success';
                    statusCharacter.textContent = 'Success 已完成';
                    
                    showToast("角色 Bible 生成完成！正在啟動大綱規劃師 Agent...");
                    
                    // 3. START PLOT PLANNER
                    nodePlot.className = 'pipeline-node node-working';
                    statusPlot.className = 'node-status-pill status-working';
                    statusPlot.textContent = 'Working 拆解中...';
                    consolePlot.value = '【Plot Planner Outline Partitioning Start】...\n';
                    
                    streamAPI(
                        '/api/agent/plot-planner',
                        { novel_id: state.currentNovelId, user_prompt: userPrompt },
                        // onThinking
                        (delta) => {
                            consolePlot.value += delta;
                            consolePlot.scrollTop = consolePlot.scrollHeight;
                        },
                        // onContent
                        (delta) => {
                            consolePlot.value += delta;
                            consolePlot.scrollTop = consolePlot.scrollHeight;
                        },
                        // onError
                        (msg) => {
                            consolePlot.value += `\n[Error: ${msg}]`;
                            showToast(`Plot Planner Error: ${msg}`);
                        },
                        // onDone
                        async () => {
                            nodePlot.className = 'pipeline-node node-success';
                            statusPlot.className = 'node-status-pill status-success';
                            statusPlot.textContent = 'Success 已完成';
                            
                            showToast("🎉 聯動工作流全線執行完畢！所有大綱、角色已成功儲存！");
                            
                            // Reload novel details so other tabs instantly have the data loaded
                            await loadNovelDetails(state.currentNovelId);
                        }
                    );
                }
            );
        }
    );
}

function handleDrawerPromptSubmit() {
    const userPrompt = el.promptDrawerTextarea.value;
    el.drawerPrompt.classList.remove('active');
    
    if (state.activeDrawerAction === 'pipeline_orchestration') {
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
            el.promptDrawerDesc.textContent = "AI 聯動大腦將會啟動【世界觀規劃師 ➡️ 角色設計大師 ➡️ 劇情規劃大師】三階流水線，全自動生成整本小說的完整企劃案！請輸入您的小說主線大綱靈感：";
            el.promptDrawerTextarea.value = "例如：仙俠題材。主角是一個身懷魔門功法的正道弟子，講述他如何游走黑白兩道，修得太上斬仙之路。基調宏大，充滿宿命感。";
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

// ==========================================
// INITIALIZATION
// ==========================================
window.addEventListener('DOMContentLoaded', async () => {
    // 1. Load initial novels
    await loadNovels();
    
    // Auto select first novel if available
    if (state.novels.length > 0) {
        await loadNovelDetails(state.novels[0].id);
    }
    
    // 2. Setup buttons and tabs handlers
    setupEventListeners();
});
