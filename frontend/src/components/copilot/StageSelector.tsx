import React from 'react';
import { StageSelectorProps, STAGE_DEFINITIONS } from './types';
import { Button } from '../common/Button';
import { IconPlay, IconSquare, IconChevronDown } from '../common/Icons';

export const StageSelector: React.FC<StageSelectorProps> = ({
  activeStage,
  isCollapsed,
  isAutoRunning,
  onSelectStage,
  onToggleCollapse,
  onToggleAuto,
}) => {
  const currentStageDef = STAGE_DEFINITIONS.find((s) => s.id === activeStage) || STAGE_DEFINITIONS[0];

  return (
    <div className="copilot-stage-selector">
      {/* Selector Header with Collapsible Trigger */}
      <div
        className={`copilot-section-header clickable ${isCollapsed ? 'collapsed' : 'open'}`}
        onClick={onToggleCollapse}
        title="點擊展開或收合流水線階段"
      >
        <div className="header-left">
          <span className="copilot-section-label">選擇流水線階段</span>
          {isCollapsed && (
            <span className="stage-collapsed-badge">{currentStageDef.label}</span>
          )}
        </div>
        <div className="accordion-toggle-indicator">
          <span className="toggle-text">{isCollapsed ? '展開' : '收合'}</span>
          <div className={`arrow-indicator ${isCollapsed ? '' : 'open'}`}>
            <IconChevronDown size={12} />
          </div>
        </div>
      </div>

      {/* Smoothly Collapsible Stage Buttons and Indicator */}
      <div className={`stage-collapsible-wrapper ${isCollapsed ? 'collapsed' : 'open'}`}>
        <div className="stage-pill-grid">
          {STAGE_DEFINITIONS.map((st) => (
            <button
              key={st.id}
              type="button"
              className={`stage-pill-btn ${activeStage === st.id ? 'active' : ''}`}
              onClick={() => onSelectStage(st.id)}
              title={st.desc}
            >
              {st.label}
            </button>
          ))}
        </div>

        {/* Active Stage Details */}
        <div className="stage-switch-indicator">
          <div className="stage-indicator-left">
            <span className="stage-indicator-badge">當前階段</span>
            <span className="stage-indicator-title">{currentStageDef.label}</span>
          </div>
          <span className="stage-indicator-desc">{currentStageDef.desc}</span>
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
    </div>
  );
};
