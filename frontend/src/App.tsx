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
import { TemporalGraphBoard } from './components/graph/TemporalGraphBoard';
import { WorldviewPane } from './components/editor/WorldviewPane';
import { CopilotDrawer } from './components/copilot/CopilotDrawer';
import { SettingsModal } from './components/settings/SettingsModal';
import { TermsModal } from './components/settings/TermsModal';
import {
  streamGenerationTask,
  startAutoPipeline,
  getAutoPipelineStatus,
  stopAutoPipeline,
} from './api/generation';
import { CreationStage, DraftProposal } from './types';
import { ToastContainer, showToast } from './components/common/Toast';
import { useExpansionSync } from './hooks/useExpansionSync';

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

  // Theme state
  const [theme, setTheme] = useState<'light' | 'neutral' | 'dark'>(() => {
    const saved = localStorage.getItem('ai_novel_theme');
    return (saved === 'dark' || saved === 'neutral' || saved === 'light') ? saved : 'dark';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('ai_novel_theme', theme);
  }, [theme]);

  // Middle Editor Font Size state & instant reactive synchronization
  const [editorFontSize, setEditorFontSize] = useState<number>(() => {
    const saved = localStorage.getItem('editor_font_size');
    return saved ? parseInt(saved, 10) || 16 : 16;
  });

  const handleFontSizeChange = useCallback((size: number) => {
    setEditorFontSize(size);
    document.documentElement.style.setProperty('--editor-font-size', `${size}px`);
    localStorage.setItem('editor_font_size', String(size));
  }, []);

  useEffect(() => {
    document.documentElement.style.setProperty('--editor-font-size', `${editorFontSize}px`);
  }, [editorFontSize]);

  // Layout and view state
  const [activeView, setActiveView] = useState<ActiveView>(() => {
    const saved = localStorage.getItem('writenovel_last_view');
    return (saved === 'editor' || saved === 'graph' || saved === 'inbox' || saved === 'worldview' || saved === 'diff') ? (saved as ActiveView) : 'editor';
  });
  const [worldviewTab, setWorldviewTab] = useState<'worldview' | 'characters' | 'plot'>(() => {
    const saved = localStorage.getItem('writenovel_last_worldview_tab');
    return (saved === 'worldview' || saved === 'characters' || saved === 'plot') ? saved : 'worldview';
  });

  useEffect(() => {
    localStorage.setItem('writenovel_last_view', activeView);
  }, [activeView]);

  useEffect(() => {
    localStorage.setItem('writenovel_last_worldview_tab', worldviewTab);
  }, [worldviewTab]);
  const [isExplorerOpenMobile, setIsExplorerOpenMobile] = useState(false);
  const [isCopilotOpenMobile, setIsCopilotOpenMobile] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isTermsOpen, setIsTermsOpen] = useState(false);

  // Copilot and Generation state
  const [currentStage, setCurrentStage] = useState<CreationStage>('writer');
  const [isStreaming, setIsStreaming] = useState(false);
  const [isAutoRunning, setIsAutoRunning] = useState(false);
  const [thinkingText, setThinkingText] = useState('');
  const [streamingContent, setStreamingContent] = useState('');
  const [currentStatus, setCurrentStatus] = useState('');
  const [logs, setLogs] = useState<string[]>([]);
  const [autoStatusText, setAutoStatusText] = useState('');
  const [isBottomDockOpen, setIsBottomDockOpen] = useState(false);

  // Synchronize stage selection with workspace view
  const handleSelectStage = useCallback((stage: CreationStage) => {
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
    }
  }, []);

  // Bi-directional synchronization: sync workspace view & worldviewTab back to currentStage
  useEffect(() => {
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
    }
  }, [activeView, worldviewTab]);

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
  const autoPollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastSeenLogCountRef = useRef<number>(0);
  const prevAutoStageRef = useRef<string | null>(null);
  const hasMountedReconnectRef = useRef<boolean>(false);

  const addLog = useCallback((message: string) => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs((prev) => [...prev, `[${timestamp}] ${message}`]);
  }, []);

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
          // 僅在前端初次進入且尚未選擇任何作品時，才自動切換至運行中的那本
          if (activeTask.novel_id && !activeNovelId) {
            setActiveNovelId(activeTask.novel_id);
            setIsAutoRunning(true);
          } else if (activeTask.novel_id && activeTask.novel_id === activeNovelId) {
            setIsAutoRunning(true);
          }
          if (activeTask.status_message || activeTask.current_stage) {
            setAutoStatusText(
              `作品: ${activeTask.novel_title || '進行中'}\n當前章節: 第 ${activeTask.current_chapter || 0} 章\n階段: ${activeTask.status_message || activeTask.current_stage}\n進度: ${activeTask.progress_percent || 0}%`
            );
          }
          if (activeTask.logs && Array.isArray(activeTask.logs)) {
            lastSeenLogCountRef.current = activeTask.logs.length;
          }
          addLog(`已連線至背景自主寫作流水線 (${activeTask.novel_title || '小說'} / ${activeTask.status_message || activeTask.current_stage})`);
        }
      })
      .catch((err) => console.warn('檢查背景自主流水線狀態失敗:', err));
  }, []); // 僅在 mount 時執行一次，絕不可將 activeNovelId 放入依賴項

  // Continuous background monitoring: polls current novel & active background tasks without hijacking active view
  useEffect(() => {
    const pollFn = async () => {
      try {
        const status = await getAutoPipelineStatus(activeNovelId || undefined);
        const isCurrentRunning = Boolean(status.is_running ?? status.running);
        const activeTasks = Array.isArray(status.active_tasks) ? status.active_tasks : [];

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
          if (status.logs && Array.isArray(status.logs)) {
            if (status.logs.length > lastSeenLogCountRef.current) {
              const newEntries = status.logs.slice(lastSeenLogCountRef.current);
              newEntries.forEach((entry) => {
                addLog(`[雲端] ${entry.msg}`);
                if (
                  entry.msg.includes('✅') ||
                  entry.msg.includes('完成') ||
                  entry.msg.includes('就緒') ||
                  entry.msg.includes('持久化')
                ) {
                  stageCompleted = true;
                }
              });
              lastSeenLogCountRef.current = status.logs.length;
            }
          }

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
          }
        } else if (activeTasks.length > 0) {
          // 當前小說未在運行，但背景有其他小說正在自主寫作中
          const bgTask = activeTasks[0];
          setAutoStatusText(
            `【背景創作進行中】作品：《${bgTask.novel_title}》\n當前進度: 第 ${bgTask.current_chapter || 0}/${bgTask.total_chapters || 0} 章 (${bgTask.progress_percent || 0}%)\n當前階段: ${bgTask.status_message || bgTask.current_stage}\n\n(提示：您目前正在瀏覽其他小說，背景任務持續穩定運行中)`
          );

          // 仍可同步背景任務的新日誌至 dock
          if (bgTask.logs && Array.isArray(bgTask.logs)) {
            if (bgTask.logs.length > lastSeenLogCountRef.current) {
              const newEntries = bgTask.logs.slice(lastSeenLogCountRef.current);
              newEntries.forEach((entry: any) => {
                addLog(`[雲端·${bgTask.novel_title}] ${entry.msg}`);
              });
              lastSeenLogCountRef.current = bgTask.logs.length;
            }
          }
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
  }, [activeNovelId, addLog, refreshActiveNovel, refreshGraph, refreshProposals, refreshChatMemory]);

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
        addLog(`[發送請求] 正在向伺服器發送啟動《${activeNovel?.title || ''}》雲端自主寫作任務...`);
        lastSeenLogCountRef.current = 0;
        const res = await startAutoPipeline(activeNovelId, activeNovel?.pipeline_prompt || '', 5);
        if (res.status === 'success' || res.status === 'started' || res.status === 'already_running' || res.success) {
          setIsAutoRunning(true);
          addLog(`[啟動成功] ${res.message || '自主寫作管線已成功在背景啟動！'}`);
          showToast(res.message || '自主寫作任務已在背景啟動！', 'success');
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
            if (status.logs && Array.isArray(status.logs)) {
              status.logs.forEach((entry) => addLog(`[雲端] ${entry.msg}`));
              lastSeenLogCountRef.current = status.logs.length;
            }
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
      const count = scopes?.length ?? 0;
      showToast(count > 0 ? `已清空所選 ${count} 項生成內容！` : '小說生成內容已成功清空，回到初始設定狀態！', 'success');
      addLog(`[清空生成] 小說生成內容已清空${count > 0 ? `（${count} 項）` : ''}並重置回初始狀態`);
    } catch (err: any) {
      showToast(`清空內容失敗: ${err.message || '未知錯誤'}`, 'danger');
      addLog(`[清空失敗] ${err.message || '未知錯誤'}`);
    }
  };

  return (
    <div className="app-container">
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
        onSelectNovel={(id) => {
          setActiveNovelId(id);
          setIsExplorerOpenMobile(false);
        }}
        onSelectChapter={(idx) => {
          selectChapter(idx);
          setIsExplorerOpenMobile(false);
          // Preserve 'graph' tab if user is currently inspecting temporal memory graph
          if (activeView !== 'graph') {
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
          isDirty={isDirty}
          isSaving={isSaving}
          isLoading={isNovelLoading}
          activeView={activeView}
          onSave={saveActiveChapter}
          onToggleExplorerMobile={() => setIsExplorerOpenMobile(!isExplorerOpenMobile)}
          onToggleCopilotMobile={() => setIsCopilotOpenMobile(!isCopilotOpenMobile)}
          onSelectView={setActiveView}
        />

        <div
          className="workspace-body"
          style={{ '--editor-font-size': `${editorFontSize}px`, fontSize: `${editorFontSize}px` } as React.CSSProperties}
        >
          {activeView === 'editor' && (
            <EditorPane
              content={editorContent}
              chapterIndex={activeChapterIndex}
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

          {activeView === 'graph' && (
            <TemporalGraphBoard
              graphSlice={graphSlice}
              chapterIndex={activeChapterIndex}
              chapterContent={editorContent}
              isLoading={isGraphLoading}
              isExtracting={isGraphExtracting}
              onRefresh={refreshGraph}
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

      {/* 4. Copilot Drawer (320px / Mobile Drawer) */}
      <CopilotDrawer
        isOpenMobile={isCopilotOpenMobile}
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
        logs={logs}
        autoStatusText={autoStatusText}
        onClearLogs={() => setLogs([])}
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
        onThemeChange={setTheme}
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
    </div>
  );
};
