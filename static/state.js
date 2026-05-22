export const state = {
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
    isAutoExecuteMode: false,
    showStreamLog: true,
    
    // 策略卡片顯示狀態：'all' | '<' | '>'
    strategyCardView: 'all',
    // 當前顯示的卡片索引（0-3），用於 < 和 > 模式
    currentCardIndex: 0,
    // 當前顯示的子章節索引（'all' 或數字索引），用於單張卡片內的子項目切換
    currentSubSectionIndex: 'all'
};