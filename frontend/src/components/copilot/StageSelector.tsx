import React from 'react';
import { StageSelectorProps, STAGE_GROUPS, STAGE_DEFINITIONS } from './types';
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
          <span className="copilot-section-label">流水線階段</span>
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
        <div className="stage-grouped-container">
          {STAGE_GROUPS.map((group) => (
            <div key={group.id} className="stage-group-block">
              <div className="stage-group-header">
                <span className="stage-group-tag">{group.id === 'outline' ? '🏛️' : '✍️'}</span>
                <span className="stage-group-title">{group.title}</span>
              </div>
              <div className={`stage-group-grid grid-${group.stages.length}`}>
                {group.stages.map((st) => (
                  <button
                    key={st.id}
                    type="button"
                    className={`stage-pill-btn ${activeStage === st.id ? 'active' : ''}`}
                    onClick={() => onSelectStage(st.id)}
                    title={st.desc}
                  >
                    <span className="stage-pill-label">{st.label}</span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Active Stage Details - Ultra Compact */}
        <div className="stage-switch-indicator compact">
          <div className="stage-indicator-left">
            <span className="stage-indicator-badge">當前階段:</span>
            <span className="stage-indicator-title">{currentStageDef.label}</span>
          </div>
          <span className="stage-indicator-desc">{currentStageDef.desc}</span>
        </div>
      </div>

      {/* Autonomous Writing Quick Card */}
      <div className="copilot-auto-card compact">
        <div className="auto-card-info">
          <span className="auto-card-title">全自動自主寫作</span>
          <span className="auto-card-desc">全流程自動推進與審閱</span>
        </div>
        <Button
          size="xs"
          variant={isAutoRunning ? 'danger' : 'secondary'}
          onClick={onToggleAuto}
          icon={isAutoRunning ? <IconSquare size={11} /> : <IconPlay size={11} />}
        >
          {isAutoRunning ? '停止' : '啟動'}
        </Button>
      </div>
    </div>
  );
};
