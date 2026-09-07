import React, { useState, useEffect } from 'react';
import { CreationStage } from '../../types';
import { Button } from '../common/Button';
import { Badge } from '../common/Badge';
import {
  IconCpu,
  IconPlay,
  IconSquare,
  IconSparkles,
  IconX,
  IconRefresh,
  IconMessageSquare,
} from '../common/Icons';

interface CopilotDrawerProps {
  isOpenMobile: boolean;
  isStreaming: boolean;
  isAutoRunning: boolean;
  thinkingText: string;
  streamingContent: string;
  currentStatus: string;
  currentStage?: CreationStage;
  onSelectStage?: (stage: CreationStage) => void;
  onCloseMobile: () => void;
  onTriggerStage: (stage: CreationStage, prompt: string) => void;
  onToggleAuto: () => void;
  onClearStreaming: () => void;
}

export const CopilotDrawer: React.FC<CopilotDrawerProps> = ({
  isOpenMobile,
  isStreaming,
  isAutoRunning,
  thinkingText,
  streamingContent,
  currentStatus,
  currentStage = 'writer',
  onSelectStage,
  onCloseMobile,
  onTriggerStage,
  onToggleAuto,
  onClearStreaming,
}) => {
  const [prompt, setPrompt] = useState('');
  const [activeStage, setActiveStage] = useState<CreationStage>(currentStage);

  useEffect(() => {
    if (currentStage) {
      setActiveStage(currentStage);
    }
  }, [currentStage]);

  const stages: { id: CreationStage; label: string; desc: string }[] = [
    { id: 'writer', label: '正文撰寫', desc: '結合時序知識圖譜生成章節正文' },
    { id: 'editor', label: '審閱修訂', desc: '產出審閱建議與修改提案' },
    { id: 'worldview', label: '世界觀構建', desc: '設定歷史、修煉體系與法則' },
    { id: 'characters', label: '角色聖經', desc: '角色性格、慾望與關係網' },
    { id: 'volumes', label: '分卷骨架', desc: '大綱主線與伏筆鋪設' },
    { id: 'evaluate', label: '深度評估', desc: '節奏、文筆與劇情衝突評分' },
  ];

  const handleRunStage = () => {
    onTriggerStage(activeStage, prompt);
  };

  return (
    <aside className={`copilot-panel ${isOpenMobile ? 'mobile-open' : ''}`}>
      <div className="copilot-header">
        <div className="copilot-title">
          <IconCpu size={16} className="text-accent" />
          <span>AI 導演總控室</span>
          {isStreaming && <Badge variant="accent">生成中</Badge>}
          {isAutoRunning && <Badge variant="success">自主運行中</Badge>}
        </div>
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

      <div className="copilot-messages">
        {/* Quick Stage Action Selector */}
        <div className="copilot-stage-selector">
          <span className="copilot-section-label">選擇流水線階段</span>
          <div className="stage-pill-grid">
            {stages.map((st) => (
              <button
                key={st.id}
                type="button"
                className={`stage-pill-btn ${activeStage === st.id ? 'active' : ''}`}
                onClick={() => {
                  setActiveStage(st.id);
                  onSelectStage?.(st.id);
                }}
                title={st.desc}
              >
                {st.label}
              </button>
            ))}
          </div>

          {/* Active Stage Details & View Switch Indicator */}
          <div className="stage-switch-indicator">
            <div className="stage-indicator-left">
              <span className="stage-indicator-badge">當前階段</span>
              <span className="stage-indicator-title">
                {stages.find((s) => s.id === activeStage)?.label}
              </span>
            </div>
            <span className="stage-indicator-desc">
              {stages.find((s) => s.id === activeStage)?.desc}
            </span>
          </div>
        </div>

        {/* Autonomous Writing Quick Card */}
        <div className="copilot-auto-card">
          <div className="auto-card-info">
            <span className="auto-card-title">全自動自主寫作</span>
            <span className="auto-card-desc">依大綱、時序事實自驅撰寫並審閱章節</span>
          </div>
          <Button
            size="xs"
            variant={isAutoRunning ? 'danger' : 'secondary'}
            onClick={onToggleAuto}
            icon={isAutoRunning ? <IconSquare size={12} /> : <IconPlay size={12} />}
          >
            {isAutoRunning ? '執行中 (停止)' : '啟動'}
          </Button>
        </div>

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
            <p>請選擇上方階段，或在下方輸入導演引導提示詞，點擊「執行階段生成」開始。</p>
          </div>
        )}
      </div>

      <div className="copilot-input-area">
        <textarea
          className="copilot-textarea"
          placeholder={`對【${stages.find((s) => s.id === activeStage)?.label}】提供引導提示（選填）...`}
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
          icon={<IconSparkles size={14} />}
        >
          {isStreaming ? '執行中...' : '執行階段生成'}
        </Button>
      </div>
    </aside>
  );
};
