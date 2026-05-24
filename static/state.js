export const state = {
    novels: [],
    currentNovelId: localStorage.getItem('currentNovelId') || null,
    currentNovelData: null,
    activeTab: localStorage.getItem('activeTab') || 'worldview', // worldview, characters, plot, writer
    activeChapterIndex: null,
    settingsData: {},
    activeSettingAgent: 'global',
    
    // UI Drawer state
    activeDrawerAction: null, // pipeline_orchestration, architect, character, plot, writer, editor
    
    // Pipeline workflow state
    isPipelineRunning: false,
    // 追蹤當前正在寫作的章節索引，用於防止串流內容寫入錯誤的章節
    currentlyWritingChapterIndex: null,
    
    // 當前正在操作的大綱卷索引（用於 volume_skeleton 階段）
    activeVolumeIndex: 1,
    
    // Director pipeline stage control（四階段漏斗流）
    pipelineStages: ['worldview', 'characters', 'plot', 'volume_skeleton', 'foreshadowing_orchestration', 'writer'],
    currentPipelineStageIndex: 0,
    
    // Director execution mode: 一鍵執行模式 vs 一般模式
    // 一鍵執行模式：總監的建議即為執行令（自動執行）
    // 一般模式：總監提供建議，由用戶決定
    isAutoExecuteMode: localStorage.getItem('isAutoExecuteMode') !== 'false',
    showStreamLog: localStorage.getItem('showStreamLog') !== 'false',
    
    // 策略卡片顯示狀態：'all' | '<' | '>'
    strategyCardView: 'all',
    // 當前顯示的卡片索引（0-3），用於 < 和 > 模式
    currentCardIndex: 0,
    // 當前顯示的子章節索引（'all' 或數字索引），用於單張卡片內的子項目切換
    currentSubSectionIndex: 'all'
};