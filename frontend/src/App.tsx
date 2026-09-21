import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNovel } from './hooks/useNovel';
import { useTemporalGraph } from './hooks/useTemporalGraph';
import { useProposals } from './hooks/useProposals';
import { ActivityRail, ActiveView } from './components/layout/ActivityRail';
import { ExplorerDrawer } from './components/layout/ExplorerDrawer';
import { WorkspaceHeader } from './components/layout/WorkspaceHeader';
import { BottomDock } from './components/layout/BottomDock';
import { MobileNav } from './components/layout/MobileNav';
import { EditorPane } from './components/editor/EditorPane';
import { DiffViewer } from './components/editor/DiffViewer';
import { ProposalInbox } from './components/editor/ProposalInbox';
import { WorldviewPane } from './components/editor/WorldviewPane';
import { StoryHubBoard, StoryHubSubTab } from './components/architecture';
import { CopilotDrawer } from './components/copilot/CopilotDrawer';
import { SettingsModal } from './components/settings/SettingsModal';
import { GlobalTooltip } from './components/ui/GlobalTooltip';
import { TermsModal } from './components/settings/TermsModal';
import {
  streamGenerationTask,
  startAutoPipeline,
  getAutoPipelineStatus,
  stopAutoPipeline,
} from './api/generation';
import { CreationStage, DraftProposal } from './types';
import { getChapterTitle } from './utils/chapters';
import { ToastContainer, showToast } from './components/common/Toast';
import { useExpansionSync } from './hooks/useExpansionSync';
import { emitChapterContentUpdated } from './utils/narrativeRefresh';
import {
  ThemeMode,
  getCachedPreferences,
  applyAllPreferences,
  savePreferences,
  syncPreferencesFromServer,
  subscribePreferences,
} from './services/preferences';


export const App: React.FC = () => {
  const expansionSync = useExpansionSync();
  const {
    novels,
    activeNovelId,
    setActiveNovelId,
    novelDetail,
    activeChapterIndex,
    editorContent,
    originalContent,
    setContent,
    isDirty,
    isSaving,
    isLoading: isNovelLoading,
    selectChapter,
    saveActiveChapter,
    createChapter,
    handleCreateNovel,
    handleDeleteNovel,
    handleResetNovelContent,
    handleUpdateNovel,
    refreshActiveNovel,
    refreshChatMemory,
    handleDeleteChatMessage,
    handleClearChatMemory,
    deleteTurningPoint,
    deleteForeshadowingSeed,
    deleteCharacter,
    deleteVolume,
    deleteChapterOutline,
    cleanEmptyTurningPoints,
    cleanEmptySeeds,
    cleanEmptyCharacters,
  } = useNovel();

  const {
    graphSlice,
    isLoading: isGraphLoading,
    isExtracting: isGraphExtracting,
    refreshGraph,
    addFact,
    invalidateFact,
    deleteFact,
    extractFromChapter,
  } = useTemporalGraph(activeNovelId, activeChapterIndex);

  const {
    proposals,
    selectedProposal,
    setSelectedProposal,
    applyProposal,
    rejectProposal,
    refreshProposals,
  } = useProposals(activeNovelId, activeChapterIndex);

  // Preferences (Theme & Editor Font Size) - Modular SSOT
  const [theme, setTheme] = useState<ThemeMode>(() => getCachedPreferences().theme);
  const [editorFontSize, setEditorFontSize] = useState<number>(() => getCachedPreferences().editor_font_size);

  useEffect(() => {
    // 1. 套用當前快取設定至 DOM
    applyAllPreferences({ theme, editor_font_size: editorFontSize });

    // 2. 背景從後端 SQLite 同步持久化設定
    syncPreferencesFromServer().then((synced) => {
      setTheme(synced.theme);
      setEditorFontSize(synced.editor_font_size);
    });

    // 3. 監聽跨組件變更通知
    const unsubscribe = subscribePreferences((latest) => {
      setTheme(latest.theme);
      setEditorFontSize(latest.editor_font_size);
    });
    return unsubscribe;
  }, []);

  const handleThemeChange = useCallback((newTheme: ThemeMode) => {
    setTheme(newTheme);
    savePreferences({ theme: newTheme });
  }, []);

  const handleFontSizeChange = useCallback((newSize: number) => {
    setEditorFontSize(newSize);
    savePreferences({ editor_font_size: newSize });
  }, []);

  // Layout and view state
  const [activeView, setActiveView] = useState<ActiveView>(() => {
    const saved = localStorage.getItem('writenovel_last_view');
    return (saved === 'editor' || saved === 'graph' || saved === 'inbox' || saved === 'worldview' || saved === 'diff' || saved === 'narrative' || saved === 'geometry' || saved === 'structure') ? (saved as ActiveView) : 'editor';
  });
  const [worldviewTab, setWorldviewTab] = useState<'worldview' | 'characters' | 'plot'>(() => {
    const saved = localStorage.getItem('writenovel_last_worldview_tab');
    return (saved === 'worldview' || saved === 'characters' || saved === 'plot') ? saved : 'worldview';
  });
  const [structureSubTab, setStructureSubTab] = useState<StoryHubSubTab>(() => {
    const saved = localStorage.getItem('writenovel_last_structure_tab');
    return (saved === 'geometry' || saved === 'graph' || saved === 'narrative') ? (saved as StoryHubSubTab) : 'geometry';
  });

  useEffect(() => {
    localStorage.setItem('writenovel_last_view', activeView);
  }, [activeView]);

  useEffect(() => {
    localStorage.setItem('writenovel_last_worldview_tab', worldviewTab);
  }, [worldviewTab]);

  useEffect(() => {
    localStorage.setItem('writenovel_last_structure_tab', structureSubTab);
  }, [structureSubTab]);

  const [isExplorerOpenMobile, setIsExplorerOpenMobile] = useState(false);
  const [isCopilotOpenMobile, setIsCopilotOpenMobile] = useState(false);
  // 桌面端兩側欄折疊狀態（進入架構/幾何拓撲中樞時預設雙收合，釋放 260px + 320px 畫布；
  // 切回編輯/世界觀時自動回歸展開）
  const isStructureFamily = (v: string) =>
    v === 'structure' || v === 'geometry' || v === 'graph' || v === 'narrative';
  const [isCopilotCollapsedDesktop, setIsCopilotCollapsedDesktop] = useState<boolean>(() => {
    return isStructureFamily(activeView);
  });
  const [isExplorerCollapsedDesktop, setIsExplorerCollapsedDesktop] = useState<boolean>(() => {
    return isStructureFamily(activeView);
  });
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isTermsOpen, setIsTermsOpen] = useState(false);

  // 視圖切換時自動收合/回歸：進拓撲雙收合放大中間，離開即回歸，避免導演室卡死收合態
  useEffect(() => {
    if (isStructureFamily(activeView)) {
      setIsCopilotCollapsedDesktop(true);
      setIsExplorerCollapsedDesktop(true);
    } else {
      setIsCopilotCollapsedDesktop(false);
      setIsExplorerCollapsedDesktop(false);
    }
  }, [activeView]);

  // Copilot and Generation state
  const [currentStage, setCurrentStage] = useState<CreationStage>('writer');
  const [isStreaming, setIsStreaming] = useState(false);
  const [isAutoRunning, setIsAutoRunning] = useState(false);
  const [thinkingText, setThinkingText] = useState('');
  const [streamingContent, setStreamingContent] = useState('');
  const [currentStatus, setCurrentStatus] = useState('');
  const [autoStatusText, setAutoStatusText] = useState('');
  const [isBottomDockOpen, setIsBottomDockOpen] = useState(false);

  // Synchronize stage selection with workspace view
  // suppressStageSyncRef：本次視圖切換來自右側階段按鈕，反向同步跳過一次，
  // 避免 effect 把剛選的 macro_semantic / character_semantic / cross_relation 蓋成 geometry。
  const suppressStageSyncRef = useRef(false);
  const handleSelectStage = useCallback((stage: CreationStage) => {
    suppressStageSyncRef.current = true;
    setCurrentStage(stage);
    if (stage === 'writer') {
      setActiveView('editor');
    } else if (stage === 'editor' || stage === 'evaluate') {
      setActiveView('diff');
    } else if (stage === 'worldview') {
      setActiveView('worldview');
      setWorldviewTab('worldview');
    } else if (stage === 'characters') {
      setActiveView('worldview');
      setWorldviewTab('characters');
    } else if (stage === 'volumes' || stage === 'volume_skeleton') {
      setActiveView('worldview');
      setWorldviewTab('plot');
    } else if (stage === 'geometry' || stage === 'macro_semantic' || stage === 'character_semantic' || stage === 'cross_relation') {
      setActiveView('structure');
      setStructureSubTab('geometry');
    }
  }, []);

  // Hierarchical view navigation handler supporting worldview & structure sub-tabs
  const handleSelectWorkspaceView = useCallback((view: ActiveView, subTab?: any) => {
    if (view === 'terms') {
      setIsTermsOpen(true);
      return;
    }
    if (view === 'geometry') {
      setActiveView('structure');
      setStructureSubTab('geometry');
      return;
    }
    if (view === 'graph') {
      setActiveView('structure');
      setStructureSubTab('graph');
      return;
    }
    if (view === 'narrative') {
      setActiveView('structure');
      setStructureSubTab('narrative');
      return;
    }
    if (view === 'structure') {
      setActiveView('structure');
      if (subTab === 'geometry' || subTab === 'graph' || subTab === 'narrative') {
        setStructureSubTab(subTab);
      }
      return;
    }
    setActiveView(view);
    if (subTab) {
      setWorldviewTab(subTab);
    }
  }, []);

  // Bi-directional synchronization: sync workspace view & sub-tabs back to currentStage.
  // 反向跟隨：直接點中樞三頁籤（幾何 / 圖譜 / 推理）時，右側流水線高亮同步；
  // 時序圖譜與推理引擎無對應流水線階段，保留目前階段不動。
  useEffect(() => {
    if (suppressStageSyncRef.current) {
      suppressStageSyncRef.current = false;
      return;
    }
    if (activeView === 'editor') {
      setCurrentStage('writer');
    } else if (activeView === 'diff' || activeView === 'proposals') {
      setCurrentStage('editor');
    } else if (activeView === 'worldview') {
      if (worldviewTab === 'worldview') {
        setCurrentStage('worldview');
      } else if (worldviewTab === 'characters') {
        setCurrentStage('characters');
      } else if (worldviewTab === 'plot') {
        setCurrentStage('volumes');
      }
    } else if (
      activeView === 'structure' ||
      activeView === 'geometry' ||
      activeView === 'graph' ||
      activeView === 'narrative'
    ) {
      const sub =
        activeView === 'graph'
          ? 'graph'
          : activeView === 'narrative'
            ? 'narrative'
            : activeView === 'geometry'
              ? 'geometry'
              : structureSubTab;
      if (sub === 'geometry') {
        setCurrentStage('geometry');
      }
    }
  }, [activeView, worldviewTab, structureSubTab]);

  const [worldviewTarget, setWorldviewTarget] = useState<{
    type: 'character' | 'volume';
    id: string | number;
  } | null>(null);

  const [worldviewActionTrigger, setWorldviewActionTrigger] = useState<{
    type: 'section' | 'character' | 'volume' | 'tp' | 'seed' | 'chapter_outline';
    id?: string | number;
    action?: 'add' | 'edit' | 'delete' | 'clean' | 'scroll';
    volIndex?: number;
    chIndex?: number;
    timestamp: number;
  } | null>(null);

  const handleWorldviewAction = useCallback(
    (action: {
      type: 'section' | 'character' | 'volume' | 'tp' | 'seed' | 'chapter_outline';
      id?: string | number;
      action?: 'add' | 'edit' | 'delete' | 'clean' | 'scroll';
      volIndex?: number;
      chIndex?: number;
    }) => {
      setActiveView('worldview');
      if (action.type === 'section' || action.type === 'tp' || action.type === 'seed') {
        setWorldviewTab('worldview');
      } else if (action.type === 'character') {
        setWorldviewTab('characters');
      } else if (action.type === 'volume' || action.type === 'chapter_outline') {
        setWorldviewTab('plot');
      }
      setWorldviewActionTrigger({ ...action, timestamp: Date.now() });
    },
    []
  );

  const handleSelectCharacter = useCallback((charName: string) => {
    setActiveView('worldview');
    setWorldviewTab('characters');
    setWorldviewTarget({ type: 'character', id: charName });
  }, []);

  const handleSelectVolume = useCallback((volIndex: number) => {
    setActiveView('worldview');
    setWorldviewTab('plot');
    setWorldviewTarget({ type: 'volume', id: volIndex });
  }, []);

  const currentVolumeIndex = React.useMemo(() => {
    if (worldviewTarget?.type === 'volume') return Number(worldviewTarget.id);
    const vols = novelDetail?.volumes || [];
    for (const v of vols) {
      const outline = Array.isArray(v.chapters_outline) ? v.chapters_outline : [];
      if (outline.some((c: any) => c.chapter_index === activeChapterIndex)) {
        return Number(v.volume_index);
      }
    }
    return 1;
  }, [worldviewTarget, novelDetail, activeChapterIndex]);

  const activeNovel = novelDetail?.novel || novels.find((n) => n.id === activeNovelId) || null;
  const activeChapterTitle = React.useMemo(
    () => getChapterTitle(novelDetail, activeChapterIndex),
    [novelDetail, activeChapterIndex],
  );
  const autoPollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // 每本小說各自追蹤已同步的後端日誌序號（seq 單調遞增，不受後端 logs[-100:] 截斷影響）
  const lastSeenLogSeqRef = useRef<Record<string, number>>({});
  const prevAutoStageRef = useRef<string | null>(null);
  const hasMountedReconnectRef = useRef<boolean>(false);

  // 日誌按小說隔離：key 為 novelId；無活躍小說時的全域訊息歸入 '_global'
  const [logsByNovel, setLogsByNovel] = useState<Record<string, string[]>>({});
  const activeNovelIdRef = useRef<string | null>(activeNovelId);
  useEffect(() => {
    activeNovelIdRef.current = activeNovelId;
  }, [activeNovelId]);

  const pushLogTo = useCallback((novelKey: string, message: string) => {
    const timestamp = new Date().toLocaleTimeString();
    setLogsByNovel((prev) => ({
      ...prev,
      [novelKey]: [...(prev[novelKey] || []), `[${timestamp}] ${message}`].slice(-400),
    }));
  }, []);

  const addLog = useCallback((message: string) => {
    pushLogTo(activeNovelIdRef.current || '_global', message);
  }, [pushLogTo]);

  // 以後端單調遞增 seq 做增量同步（舊後端無 seq 時退回以筆數比對），
  // 回傳本次新同步的 entries 供呼叫端判斷階段是否完成
  const ingestPipelineLogs = useCallback((novelId: string, entries: any[] | undefined | null, prefix: string): any[] => {
    if (!novelId || !Array.isArray(entries) || entries.length === 0) return [];
    const lastSeen = lastSeenLogSeqRef.current[novelId] || 0;
    const seqOf = (e: any) => (typeof e?.seq === 'number' ? e.seq : 0);
    let fresh: any[];
    let newSeen: number;
    if (entries.every((e: any) => typeof e?.seq !== 'number')) {
      // 舊後端相容：logs 只追加時以筆數做增量
      if (entries.length <= lastSeen) return [];
      fresh = entries.slice(lastSeen);
      newSeen = entries.length;
    } else {
      fresh = entries.filter((e: any) => seqOf(e) > lastSeen);
      if (fresh.length === 0) return [];
      newSeen = Math.max(lastSeen, ...entries.map(seqOf));
    }
    lastSeenLogSeqRef.current[novelId] = newSeen;
    const lines = fresh.map((e: any) => `[${e.time || new Date().toLocaleTimeString()}] ${prefix}${e.msg}`);
    setLogsByNovel((prev) => ({
      ...prev,
      [novelId]: [...(prev[novelId] || []), ...lines].slice(-400),
    }));
    return fresh;
  }, []);

  // 當前小說專屬日誌（與其他作品完全隔離）
  const activeLogs = logsByNovel[activeNovelId || '_global'] || [];

  // 切換作品時：重置階段追蹤與殘留的自主進度文字，避免跨小說污染顯示
  const isFirstNovelSyncRef = useRef(true);
  useEffect(() => {
    prevAutoStageRef.current = null;
    if (isFirstNovelSyncRef.current) {
      isFirstNovelSyncRef.current = false;
      return;
    }
    setAutoStatusText('');
  }, [activeNovelId]);

  // Reconnect on mount if autonomous writing is actively running in background (one-time check)
  useEffect(() => {
    if (hasMountedReconnectRef.current) return;
    hasMountedReconnectRef.current = true;

    getAutoPipelineStatus(undefined)
      .then((status) => {
        const running = Boolean(status.is_running ?? status.running);
        const activeTasks = Array.isArray(status.active_tasks) ? status.active_tasks : [];
        if (running || activeTasks.length > 0) {
          setIsBottomDockOpen(true);
          const activeTask = running ? status : activeTasks[0];
          const taskNovelId = activeTask.novel_id ? String(activeTask.novel_id) : null;
          // 僅在前端初次進入且尚未選擇任何作品時，才自動切換至運行中的那本
          if (taskNovelId && !activeNovelId) {
            setActiveNovelId(taskNovelId);
            setIsAutoRunning(true);
          } else if (taskNovelId && taskNovelId === activeNovelId) {
            setIsAutoRunning(true);
          }
          if (activeTask.status_message || activeTask.current_stage) {
            setAutoStatusText(
              `作品: ${activeTask.novel_title || '進行中'}\n當前章節: 第 ${activeTask.current_chapter || 0} 章\n階段: ${activeTask.status_message || activeTask.current_stage}\n進度: ${activeTask.progress_percent || 0}%`
            );
          }
          // 回放後端已累積的歷史日誌（不再丟失），並以 seq 記錄同步游標
          if (taskNovelId) {
            ingestPipelineLogs(taskNovelId, activeTask.logs, '[自主寫作] ');
            pushLogTo(taskNovelId, `已連線至背景自主寫作流水線 (${activeTask.novel_title || '小說'} / ${activeTask.status_message || activeTask.current_stage})`);
          }
        }
      })
      .catch((err) => console.warn('檢查背景自主流水線狀態失敗:', err));
  }, []); // 僅在 mount 時執行一次，絕不可將 activeNovelId 放入依賴項

  // Continuous background monitoring: polls current novel & active background tasks without hijacking active view
  useEffect(() => {
    const pollFn = async () => {
      try {
        const status = await getAutoPipelineStatus(activeNovelId || undefined);
        const rawRunning = Boolean(status.is_running ?? status.running);
        const statusNovelId = status.novel_id ? String(status.novel_id) : null;
        const activeTasks = Array.isArray(status.active_tasks) ? status.active_tasks : [];
        // 僅當回傳任務確實屬於當前活躍小說時才視為「當前運行中」，
        // 避免未選小說時把背景任務誤判為當前任務
        const isCurrentRunning = rawRunning && !!activeNovelId && statusNovelId === String(activeNovelId);

        // 更新當前檢視小說的運行狀態 (決定啟動/中止按鈕)
        setIsAutoRunning(isCurrentRunning);

        if (isCurrentRunning) {
          // 當前小說正在背景運行
          if (status.status_message || status.current_stage) {
            setAutoStatusText(
              `當前章節: 第 ${status.current_chapter || 0} 章\n階段: ${status.status_message || status.current_stage}\n進度: ${status.progress_percent || 0}%`
            );
          }

          let stageCompleted = false;
          const freshEntries = ingestPipelineLogs(String(activeNovelId), status.logs, '[自主寫作] ');
          freshEntries.forEach((entry: any) => {
            if (
              entry.msg.includes('✅') ||
              entry.msg.includes('完成') ||
              entry.msg.includes('就緒') ||
              entry.msg.includes('持久化')
            ) {
              stageCompleted = true;
            }
          });

          const currStage = status.current_stage || null;
          if (currStage && currStage !== prevAutoStageRef.current) {
            if (prevAutoStageRef.current !== null) {
              stageCompleted = true;
            }
            prevAutoStageRef.current = currStage;
          }

          if (stageCompleted) {
            refreshActiveNovel();
            refreshGraph();
            refreshChatMemory();
            // 每章內容生成後 Story Engine 2.0 自己刷新，和前端正文同步更新顯示
            if (activeNovelId) {
              emitChapterContentUpdated(
                activeNovelId,
                'auto-pipeline',
                status.current_chapter || activeChapterIndex,
              );
            }
          }
        } else if (activeTasks.length > 0) {
          // 當前小說未在運行，但背景有其他小說正在自主寫作中
          const bgTask = activeTasks[0];
          setAutoStatusText(
            `【背景創作進行中】作品：《${bgTask.novel_title}》\n當前進度: 第 ${bgTask.current_chapter || 0}/${bgTask.total_chapters || 0} 章 (${bgTask.progress_percent || 0}%)\n當前階段: ${bgTask.status_message || bgTask.current_stage}\n\n(提示：您目前正在瀏覽其他小說，背景任務持續穩定運行中)`
          );

          // 仍可同步背景任務的新日誌至 dock（以該背景小說自己的 seq 游標增量）
          if (bgTask.novel_id) {
            ingestPipelineLogs(String(bgTask.novel_id), bgTask.logs, `[雲端·${bgTask.novel_title}] `);
          }
        } else {
          // 當前小說與背景皆無運行中任務：清空殘留的自主進度文字，
          // 避免任務完成/中止/切換作品後仍顯示上一本的章節與進度
          setAutoStatusText('');
        }

        // 當前小說剛結束運行的提示與重新整理
        if (!isCurrentRunning && prevAutoStageRef.current && prevAutoStageRef.current !== 'idle') {
          if (status.error || status.current_stage === 'error') {
            addLog(`[任務中斷] 自主寫作異常中斷: ${status.error || status.status_message || '未知錯誤'}`);
            showToast(`自主寫作異常中斷: ${status.error || status.status_message || '未知錯誤'}`, 'danger');
          } else if (status.current_stage === 'completed' || status.progress_percent === 100) {
            addLog(`[任務完成] 自主寫作任務已圓滿結束 (${status.status_message || '全數完成'})`);
            showToast('自主寫作任務已全數完成！', 'success');
          } else if (status.stop_requested) {
            addLog(`[任務中止] 自主寫作已由使用者中止 (${status.status_message || '已停止'})`);
            showToast('自主寫作已停止', 'info');
          }
          prevAutoStageRef.current = 'idle';
          refreshActiveNovel();
          refreshGraph();
          refreshProposals();
          refreshChatMemory();
          // 自主寫作結束（完成/中止/異常）也同步刷新敘事推理引擎
          if (activeNovelId) {
            emitChapterContentUpdated(activeNovelId, 'auto-pipeline', activeChapterIndex);
          }
        }
      } catch (err) {
        // 忽略偶發網路抖動
      }
    };

    autoPollTimerRef.current = setInterval(pollFn, 3000);
    return () => {
      if (autoPollTimerRef.current) {
        clearInterval(autoPollTimerRef.current);
      }
    };
  }, [activeNovelId, addLog, ingestPipelineLogs, refreshActiveNovel, refreshGraph, refreshProposals, refreshChatMemory]);

  // Handle stage execution
  const handleTriggerStage = async (stage: CreationStage, prompt: string) => {
    if (!activeNovelId) {
      addLog('請先選擇或建立一部作品');
      return;
    }

    setIsBottomDockOpen(true);
    setIsStreaming(true);
    setThinkingText('');
    setStreamingContent('');
    setCurrentStatus(`正在啟動【${stage}】階段...`);
    // 手動單階段與自主任務狀態分離：清掉殘留的自主進度，避免「自主進度」頁籤顯示舊狀態
    setAutoStatusText('');
    addLog(`開始執行【${stage}】階段生成...`);

    let accumulatedContent = '';

    try {
      const trimmedPrompt = prompt.trim();
      await streamGenerationTask(
        {
          novel_id: activeNovelId,
          stage,
          task_type: stage === 'writer' ? 'generate' : stage === 'editor' ? 'refine' : 'generate',
          target: {
            chapter_index: activeChapterIndex,
            volume_index: currentVolumeIndex,
            ...(worldviewTarget?.type === 'character' ? { character_name: String(worldviewTarget.id) } : {}),
          },
          prompt: trimmedPrompt || undefined,
          user_prompt: trimmedPrompt || undefined,
          instruction: trimmedPrompt || undefined,
          frontend_state: {
            activeView,
            worldviewTab,
            worldviewTarget,
          },
          options: { stream: true },
        },
        {
          onThinking: (delta) => {
            if (delta === null) {
              setThinkingText('');
            } else {
              setThinkingText((prev) => prev + delta);
            }
          },
          onContent: (delta) => {
            if (delta === null) {
              setStreamingContent('');
              accumulatedContent = '';
            } else {
              setStreamingContent((prev) => prev + delta);
              accumulatedContent += delta;
            }
          },
          onStatus: (msg) => {
            setCurrentStatus(msg);
            addLog(msg);
          },
          onError: (err) => {
            addLog(`生成錯誤: ${err}`);
            setCurrentStatus(`錯誤: ${err}`);
          },
          onDone: async () => {
            addLog(`【${stage}】階段生成完畢！`);
            setCurrentStatus('生成完成');

            // If writer stage generated content, update editor
            if (stage === 'writer' && accumulatedContent.trim()) {
              setContent(accumulatedContent);
            }

            // Refresh novel, graph and proposals
            await refreshActiveNovel();
            await refreshGraph();
            await refreshProposals();
            await refreshChatMemory();

            // Story Engine 2.0 和正文同步更新：章節生成完成即通知敘事推理引擎刷新
            if (activeNovelId) {
              emitChapterContentUpdated(
                activeNovelId,
                stage === 'writer' ? 'writer-done' : 'editor-done',
                activeChapterIndex,
              );
            }

            // When editor completes, auto-switch to diff view so user can review changes immediately
            if (stage === 'editor' || stage === 'evaluate') {
              setActiveView('diff');
            }
          },
        }
      );
    } catch (err: any) {
      addLog(`請求失敗: ${err.message}`);
      setCurrentStatus(`失敗: ${err.message}`);
    } finally {
      setIsStreaming(false);
    }
  };

  // Toggle Auto Pipeline
  const handleToggleAuto = async () => {
    if (!activeNovelId) {
      addLog('請先選擇一部作品');
      showToast('請先選擇一部作品', 'warning');
      return;
    }

    if (isAutoRunning) {
      try {
        addLog(`[發送請求] 正在向伺服器發送中止《${activeNovel?.title || ''}》自主寫作請求...`);
        const stopRes = await stopAutoPipeline(activeNovelId);
        setIsAutoRunning(false);
        addLog(`[已發送中止] ${stopRes.message || '已發送停止自主寫作請求'}`);
        showToast(stopRes.message || '已發送中止請求', 'info');
      } catch (err: any) {
        addLog(`[停止失敗] ${err.message}`);
        showToast(`停止失敗: ${err.message}`, 'danger');
      }
    } else {
      try {
        setIsBottomDockOpen(true);
        addLog(`[發送請求] 正在向伺服器發送啟動《${activeNovel?.title || ''}》自主寫作任務...`);
        const res = await startAutoPipeline(activeNovelId, activeNovel?.pipeline_prompt || '', 5);
        if (res.status === 'success' || res.status === 'started' || res.status === 'already_running' || res.success) {
          setIsAutoRunning(true);
          addLog(`[啟動成功] ${res.message || '自主寫作管線已成功在背景啟動！'}`);
          showToast(res.message || '自主寫作任務已在背景啟動！', 'success');
          // 全新啟動（非 already_running）：重置該小說的 seq 游標，從頭同步新任務日誌
          if (res.status === 'started' || res.status === 'success') {
            lastSeenLogSeqRef.current[String(activeNovelId)] = 0;
          }
          // 立即主動查詢一次最新狀態，確保畫面即刻同步
          try {
            const status = await getAutoPipelineStatus(activeNovelId);
            const running = Boolean(status.is_running ?? status.running);
            setIsAutoRunning(running);
            if (status.status_message || status.current_stage) {
              setAutoStatusText(
                `當前章節: 第 ${status.current_chapter || 0} 章\n階段: ${status.status_message || status.current_stage}\n進度: ${status.progress_percent || 0}%`
              );
            }
            // 以 seq 增量同步（already_running 時不會重複灌入既有日誌）
            ingestPipelineLogs(String(activeNovelId), status.logs, '[自主寫作] ');
          } catch {}
        } else {
          addLog(`[啟動失敗] ${res.message || '伺服器拒絕啟動'}`);
          showToast(`啟動失敗: ${res.message || '伺服器拒絕啟動'}`, 'danger');
        }
      } catch (err: any) {
        addLog(`[啟動失敗] ${err.message}`);
        showToast(`啟動失敗: ${err.message}`, 'danger');
      }
    }
  };

  // Select proposal for diff review
  const handleSelectProposalForDiff = (prop: DraftProposal) => {
    setSelectedProposal(prop);
    setActiveView('diff');
  };

  // Apply proposal and switch back to editor
  const handleApplyProposal = async (propId: string) => {
    const success = await applyProposal(propId);
    if (success) {
      addLog(`草稿修訂案 (${propId}) 已套用至第 ${activeChapterIndex} 章`);
      await refreshActiveNovel();
      if (activeNovelId) {
        emitChapterContentUpdated(activeNovelId, 'proposal-applied', activeChapterIndex);
      }
      setActiveView('editor');
    }
  };

  // Reject proposal
  const handleRejectProposal = async (propId: string) => {
    const success = await rejectProposal(propId);
    if (success) {
      addLog(`草稿修訂案 (${propId}) 已標記為放棄`);
    }
  };

  // Reset novel generated content (selective scopes)
  const handleResetNovel = async (id: string, scopes?: string[]) => {
    try {
      await handleResetNovelContent(id, scopes);
      // 清空後各看板 SSOT 同步刷新：graphSlice / proposals / chat / 幾何快取皆為獨立 state，
      // 不會隨 novelDetail 自動更新；若不主動刷新，時序圖譜與幾何樹會殘留舊顯示（本次回報 bug）。
      try {
        await refreshGraph();
      } catch { /* 忽略偶發刷新失敗，底層看板仍可手動重整 */ }
      try {
        await refreshProposals();
      } catch { /* 同上 */ }
      try {
        await refreshChatMemory();
      } catch { /* 同上 */ }
      // 章節游標歸 1（此時 isDirty 已被 refreshActiveNovel 清掉，不會誤存已刪章節），
      // 並廣播 reset-content 事件：敘事引擎經事件自動刷新，幾何經事件自動重載樹。
      try {
        if (activeChapterIndex !== 1) {
          selectChapter(1);
        }
      } catch { /* 忽略 */ }
      emitChapterContentUpdated(id, 'reset-content', 1);
      const count = scopes?.length ?? 0;
      showToast(count > 0 ? `已清空所選 ${count} 項生成內容！` : '小說生成內容已成功清空，回到初始設定狀態！', 'success');
      addLog(`[清空生成] 小說生成內容已清空${count > 0 ? `（${count} 項）` : ''}並重置回初始狀態`);
    } catch (err: any) {
      showToast(`清空內容失敗: ${err.message || '未知錯誤'}`, 'danger');
      addLog(`[清空失敗] ${err.message || '未知錯誤'}`);
    }
  };

  return (
    <div
      className={`app-container${isExplorerCollapsedDesktop ? ' explorer-collapsed' : ''}${isCopilotCollapsedDesktop ? ' copilot-collapsed' : ''}`}
    >
      {/* 1. Activity Rail (48px) */}
      <ActivityRail
        activeView={activeView}
        onSelectView={(v) => {
          if (v === 'terms') {
            setIsTermsOpen(true);
          } else {
            setActiveView(v);
          }
        }}
        onOpenSettings={() => setIsSettingsOpen(true)}
      />

      {/* 2. Explorer Drawer (260px / Mobile Drawer) */}
      <ExplorerDrawer
        novels={novels}
        activeNovelId={activeNovelId}
        chapters={novelDetail?.chapters || []}
        activeChapterIndex={activeChapterIndex}
        activeView={activeView}
        worldviewTab={worldviewTab}
        characters={novelDetail?.characters}
        charactersRaw={novelDetail?.characters_raw}
        worldbuilding={novelDetail?.worldbuilding || ''}
        volumes={novelDetail?.volumes || []}
        plot={novelDetail?.plot}
        expansionSync={expansionSync}
        isLoadingNovel={isNovelLoading}
        onSelectWorldviewTab={(tab) => {
          setActiveView('worldview');
          setWorldviewTab(tab);
        }}
        onSelectCharacter={handleSelectCharacter}
        onSelectVolume={handleSelectVolume}
        onWorldviewAction={handleWorldviewAction}
        isOpenMobile={isExplorerOpenMobile}
        onCloseMobile={() => setIsExplorerOpenMobile(false)}
        isCollapsedDesktop={isExplorerCollapsedDesktop}
        onToggleCollapseDesktop={() => setIsExplorerCollapsedDesktop((v) => !v)}
        onSelectNovel={(id) => {
          setActiveNovelId(id);
          setIsExplorerOpenMobile(false);
        }}
        onSelectChapter={(idx) => {
          selectChapter(idx);
          setIsExplorerOpenMobile(false);
          // Preserve 'structure' / 'graph' tab if user is currently inspecting architecture
          if (
            activeView !== 'structure' &&
            activeView !== 'graph' &&
            activeView !== 'geometry' &&
            activeView !== 'narrative'
          ) {
            setActiveView('editor');
          }
        }}
        onCreateNovel={handleCreateNovel}
        onDeleteNovel={handleDeleteNovel}
        onResetNovelContent={handleResetNovel}
        onCreateChapter={createChapter}
      />

      {/* 3. Center Workspace */}
      <main
        className="workspace-center"
        style={{ '--editor-font-size': `${editorFontSize}px` } as React.CSSProperties}
      >
        <WorkspaceHeader
          activeNovel={activeNovel}
          activeChapterIndex={activeChapterIndex}
          activeChapterTitle={activeChapterTitle}
          isDirty={isDirty}
          isSaving={isSaving}
          isLoading={isNovelLoading}
          activeView={activeView}
          worldviewTab={worldviewTab}
          structureSubTab={structureSubTab}
          onSave={saveActiveChapter}
          onToggleExplorerMobile={() => setIsExplorerOpenMobile(!isExplorerOpenMobile)}
          onToggleCopilotMobile={() => setIsCopilotOpenMobile(!isCopilotOpenMobile)}
          onSelectView={handleSelectWorkspaceView}
        />

        <div
          className="workspace-body"
          style={{ '--editor-font-size': `${editorFontSize}px`, fontSize: `${editorFontSize}px` } as React.CSSProperties}
        >
          {activeView === 'editor' && (
            <EditorPane
              content={editorContent}
              chapterIndex={activeChapterIndex}
              chapterTitle={activeChapterTitle}
              isDirty={isDirty}
              isSaving={isSaving}
              isLoading={isNovelLoading}
              fontSize={editorFontSize}
              onFontSizeChange={handleFontSizeChange}
              onChangeContent={setContent}
              onSave={saveActiveChapter}
            />
          )}

          {activeView === 'diff' && (
            <DiffViewer
              originalText={selectedProposal?.original_text || (isDirty ? originalContent : editorContent)}
              proposedText={selectedProposal?.proposed_text || editorContent}
              proposalId={selectedProposal?.id}
              onApply={
                selectedProposal?.status === 'pending'
                  ? () => handleApplyProposal(selectedProposal.id)
                  : undefined
              }
              onReject={
                selectedProposal?.status === 'pending'
                  ? () => handleRejectProposal(selectedProposal.id)
                  : undefined
              }
              onBackToEditor={() => setActiveView('editor')}
            />
          )}

          {(activeView === 'structure' ||
            activeView === 'geometry' ||
            activeView === 'graph' ||
            activeView === 'narrative') && (
            <StoryHubBoard
              novel={activeNovel}
              novelId={activeNovelId || ''}
              activeChapterIndex={activeChapterIndex}
              chapterContent={editorContent}
              activeSubTab={structureSubTab}
              onSelectSubTab={setStructureSubTab}
              onNavigateToChapter={(ch) => {
                selectChapter(ch);
                setActiveView('editor');
              }}
              onLog={addLog}
              graphSlice={graphSlice}
              isGraphLoading={isGraphLoading}
              isGraphExtracting={isGraphExtracting}
              onRefreshGraph={refreshGraph}
              onAddFact={addFact}
              onInvalidateFact={invalidateFact}
              onDeleteFact={deleteFact}
              onExtractFromChapter={extractFromChapter}
            />
          )}

          {activeView === 'worldview' && (
            <WorldviewPane
              novel={activeNovel}
              worldbuilding={novelDetail?.worldbuilding || ''}
              charactersRaw={novelDetail?.characters_raw || ''}
              plotRaw={novelDetail?.plot_raw || ''}
              volumes={novelDetail?.volumes || []}
              activeTabProp={worldviewTab}
              targetElement={worldviewTarget}
              actionTrigger={worldviewActionTrigger}
              fontSize={editorFontSize}
              expansionSync={expansionSync}
              onFontSizeChange={handleFontSizeChange}
              onTabChange={setWorldviewTab}
              onRefresh={refreshActiveNovel}
              onLog={addLog}
              onUpdateNovel={handleUpdateNovel}
              onDeleteTurningPoint={deleteTurningPoint}
              onDeleteForeshadowingSeed={deleteForeshadowingSeed}
              onDeleteCharacter={deleteCharacter}
              onDeleteVolume={deleteVolume}
              onDeleteChapterOutline={deleteChapterOutline}
              onCleanEmptyTurningPoints={cleanEmptyTurningPoints}
              onCleanEmptySeeds={cleanEmptySeeds}
              onCleanEmptyCharacters={cleanEmptyCharacters}
            />
          )}

          {activeView === 'proposals' && (
            <ProposalInbox
              proposals={proposals}
              selectedProposalId={selectedProposal?.id}
              onSelectProposal={handleSelectProposalForDiff}
              onApplyProposal={handleApplyProposal}
              onRejectProposal={handleRejectProposal}
            />
          )}
        </div>
      </main>

      {/* 4. Copilot Drawer (320px / Desktop Collapsible / Mobile Drawer) */}
      <CopilotDrawer
        isOpenMobile={isCopilotOpenMobile}
        isCollapsedDesktop={isCopilotCollapsedDesktop}
        onToggleCollapseDesktop={() => setIsCopilotCollapsedDesktop((prev) => !prev)}
        isStreaming={isStreaming}
        isAutoRunning={isAutoRunning}
        thinkingText={thinkingText}
        streamingContent={streamingContent}
        currentStatus={currentStatus}
        currentStage={currentStage}
        chatMemory={novelDetail?.chat_memory || []}
        activeNovelId={activeNovelId}
        activeChapterIndex={activeChapterIndex}
        activeVolumeIndex={currentVolumeIndex}
        activeView={activeView}
        onSelectStage={handleSelectStage}
        onCloseMobile={() => setIsCopilotOpenMobile(false)}
        onTriggerStage={handleTriggerStage}
        onToggleAuto={handleToggleAuto}
        onClearStreaming={() => setStreamingContent('')}
        onRefreshChatMemory={refreshChatMemory}
        onDeleteChatMessage={handleDeleteChatMessage}
        onClearChatMemory={handleClearChatMemory}
      />

      {/* 5. Collapsible Bottom Dock */}
      <BottomDock
        logs={activeLogs}
        autoStatusText={autoStatusText}
        onClearLogs={() =>
          setLogsByNovel((prev) => ({ ...prev, [activeNovelId || '_global']: [] }))
        }
        isOpen={isBottomDockOpen}
        onToggleOpen={() => setIsBottomDockOpen(!isBottomDockOpen)}
      />

      {/* 6. Mobile 3-Button Navigation Bar */}
      <MobileNav
        isExplorerOpen={isExplorerOpenMobile}
        isCopilotOpen={isCopilotOpenMobile}
        onToggleExplorer={() => {
          setIsExplorerOpenMobile(!isExplorerOpenMobile);
          setIsCopilotOpenMobile(false);
        }}
        onToggleCopilot={() => {
          setIsCopilotOpenMobile(!isCopilotOpenMobile);
          setIsExplorerOpenMobile(false);
        }}
        onFocusEditor={() => {
          setIsExplorerOpenMobile(false);
          setIsCopilotOpenMobile(false);
          setActiveView('editor');
        }}
      />

      {/* Mobile Drawer Backdrop */}
      {(isExplorerOpenMobile || isCopilotOpenMobile) && (
        <div
          className="mobile-drawer-backdrop"
          onClick={() => {
            setIsExplorerOpenMobile(false);
            setIsCopilotOpenMobile(false);
          }}
        />
      )}

      {/* Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        theme={theme}
        onThemeChange={handleThemeChange}
        editorFontSize={editorFontSize}
        onFontSizeChange={handleFontSizeChange}
      />

      {/* Story Terms Modal */}
      <TermsModal
        isOpen={isTermsOpen}
        onClose={() => setIsTermsOpen(false)}
        novelId={activeNovelId}
      />

      {/* Toast Notification Container */}
      <ToastContainer />

      {/* Global Tooltip（portal 到 body，不受 overflow / 堆疊上下文遮擋） */}
      <GlobalTooltip />
    </div>
  );
};
