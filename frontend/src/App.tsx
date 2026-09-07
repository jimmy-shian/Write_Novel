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
    setContent,
    isDirty,
    isSaving,
    selectChapter,
    saveActiveChapter,
    createChapter,
    handleCreateNovel,
    handleDeleteNovel,
    handleResetNovelContent,
    refreshActiveNovel,
    refreshChatMemory,
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

  const activeNovel = novelDetail?.novel || novels.find((n) => n.id === activeNovelId) || null;
  const autoPollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastSeenLogCountRef = useRef<number>(0);
  const prevAutoStageRef = useRef<string | null>(null);

  const addLog = useCallback((message: string) => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs((prev) => [...prev, `[${timestamp}] ${message}`]);
  }, []);

  // Reconnect on mount if autonomous writing is actively running in background
  useEffect(() => {
    getAutoPipelineStatus(activeNovelId || undefined)
      .then((status) => {
        const running = Boolean(status.is_running ?? status.running);
        if (running) {
          setIsAutoRunning(true);
          setIsBottomDockOpen(true);
          if (status.novel_id && (!activeNovelId || activeNovelId !== status.novel_id)) {
            setActiveNovelId(status.novel_id);
          }
          if (status.status_message || status.current_stage) {
            setAutoStatusText(
              `當前章節: 第 ${status.current_chapter || 0} 章\n階段: ${status.status_message || status.current_stage}\n進度: ${status.progress_percent || 0}%`
            );
          }
          if (status.logs && Array.isArray(status.logs)) {
            lastSeenLogCountRef.current = status.logs.length;
          }
          addLog(`已重新連線至背景自主寫作流水線 (${status.novel_title || '小說'} / ${status.status_message || status.current_stage})`);
        }
      })
      .catch((err) => console.warn('檢查背景自主流水線狀態失敗:', err));
  }, [activeNovelId, setActiveNovelId, addLog]);

  // Poll autonomous pipeline status
  useEffect(() => {
    if (!isAutoRunning) {
      if (autoPollTimerRef.current) {
        clearInterval(autoPollTimerRef.current);
        autoPollTimerRef.current = null;
      }
      return;
    }

    autoPollTimerRef.current = setInterval(async () => {
      try {
        const status = await getAutoPipelineStatus(activeNovelId || undefined);
        const running = Boolean(status.is_running ?? status.running);
        setIsAutoRunning(running);
        if (status.status_message || status.current_stage) {
          setAutoStatusText(
            `當前章節: 第 ${status.current_chapter || 0} 章\n階段: ${status.status_message || status.current_stage}\n進度: ${status.progress_percent || 0}%`
          );
        }

        let stageCompleted = false;
        // 同步後端任務即時 logs 到前端日誌池
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

        if (!running) {
          if (status.error || status.current_stage === 'error') {
            addLog(`[任務中斷] 自主寫作異常中斷: ${status.error || status.status_message || '未知錯誤'}`);
            showToast(`自主寫作異常中斷: ${status.error || status.status_message || '未知錯誤'}`, 'danger');
          } else if (status.current_stage === 'completed' || status.progress_percent === 100) {
            addLog(`[任務完成] 自主寫作任務已圓滿結束 (${status.status_message || '全數完成'})`);
            showToast('自主寫作任務已全數完成！', 'success');
          } else if (status.stop_requested) {
            addLog(`[任務中止] 自主寫作已由使用者中止 (${status.status_message || '已停止'})`);
            showToast('自主寫作已停止', 'info');
          } else {
            addLog(`[任務結束] 自主寫作流水線已結束 (${status.status_message || '等待啟動'})`);
          }
          refreshActiveNovel();
          refreshGraph();
          refreshProposals();
          refreshChatMemory();
        }
      } catch (err) {
        console.error('輪詢自主流水線狀態失敗:', err);
      }
    }, 3000);

    return () => {
      if (autoPollTimerRef.current) {
        clearInterval(autoPollTimerRef.current);
      }
    };
  }, [isAutoRunning, activeNovelId, addLog, refreshActiveNovel, refreshGraph, refreshProposals, refreshChatMemory]);

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
      await streamGenerationTask(
        {
          novel_id: activeNovelId,
          stage,
          task_type: stage === 'writer' ? 'generate' : stage === 'editor' ? 'refine' : 'generate',
          target: { chapter_index: activeChapterIndex },
          prompt,
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

            // Refresh novel and graph
            await refreshActiveNovel();
            await refreshGraph();
            await refreshProposals();
            await refreshChatMemory();
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

  // Reset novel generated content
  const handleResetNovel = async (id: string) => {
    try {
      await handleResetNovelContent(id);
      showToast('小說生成內容已成功清空，回到初始設定狀態！', 'success');
      addLog(`[清空生成] 小說生成內容已清空並重置回初始狀態`);
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
              fontSize={editorFontSize}
              onFontSizeChange={handleFontSizeChange}
              onChangeContent={setContent}
              onSave={saveActiveChapter}
            />
          )}

          {activeView === 'diff' && (
            <DiffViewer
              originalText={selectedProposal?.original_text || editorContent}
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
        onSelectStage={handleSelectStage}
        onCloseMobile={() => setIsCopilotOpenMobile(false)}
        onTriggerStage={handleTriggerStage}
        onToggleAuto={handleToggleAuto}
        onClearStreaming={() => setStreamingContent('')}
        onRefreshChatMemory={refreshChatMemory}
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
