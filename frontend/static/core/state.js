export const state = {
    novels: [],
    currentNovelId: localStorage.getItem('currentNovelId') || null,
    currentNovelData: null,
    activeTab: localStorage.getItem('activeTab') || 'worldview', // worldview, characters, plot, writer
    activeChapterIndex: 1,
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
    
    // Director pipeline stage control
    pipelineStages: ['worldview', 'characters', 'foreshadowing', 'volumes', 'volume_skeleton', 'writer', 'editor'],
    currentPipelineStageIndex: 0,
    
    // Director execution mode: 一鍵執行模式 vs 一般模式
    // 一鍵執行模式：總監的建議即為執行令（自動執行）
    // 一般模式：總監提供建議，由用戶決定
    isAutoExecuteMode: localStorage.getItem('isAutoExecuteMode') !== 'false',
    showStreamLog: localStorage.getItem('showStreamLog') !== 'false',
    
    directorLoopCount: 0,
    directorSubAgentStatus: {},     // { agentName: "running" | "done" | "error" }
    pipelineStartTime: null,        // 管線啟動時間戳
    heartbeatTimer: null,           // keep-alive 定時器
    maxPipelineTimeout: 600000,     // 10 分鐘 (ms)
    receiveFinishCommand: false     // 前端是否收到 finish 指令
};
