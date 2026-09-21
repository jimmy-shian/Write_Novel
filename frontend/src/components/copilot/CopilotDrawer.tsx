import React, { useState, useEffect, useRef } from 'react';
import { CreationStage, CopilotTab, STAGE_DEFINITIONS, CopilotDrawerProps, RecordFilterType } from './types';
import { StageSelector } from './StageSelector';
import { DirectorRecordsStream } from './DirectorRecordsStream';
import { StageGuideTour } from './StageGuideTour';
import { shouldAutoShowGuide, markGuideSeen } from './stageGuide';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import {
  IconCpu,
  IconSparkles,
  IconX,
  IconMessageSquare,
  IconLayers,
  IconSend,
} from '../common/Icons';
import { clearChatMemory, deleteChatMessage } from '../../api/novels';

export const CopilotDrawer: React.FC<CopilotDrawerProps> = ({
  isOpenMobile,
  isCollapsedDesktop = false,
  onToggleCollapseDesktop,
  isStreaming,
  isAutoRunning,
  thinkingText,
  streamingContent,
  currentStatus,
  currentStage = 'writer',
  chatMemory = [],
  activeNovelId,
  activeChapterIndex,
  activeVolumeIndex,
  activeView,
  onSelectStage,
  onCloseMobile,
  onTriggerStage,
  onToggleAuto,
  onClearStreaming,
  onRefreshChatMemory,
  onDeleteChatMessage,
  onClearChatMemory,
}) => {
  const [activeTab, setActiveTab] = useState<CopilotTab>('stages');
  const [prompt, setPrompt] = useState('');
  const [activeStage, setActiveStage] = useState<CreationStage>(currentStage);
  const [isStageCollapsed, setIsStageCollapsed] = useState(false);
  const [isRefreshingMemory, setIsRefreshingMemory] = useState(false);
  const [isGuideOpen, setIsGuideOpen] = useState(false);
  const [guideStep, setGuideStep] = useState(0);
  const autoGuideShownRef = useRef(false);

  useEffect(() => {
    if (currentStage) {
      setActiveStage(currentStage);
    }
  }, [currentStage]);

  // 階段導覽自動播放：預設開、看過（完成/跳過）即記住不再打擾
  useEffect(() => {
    if (autoGuideShownRef.current || isCollapsedDesktop) return;
    autoGuideShownRef.current = true;
    if (shouldAutoShowGuide()) {
      setActiveTab('stages');
      setIsStageCollapsed(false);
      setGuideStep(0);
      setIsGuideOpen(true);
    }
  }, [isCollapsedDesktop]);

  const handleStageSelect = (stage: CreationStage) => {
    setActiveStage(stage);
    onSelectStage?.(stage);
  };

  const handleRunStage = () => {
    onTriggerStage(activeStage, prompt);
  };

  const handleOpenGuide = () => {
    setActiveTab('stages');
    setIsStageCollapsed(false);
    setGuideStep(0);
    setIsGuideOpen(true);
  };

  const handleCloseGuide = () => {
    markGuideSeen();
    setIsGuideOpen(false);
  };

  const handleRefreshRecords = async () => {
    if (onRefreshChatMemory) {
      setIsRefreshingMemory(true);
      try {
        await onRefreshChatMemory();
      } finally {
        setIsRefreshingMemory(false);
      }
    }
  };

  const handleClearRecords = async (filter?: RecordFilterType) => {
    if (!activeNovelId) return;
    const filterLabel =
      filter === 'director'
        ? '【總監評斷】'
        : filter === 'pipeline'
        ? '【創作指令】'
        : filter === 'system'
        ? '【系統通知】'
        : '所有';
    if (window.confirm(`確定要清空此小說的${filterLabel}對話與紀錄嗎？此操作無法還原。`)) {
      try {
        if (onClearChatMemory) {
          await onClearChatMemory(filter);
        } else {
          await clearChatMemory(activeNovelId, filter);
          onRefreshChatMemory?.();
        }
      } catch (err: any) {
        alert(err.message || '清空失敗');
      }
    }
  };

  const handleDeleteRecord = async (messageId: number) => {
    if (!activeNovelId) return;
    try {
      if (onDeleteChatMessage) {
        await onDeleteChatMessage(messageId);
      } else {
        await deleteChatMessage(activeNovelId, messageId);
        onRefreshChatMemory?.();
      }
    } catch (err: any) {
      alert(err.message || '刪除失敗');
    }
  };

  const currentStageDef = STAGE_DEFINITIONS.find((s) => s.id === activeStage) || STAGE_DEFINITIONS[0];

  if (isCollapsedDesktop) {
    return (
      <aside className={`copilot-panel desktop-collapsed ${isOpenMobile ? 'mobile-open' : ''}`}>
        <button
          type="button"
          className="copilot-expand-trigger-btn"
          onClick={onToggleCollapseDesktop}
          title="展開"
          aria-label="展開"
        >
          <IconCpu size={15} className="text-accent" />
          <span className="copilot-vertical-label">AI 導演</span>
        </button>
      </aside>
    );
  }

  return (
    <aside className={`copilot-panel ${isOpenMobile ? 'mobile-open' : ''}`}>
      {/* 1. Header with Title & Badges（標題本身可點收合） */}
      <div className="copilot-header">
        {onToggleCollapseDesktop ? (
          <button
            type="button"
            className="copilot-title copilot-title-toggle"
            onClick={onToggleCollapseDesktop}
            title="收合"
            aria-label="收合"
          >
            <IconCpu size={16} className="text-accent" />
            <span>AI 導演總控室</span>
            {isStreaming && <Badge variant="accent">生成中</Badge>}
            {isAutoRunning && <Badge variant="success">自主運行中</Badge>}
          </button>
        ) : (
          <div className="copilot-title">
            <IconCpu size={16} className="text-accent" />
            <span>AI 導演總控室</span>
            {isStreaming && <Badge variant="accent">生成中</Badge>}
            {isAutoRunning && <Badge variant="success">自主運行中</Badge>}
          </div>
        )}
        <div className="copilot-header-actions">
          {isOpenMobile && (
            <button
              type="button"
              className="btn btn-ghost btn-xs text-muted"
              onClick={onCloseMobile}
              aria-label="關閉導演面板"
            >
              <IconX size={14} />
            </button>
          )}
        </div>
      </div>

      {/* 2. Switcher: 選擇流水線階段 vs 總監評斷／指令紀錄 */}
      <div className="copilot-tab-switch-bar">
        <button
          type="button"
          className={`copilot-tab-btn ${activeTab === 'stages' ? 'active' : ''}`}
          onClick={() => setActiveTab('stages')}
          data-tooltip="選擇創作流水線階段並送出導演指令"
          data-tooltip-pos="bottom"
        >
          <IconLayers size={13} />
          <span>選擇流水線階段</span>
        </button>
        <button
          type="button"
          className={`copilot-tab-btn ${activeTab === 'records' ? 'active' : ''}`}
          onClick={() => {
            setActiveTab('records');
            onRefreshChatMemory?.();
          }}
          data-tooltip="查看總監評斷與流水線工作紀錄"
          data-tooltip-pos="bottom"
        >
          <IconMessageSquare size={13} />
          <span>總監評斷紀錄</span>
          {chatMemory.length > 0 && (
            <span className="copilot-tab-count">{chatMemory.length}</span>
          )}
        </button>
      </div>

      {/* 3. Tab Content Area */}
      <div className="copilot-body-area">
        {activeTab === 'stages' ? (
          <div className="copilot-messages">
            {/* Stage Selector Subcomponent */}
            <StageSelector
              activeStage={activeStage}
              isCollapsed={isStageCollapsed}
              isAutoRunning={isAutoRunning}
              onSelectStage={handleStageSelect}
              onToggleCollapse={() => setIsStageCollapsed(!isStageCollapsed)}
              onToggleAuto={onToggleAuto}
              onOpenGuide={handleOpenGuide}
            />

            {/* Live Status Indicator */}
            {currentStatus && (
              <div className="copilot-status-box">
                <span className="copilot-status-text">{currentStatus}</span>
              </div>
            )}

            {/* Live Thinking Process Display */}
            {thinkingText && (
              <div className="copilot-thinking-box">
                <div className="thinking-box-header">
                  <IconSparkles size={12} className="text-accent" />
                  <span>AI 思考推理歷程 (Thinking)</span>
                </div>
                <div className="thinking-box-content">{thinkingText}</div>
              </div>
            )}

            {/* Live Output Preview */}
            {streamingContent && (
              <div className="copilot-output-box">
                <div className="output-box-header">
                  <IconMessageSquare size={12} className="text-muted" />
                  <span>即時生成內容</span>
                  <button
                    type="button"
                    className="btn btn-ghost btn-xs text-muted"
                    onClick={onClearStreaming}
                  >
                    清除
                  </button>
                </div>
                <div className="output-box-content">{streamingContent}</div>
              </div>
            )}

            {!thinkingText && !streamingContent && !currentStatus && (
              <div className="copilot-empty-placeholder">
                <p>請選擇上方階段，或在下方輸入導演引導提示詞，點擊「送出」開始。</p>
              </div>
            )}
          </div>
        ) : (
          <DirectorRecordsStream
            records={chatMemory}
            isLoading={isRefreshingMemory}
            onRefresh={handleRefreshRecords}
            onClear={handleClearRecords}
            onDeleteMessage={handleDeleteRecord}
          />
        )}
      </div>

      {/* 4. Bottom Input Area */}
      <div className="copilot-input-area">
        <textarea
          className="copilot-textarea"
          data-tour="copilot-input"
          placeholder={
            activeTab === 'records'
              ? '向總監或流水線發送引導指令與反饋...'
              : activeStage === 'writer'
              ? `對【第 ${activeChapterIndex || 1} 章 正文撰寫】提供創作要求（如對白、情緒、節奏、風格）...`
              : activeStage === 'editor'
              ? `對【第 ${activeChapterIndex || 1} 章 審閱修訂】提供潤飾與修改指示...`
              : activeStage === 'volume_skeleton'
              ? `對【第 ${activeVolumeIndex || 1} 卷 卷章細綱】提供情節走向與細綱要求...`
              : activeStage === 'volumes'
              ? '對【分卷結構】提供主線脈絡、衝突高潮與卷數規劃提示...'
              : activeStage === 'characters'
              ? '對【角色聖經】提供新人物、性格特徵或動機設定指示...'
              : activeStage === 'worldview'
              ? '對【世界觀構建】提供力量體系、地理法則與背景設定指示...'
              : `對【${currentStageDef.label}】提供引導提示（選填）...`
          }
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          disabled={isStreaming}
        />
        <Button
          className="copilot-run-btn-inline"
          variant="primary"
          onClick={handleRunStage}
          isLoading={isStreaming}
          disabled={isStreaming}
          icon={isStreaming ? undefined : <IconSend size={14} />}
          data-tooltip={isStreaming ? '正在生成中...' : `送出（當前階段：${currentStageDef.label}）`}
          data-tooltip-pos="top"
          data-tour="copilot-send"
        >
          {isStreaming ? '執行中...' : '送出'}
        </Button>
      </div>
      <StageGuideTour
        open={isGuideOpen}
        step={guideStep}
        onStepChange={setGuideStep}
        onDone={handleCloseGuide}
      />
    </aside>
  );
};
