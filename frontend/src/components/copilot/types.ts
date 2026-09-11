import { CreationStage, ChatRecord, CopilotTab } from '../../types';

export type { CreationStage, ChatRecord, CopilotTab };

export interface StageDefinition {
  id: CreationStage;
  label: string;
  desc: string;
}

export const STAGE_DEFINITIONS: StageDefinition[] = [
  { id: 'writer', label: '正文撰寫', desc: '結合時序知識圖譜生成章節正文' },
  { id: 'editor', label: '審閱修訂', desc: '產出審閱建議與修改提案' },
  { id: 'worldview', label: '世界觀構建', desc: '設定歷史、修煉體系與法則' },
  { id: 'characters', label: '角色聖經', desc: '角色性格、慾望與關係網' },
  { id: 'volumes', label: '分卷結構', desc: '全書宏觀分卷主線與高潮節奏' },
  { id: 'volume_skeleton', label: '卷章細綱', desc: '針對選定卷生成逐章情節細綱' },
  { id: 'evaluate', label: '深度評估', desc: '節奏、文筆與劇情衝突評分' },
];

export type RecordFilterType = 'all' | 'director' | 'pipeline' | 'system';

export interface StageSelectorProps {
  activeStage: CreationStage;
  isCollapsed: boolean;
  isAutoRunning: boolean;
  onSelectStage: (stage: CreationStage) => void;
  onToggleCollapse: () => void;
  onToggleAuto: () => void;
}

export interface DirectorMessageItemProps {
  record: ChatRecord;
  onCopy?: (text: string) => void;
  onDelete?: (id: number) => void;
}

export interface DirectorRecordsStreamProps {
  records: ChatRecord[];
  isLoading?: boolean;
  onRefresh: () => void;
  onClear: (filter?: RecordFilterType) => void;
  onDeleteMessage?: (id: number) => void;
}

export interface CopilotDrawerProps {
  isOpenMobile: boolean;
  isStreaming: boolean;
  isAutoRunning: boolean;
  thinkingText: string;
  streamingContent: string;
  currentStatus: string;
  currentStage?: CreationStage;
  chatMemory?: ChatRecord[];
  activeNovelId?: string | null;
  activeChapterIndex?: number;
  activeVolumeIndex?: number;
  activeView?: string;
  onSelectStage?: (stage: CreationStage) => void;
  onCloseMobile: () => void;
  onTriggerStage: (stage: CreationStage, prompt: string) => void;
  onToggleAuto: () => void;
  onClearStreaming: () => void;
  onRefreshChatMemory?: () => void;
  onDeleteChatMessage?: (id: number) => void;
  onClearChatMemory?: (filter?: RecordFilterType) => void;
}
