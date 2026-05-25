export const el = {
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
    btnPlotAddVolume: document.getElementById('btn-plot-add-volume'),
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

