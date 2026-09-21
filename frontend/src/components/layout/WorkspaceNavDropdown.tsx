import React, { useMemo } from 'react';
import { ActiveView } from './ActivityRail';
import { CustomSelect } from '../common/CustomSelect';

export type WorldviewSubTab = 'worldview' | 'characters' | 'plot';
export type StructureSubTab = 'geometry' | 'graph' | 'narrative';

interface WorkspaceNavDropdownProps {
  activeView: ActiveView;
  worldviewTab?: WorldviewSubTab;
  structureSubTab?: StructureSubTab;
  onSelectView: (view: ActiveView, subTab?: any) => void;
  className?: string;
}

// 直接複用模組化 CustomSelect（下拉式選單動畫.txt 樣式：scaleY + 箭頭旋轉 + 外點關閉），
// 不再各自重寫 open / outside-click / keyboard 邏輯。
export const WorkspaceNavDropdown: React.FC<WorkspaceNavDropdownProps> = ({
  activeView,
  worldviewTab = 'worldview',
  structureSubTab = 'geometry',
  onSelectView,
  className = '',
}) => {
  const currentValue = useMemo(() => {
    if (activeView === 'editor') return 'writer';
    if (activeView === 'diff') return 'editor-review';
    if (activeView === 'structure') {
      if (structureSubTab === 'graph') return 'temporal_graph';
      if (structureSubTab === 'narrative') return 'narrative_engine';
      return 'geometry_graph';
    }
    if (activeView === 'narrative') return 'narrative_engine';
    if (activeView === 'graph') return 'temporal_graph';
    if (activeView === 'geometry') return 'geometry_graph';
    if (activeView === 'worldview') {
      if (worldviewTab === 'characters') return 'characters';
      if (worldviewTab === 'plot') return 'volumes';
      return 'worldview';
    }
    return 'writer';
  }, [activeView, worldviewTab, structureSubTab]);

  const groups = useMemo(
    () => [
      {
        title: '架構',
        options: [
          { value: 'worldview', label: '世界觀構建' },
          { value: 'characters', label: '角色聖經' },
          { value: 'volumes', label: '分卷結構' },
          { value: 'volume_skeleton', label: '卷章細綱' },
        ],
      },
      {
        title: '正文',
        options: [
          { value: 'writer', label: '正文撰寫' },
          { value: 'editor-review', label: '審閱修訂' },
        ],
      },
      {
        title: '推理',
        options: [
          { value: 'temporal_graph', label: '時序記憶圖譜' },
          { value: 'narrative_engine', label: '敘事推理引擎' },
          { value: 'geometry_graph', label: '敘事幾何骨架圖' },
        ],
      },
    ],
    [],
  );

  const handleChange = (val: string) => {
    // 選單文字與「AI 導演總控室」完全一致對齊
    if (val === 'writer') onSelectView('editor');
    else if (val === 'editor-review') onSelectView('diff');
    else if (val === 'narrative_engine') onSelectView('structure', 'narrative');
    else if (val === 'temporal_graph') onSelectView('structure', 'graph');
    else if (val === 'geometry_graph') onSelectView('structure', 'geometry');
    else if (val === 'worldview') onSelectView('worldview', 'worldview');
    else if (val === 'characters') onSelectView('worldview', 'characters');
    else if (val === 'volumes' || val === 'volume_skeleton') onSelectView('worldview', 'plot');
  };

  return (
    <CustomSelect
      value={currentValue}
      groups={groups}
      onChange={handleChange}
      className={`topbar-view-select ${className}`}
    />
  );
};
